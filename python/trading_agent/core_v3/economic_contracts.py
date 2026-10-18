"""V3.2 immutable research inputs/results. Metadata never grants authority."""
from dataclasses import dataclass, fields
from datetime import datetime
from decimal import Decimal
from enum import Enum
import re
from types import UnionType
from typing import get_args, get_origin

from .contracts import (
    ContractError, EvidenceRef, Instrument, Money, Price, Quantity, Value, Versioned,
    content_hash, currency, decimal_text, enum_value, identifier, instant,
    parse_decimal, require, unit, utc,
)


def _typed_value(value, annotation):
    origin, args = get_origin(annotation), get_args(annotation)
    if origin is UnionType:
        require(value is None or type(value) is next(t for t in args if t is not type(None)), 'ECONOMIC_TYPE_INVALID')
    elif origin is tuple:
        require(type(value) is tuple and len(value) <= 32, 'IMMUTABLE_COLLECTION_REQUIRED')
        for item in value:
            _typed_value(item, args[0])
    else:
        require(type(value) is annotation, 'ECONOMIC_TYPE_INVALID')


def _typed(record):
    for field in fields(record):
        _typed_value(getattr(record, field.name), field.type)


def _decode(value, annotation):
    origin, args = get_origin(annotation), get_args(annotation)
    if origin is UnionType:
        return None if value is None else _decode(value, next(t for t in args if t is not type(None)))
    if origin is tuple:
        require(type(value) is list and len(value) <= 32, 'COLLECTION_INVALID')
        return tuple(_decode(v, args[0]) for v in value)
    if annotation is Decimal:
        return parse_decimal(value)
    if annotation is datetime:
        return instant(value)
    if issubclass(annotation, Enum):
        return enum_value(annotation, value)
    if issubclass(annotation, Value):
        return annotation.from_dict(value)
    _typed_value(value, annotation)
    return value


def _hash(value):
    require(type(value) is str and re.fullmatch('[a-f0-9]{64}', value) is not None, 'HASH_INVALID')


def _amounts(*values):
    for value in values:
        if value is not None:
            require(value.amount >= 0, 'NEGATIVE_ECONOMIC_INPUT')


def _fraction(value, *, zero=True):
    if value is not None:
        decimal_text(value)
        require(0 <= value if zero else 0 < value, 'MARGIN_FRACTION_INVALID')


class EconomicRecord(Versioned):
    __slots__ = ()

    @classmethod
    def from_dict(cls, data):
        values = cls.payload(data)
        return cls(**{f.name: _decode(values[f.name], f.type) for f in fields(cls)})

    def material_hash(self):
        """Evidence content identity excludes only its own EvidenceRef."""
        return content_hash({k: v for k, v in self.to_dict().items() if k != 'evidence'})


class Direction(str, Enum):
    LONG = 'LONG'
    SHORT = 'SHORT'


class EconomicStatus(str, Enum):
    FEASIBLE = 'FEASIBLE'
    INFEASIBLE = 'INFEASIBLE'
    UNKNOWN = 'UNKNOWN'
    UNRESOLVED = 'UNRESOLVED'


@dataclass(frozen=True, slots=True)
class UnitAmount(EconomicRecord):
    SCHEMA = 'trading.core_v3.economic.unit_amount'
    money: Money
    per_unit: str

    def __post_init__(self):
        _typed(self)
        unit(self.per_unit)
        _amounts(self.money)


@dataclass(frozen=True, slots=True)
class MarketSnapshot(EconomicRecord):
    SCHEMA = 'trading.core_v3.economic.market_snapshot'
    snapshot_id: str
    revision: int
    instrument: Instrument
    bid: Price
    ask: Price
    evidence: EvidenceRef

    def __post_init__(self):
        _typed(self)
        identifier(self.snapshot_id)
        require(self.revision >= 1, 'REVISION_INVALID')


@dataclass(frozen=True, slots=True)
class PortfolioSnapshot(EconomicRecord):
    SCHEMA = 'trading.core_v3.economic.portfolio_snapshot'
    portfolio_id: str
    revision: int
    account_currency: str
    equity: Money | None
    allocation_available: Money | None
    free_margin: Money | None
    remaining_exposure: Money | None
    remaining_risk: Money | None
    evidence: EvidenceRef

    def __post_init__(self):
        _typed(self)
        identifier(self.portfolio_id)
        currency(self.account_currency)
        require(self.revision >= 1, 'REVISION_INVALID')
        _amounts(self.equity, self.allocation_available, self.free_margin,
                 self.remaining_exposure, self.remaining_risk)


