"""Isolated read-only socket profile. No SDK, provider, credentials, or order API."""
import base64
from datetime import datetime, timezone
import hashlib
import socket
import struct
import time
import uuid

from ..contracts import ContractError, require
from .authorization import Approval, Scope
from .contracts import CapturePolicy, RawEvent, Origin, Kind, SessionKind
from .ibkr_protocol import Command, encode, handshake, decode, fields


def _now():
    return datetime.now(timezone.utc)


class _Epoch:
    """One connection's preflight. Shared only with a labelled transcript fixture."""
    def __init__(self, session_id, connection_id, origin, session_kind, now, mono):
        self.session_id, self.connection_id, self.origin, self.session_kind = session_id, connection_id, origin, session_kind
        self.now, self.mono, self.sequence = now, mono, 0
        self.contract, self.ended, self.accounts = None, False, False

    def raw(self, kind, **values):
        self.sequence += 1
        return RawEvent(self.session_id, self.connection_id, 101, self.sequence, kind,
                        self.now(), self.mono(), self.origin, self.session_kind, **values)

    def message(self, payload, policy, approval=None):
        try:
            return self._message(payload, policy, approval)
        except ContractError:
            # Preserve the offending bounded frame, not just a later generic error.
            safe_market = payload.split(b'\0', 1)[0] in (b'1', b'10', b'52', b'58')
            return self.raw(Kind.GAP, diagnostic='DECODE_OR_PREFLIGHT_REJECTED',
                raw_frame_b64=base64.b64encode(payload).decode('ascii') if safe_market else '',
                raw_frame_sha256=hashlib.sha256(payload).hexdigest(), raw_frame_size=len(payload), redacted=not safe_market)

    def late_frame(self, payload):
        return self.raw(Kind.GAP, diagnostic='FRAME_AFTER_PERMISSION_OR_DEADLINE', redacted=True,
                        raw_frame_sha256=hashlib.sha256(payload).hexdigest(), raw_frame_size=len(payload))

    def _message(self, payload, policy, approval=None):
        value = decode(payload, policy.max_frame_bytes)
        if value.accounts is not None:
            if approval:
                approval.check_accounts(value.accounts)
            self.accounts = True
        if value.contract is not None:
            require(value.request_id == 100 and self.contract is None and not self.ended, 'OBS_CONTRACT_RESPONSE')
            self.contract = value.contract
        if value.details_end:
            require(value.request_id == 100 and self.contract is not None and not self.ended, 'OBS_CONTRACT_RESPONSE')
            self.ended = True
        if value.kind in (Kind.DATA_TYPE, Kind.BID, Kind.ASK):
            require(self.ended and self.accounts and value.request_id == 101, 'OBS_PREFLIGHT_REQUIRED')
        return self.raw(value.kind, contract=value.contract, data_type=value.data_type,
            price_text=value.price_text, tick_type=value.tick_type, diagnostic=value.diagnostic,
            redacted=value.redacted, raw_frame_b64='' if value.redacted else base64.b64encode(payload).decode('ascii'),
            raw_frame_sha256=hashlib.sha256(payload).hexdigest(), raw_frame_size=len(payload),
            wire_request_id=value.request_id if value.request_id >= 0 else None)


class TranscriptAdapter:
    """Offline protocol fixture. This path cannot declare authentic socket origin."""
    def __init__(self, payloads, policy, session_id, session_kind, *, now=_now, mono=time.monotonic_ns):
        require(type(payloads) is tuple and len(payloads) <= policy.max_events-2, 'OBS_TRANSCRIPT_BUDGET')
        require(all(type(blob) is bytes and len(blob) <= policy.max_frame_bytes for blob in payloads), 'OBS_TRANSCRIPT_FRAME')
        self.payloads, self.policy = payloads, policy
        self.epoch = _Epoch(session_id, 'transcript-1', Origin.FIXTURE, session_kind, now, mono)
        self.closed = False

    def events(self):
        try:
            yield self.epoch.raw(Kind.CONNECTED)
            for payload in self.payloads:
                raw = self.epoch.message(payload, self.policy)
                yield raw
                if raw.kind is Kind.GAP:
                    return
            if not self.epoch.ended or not self.epoch.accounts:
                yield self.epoch.raw(Kind.GAP, diagnostic='PREFLIGHT_INCOMPLETE')
            yield self.epoch.raw(Kind.DISCONNECTED)
        finally:
            self.closed = True

    def close(self):
        self.closed = True


