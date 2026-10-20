"""Immutable observational contracts, independent of protected Core contracts."""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from .serialization import AnalystError, Record, hash_text, identifier, require

ENGINE_VERSION = 'MARKET_ANALYST_V1_FLOAT_RESEARCH_1'
INDICATOR_NAMES = ('ema_fast', 'ema_slow', 'rsi', 'macd', 'macd_signal',
                   'macd_histogram', 'atr', 'ema_fast_slope', 'ema_slow_slope',
                   'log_return_std', 'range', 'atr_ratio')


@dataclass(frozen=True, slots=True)
class Instrument(Record):
    symbol: str = 'EUR/USD'
    contract_ref: str = 'fixture-EURUSD-MID-v1'
    price_unit: str = 'USD_PER_EUR'
    representation: str = 'SYNTHETIC_MID_OHLC'

    def __post_init__(self):
        Record.__post_init__(self)
        require((self.symbol, self.contract_ref, self.price_unit) in (
            ('EUR/USD', 'fixture-EURUSD-MID-v1', 'USD_PER_EUR'),
            ('GBP/USD', 'fixture-GBPUSD-MID-v1', 'USD_PER_GBP')), 'MA_INSTRUMENT')
        require(self.representation == 'SYNTHETIC_MID_OHLC', 'MA_REPRESENTATION')


@dataclass(frozen=True, slots=True)
class Policy(Record):
    version: str = 'market-analyst-policy-v1'
    ema_fast: int = 20
    ema_slow: int = 50
    rsi: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    atr: int = 14
    volatility: int = 20
    slope: int = 1
    trend_gap_atr: Decimal = Decimal('0.25')
    trend_slope_atr: Decimal = Decimal('0.03')
    high_volatility_atr_ratio: Decimal = Decimal('0.002')
    low_volatility_atr_ratio: Decimal = Decimal('0.0004')
    max_age_seconds: int = 3600
    max_bars: int = 4096

    def __post_init__(self):
        Record.__post_init__(self)
        identifier(self.version)
        for name in ('ema_fast', 'ema_slow', 'rsi', 'macd_fast', 'macd_slow',
                     'macd_signal', 'atr', 'volatility', 'slope'):
            require(1 <= getattr(self, name) <= 1000, 'MA_INDICATOR_PERIOD')
        require(self.ema_fast < self.ema_slow and self.macd_fast < self.macd_slow,
                'MA_PERIOD_ORDER')
        for name in ('trend_gap_atr', 'trend_slope_atr', 'high_volatility_atr_ratio',
                     'low_volatility_atr_ratio'):
            require(Decimal('1e-12') <= getattr(self, name) < 100, 'MA_THRESHOLD')
        require(self.low_volatility_atr_ratio < self.high_volatility_atr_ratio,
                'MA_VOLATILITY_THRESHOLDS')
        require(0 <= self.max_age_seconds <= 86400 and 1 <= self.max_bars <= 4096, 'MA_LIMIT')


@dataclass(frozen=True, slots=True)
class Authority(Record):
    mode: str = 'OFFLINE'
    decision: str = 'NO_TRADE'
    execution_authorized: bool = False
    paper_eligible: bool = False
    live_approved: bool = False

    def __post_init__(self):
        Record.__post_init__(self)
        require(self.mode == 'OFFLINE' and self.decision == 'NO_TRADE'
                and not any((self.execution_authorized, self.paper_eligible, self.live_approved)),
                'MA_AUTHORITY_FORBIDDEN')


@dataclass(frozen=True, slots=True)
class Indicator(Record):
    name: str
    value: Decimal | None
    unit: str
    warmup_bars: int
    observed_bars: int
    status: str

    def __post_init__(self):
        Record.__post_init__(self)
        require(self.name in INDICATOR_NAMES and 1 <= self.warmup_bars <= 2001
                and 0 <= self.observed_bars <= 4096, 'MA_INDICATOR')
        require(self.unit in ('USD_PER_EUR', 'USD_PER_GBP', 'USD_PER_EUR_PER_BAR',
                             'USD_PER_GBP_PER_BAR', 'INDEX_0_100', 'DIMENSIONLESS',
                             'LOG_RETURN_PER_BAR'), 'MA_UNIT')
        require(self.status in ('READY', 'WARMUP', 'UNAVAILABLE'), 'MA_INDICATOR_STATUS')
        require((self.status == 'READY') == (self.value is not None), 'MA_INDICATOR_VALUE')
        require(self.status != 'READY' or self.observed_bars >= self.warmup_bars, 'MA_WARMUP')