@dataclass(frozen=True, slots=True)
class CostSchedule(EconomicRecord):
    SCHEMA = 'trading.core_v3.economic.cost_schedule'
    schedule_id: str
    directions: tuple[Direction, ...]
    opening_minimum: Money | None
    opening_per_unit: UnitAmount | None
    closing_minimum: Money | None
    closing_per_unit: UnitAmount | None
    financing_fixed: Money | None
    financing_per_unit_per_hour: UnitAmount | None
    slippage_per_side: UnitAmount | None
    evidence: EvidenceRef

    def __post_init__(self):
        _typed(self)
        identifier(self.schedule_id)
        require(1 <= len(self.directions) <= 2 and len(set(self.directions)) == len(self.directions),
                'COST_DIRECTIONS_INVALID')
        _amounts(self.opening_minimum, self.closing_minimum, self.financing_fixed)


@dataclass(frozen=True, slots=True)
class MarginModel(EconomicRecord):
    SCHEMA = 'trading.core_v3.economic.margin_model'
    initial_fraction: Decimal | None
    maintenance_fraction: Decimal | None
    evidence: EvidenceRef

    def __post_init__(self):
        _typed(self)
        _fraction(self.initial_fraction, zero=False)
        _fraction(self.maintenance_fraction)
        if self.initial_fraction is not None and self.maintenance_fraction is not None:
            require(self.maintenance_fraction <= self.initial_fraction, 'MARGIN_ORDER_INVALID')


@dataclass(frozen=True, slots=True)
class FxConversion(EconomicRecord):
    SCHEMA = 'trading.core_v3.economic.fx_conversion'
    from_currency: str
    to_currency: str
    rate: Decimal
    evidence: EvidenceRef

    def __post_init__(self):
        _typed(self)
        currency(self.from_currency)
        currency(self.to_currency)
        decimal_text(self.rate)
        require(self.from_currency != self.to_currency and self.rate > 0, 'FX_RATE_INVALID')


@dataclass(frozen=True, slots=True)
class TechnicalHypothesis(EconomicRecord):
    SCHEMA = 'trading.core_v3.economic.technical_hypothesis'
    hypothesis_id: str
    instrument_sha256: str
    direction: Direction
    entry: Price
    stop_distance: Price
    target_distance: Price
    plausible_move: Price
    horizon_hours: int
    evidence: EvidenceRef

    def __post_init__(self):
        _typed(self)
        identifier(self.hypothesis_id)
        _hash(self.instrument_sha256)
        require(1 <= self.horizon_hours <= 720, 'HORIZON_INVALID')


@dataclass(frozen=True, slots=True)
class StressCase(EconomicRecord):
    SCHEMA = 'trading.core_v3.economic.stress_case'
    stress_id: str
    adverse_gap: UnitAmount
    extra_slippage_per_side: UnitAmount
    maintenance_fraction: Decimal

    def __post_init__(self):
        _typed(self)
        identifier(self.stress_id)
        require(self.stress_id != 'BASE_STOP', 'RESERVED_STRESS_ID')
        _fraction(self.maintenance_fraction)


@dataclass(frozen=True, slots=True)
class ResearchPolicy(EconomicRecord):
    SCHEMA = 'trading.core_v3.economic.research_policy'
    policy_id: str
    revision: int
    effective_from: datetime
    valid_until: datetime
    max_quantity: Quantity
    minimum_net_target: Money
    max_loss: Money
    max_target_distance: Price
    max_stop_distance: Price
    max_entry_deviation: UnitAmount
    maximum_spread: UnitAmount
    max_horizon_hours: int
    max_evidence_age_seconds: int
    max_evaluations: int
    allow_synthetic: bool
    stresses: tuple[StressCase, ...]

    def __post_init__(self):
        _typed(self)
        identifier(self.policy_id)
        require(self.revision >= 1 and 1 <= self.max_evaluations <= 10000, 'SEARCH_LIMIT_INVALID')
        require(1 <= self.max_horizon_hours <= 720, 'HORIZON_INVALID')
        require(1 <= self.max_evidence_age_seconds <= 86400, 'EVIDENCE_AGE_LIMIT_INVALID')
        require(1 <= len(self.stresses) <= 16, 'STRESS_DOMAIN_REQUIRED')
        require(len({s.stress_id for s in self.stresses}) == len(self.stresses), 'DUPLICATE_STRESS')
        _amounts(self.minimum_net_target, self.max_loss)
        object.__setattr__(self, 'effective_from', utc(self.effective_from))
        object.__setattr__(self, 'valid_until', utc(self.valid_until))
        require(self.effective_from < self.valid_until, 'POLICY_TIME_INVALID')


