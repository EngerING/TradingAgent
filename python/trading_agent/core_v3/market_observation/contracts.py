"""Closed immutable observation records. Provenance is a declaration, not authority."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext
from enum import Enum
import base64
import binascii
import hashlib

from ..contracts import require, identifier, utc, decimal_text
from ..economic_contracts import _hash
from ..historical_ingestion.contracts import Record


class Origin(str, Enum):
    FIXTURE = 'SYNTHETIC_TEST_FIXTURE'
    SOCKET = 'IBKR_SOCKET_OBSERVED'


class SessionKind(str, Enum):
    PAPER = 'PAPER'
    LIVE = 'LIVE'


class DataType(str, Enum):
    UNKNOWN = 'UNKNOWN'
    LIVE = 'LIVE'
    FROZEN = 'FROZEN'
    DELAYED = 'DELAYED'
    DELAYED_FROZEN = 'DELAYED_FROZEN'


class Kind(str, Enum):
    CONNECTED = 'CONNECTED'
    CONTRACT = 'CONTRACT'
    DATA_TYPE = 'DATA_TYPE'
    BID = 'BID'
    ASK = 'ASK'
    DISCONNECTED = 'DISCONNECTED'
    GAP = 'GAP'
    NOTICE = 'NOTICE'


@dataclass(frozen=True, slots=True)
class CapturePolicy(Record):
    SCHEMA = 'trading.core_v3.observation.capture_policy'
    policy_id: str
    side_max_age_ms: int = 2000
    clock_tolerance_ms: int = 500
    max_spread: Decimal = Decimal('.01')
    max_jump_bps: int = 500
    max_events: int = 512
    max_disk_bytes: int = 16777216
    max_duration_seconds: int = 60
    max_requests: int = 16
    max_reconnects: int = 2
    max_frame_bytes: int = 16384

    def __post_init__(self):
        self.check_types()
        identifier(self.policy_id)
        decimal_text(self.max_spread)
        require(0 < self.max_spread <= 1, 'OBS_SPREAD_POLICY')
        for name, low, high in (('side_max_age_ms', 1, 60000), ('clock_tolerance_ms', 0, 10000),
                ('max_jump_bps', 1, 10000), ('max_events', 1, 4096),
                ('max_disk_bytes', 262144, 67108864), ('max_duration_seconds', 1, 300),
                ('max_requests', 1, 16), ('max_reconnects', 0, 2), ('max_frame_bytes', 128, 16384)):
            require(low <= getattr(self, name) <= high, 'OBS_POLICY_LIMIT')


@dataclass(frozen=True, slots=True)
class ContractIdentity(Record):
    SCHEMA = 'trading.core_v3.observation.contract'
    con_id: int
    symbol: str
    sec_type: str
    currency: str
    exchange: str
    min_tick: Decimal
    details_sha256: str

    def __post_init__(self):
        self.check_types()
        require(0 < self.con_id < 2**31 and (self.symbol, self.sec_type, self.currency, self.exchange)
                == ('EUR', 'CASH', 'USD', 'IDEALPRO'), 'OBS_CONTRACT')
        decimal_text(self.min_tick)
        require(self.min_tick > 0, 'OBS_TICK')
        _hash(self.details_sha256)


@dataclass(frozen=True, slots=True)
class RawEvent(Record):
    SCHEMA = 'trading.core_v3.observation.raw_event'
    session_id: str
    connection_id: str
    request_id: int
    sequence: int
    kind: Kind
    received_at: datetime
    monotonic_ns: int
    origin: Origin
    session_kind: SessionKind
    contract: ContractIdentity | None = None
    data_type: DataType | None = None
    price_text: str | None = None
    tick_type: int | None = None
    source_at: datetime | None = None
    raw_frame_b64: str = ''
    diagnostic: str = ''
    redacted: bool = False
    raw_frame_sha256: str | None = None
    raw_frame_size: int = 0
    wire_request_id: int | None = None
    host_attestation_sha256: str | None = None
    capture_grant_sha256: str | None = None

    def __post_init__(self):
        self.check_types()
        identifier(self.session_id)
        identifier(self.connection_id)
        require(0 <= self.request_id < 2**31 and 1 <= self.sequence <= 2**63-1
                and 0 <= self.monotonic_ns < 2**63, 'OBS_EVENT_ID')
        object.__setattr__(self, 'received_at', utc(self.received_at))
        if self.source_at is not None:
            object.__setattr__(self, 'source_at', utc(self.source_at))
        require(self.price_text is None or len(self.price_text) <= 128, 'OBS_PRICE_LENGTH')
        require(len(self.raw_frame_b64) <= 22000 and len(self.diagnostic) <= 80
                and all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ_0123456789' for c in self.diagnostic), 'OBS_RAW_LIMIT')
        require(0 <= self.raw_frame_size <= 16384 and (self.raw_frame_sha256 is not None or self.raw_frame_size == 0), 'OBS_RAW_SIZE')
        if self.raw_frame_sha256 is not None:
            _hash(self.raw_frame_sha256)
        for digest in (self.host_attestation_sha256, self.capture_grant_sha256):
            if digest is not None:
                _hash(digest)
        require(not self.redacted or not self.raw_frame_b64, 'OBS_REDACTION')
        if self.raw_frame_b64:
            try:
                raw_bytes = base64.b64decode(self.raw_frame_b64, validate=True)
            except (binascii.Error, ValueError):
                require(False, 'OBS_RAW_ENCODING')
            require(len(raw_bytes) == self.raw_frame_size and hashlib.sha256(raw_bytes).hexdigest() == self.raw_frame_sha256, 'OBS_RAW_HASH')
        else:
            require(self.raw_frame_size == 0 or self.redacted, 'OBS_RAW_MISSING')
        self.to_json()  # Reject invalid Unicode and enforce inherited document budget.


@dataclass(frozen=True, slots=True)
class Quote(Record):
    SCHEMA = 'trading.core_v3.observation.quote'
    bid: Decimal
    ask: Decimal
    spread: Decimal
    bid_sequence: int
    ask_sequence: int
    bid_received_at: datetime
    ask_received_at: datetime
    bid_source_at: datetime | None
    ask_source_at: datetime | None
    source_age_us: int | None
    data_type: DataType
    contract: ContractIdentity

    def __post_init__(self):
        self.check_types()
        for value in (self.bid, self.ask, self.spread):
            decimal_text(value)
        with localcontext() as context:
            context.prec = 160
            require(0 < self.bid <= self.ask and self.spread == self.ask-self.bid, 'OBS_QUOTE')


@dataclass(frozen=True, slots=True)
class ValidatedEvent(Record):
    SCHEMA = 'trading.core_v3.observation.validated_event'
    event: RawEvent
    as_of: datetime
    accepted: bool
    reasons: tuple[str, ...]
    quote: Quote | None

    def __post_init__(self):
        self.check_types()
        object.__setattr__(self, 'as_of', utc(self.as_of))
        require(len(self.reasons) <= 16 and (self.accepted or self.quote is None), 'OBS_VERDICT')
