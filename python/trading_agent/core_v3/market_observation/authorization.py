"""Trusted host attestation for data only. No authority provisioned by this module."""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import hashlib
import hmac

from ..contracts import require, identifier, canonical_bytes, content_hash, utc
from ..economic_contracts import _hash
from ..historical_ingestion.contracts import Record
from .contracts import CapturePolicy, SessionKind


class Scope(str, Enum):
    CAPTURE = 'DATA_CAPTURE_ONLY'
    SHADOW = 'OBSERVATIONAL_SHADOW_ONLY'


@dataclass(frozen=True, slots=True)
class Grant(Record):
    SCHEMA = 'trading.core_v3.observation.host_grant'
    approval_id: str
    scope: Scope
    host: str
    port: int
    client_id: int
    session_id: str
    session_kind: SessionKind
    policy_sha256: str
    accounts_hmac: str
    attestation_sha256: str
    issued_at: datetime
    expires_at: datetime
    tws_read_only_confirmed: bool
    market_permission_confirmed: bool
    shadow_spec_sha256: str | None = None
    journal_metadata_sha256: str | None = None

    def __post_init__(self):
        self.check_types()
        identifier(self.approval_id)
        identifier(self.session_id)
        require(self.host == '127.0.0.1' and 1 <= self.port <= 65535 and 0 <= self.client_id <= 2**31-1, 'OBS_ENDPOINT')
        for digest in (self.policy_sha256, self.accounts_hmac, self.attestation_sha256):
            _hash(digest)
        for digest in (self.shadow_spec_sha256, self.journal_metadata_sha256):
            if digest is not None:
                _hash(digest)
        object.__setattr__(self, 'issued_at', utc(self.issued_at))
        object.__setattr__(self, 'expires_at', utc(self.expires_at))
        require(self.issued_at < self.expires_at and (self.expires_at-self.issued_at).total_seconds() <= 3600, 'OBS_GRANT_WINDOW')


def accounts_digest(csv, key):
    require(type(csv) is str and 0 < len(csv) <= 4096 and type(key) is bytes and len(key) >= 32, 'OBS_ACCOUNT_ATTESTATION')
    values = sorted(csv.rstrip(',').split(','))
    require(values and all(value and len(value) <= 80 and value.isascii() and value.isalnum() for value in values)
            and len(set(values)) == len(values), 'OBS_ACCOUNT_ATTESTATION')
    return hmac.new(key, ('accounts\0'+','.join(values)).encode('ascii'), hashlib.sha256).hexdigest()


class Approval:
    """In-process trusted host boundary, not isolation from a Python/file owner."""
    def __init__(self, grant, signature, verification_key, *, enabled=False):
        require(type(grant) is Grant and type(verification_key) is bytes and len(verification_key) >= 32
                and type(enabled) is bool, 'OBS_HOST_APPROVAL_REQUIRED')
        _hash(signature)
        self.grant, self.signature, self._key, self.enabled = grant, signature, verification_key, enabled
        self._revoked = False

    def revoke(self):
        self._revoked = True

    def verify(self, scope, policy, session_id, session_kind, now):
        require(type(scope) is Scope and type(policy) is CapturePolicy and type(session_kind) is SessionKind, 'OBS_HOST_APPROVAL_REQUIRED')
        expected = hmac.new(self._key, canonical_bytes(self.grant.to_dict()), hashlib.sha256).hexdigest()
        g = self.grant
        require(self.enabled and not self._revoked and hmac.compare_digest(expected, self.signature), 'OBS_CAPTURE_DISABLED')
        require(g.scope is scope and (g.session_id, g.session_kind, g.policy_sha256) ==
                (session_id, session_kind, content_hash(policy.to_dict())), 'OBS_APPROVAL_BINDING')
        require(g.issued_at <= utc(now) < g.expires_at and g.tws_read_only_confirmed and g.market_permission_confirmed, 'OBS_APPROVAL_EXPIRED_OR_UNVERIFIED')

    def check_accounts(self, csv):
        require(hmac.compare_digest(accounts_digest(csv, self._key), self.grant.accounts_hmac), 'OBS_ACCOUNT_MISMATCH')