@dataclass(frozen=True, slots=True)
class EconomicContext(EconomicRecord):
    SCHEMA = 'trading.core_v3.economic.context'
    market: MarketSnapshot
    portfolio: PortfolioSnapshot
    costs: CostSchedule | None
    margin: MarginModel | None
    hypotheses: tuple[TechnicalHypothesis, ...]
    fx: FxConversion | None

    def __post_init__(self):
        _typed(self)
        require(len({h.hypothesis_id for h in self.hypotheses}) == len(self.hypotheses), 'DUPLICATE_HYPOTHESIS')


@dataclass(frozen=True, slots=True)
class Scenario(EconomicRecord):
    SCHEMA = 'trading.core_v3.economic.scenario'
    hypothesis_id: str
    direction: Direction
    quantity: Quantity
    entry: Price
    stop: Price
    target: Price
    horizon_hours: int
    context_sha256: str
    policy_sha256: str

    def __post_init__(self):
        _typed(self)
        identifier(self.hypothesis_id)
        _hash(self.context_sha256)
        _hash(self.policy_sha256)
        require(1 <= self.horizon_hours <= 720, 'HORIZON_INVALID')
        sign = 1 if self.direction is Direction.LONG else -1
        require((self.stop.amount < self.entry.amount < self.target.amount) if sign == 1 else
                (self.target.amount < self.entry.amount < self.stop.amount), 'GEOMETRY_INVALID')


@dataclass(frozen=True, slots=True)
class StressOutcome(EconomicRecord):
    SCHEMA = 'trading.core_v3.economic.stress_outcome'
    stress_id: str
    loss: Money
    maintenance_required: Money
    equity_after_loss: Money
    margin_capacity_after_loss: Money

    def __post_init__(self):
        _typed(self)
        identifier(self.stress_id)


@dataclass(frozen=True, slots=True)
class Evaluation(EconomicRecord):
    SCHEMA = 'trading.core_v3.economic.evaluation'
    reasons: tuple[str, ...]
    opening_commission: Money
    closing_commission: Money
    spread_cost: Money
    slippage_cost: Money
    financing_cost: Money
    round_trip_cost: Money
    net_target: Money
    stop_loss: Money
    worst_stress_loss: Money
    notional: Money
    required_margin: Money
    stress_outcomes: tuple[StressOutcome, ...]

    def __post_init__(self):
        _typed(self)


@dataclass(frozen=True, slots=True)
class ReasonCount(EconomicRecord):
    SCHEMA = 'trading.core_v3.economic.reason_count'
    reason: str
    count: int

    def __post_init__(self):
        _typed(self)
        require(re.fullmatch('[A-Z][A-Z0-9_]{0,79}', self.reason) is not None and self.count > 0, 'REASON_INVALID')


@dataclass(frozen=True, slots=True)
class EconomicResult(EconomicRecord):
    SCHEMA = 'trading.core_v3.economic.result'
    status: EconomicStatus
    as_of: datetime
    context_sha256: str | None
    policy_sha256: str | None
    domain_size: int
    evaluated: int
    search_limit: int
    search_complete: bool
    rejections: tuple[ReasonCount, ...]
    trace_sha256: str
    witness: Scenario | None
    evaluation: Evaluation | None
    stage: str = 'PREFLIGHT'
    engine_version: str = 'CORE_V3_2_V1'
    scope: str = 'ECONOMIC_RESEARCH_ONLY'
    execution_authority: bool = False
    paper_execution_eligible: bool = False
    live_enabled: bool = False
    statistically_validated: bool = False
    broker_executability_verified: bool = False
    trading_decision: str = 'NO_TRADE'

    def __post_init__(self):
        _typed(self)
        object.__setattr__(self, 'as_of', utc(self.as_of))
        for value in (self.context_sha256, self.policy_sha256):
            if value is not None:
                _hash(value)
        _hash(self.trace_sha256)
        require(0 <= self.evaluated <= self.search_limit <= 10000 and self.domain_size >= self.evaluated,
                'SEARCH_COUNTS_INVALID')
        require(self.stage in ('PREFLIGHT', 'POSTFLIGHT'), 'STAGE_INVALID')
        require(self.engine_version == 'CORE_V3_2_V1', 'ENGINE_VERSION_INVALID')
        require(self.scope == 'ECONOMIC_RESEARCH_ONLY' and self.trading_decision == 'NO_TRADE'
                and all(value is False for value in (self.execution_authority, self.paper_execution_eligible,
                    self.live_enabled, self.statistically_validated, self.broker_executability_verified)),
                'EXECUTION_AUTHORITY_FORBIDDEN')
        require((self.witness is not None and self.evaluation is not None and not self.evaluation.reasons)
                if self.status is EconomicStatus.FEASIBLE else self.witness is None, 'RESULT_WITNESS_INVALID')
