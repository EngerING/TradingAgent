"""Historical-only socket profile, with a labelled fragmented transcript twin."""
import base64
from datetime import datetime, timezone, timedelta
import hashlib
import time
import uuid

from trading_agent.core_v3.contracts import require, content_hash, ContractError, canonical_bytes
from trading_agent.core_v3.market_observation.contracts import Kind, Origin
from trading_agent.core_v3.market_observation.ibkr_adapter import IBKRReader, _Epoch
from trading_agent.core_v3.market_observation.ibkr_protocol import Command, handshake, fields
from ..reader import MarketReader, _TranscriptSocket
from .contracts import BackfillSpec, HistoricalApproval
from .store import HistoricalStore, cutoff_has_incomplete_bar
from .wire import request, cancel, history_fields


class HistoricalReader(IBKRReader):
    origin=Origin.SOCKET
    _open=MarketReader._open
    _receive=MarketReader._receive

    def __init__(self, spec, approval, store, *, now=lambda:datetime.now(timezone.utc),
                 mono=time.monotonic_ns, wait=lambda seconds:time.sleep(seconds), stop=lambda:False):
        require(type(spec) is BackfillSpec and type(approval) is HistoricalApproval and
                type(store) is HistoricalStore,'M032_READER_TYPE')
        super().__init__(spec.collector.capture,approval.capture,now=now,mono=mono)
        self.spec,self.history_approval,self.store=spec,approval,store
        self.wait,self.stop=wait,stop
        self._connection_grant=content_hash(approval.capture.grant.to_dict())
        self._pending=None;self._buffer=bytearray();self._needed=4;self._rejected=b''
        self.reason='HISTORICAL_BACKFILL'

    def _verify(self):
        require(self.history_approval.capture is self.approval and
                content_hash(self.approval.grant.to_dict())==self._connection_grant,'M032_CONNECTION_BINDING')
        self.history_approval.verify(self.spec,self.now())
        require(self.spec.end<=self.now(),'M032_FUTURE_REQUEST')
        g=self.approval.grant
        require((g.session_id,g.session_kind)==(self.store.session_id,self.store.environment) and
                self.origin is self.store.origin and self.spec==self.store.spec,'M032_STORE_BINDING')

    def _send(self, command, **args):
        require(command in (Command.START,Command.ACCOUNTS,Command.TIME,Command.CONTRACT),'M032_COMMAND_DENIED')
        super()._send(command,**args)

    def _release(self):
        if self._socket is not None and self._pending is not None:
            try: self._socket.sendall(cancel(self._pending));self._requests+=1
            except OSError: pass
            self._pending=None
        super()._release()

    def events(self):
        self._verify()
        used=self.store.used_grants.get(self._connection_grant,0)
        require(used+5<=self.policy.max_requests,'M032_GRANT_REQUEST_BUDGET')
        if self.store.last_planned is not None:
            require((self.now()-self.store.last_planned).total_seconds()>=600,'M032_RESTART_COOLDOWN')
        epoch=_Epoch(self.store.session_id,'history-'+uuid.uuid4().hex,self.origin,self.store.environment,
                     self.now,self.mono,self.approval)
        deadline=self.mono()+self.policy.max_duration_seconds*10**9
        ready=False;tasks=None;next_utc=self.now();next_mono=self.mono();count=0
        try:
            self._open();self._verify();self._socket.sendall(handshake())
            server=None
            while server is None and not self.stop(): server=self._receive(deadline)
            require(server is not None and fields(server)[0]=='157' and len(fields(server))==2,'M032_SERVER_PROFILE')
            yield epoch.raw(Kind.CONNECTED);count+=1
            context=canonical_bytes({'spec':self.spec.to_dict(),'permit_sha256':content_hash(self.history_approval.permit.to_dict())})
            yield epoch.raw(Kind.NOTICE,diagnostic='BACKFILL_AUTH_CONTEXT',raw_frame_b64=base64.b64encode(context).decode(),
                raw_frame_sha256=hashlib.sha256(context).hexdigest(),raw_frame_size=len(context));count+=1
            for cmd,args in ((Command.START,{'client_id':self.approval.grant.client_id}),
                             (Command.ACCOUNTS,{}),(Command.TIME,{}),(Command.CONTRACT,{'request_id':100})):
                self._send(cmd,**args)
            while not self.stop() and self.mono()<deadline and count<self.policy.max_events-3:
                self._verify()
                if ready and self._pending is None:
                    if tasks is None: tasks=list(self.store.pending())
                    if not tasks:
                        days=(self.spec.end.date()-self.spec.start.date()).days
                        if self.spec.end.time()!=datetime.min.time(): days+=1
                        complete=all((m,self.spec.start+timedelta(days=i)) in self.store.covered
                            for m in self.spec.timeframes for i in range(days)) and not cutoff_has_incomplete_bar(self.store.calendar,self.spec)
                        self.reason='HISTORICAL_COMPLETE' if complete else 'HISTORICAL_PARTIAL'
                        break
                    if self.now()<next_utc or self.mono()<next_mono:
                        if self.wait(1): self.reason='HISTORICAL_PARTIAL';break
                        continue
                    require(used+self._requests+2<=self.policy.max_requests,'M032_GRANT_REQUEST_BUDGET')
                    w=tasks.pop(0);blob=request(w,epoch.contract.con_id)
                    yield epoch.raw(Kind.NOTICE,diagnostic='BACKFILL_PLANNED',wire_request_id=w.request_id,
                        raw_frame_b64=base64.b64encode(blob[4:]).decode(),raw_frame_sha256=hashlib.sha256(blob[4:]).hexdigest(),raw_frame_size=len(blob)-4)
                    count+=1;self._verify()
                    self._socket.sendall(blob);self._requests+=1;self._pending=w.request_id
                    next_utc=self.now()+timedelta(seconds=20);next_mono=self.mono()+20*10**9
                payload=self._receive(deadline)
                if payload is None: continue
                if payload.split(b'\0',1)[0]==b'17':
                    f=history_fields(payload)
                    require(ready and int(f[1])==self._pending,'M032_UNSOLICITED_BATCH')
                    raw=epoch.raw(Kind.NOTICE,diagnostic='BACKFILL_BATCH',wire_request_id=self._pending,
                        raw_frame_b64=base64.b64encode(payload).decode(),raw_frame_sha256=hashlib.sha256(payload).hexdigest(),raw_frame_size=len(payload))
                    self._pending=None
                else:
                    raw=epoch.message(payload,self.policy,self.approval)
                    require(raw.kind not in (Kind.BID,Kind.ASK,Kind.DATA_TYPE),'M032_UNSOLICITED_QUOTE')
                if raw.diagnostic.startswith('IBKR_ERROR_'): self.reason='BACKFILL_PROVIDER_UNAVAILABLE'
                yield raw;count+=1
                if raw.diagnostic.startswith('IBKR_ERROR_'):
                    self.reason='BACKFILL_PROVIDER_UNAVAILABLE';break
                if raw.kind is Kind.GAP:
                    self.reason='BACKFILL_PREFLIGHT_OR_PERMISSION';break
                ready=epoch.accounts and epoch.ended
            else: self.reason='BACKFILL_INTERRUPTED'
        except (OSError,ContractError):
            self.reason='BACKFILL_CONNECTION_OR_VALIDATION'
            rejected=self._rejected
            safe=rejected.startswith(b'17\0') and rejected.endswith(b'\0')
            yield epoch.raw(Kind.GAP,diagnostic=self.reason,redacted=bool(rejected) and not safe,
                raw_frame_b64=base64.b64encode(rejected).decode() if safe else '',
                raw_frame_sha256=hashlib.sha256(rejected).hexdigest() if rejected else None,raw_frame_size=len(rejected))
        finally: self.close()
        yield epoch.raw(Kind.DISCONNECTED)


