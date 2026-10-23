"""Foreground, stop-aware data supervision. No dashboard, auth, broker or AI services."""
from dataclasses import dataclass
from datetime import datetime, timezone
import threading
import time

from trading_agent.core_v3.contracts import require, ContractError
from trading_agent.core_v3.market_observation.contracts import RawEvent, Kind
from .archive import Archive
from .authorization import DataApproval
from .reader import MarketReader, TranscriptReader


@dataclass(frozen=True, slots=True)
class Health:
    code: str
    committed: int
    segments: int
    decision: str = 'NO_TRADE'
    execution_authorized: bool = False


class Supervisor:
    def __init__(self, archive, approval, *, reader_factory=MarketReader,
                 now=lambda:datetime.now(timezone.utc), mono=time.monotonic_ns, wait=None):
        require(type(archive) is Archive and type(approval) is DataApproval, 'M03_SUPERVISOR_TYPE')
        self.archive, self.approval, self.reader_factory = archive, approval, reader_factory
        self.now, self.mono, self._stop = now, mono, threading.Event()
        self.wait = wait or self._stop.wait
        self.latest, self.health = None, Health('NOT_STARTED',0,len(archive.segments))

    def stop(self): self._stop.set()

    def run(self):
        cfg, committed, failures = self.archive.config, 0, 0
        code, reader = 'DISABLED', None
        if not cfg.enabled: return self._finish(code, committed)
        deadline = self.mono()+cfg.max_run_seconds*10**9
        try:
            while not self._stop.is_set() and self.mono() < deadline:
                self.approval.verify(cfg, self.now())
                g = self.approval.capture.grant
                require((g.session_id,g.session_kind) == (self.archive.session_id,self.archive.environment),
                        'M03_SUPERVISOR_BINDING')
                if len(self.archive.segments) >= cfg.max_segments:
                    code = 'SEGMENT_BUDGET'
                    break
                cooldown = self.archive.history_not_before()
                reader = self.reader_factory(cfg,self.approval,now=self.now,mono=self.mono,
                    history_not_before=cooldown,stop=lambda:self._stop.is_set() or self.mono() >= deadline)
                require(type(reader) in (MarketReader,TranscriptReader) and reader.origin is self.archive.origin,
                        'M03_TRANSPORT_ORIGIN')
                self.archive.rotate(self.now())
                iterator = reader.events()
                try:
                    for event in iterator:
                        try:
                            self.archive.append(event,as_of=self.now())
                            committed += 1
                            self.latest = self.archive.observe(self.now())
                        except (OSError,ContractError):
                            self.latest = None
                            return self._finish('STORAGE_FAILURE',committed)
                        self.health = Health('CAPTURING',committed,len(self.archive.segments))
                finally:
                    iterator.close()
                    reader.close()
                if reader.reason in ('IDENTITY_OR_PERMISSION_REJECTED','PROFILE_REJECTED','SESSION_OR_FEED_INVALID'):
                    code = reader.reason
                    break
                if self._stop.is_set() or reader.reason == 'STOPPED':
                    code = 'STOPPED'
                    break
                if reader.reason.startswith('MARKET_'):
                    # Wait in interruptible chunks; never extrapolate expired broker calendars.
                    seconds = min(60,max(1,(reader.next_open-self.now()).total_seconds())) if reader.next_open else 60
                    while reader.reason == 'MARKET_CLOSED' and reader.calendar.state(self.now()) == 'CLOSED':
                        self.health = Health('MARKET_CLOSED',committed,len(self.archive.segments))
                        if self.wait(seconds): return self._finish('STOPPED',committed)
                        self.approval.verify(cfg,self.now())
                        if self.mono() >= deadline: return self._finish('RUN_DEADLINE',committed)
                    if reader.reason == 'MARKET_CLOSED': seconds = 0
                elif reader.reason == 'CAPTURE_BOUNDARY':
                    seconds = 1
                else:
                    failures += 1
                    if failures > cfg.max_failures:
                        code = 'RETRY_BUDGET'
                        break
                    seconds = min(30,cfg.retry_seconds*2**(failures-1))
                self.health = Health('WAITING',committed,len(self.archive.segments))
                if self.wait(seconds):
                    code = 'STOPPED'
                    break
            else: code = 'STOPPED' if self._stop.is_set() else 'RUN_DEADLINE'
        except KeyboardInterrupt:
            self.stop()
            rows = self.archive.history()
            if rows:
                last = rows[-1].value.event
                seq = max(r.value.event.sequence for r in rows if r.value.event.connection_id == last.connection_id)+1
                gap = RawEvent(last.session_id,last.connection_id,last.request_id,seq,Kind.GAP,
                    self.now(),self.mono(),last.origin,last.session_kind,diagnostic='STOPPED',
                    host_attestation_sha256=last.host_attestation_sha256,capture_grant_sha256=last.capture_grant_sha256)
                self.archive.append(gap,as_of=self.now())
                committed += 1
            code = 'STOPPED'
        except ContractError:
            code = 'CONFIGURATION_OR_PERMISSION_REJECTED'
        except OSError:
            self.latest = None
            code = 'STORAGE_FAILURE'
        finally:
            if reader is not None: reader.close()
            if self.latest is not None:
                # No quote remains current after shutdown or during backoff.
                self.archive._active = False
                self.latest = self.archive.observe(self.now())
        return self._finish(code,committed)

    def _finish(self, code, committed):
        self.health = Health(code,committed,len(self.archive.segments))
        return self.health
