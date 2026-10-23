"""Additional external-host consent binds history and supervisor limits to V3.9 approval."""
from dataclasses import dataclass
from datetime import datetime
import hashlib
import hmac

from trading_agent.core_v3.contracts import require, utc, canonical_bytes, content_hash
from trading_agent.core_v3.economic_contracts import _hash
from trading_agent.core_v3.historical_ingestion.contracts import Record
from trading_agent.core_v3.market_observation.authorization import Approval, Scope


@dataclass(frozen=True, slots=True)
class DataPermit(Record):
    SCHEMA = 'trading.m03a.external_data_permit'
    capture_grant_sha256: str
    config_sha256: str
    issued_at: datetime
    expires_at: datetime
    scope: str = 'EURUSD_QUOTES_CALENDAR_MIDPOINT_15_60_240_DATA_ONLY'

    def __post_init__(self):
        self.check_types()
        _hash(self.capture_grant_sha256)
        _hash(self.config_sha256)
        object.__setattr__(self, 'issued_at', utc(self.issued_at))
        object.__setattr__(self, 'expires_at', utc(self.expires_at))
        require(0 < (self.expires_at-self.issued_at).total_seconds() <= 3600 and
                self.scope == 'EURUSD_QUOTES_CALENDAR_MIDPOINT_15_60_240_DATA_ONLY', 'M03_PERMIT')


class DataApproval:
    def __init__(self, capture, permit, signature, verification_key):
        require(type(capture) is Approval and type(permit) is DataPermit and
                type(verification_key) is bytes and len(verification_key) >= 32, 'M03_APPROVAL')
        _hash(signature)
        self.capture, self.permit, self.signature, self._key = capture, permit, signature, verification_key

    def verify(self, config, now):
        g, p = self.capture.grant, self.permit
        self.capture.verify(Scope.CAPTURE, config.capture, g.session_id, g.session_kind, now)
        expected = hmac.new(self._key, canonical_bytes(p.to_dict()), hashlib.sha256).hexdigest()
        require(config.enabled and hmac.compare_digest(expected, self.signature) and
                p.capture_grant_sha256 == content_hash(g.to_dict()) and
                p.config_sha256 == content_hash(config.to_dict()) and
                g.issued_at <= p.issued_at <= utc(now) < p.expires_at <= g.expires_at, 'M03_APPROVAL_BINDING')
