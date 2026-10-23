"""Versioned M03-B observation boundary. No synthetic-engine conversion or authority."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from trading_agent.core_v3.contracts import require, identifier, utc, decimal_text
from trading_agent.core_v3.economic_contracts import _hash
from trading_agent.core_v3.historical_ingestion.contracts import Record
from trading_agent.core_v3.market_observation.contracts import (
    CapturePolicy, ContractIdentity, Quote, Origin, SessionKind, DataType)


@dataclass(frozen=True, slots=True)
class CollectorConfig(Record):
    SCHEMA = 'trading.m03a.collector_config'
    collector_id: str
    capture: CapturePolicy
    enabled: bool = False
    max_segments: int = 16
    max_total_bytes: int = 134217728
    max_run_seconds: int = 3600
    max_failures: int = 3
    retry_seconds: int = 2

    def __post_init__(self):
        self.check_types()
        identifier(self.collector_id)
        require(32 <= self.capture.max_events <= 512 and self.capture.max_requests >= 13,
                'M03_CAPTURE_BUDGET')
        for name, lo, hi in (('max_segments', 1, 16), ('max_total_bytes', 1048576, 268435456),
                ('max_run_seconds', 1, 3600), ('max_failures', 0, 5), ('retry_seconds', 1, 30)):
            require(lo <= getattr(self, name) <= hi, 'M03_LIMIT')


@dataclass(frozen=True, slots=True)
class Bar(Record):
    SCHEMA = 'trading.m03a.bar'
    original_time: str
    opened_at: datetime
    effective_close: datetime
    available_at: datetime
    minutes: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    complete: bool
    quality: tuple[str, ...]
    evidence_sha256: str

    def __post_init__(self):
        self.check_types()
        require(self.minutes in (15, 60, 240) and len(self.original_time) <= 16, 'M03_BAR_TIMEFRAME')
        for name in ('opened_at', 'effective_close', 'available_at'):
            object.__setattr__(self, name, utc(getattr(self, name)))
        for price in (self.open, self.high, self.low, self.close):
            decimal_text(price)
        require(0 < self.low <= min(self.open, self.close) <= max(self.open, self.close) <= self.high,
                'M03_OHLC')
        require(self.opened_at < self.effective_close and (not self.complete or
                self.effective_close <= self.available_at), 'M03_BAR_AVAILABILITY')
        _hash(self.evidence_sha256)
        codes(self.quality)


def codes(values):
    require(len(values) <= 16 and all(type(v) is str and 0 < len(v) <= 80 and
            all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ_0123456789' for c in v) for v in values), 'M03_CODES')


@dataclass(frozen=True, slots=True)
class Observation(Record):
    SCHEMA = 'trading.m03a.market_observation'
    instrument: str
    contract: ContractIdentity | None
    origin: Origin
    environment: SessionKind
    connection_id: str
    as_of: datetime
    timeframe_minutes: int
    quote: Quote | None
    bars: tuple[Bar, ...]
    feed_type: DataType
    freshness: str
    quality: tuple[str, ...]
    evidence_sha256: str
    mode: str = 'OFFLINE'
    decision: str = 'NO_TRADE'
    execution_authorized: bool = False

    def __post_init__(self):
        self.check_types()
        require(self.instrument == 'EUR/USD' and self.timeframe_minutes in (0, 15, 60, 240), 'M03_INSTRUMENT')
        require(len(self.bars) <= 128 and self.freshness in ('FRESH', 'STALE', 'UNAVAILABLE'), 'M03_OUTPUT_LIMIT')
        require(self.decision == 'NO_TRADE' and not self.execution_authorized and self.mode ==
                ('IBKR_DATA_ONLY' if self.origin is Origin.SOCKET else 'OFFLINE'), 'M03_NO_TRADE')
        require((self.timeframe_minutes == 0 and not self.bars) or
                (self.timeframe_minutes != 0 and self.quote is None), 'M03_OUTPUT_KIND')
        require(all(b.complete and b.minutes == self.timeframe_minutes and b.available_at <= self.as_of
                    for b in self.bars), 'M03_CAUSAL_BARS')
        object.__setattr__(self, 'as_of', utc(self.as_of))
        codes(self.quality)
        _hash(self.evidence_sha256)
