"""Bounded linked V3.9 journals. No migration or writes to protected financial stores."""
import base64
from dataclasses import dataclass, replace
from datetime import timedelta
import json
import os
from pathlib import Path
import re

from trading_agent.core_v3.contracts import require, content_hash, canonical_bytes, utc, ContractError
from trading_agent.core_v3.historical_ingestion.files import safe_path, read_local
from trading_agent.core_v3.market_observation.contracts import RawEvent, Kind, DataType
from trading_agent.core_v3.market_observation.journal import Journal
from trading_agent.core_v3.market_observation.validation import State, step
from trading_agent.core_v3.market_observation.ibkr_protocol import fields
from .contracts import Observation
from .calendar import TradingCalendar
from .wire import historical, TIMEFRAMES


@dataclass(frozen=True, slots=True)
class ArchiveCheckpoint:
    metadata_sha256: str
    segments: int
    sha256: str


class Archive:
    def __init__(self, directory, config, session_id, origin, environment, *, create=False, checkpoint=None):
        self.root = safe_path(directory)
        require(self.root.is_dir(), 'M03_ARCHIVE_DIRECTORY')
        self.config, self.session_id, self.origin, self.environment = config, session_id, origin, environment
        self._lock, self.current, self.segments, self._active = None, None, [], False
        self._root_identity = Journal._identity(self.root)
        identity = {'schema':'trading.m03a.archive', 'schema_version':1, 'config':config.to_dict(),
                    'session_id':session_id, 'origin':origin.value, 'environment':environment.value}
        self.metadata = content_hash(identity)
        try:
            if create:
                require(not tuple(self.root.iterdir()), 'M03_ARCHIVE_NOT_EMPTY')
                with (self.root/'identity.json').open('xb') as stream:
                    stream.write(canonical_bytes(identity))
                    stream.flush()
                    os.fsync(stream.fileno())
                with (self.root/'writer.lock').open('xb') as stream: stream.write(b'M03A')
            require(read_local(self.root,'identity.json',max_bytes=4096) == canonical_bytes(identity), 'M03_ARCHIVE_IDENTITY')
            require(read_local(self.root,'writer.lock',max_bytes=4) == b'M03A', 'M03_ARCHIVE_LOCK')
            self._lock = (self.root/'writer.lock').open('r+b')
            self._lock.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self._lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._scan()
            self.history()
            if checkpoint is not None:
                require(type(checkpoint) is ArchiveCheckpoint and checkpoint.metadata_sha256 == self.metadata and
                        0 <= checkpoint.segments <= len(self.segments), 'M03_CHECKPOINT')
                digest = self.metadata if not checkpoint.segments else self._head(self.segments[checkpoint.segments-1])
                require(digest == checkpoint.sha256, 'M03_CHECKPOINT')
        except BaseException as exc:
            self.close()
            if isinstance(exc, OSError): raise ContractError('M03_ARCHIVE_LOCK_OR_IO') from None
            raise

    def _storage(self):
        safe_path(self.root)
        require(Journal._identity(self.root) == self._root_identity, 'M03_DIRECTORY_CHANGED')
        total = 0
        for p in self.root.iterdir():
            safe_path(p)
            require(p.is_file() and p.stat().st_nlink == 1, 'M03_ARCHIVE_FILE')
            total += p.stat().st_size
        require(total <= self.config.max_total_bytes-65536, 'M03_ARCHIVE_DISK_BUDGET')

    def _scan(self):
        self._storage()
        files = [p.name for p in self.root.iterdir() if p.name not in ('identity.json','writer.lock')]
        names = sorted(n for n in files if not n.endswith('-journal'))
        require(all(n in names or n.removesuffix('-journal') in names for n in files), 'M03_ARCHIVE_FILES')
        require(len(names) <= self.config.max_segments and all(
            re.fullmatch(r'[0-9]{4}-[0-9a-f]{64}\.sqlite', n) for n in names), 'M03_ARCHIVE_FILES')
        previous = self.metadata
        for i, name in enumerate(names, 1):
            require(name == f'{i:04}-{previous}.sqlite', 'M03_SEGMENT_CHAIN')
            previous = self._head(name)
        self.segments = names

    def _journal(self, name, *, create=False):
        require(create or (self.root/name).is_file(), 'M03_SEGMENT_MISSING')
        return Journal(self.root/name, self.config.capture, self.session_id, self.origin, self.environment)

    def _head(self, name):
        with self._journal(name) as journal: return journal.checkpoint().sha256

    def history(self):
        self._storage()
        rows = []
        for name in self.segments:
            if self.current is not None and name == self.segments[-1]:
                rows.extend(self.current.history())
            else:
                with self._journal(name) as journal: rows.extend(journal.history())
        require(len(rows) <= 8192, 'M03_ARCHIVE_EVENT_BUDGET')
        return tuple(rows)

    def checkpoint(self):
        self.history()
        return ArchiveCheckpoint(self.metadata, len(self.segments),
            self.current.checkpoint().sha256 if self.current else self._head(self.segments[-1]) if self.segments else self.metadata)

    def rotate(self, now):
        self._storage()
        require(len(self.segments) < self.config.max_segments, 'M03_SEGMENT_BUDGET')
        if self.current is None and self.segments:
            self.current = self._journal(self.segments[-1])
        if self.current is not None:
            rows = self.current.history()
            if rows and rows[-1].value.event.kind is not Kind.DISCONNECTED:
                last = rows[-1].value.event
                seq = max(r.value.event.sequence for r in rows if r.value.event.connection_id == last.connection_id)+1
                gap = RawEvent(self.session_id, last.connection_id, last.request_id, seq, Kind.GAP,
                    utc(now), last.monotonic_ns, self.origin, self.environment,
                    diagnostic='COLLECTOR_RESTART_GAP', host_attestation_sha256=last.host_attestation_sha256,
                    capture_grant_sha256=last.capture_grant_sha256)
                self.current.append(gap, as_of=now)
            previous = self.current.checkpoint().sha256
            self.current.close()
            self.current = None
        else: previous = self.metadata
        name = f'{len(self.segments)+1:04}-{previous}.sqlite'
        self.current = self._journal(name, create=True)
        self.segments.append(name)
        self._active = False
        self._storage()

    def append(self, event, *, as_of):
        require(type(event) is RawEvent, 'M03_EVENT_TYPE')
        if self.current is None: self.rotate(as_of)
        require(len(self.current.history()) < self.config.capture.max_events-1, 'M03_SEGMENT_EVENTS')
        # Reserve worst-case main/rollback growth before accepting another record.
        self._storage()
        total = sum(p.stat().st_size for p in self.root.iterdir())
        require(total+3*131072 <= self.config.max_total_bytes, 'M03_ARCHIVE_DISK_BUDGET')
        row = self.current.append(event, as_of=as_of)
        self._storage()
        if event.kind is Kind.CONNECTED: self._active = True
        if event.kind in (Kind.GAP, Kind.DISCONNECTED): self._active = False
        return row

    def history_not_before(self):
        planned = [r.value.event.received_at for r in self.history()
                   if r.value.event.diagnostic == 'HISTORY_REQUEST_PLANNED']
        return max(planned)+timedelta(seconds=600) if planned else None

    def observe(self, as_of, minutes=0):
        as_of = utc(as_of)
        require(minutes in (0,15,60,240), 'M03_TIMEFRAME')
        state, quote, calendar, bars, quality, contract = State(), None, None, (), (), None
        evidence = self.metadata
        for row in self.history():
            raw = row.value.event
            if max(raw.received_at, row.value.as_of) > as_of: break
            state, value = step(state, raw, self.config.capture, as_of=row.value.as_of)
            evidence = row.sha256
            if raw.kind is Kind.CONNECTED:
                quote, bars, calendar, contract = None, (), None, None
            if raw.kind is Kind.CONTRACT and value.accepted:
                contract = raw.contract
                if raw.raw_frame_b64:
                    f = fields(base64.b64decode(raw.raw_frame_b64))
                    calendar = TradingCalendar(f[27], f[28], raw.received_at)
            if raw.kind in (Kind.GAP, Kind.DISCONNECTED) or not value.accepted: quote = None
            if raw.kind in (Kind.BID, Kind.ASK): quote = value.quote
            if minutes and raw.diagnostic == 'HISTORY_BATCH' and TIMEFRAMES.get(raw.wire_request_id) == minutes:
                require(calendar is not None and contract is not None, 'M03_HISTORY_NO_CONTRACT')
                all_bars, quality = historical(base64.b64decode(raw.raw_frame_b64), minutes, raw.received_at, calendar)
                bars = tuple(b for b in all_bars if b.complete)
                quality = tuple(sorted(set(quality+tuple(c for b in all_bars for c in b.quality))))
        reasons = list(quality)
        if not self._active or not state.connected:
            quote = None
            reasons.append('DISCONNECTED_OR_RESTARTED')
        if quote and max((as_of-t).total_seconds()*1000 for t in (quote.bid_received_at,quote.ask_received_at)) > self.config.capture.side_max_age_ms:
            quote = None
            reasons.append('SIDE_RECEIPT_STALE')
        if calendar is None or calendar.state(as_of) != 'OPEN':
            quote = None
            reasons.append('MARKET_CLOSED_OR_CALENDAR_UNKNOWN')
        if state.data_type is not DataType.LIVE: reasons.append('FEED_NOT_LIVE')
        if quote and quote.source_age_us is None: reasons.append('SOURCE_TIME_NOT_PROVIDED')
        if not quote and not minutes: reasons.append('QUOTE_UNAVAILABLE')
        if minutes and not bars: reasons.append('BARS_UNAVAILABLE')
        available = bool(bars) if minutes else quote is not None
        freshness = 'STALE' if minutes and bars else 'FRESH' if available and state.data_type is DataType.LIVE else 'STALE' if available else 'UNAVAILABLE'
        from trading_agent.core_v3.market_observation.contracts import Origin
        return Observation('EUR/USD',contract,self.origin,self.environment,state.connection,as_of,minutes,
            None if minutes else quote,bars if minutes else (),state.data_type,freshness,
            tuple(sorted(set(reasons))),evidence,'IBKR_DATA_ONLY' if self.origin is Origin.SOCKET else 'OFFLINE')

    def close(self):
        if self.current is not None:
            self.current.close()
            self.current = None
        self._active = False
        if self._lock is not None:
            self._lock.close()
            self._lock = None

    def __enter__(self): return self
    def __exit__(self, *args): self.close()
