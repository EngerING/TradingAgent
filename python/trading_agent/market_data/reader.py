"""Restricted V157 socket reader plus an explicitly synthetic byte-stream twin."""
import base64
from datetime import datetime, timezone, timedelta
import hashlib
import socket
import struct
import time
import uuid

from trading_agent.core_v3.contracts import require, ContractError, content_hash
from trading_agent.core_v3.market_observation.ibkr_adapter import IBKRReader, _Epoch
from trading_agent.core_v3.market_observation.ibkr_protocol import Command, handshake, fields
from trading_agent.core_v3.market_observation.contracts import Kind, Origin
from .authorization import DataApproval
from .contracts import CollectorConfig
from .calendar import TradingCalendar
from .wire import history_request, cancel_history, history_fields, TIMEFRAMES


class MarketReader(IBKRReader):
    """One bounded connection. Supervisor owns retries and disk rotation, never the BFF."""
    origin = Origin.SOCKET

    def __init__(self, config, approval, *, now=lambda:datetime.now(timezone.utc), mono=time.monotonic_ns,
                 history_not_before=None, stop=lambda:False):
        require(type(config) is CollectorConfig and type(approval) is DataApproval, 'M03_READER_TYPE')
        super().__init__(config.capture, approval.capture, now=now, mono=mono)
        self.config, self.data_approval, self.stop = config, approval, stop
        self._connection_grant = content_hash(approval.capture.grant.to_dict())
        self.calendar, self.reason, self.next_open = None, 'NOT_STARTED', None
        self.history_not_before = history_not_before
        self._pending, self._buffer, self._needed = None, bytearray(), 4
        self._rejected = b''

    def _verify(self):
        require(self.data_approval.capture is self.approval and
                content_hash(self.approval.grant.to_dict()) == self._connection_grant, 'M03_CONNECTION_BINDING')
        self.data_approval.verify(self.config, self.now())

    def _open(self):
        g = self.approval.grant
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.settimeout(2)
        self._socket.connect((g.host, g.port))

    def _receive(self, deadline):
        # Preserve partial framing across idle polls, allowing pacing, stop and calendar checks.
        self._verify()
        require(self.mono() < deadline, 'M03_DEADLINE')
        try:
            chunk = self._socket.recv(self._needed-len(self._buffer))
        except socket.timeout:
            return None
        require(bool(chunk), 'M03_CONNECTION_CLOSED')
        self._buffer.extend(chunk)
        self._rejected = bytes(self._buffer[4:])
        self._verify()  # A blocking read may outlive permission; retain a redacted digest.
        require(self.mono() < deadline, 'M03_DEADLINE')
        if len(self._buffer) == 4 and self._needed == 4:
            size = struct.unpack('!I', self._buffer)[0]
            require(0 < size <= self.policy.max_frame_bytes, 'M03_FRAME_BUDGET')
            self._needed = size+4
        if len(self._buffer) != self._needed:
            return None
        payload = bytes(self._buffer[4:])
        self._buffer, self._needed = bytearray(), 4
        return payload

    def _release(self):
        if self._socket is not None and self._pending is not None:
            try:
                self._socket.sendall(cancel_history(self._pending))
                self._requests += 1
            except OSError:
                pass
            self._pending = None
        super()._release()

    def events(self):
        self._verify()  # No endpoint discovery or socket construction without both approvals.
        if self.stop():
            self.close()
            return
        epoch = _Epoch(self.approval.grant.session_id, 'm03-'+uuid.uuid4().hex, self.origin,
                       self.approval.grant.session_kind, self.now, self.mono, self.approval)
        deadline = self.mono()+self.policy.max_duration_seconds*10**9
        next_history = self.history_not_before or self.now()
        next_history_mono = self.mono()
        remaining = list(TIMEFRAMES)
        count, ready = 0, False
        try:
            self._open()
            self._verify()
            self._socket.sendall(handshake())
            server = None
            while server is None and not self.stop(): server = self._receive(deadline)
            require(server is not None and fields(server)[0] == '157' and len(fields(server)) == 2,
                    'M03_UNVERIFIED_SERVER_PROFILE')
            yield epoch.raw(Kind.CONNECTED)
            count += 1
            for command, args in ((Command.START, {'client_id':self.approval.grant.client_id}),
                                  (Command.ACCOUNTS, {}), (Command.TIME, {}),
                                  (Command.CONTRACT, {'request_id':100})):
                self._send(command, **args)
            while not self.closed and not self.stop() and count < self.policy.max_events-3 and self.mono() < deadline:
                self._verify()
                if ready:
                    state = self.calendar.state(self.now())
                    if state != 'OPEN':
                        self.reason = 'MARKET_'+state
                        self.next_open = self.calendar.next_open(self.now())
                        yield epoch.raw(Kind.GAP, diagnostic=self.reason)
                        count += 1
                        break
                    if remaining and self._pending is None and self.now() >= next_history and self.mono() >= next_history_mono:
                        req = remaining.pop(0)
                        request = history_request(req, epoch.contract.con_id, TIMEFRAMES[req], self.now())
                        # Persist intention first; after a crash it conservatively consumes pacing budget.
                        yield epoch.raw(Kind.NOTICE, diagnostic='HISTORY_REQUEST_PLANNED',
                            raw_frame_b64=base64.b64encode(request[4:]).decode(),
                            raw_frame_sha256=hashlib.sha256(request[4:]).hexdigest(),
                            raw_frame_size=len(request)-4, wire_request_id=req)
                        count += 1
                        self._verify()
                        require(self._requests+4 < self.policy.max_requests, 'M03_REQUEST_BUDGET')
                        self._socket.sendall(request)
                        self._requests += 1
                        self._pending = req
                        next_history = self.now()+timedelta(seconds=20)
                        next_history_mono = self.mono()+20*10**9
                payload = self._receive(deadline)
                if payload is None: continue
                if payload.split(b'\0',1)[0] == b'17':
                    f = history_fields(payload)
                    require(ready and int(f[1]) == self._pending, 'M03_UNSOLICITED_HISTORY')
                    raw = epoch.raw(Kind.NOTICE, diagnostic='HISTORY_BATCH', wire_request_id=self._pending,
                        raw_frame_b64=base64.b64encode(payload).decode(),
                        raw_frame_sha256=hashlib.sha256(payload).hexdigest(), raw_frame_size=len(payload))
                    self._pending = None
                else:
                    raw = epoch.message(payload, self.policy, self.approval)
                    if raw.kind is Kind.CONTRACT:
                        f = fields(payload)
                        self.calendar = TradingCalendar(f[27], f[28], raw.received_at)
                yield raw
                count += 1
                if raw.kind is Kind.GAP:
                    self.reason = 'DISCONNECTED' if raw.diagnostic in (
                        'IBKR_ERROR_1100','IBKR_ERROR_1101','IBKR_ERROR_1102','IBKR_ERROR_1300',
                        'IBKR_ERROR_2103','IBKR_ERROR_2108') else 'SESSION_OR_FEED_INVALID'
                    break
                if epoch.accounts and epoch.ended and not ready:
                    require(self.calendar is not None, 'M03_CALENDAR_MISSING')
                    ready = True
                    if self.calendar.state(self.now()) == 'OPEN':
                        self._send(Command.DATA_TYPE)
                        self._send(Command.SUBSCRIBE, con_id=epoch.contract.con_id)
                        self._subscribed = True
            if self.reason == 'NOT_STARTED':
                self.reason = 'STOPPED' if self.stop() else 'CAPTURE_BOUNDARY'
            yield epoch.raw(Kind.GAP, diagnostic=self.reason)
        except (OSError, ContractError) as exc:
            code = str(exc) if isinstance(exc, ContractError) else ''
            self.reason = ('IDENTITY_OR_PERMISSION_REJECTED' if code in
                ('OBS_ACCOUNT_MISMATCH','OBS_CAPTURE_DISABLED','OBS_APPROVAL_BINDING',
                 'OBS_APPROVAL_EXPIRED_OR_UNVERIFIED','M03_APPROVAL_BINDING','M03_CONNECTION_BINDING') else
                'PROFILE_REJECTED' if code == 'M03_UNVERIFIED_SERVER_PROFILE' else 'DISCONNECTED')
            rejected = self._rejected
            safe = rejected.split(b'\0',1)[0] in (b'1',b'10',b'17',b'52',b'58') and rejected.endswith(b'\0')
            yield epoch.raw(Kind.GAP, diagnostic=self.reason,
                raw_frame_b64=base64.b64encode(rejected).decode() if safe else '',
                raw_frame_sha256=hashlib.sha256(rejected).hexdigest() if rejected else None,
                raw_frame_size=len(rejected), redacted=bool(rejected) and not safe)
        finally:
            self.close()
        yield epoch.raw(Kind.DISCONNECTED)


class _TranscriptSocket:
    def __init__(self, packets):
        greeting = b'157\0fixture\0'
        self.data = bytearray(b''.join(struct.pack('!I',len(p))+p for p in (greeting,)+packets))
        self.sent = []

    def recv(self, n):
        value = bytes(self.data[:min(n,3)])
        del self.data[:len(value)]
        return value

    def sendall(self, data): self.sent.append(data)
    def close(self): pass


class TranscriptReader(MarketReader):
    origin = Origin.FIXTURE

    def __init__(self, packets, *args, **kwargs):
        require(type(packets) is tuple and len(packets) <= 256 and
                all(type(p) is bytes and 0 < len(p) <= 16384 for p in packets), 'M03_FIXTURE_LIMIT')
        self.fixture = _TranscriptSocket(packets)
        super().__init__(*args, **kwargs)

    def _open(self): self._socket = self.fixture

    @property
    def sent_opcodes(self):
        return tuple(int(b[4:].split(b'\0',1)[0]) for b in self.fixture.sent if not b.startswith(b'API'))