class FixtureHistoricalReader(HistoricalReader):
    origin=Origin.FIXTURE

    def __init__(self, payloads, *args, fragment=4096, **kwargs):
        require(type(payloads) is tuple and len(payloads)<=64 and
                all(type(p) is bytes and 0<len(p)<=16384 for p in payloads),'M032_FIXTURE')
        require(type(fragment) is int and 1<=fragment<=4096,'M032_FRAGMENT')
        self.fixture=_TranscriptSocket(payloads)
        self.fragment=fragment
        super().__init__(*args,**kwargs)

    def _open(self):
        fixture=self.fixture
        def receive(n):
            value=bytes(fixture.data[:min(n,self.fragment)]);del fixture.data[:len(value)];return value
        fixture.recv=receive
        self._socket=fixture

    @property
    def sent_opcodes(self):
        return tuple(int(b[4:].split(b'\0',1)[0]) for b in self.fixture.sent if not b.startswith(b'API'))


def collect(reader, store):
    require(type(reader) in (HistoricalReader,FixtureHistoricalReader) and type(store) is HistoricalStore and
            reader.store is store,'M032_COLLECTOR_TYPE')
    iterator=reader.events()
    try:
        reader._verify()
        store.archive.rotate(reader.now())
        for event in iterator:
            if event.kind is Kind.GAP and not store.archive.current.history():
                # A failed preflight is local failure metadata, never a fabricated
                # CONNECTED event or a market frame in a broker epoch.
                store.quality.add('BACKFILL_CONNECTION_OR_VALIDATION')
                return store.publish(reader.now())
            row=store.append(event,as_of=reader.now())
            if event.kind is Kind.GAP: break
            if not row.value.accepted:
                require(False,'M032_REJECTED_EVENT')
        return store.publish(reader.now())
    finally:
        try: iterator.close()
        finally:
            try: reader.close()
            finally: store.close()
