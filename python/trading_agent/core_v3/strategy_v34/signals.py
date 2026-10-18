"""Bounded synthetic candle diagnostics. No positions, fills, P&L, or orders."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Context, localcontext

from ..contracts import Price, SourceKind, content_hash, enum_value, require, utc
from ..economic_contracts import EconomicRecord, _hash, _typed
from ..research_contracts import InstrumentIdentity
from .contracts import Indicator, Operator, Timeframe
from .validation import validate


@dataclass(frozen=True, slots=True)
class Candle(EconomicRecord):
    SCHEMA = 'trading.core_v3.strategy_v34.candle'
    closed_at: datetime
    available_at: datetime
    open: Price
    high: Price
    low: Price
    close: Price

    def __post_init__(self):
        _typed(self)
        object.__setattr__(self, 'closed_at', utc(self.closed_at))
        object.__setattr__(self, 'available_at', utc(self.available_at))
        require(self.available_at >= self.closed_at, 'CANDLE_AVAILABILITY_INVALID')
        prices = (self.open, self.high, self.low, self.close)
        require(len({(v.currency, v.per_unit) for v in prices}) == 1, 'CANDLE_UNIT_MISMATCH')
        require(self.low.amount <= min(v.amount for v in prices)
                and self.high.amount >= max(v.amount for v in prices), 'CANDLE_OHLC_INVALID')


@dataclass(frozen=True, slots=True)
class CandleSeries(EconomicRecord):
    SCHEMA = 'trading.core_v3.strategy_v34.candle_series'
    instrument: InstrumentIdentity
    timeframe: Timeframe
    bars: tuple[Candle, ...]
    source_kind: SourceKind = SourceKind.SYNTHETIC

    def __post_init__(self):
        # V3.2's generic decoder caps tuples at 32; this dedicated boundary permits 256.
        require(type(self.instrument) is InstrumentIdentity and type(self.timeframe) is Timeframe
                and type(self.bars) is tuple and 1 <= len(self.bars) <= 256
                and all(type(b) is Candle for b in self.bars), 'CANDLE_SERIES_INVALID')
        require(self.source_kind is SourceKind.SYNTHETIC, 'SYNTHETIC_SERIES_REQUIRED')
        previous = None
        for bar in self.bars:
            end = bar.closed_at
            aligned = end.second == end.microsecond == 0
            if self.timeframe is Timeframe.M5:
                aligned = aligned and end.minute % 5 == 0
            if self.timeframe is Timeframe.H1:
                aligned = aligned and end.minute == 0
            require(aligned, 'CANDLE_ALIGNMENT_INVALID')
            if previous is not None:
                require(end - previous.closed_at == timedelta(seconds=self.timeframe.seconds)
                        and bar.available_at >= previous.available_at, 'CANDLE_SEQUENCE_INVALID')
            previous = bar

    @classmethod
    def from_dict(cls, data):
        values = cls.payload(data)
        bars = values['bars']
        require(type(bars) is list and 1 <= len(bars) <= 256, 'CANDLE_SERIES_INVALID')
        return cls(InstrumentIdentity.from_dict(values['instrument']), enum_value(Timeframe, values['timeframe']),
                   tuple(Candle.from_dict(b) for b in bars), enum_value(SourceKind, values['source_kind']))


@dataclass(frozen=True, slots=True)
class SignalResult(EconomicRecord):
    SCHEMA = 'trading.core_v3.strategy_v34.signal_result'
    strategy_sha256: str
    prefix_sha256: str
    postflight_sha256: str
    as_of: datetime
    latest_close: datetime
    used_bars: int
    entry_rules_met: bool
    exit_rules_met: bool
    scope: str = 'SYNTHETIC_RULE_DIAGNOSTIC_ONLY'
    trading_decision: str = 'NO_TRADE'
    execution_authority: bool = False
    paper_execution_eligible: bool = False
    live_enabled: bool = False
    statistically_validated: bool = False

    def __post_init__(self):
        _typed(self)
        for digest in (self.strategy_sha256, self.prefix_sha256, self.postflight_sha256):
            _hash(digest)
        object.__setattr__(self, 'as_of', utc(self.as_of))
        object.__setattr__(self, 'latest_close', utc(self.latest_close))
        require(self.latest_close <= self.as_of and 1 <= self.used_bars <= 256, 'SIGNAL_TIME_INVALID')
        require(not (self.entry_rules_met and self.exit_rules_met), 'CONFLICTING_RULES')
        require(self.scope == 'SYNTHETIC_RULE_DIAGNOSTIC_ONLY' and self.trading_decision == 'NO_TRADE'
                and all(v is False for v in (self.execution_authority, self.paper_execution_eligible,
                                            self.live_enabled, self.statistically_validated)),
                'SIGNAL_AUTHORITY_FORBIDDEN')


def _value(operand, bars, previous):
    end = len(bars) - operand.lag - previous
    window = bars[end-operand.period:end]
    # Rational numerator/denominator: no repeating mean or rounding at a crossing.
    if operand.indicator is Indicator.CLOSE:
        return window[-1].close.amount, 1
    return sum(b.close.amount for b in window), operand.period


def _comparison(rule, bars, previous):
    left, ln = _value(rule.left, bars, previous)
    right, rn = _value(rule.right, bars, previous)
    return left * rn - right * ln


def _matches(rule, bars):
    current = _comparison(rule, bars, 0)
    if rule.operator is Operator.GT:
        return current > 0
    if rule.operator is Operator.LT:
        return current < 0
    previous = _comparison(rule, bars, 1)
    return (previous <= 0 < current) if rule.operator is Operator.CROSS_ABOVE else (previous >= 0 > current)


def evaluate(strategy, request, series: CandleSeries, *, as_of: datetime) -> SignalResult:
    """Rules at an explicit cutoff; any hypothetical action would be strictly later."""
    require(type(series) is CandleSeries, 'SYNTHETIC_SERIES_REQUIRED')
    as_of = utc(as_of)
    after = validate(strategy, request, series.timeframe, now=as_of)
    require(series.instrument == strategy.instrument, 'SIGNAL_INSTRUMENT_MISMATCH')
    bars = tuple(b for b in series.bars if b.closed_at <= as_of and b.available_at <= as_of)
    require(bars and as_of - bars[-1].closed_at < timedelta(seconds=series.timeframe.seconds),
            'STALE_SYNTHETIC_SERIES')
    rules = strategy.entry_rules + strategy.exit_rules
    require(len(bars) >= max(r.required_bars for r in rules), 'SIGNAL_WARMUP_REQUIRED')
    instrument = request.inputs.context.market.instrument
    for bar in bars:
        for price in (bar.open, bar.high, bar.low, bar.close):
            instrument.check_terms(strategy.scenario.quantity, price)
    with localcontext(Context(prec=160)):
        entry = all(_matches(r, bars) for r in strategy.entry_rules)
        exit_met = all(_matches(r, bars) for r in strategy.exit_rules)
    prefix = dict(instrument=series.instrument, timeframe=series.timeframe, bars=bars, source_kind=series.source_kind)
    return SignalResult(content_hash(strategy), content_hash(prefix), content_hash(after), as_of,
                        bars[-1].closed_at, len(bars), entry, exit_met)
