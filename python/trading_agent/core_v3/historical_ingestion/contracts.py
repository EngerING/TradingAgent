"""Separate real-material boundary; hashes identify bytes, never authenticate origin."""
from dataclasses import dataclass, fields
from datetime import datetime
from decimal import Decimal
import re
from typing import get_args, get_origin

from ..contracts import decimal_text, identifier, require, utc, currency, unit
from ..economic_contracts import EconomicRecord, _decode, _hash, _typed_value


MAX_ROWS = 4096
MAX_BYTES = 1048576
PARSER_VERSION = 'CORE_V38_LOCAL_CSV_V1'


class Record(EconomicRecord):
    __slots__ = ()

    def check_types(self):
        for field in fields(self):
            value = getattr(self, field.name)
            if get_origin(field.type) is tuple:
                require(type(value) is tuple and len(value) <= MAX_ROWS, 'H38_COLLECTION_LIMIT')
                for item in value:
                    _typed_value(item, get_args(field.type)[0])
            else:
                _typed_value(value, field.type)

    @classmethod
    def from_dict(cls, data):
        values = cls.payload(data)
        result = {}
        for field in fields(cls):
            value = values[field.name]
            if get_origin(field.type) is tuple:
                require(type(value) is list and len(value) <= MAX_ROWS, 'H38_COLLECTION_LIMIT')
                result[field.name] = tuple(_decode(v, get_args(field.type)[0]) for v in value)
            else:
                result[field.name] = _decode(value, field.type)
        return cls(**result)


@dataclass(frozen=True, slots=True)
class DatasetSpec(Record):
    SCHEMA = 'trading.core_v3.historical.dataset_spec'
    provider_id: str
    export_id: str
    instrument_id: str
    symbol: str
    venue: str
    quote_currency: str
    price_unit: str
    tick: Decimal
    data_origin: str
    kind: str
    representation: str
    interval_seconds: int
    quote_max_gap_seconds: int
    timezone_name: str
    available_basis: str
    window_start: datetime
    window_end: datetime
    exported_at: datetime
    observed_at: datetime
    raw_sha256: str
    evidence_sha256: str
    calendar_sha256: str
    tzif_sha256: str

    def __post_init__(self):
        self.check_types()
        for value in (self.provider_id, self.export_id, self.instrument_id, self.venue):
            identifier(value)
        require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9./_-]{0,79}', self.symbol) is not None, 'H38_SYMBOL')
        currency(self.quote_currency)
        unit(self.price_unit)
        decimal_text(self.tick)
        require(self.tick > 0, 'H38_TICK')
        require(self.data_origin in ('PROVIDER_EXPORT', 'TEST_FIXTURE'), 'H38_ORIGIN')
        require((self.kind == 'OHLC' and self.representation in ('MID', 'BID', 'ASK', 'TRADE')
                 and 1 <= self.interval_seconds <= 86400 and self.quote_max_gap_seconds == 0)
                or (self.kind == 'QUOTE' and self.representation == 'BID_ASK'
                    and self.interval_seconds == 0 and 1 <= self.quote_max_gap_seconds <= 86400), 'H38_FORMAT')
        require(re.fullmatch(r'[A-Za-z0-9_+-]+(?:/[A-Za-z0-9_+-]+)*', self.timezone_name) is not None
                and len(self.timezone_name) <= 80, 'H38_TIMEZONE')
        require(self.available_basis in ('PROVIDER_PUBLISHED', 'EXPORT_OBSERVED'), 'H38_AVAILABILITY_BASIS')
        for name in ('window_start', 'window_end', 'exported_at', 'observed_at'):
            object.__setattr__(self, name, utc(getattr(self, name)))
        require(self.window_start < self.window_end <= self.exported_at <= self.observed_at, 'H38_SPEC_TIME')
        for value in (self.raw_sha256, self.evidence_sha256, self.calendar_sha256, self.tzif_sha256):
            _hash(value)


@dataclass(frozen=True, slots=True)
class ReviewReceipt(Record):
    """Trusted host attests an EXTERNAL review; not a provider signature verifier."""
    SCHEMA = 'trading.core_v3.historical.host_review'
    provider_id: str
    export_id: str
    descriptor_sha256: str
    evidence_sha256: str
    reviewer_id: str
    verification_reference: str
    reviewed_at: datetime
    method: str = 'LOCAL_REVIEW_EXTERNAL_PROVIDER_RECONCILIATION'

    def __post_init__(self):
        self.check_types()
        for value in (self.provider_id, self.export_id, self.reviewer_id, self.verification_reference):
            identifier(value)
        _hash(self.descriptor_sha256)
        _hash(self.evidence_sha256)
        object.__setattr__(self, 'reviewed_at', utc(self.reviewed_at))
        require(self.method == 'LOCAL_REVIEW_EXTERNAL_PROVIDER_RECONCILIATION', 'H38_REVIEW_METHOD')

    @classmethod
    def from_dict(cls, data):
        require(False, 'H38_HOST_REVIEW_REQUIRED')