@dataclass(frozen=True, slots=True)
class Provenance(Record):
    source_kind: str = 'UNKNOWN'
    evidence_ref: str | None = None
    data_sha256: str | None = None
    authentication: str = 'UNVERIFIED'
    provider_authenticated: bool = False

    def __post_init__(self):
        Record.__post_init__(self)
        require(self.source_kind in ('UNKNOWN', 'SYNTHETIC_TEST_FIXTURE'), 'MA_SOURCE')
        require(not self.provider_authenticated, 'MA_PROVIDER_AUTHENTICATION_UNSUPPORTED')
        if self.source_kind == 'UNKNOWN':
            require(self.authentication == 'UNVERIFIED' and self.evidence_ref is None
                    and self.data_sha256 is None, 'MA_UNVERIFIED_SOURCE')
        else:
            require(self.authentication == 'NOT_APPLICABLE_SYNTHETIC', 'MA_SYNTHETIC_AUTH')
            identifier(self.evidence_ref)
            hash_text(self.data_sha256)


@dataclass(frozen=True, slots=True)
class Quality(Record):
    evaluated_bars: int | None = None
    missing_bars: int | None = None
    duplicates: int | None = None
    discontinuities: int | None = None
    age_seconds: Decimal | None = None
    reasons: tuple[str, ...] = ()

    def __post_init__(self):
        Record.__post_init__(self)
        for value in (self.evaluated_bars, self.missing_bars, self.duplicates, self.discontinuities):
            require(value is None or 0 <= value <= 1000000, 'MA_QUALITY_COUNT')
        require(self.age_seconds is None or self.age_seconds >= 0, 'MA_AGE')
        require(len(self.reasons) <= 32 and len(set(self.reasons)) == len(self.reasons), 'MA_REASONS')
        for reason in self.reasons:
            identifier(reason)


@dataclass(frozen=True, slots=True)
class SupplementaryEvidenceRef(Record):
    """Future metadata boundary only; evaluator V1 does not consume evidence."""
    provider: str
    model_version: str
    input_sha256: str
    generated_at: datetime
    available_at: datetime
    calibration_reference: str | None
    execution_authorized: bool = False

    def __post_init__(self):
        Record.__post_init__(self)
        require(self.provider in ('KRONOS', 'SOL') and not self.execution_authorized, 'MA_EVIDENCE')
        identifier(self.model_version)
        hash_text(self.input_sha256)
        require(self.available_at >= self.generated_at, 'MA_EVIDENCE_TIME')
        if self.calibration_reference is not None:
            identifier(self.calibration_reference)


@dataclass(frozen=True, slots=True)
class MarketAssessment(Record):
    instrument: Instrument
    minutes: int
    cutoff: datetime
    window_start: datetime | None
    window_end: datetime | None
    last_closed_at: datetime | None
    available_at: datetime | None
    source: Provenance
    indicators: tuple[Indicator, ...]
    trend: str
    volatility: str
    quality: Quality
    policy: Policy
    policy_sha256: str
    status: str
    engine_version: str = ENGINE_VERSION
    authority: Authority = field(default_factory=Authority)

    def __post_init__(self):
        Record.__post_init__(self)
        require(self.minutes in (15, 60, 240), 'MA_TIMEFRAME')
        require(self.status in ('COMPLETE', 'INSUFFICIENT_DATA', 'STALE_DATA',
                'SOURCE_UNAVAILABLE', 'UNVERIFIED_PROVENANCE', 'VALIDATION_ERROR'), 'MA_STATUS')
        require(self.trend in ('UPTREND', 'DOWNTREND', 'SIDEWAYS', 'UNKNOWN')
                and self.volatility in ('HIGH', 'NORMAL', 'LOW', 'UNKNOWN'), 'MA_REGIME')
        require(self.policy_sha256 == self.policy.sha256() and self.engine_version == ENGINE_VERSION,
                'MA_VERSION_BINDING')
        require(tuple(i.name for i in self.indicators) == INDICATOR_NAMES, 'MA_INDICATOR_SET')
        times = (self.window_start, self.window_end, self.last_closed_at, self.available_at)
        require(all(t is None for t in times) or all(t is not None for t in times), 'MA_PERIOD')
        if self.window_start is not None:
            require(self.window_start < self.window_end == self.last_closed_at
                    <= self.available_at <= self.cutoff, 'MA_CAUSAL_TIME')
        if self.status != 'COMPLETE':
            require(self.trend == self.volatility == 'UNKNOWN' and bool(self.quality.reasons),
                    'MA_INCONCLUSIVE_REGIME')
        else:
            require(self.trend != 'UNKNOWN' and self.volatility != 'UNKNOWN'
                    and not self.quality.reasons and all(i.status == 'READY' for i in self.indicators)
                    and self.source.source_kind == 'SYNTHETIC_TEST_FIXTURE', 'MA_COMPLETE')