class IBKRReader:
    """Future trusted-host use only; default-disabled Approval is checked before socket creation."""
    def __init__(self, policy, approval, *, now=_now, mono=time.monotonic_ns):
        require(type(policy) is CapturePolicy and type(approval) is Approval, 'OBS_EXACT_TYPE')
        self.policy, self.approval, self.now, self.mono = policy, approval, now, mono
        self._socket, self._subscribed, self._requests = None, False, 0
        self.closed = False

    def _verify(self):
        g = self.approval.grant
        self.approval.verify(Scope.CAPTURE, self.policy, g.session_id, g.session_kind, self.now())

    def _send(self, command, **args):
        self._verify()
        require(self._requests < self.policy.max_requests, 'OBS_REQUEST_BUDGET')
        self._socket.sendall(encode(command, **args))
        self._requests += 1

    def _receive(self, deadline):
        data, needed = bytearray(), 4
        while len(data) < needed:
            self._verify()
            require(self.mono() < deadline, 'OBS_CAPTURE_DEADLINE')
            try:
                chunk = self._socket.recv(needed-len(data))
            except socket.timeout:
                continue
            require(bool(chunk), 'OBS_CONNECTION_CLOSED')
            data.extend(chunk)
            if len(data) == 4 and needed == 4:
                size = struct.unpack('!I', data)[0]
                require(0 < size <= self.policy.max_frame_bytes, 'OBS_FRAME_BUDGET')
                needed = 4+size
        return bytes(data[4:])

    def events(self):
        self._verify()  # No socket, even construction, before independent host approval.
        deadline = self.mono()+self.policy.max_duration_seconds*1000000000
        emitted = 0
        try:
            for attempt in range(self.policy.max_reconnects+1):
                self._verify()
                if self.closed or self.mono() >= deadline or emitted+3 >= self.policy.max_events:
                    break
                epoch = _Epoch(self.approval.grant.session_id, 'ibkr-'+uuid.uuid4().hex,
                               Origin.SOCKET, self.approval.grant.session_kind, self.now, self.mono)
                try:
                    self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self._socket.settimeout(2)
                    self._socket.connect((self.approval.grant.host, self.approval.grant.port))
                    self._verify()
                    self._socket.sendall(handshake())
                    server = fields(self._receive(deadline), self.policy.max_frame_bytes)
                    self._verify()
                    require(self.mono() < deadline, 'OBS_CAPTURE_DEADLINE')
                    require(len(server) == 2 and server[0] == '157', 'OBS_UNVERIFIED_SERVER_PROFILE')
                    yield epoch.raw(Kind.CONNECTED)
                    emitted += 1
                    self._send(Command.START, client_id=self.approval.grant.client_id)
                    self._send(Command.ACCOUNTS)
                    self._send(Command.TIME)
                    self._send(Command.CONTRACT, request_id=100)
                    while not self.closed and emitted+2 < self.policy.max_events and self.mono() < deadline:
                        self._verify()
                        payload = self._receive(deadline)
                        try:
                            self._verify()
                            require(self.mono() < deadline, 'OBS_CAPTURE_DEADLINE')
                        except ContractError:
                            yield epoch.late_frame(payload)
                            emitted += 1
                            break
                        raw = epoch.message(payload, self.policy, self.approval)
                        yield raw
                        emitted += 1
                        if raw.kind is Kind.GAP:
                            break
                        if epoch.accounts and epoch.ended and not self._subscribed:
                            # Reserve one permitted cancellation request before subscribing.
                            require(self._requests+3 <= self.policy.max_requests, 'OBS_REQUEST_BUDGET')
                            self._send(Command.DATA_TYPE)
                            self._send(Command.SUBSCRIBE, con_id=epoch.contract.con_id)
                            self._subscribed = True
                except (OSError, ContractError):
                    if epoch.sequence and emitted+1 < self.policy.max_events:
                        yield epoch.raw(Kind.GAP, diagnostic='CONNECTION_OR_PREFLIGHT_FAILURE')
                        emitted += 1
                    elif not epoch.sequence:
                        raise ContractError('OBS_CONNECTION_PREFLIGHT_FAILED') from None
                finally:
                    self._release()
                if epoch.sequence and emitted < self.policy.max_events:
                    yield epoch.raw(Kind.DISCONNECTED)
                    emitted += 1
        finally:
            self.close()

    def _release(self):
        if self._socket is not None:
            try:
                if self._subscribed:
                    # Cleanup is data-subscription-only even after approval expiry/revocation.
                    self._socket.sendall(encode(Command.CANCEL))
                    self._requests += 1
            except OSError:
                pass
            finally:
                self._socket.close()
                self._socket, self._subscribed = None, False

    def close(self):
        self.closed = True
        self._release()
