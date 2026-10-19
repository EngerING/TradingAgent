"""Closed statistical wire. Descriptive evidence never grants operational authority."""
from dataclasses import dataclass, fields
from datetime import datetime
from decimal import Decimal
from enum import Enum
import re

from ..contracts import Money, content_hash, decimal_text, identifier, require, utc
from ..economic_contracts import _hash
from ..event_backtest.contracts import (Record, BacktestPolicy, BacktestRequest, BacktestResult,
                                       SyntheticDataset)
from ..research_contracts import InstrumentIdentity
from ..strategy_catalog.contracts import CatalogRef
from ..strategy_v34.contracts import Timeframe

ENGINE_VERSION = 'CORE_V37_STATISTICAL_V1'


class Partition(str, Enum):
    TRAIN = 'TRAIN'
    VALIDATION = 'VALIDATION'
    TEST = 'TEST'


class Dependence(str, Enum):
    UNKNOWN = 'UNKNOWN'
    DEPENDENT_UNMODELLED = 'DEPENDENT_UNMODELLED'
    IID_WINDOW_BLOCKS_ASSUMED = 'IID_WINDOW_BLOCKS_ASSUMED'


class Status(str, Enum):
    COMPLETE = 'COMPLETE'
    INCONCLUSIVE = 'INCONCLUSIVE'
    REJECTED = 'REJECTED'


class StatisticalRecord(Record):
    __slots__ = ()

    def __post_init__(self):
        self.check_types()
        for field in fields(self):
            value, name = getattr(self, field.name), field.name
            if isinstance(value, Decimal):
                decimal_text(value)
            if type(value) is int:
                require(0 <= value < 2**63, 'STATISTICAL_COUNT_INVALID')
            if type(value) is str:
                require(len(value) <= 160, 'STATISTICAL_STRING_LIMIT')
                if name.endswith('_sha256'):
                    _hash(value)
                elif name.endswith('_id'):
                    identifier(value)
            if type(value) is datetime:
                object.__setattr__(self, name, utc(value))


@dataclass(frozen=True, slots=True)
class ChunkRef(StatisticalRecord):
    SCHEMA = 'trading.core_v3.statistics.chunk'
    dataset_id: str
    dataset_sha256: str
    bars: int
    opened_at: datetime
    closed_at: datetime

    def __post_init__(self):
        StatisticalRecord.__post_init__(self)
        require(1 <= self.bars <= 128 and self.opened_at < self.closed_at, 'MANIFEST_CHUNK_INVALID')


@dataclass(frozen=True, slots=True)
class DatasetManifest(StatisticalRecord):
    SCHEMA = 'trading.core_v3.statistics.dataset_manifest'
    dataset_id: str
    instrument: InstrumentIdentity
    timeframe: Timeframe
    chunks: tuple[ChunkRef, ...]
    total_bars: int
    source_kind: str = 'SYNTHETIC'

    def __post_init__(self):
        StatisticalRecord.__post_init__(self)
        require(self.source_kind == 'SYNTHETIC' and 1 <= len(self.chunks) <= 4
                and self.total_bars == sum(c.bars for c in self.chunks)
                and len({c.dataset_id for c in self.chunks}) == len(self.chunks), 'MANIFEST_INVALID')
        require(all(a.closed_at == b.opened_at for a, b in zip(self.chunks, self.chunks[1:])),
                'MANIFEST_NONCONTIGUOUS')


@dataclass(frozen=True, slots=True)
class TemporalSplit(StatisticalRecord):
    SCHEMA = 'trading.core_v3.statistics.temporal_split'
    window_id: str
    fold: int
    partition: Partition
    history_start: int
    evaluation_start: int
    evaluation_end: int
    reuse_test_declared: bool = False

    def __post_init__(self):
        StatisticalRecord.__post_init__(self)
        require(1 <= self.fold <= 4 and 0 <= self.history_start <= self.evaluation_start
                < self.evaluation_end <= 512, 'TEMPORAL_SPLIT_INVALID')


@dataclass(frozen=True, slots=True)
class CandidateRef(StatisticalRecord):
    SCHEMA = 'trading.core_v3.statistics.candidate'
    candidate_id: str
    catalog_ref: CatalogRef
    validation_operation_id: str
    research_cutoff: datetime


@dataclass(frozen=True, slots=True)
class RobustnessScenario(StatisticalRecord):
    SCHEMA = 'trading.core_v3.statistics.scenario'
    scenario_id: str
    extra_half_spread_ticks: int = 0
    extra_slippage_ticks: int = 0
    extra_opening_fee: Money | None = None
    extra_closing_fee: Money | None = None
    extra_financing_fixed: Money | None = None
    extra_financing_per_unit_hour: Money | None = None
    close_at_end: bool | None = None

    def __post_init__(self):
        StatisticalRecord.__post_init__(self)
        require(0 <= self.extra_half_spread_ticks <= 100 and 0 <= self.extra_slippage_ticks <= 100,
                'ROBUSTNESS_SCENARIO_LIMIT')
        extras = (self.extra_opening_fee, self.extra_closing_fee, self.extra_financing_fixed,
                  self.extra_financing_per_unit_hour)
        require(all(m is None or m.amount >= 0 for m in extras), 'ROBUSTNESS_NEGATIVE_COST')
        cost_change = self.extra_half_spread_ticks or self.extra_slippage_ticks or any(m is not None for m in extras)
        require(bool(cost_change) != (self.close_at_end is not None), 'ROBUSTNESS_SCENARIO_KIND')


@dataclass(frozen=True, slots=True)
class ExperimentPlan(StatisticalRecord):
    SCHEMA = 'trading.core_v3.statistics.experiment_plan'
    plan_id: str
    manifest: DatasetManifest
    candidates: tuple[CandidateRef, ...]
    splits: tuple[TemporalSplit, ...]
    scenarios: tuple[RobustnessScenario, ...] = ()

    def __post_init__(self):
        StatisticalRecord.__post_init__(self)
        require(1 <= len(self.candidates) <= 4 and 3 <= len(self.splits) <= 12
                and len(self.scenarios) <= 4, 'EXPERIMENT_LIMIT')
        for values, key in ((self.candidates, 'candidate_id'), (self.splits, 'window_id'),
                            (self.scenarios, 'scenario_id')):
            require(len({getattr(v, key) for v in values}) == len(values), 'EXPERIMENT_DUPLICATE_ID')
        require(len({content_hash(c.catalog_ref) for c in self.candidates}) == len(self.candidates),
                'DUPLICATE_CANDIDATE')


@dataclass(frozen=True, slots=True)
class ValidationPolicy(StatisticalRecord):
    SCHEMA = 'trading.core_v3.statistics.policy'
    policy_id: str
    backtest: BacktestPolicy
    min_trades: int = 20
    min_test_windows: int = 3
    embargo_bars: int = 1
    dependence: Dependence = Dependence.UNKNOWN
    bootstrap_replicas: int = 200
    confidence_bps: int = 9000
    seed: int = 7
    declared_family_size: int = 1
    parameter_variants: int = 1
    selected_after_analysis: bool = False
    require_inference: bool = True
    require_robustness: bool = True
    require_oos: bool = False
    max_datasets: int = 4
    max_windows: int = 12
    max_candidates: int = 4
    max_backtests: int = 64
    max_trades: int = 256
    max_scenarios: int = 4
    max_input_bytes: int = 524288
    max_observation_bytes: int = 131072
    max_result_bytes: int = 131072
    max_work_units: int = 32768
    capital_policy: str = 'RESET_ORIGINAL_SNAPSHOT_EACH_WINDOW'
    engine_version: str = ENGINE_VERSION

    def __post_init__(self):
        StatisticalRecord.__post_init__(self)
        caps = dict(max_datasets=4, max_windows=12, max_candidates=4, max_backtests=64, max_trades=256,
                    max_scenarios=4, max_input_bytes=524288, max_observation_bytes=131072,
                    max_result_bytes=131072, max_work_units=32768)
        require(all(1 <= getattr(self, k) <= v for k, v in caps.items()), 'STATISTICAL_RESOURCE_LIMIT')
        require(4096 <= self.max_result_bytes and 4096 <= self.max_observation_bytes
                and 1 <= self.min_trades <= 256 and 2 <= self.min_test_windows <= 12
                and 0 <= self.embargo_bars <= 512 and 32 <= self.bootstrap_replicas <= 512
                and 5000 <= self.confidence_bps <= 9900 and 0 <= self.seed < 2**63
                and 1 <= self.declared_family_size <= 256 and 1 <= self.parameter_variants <= 16,
                'STATISTICAL_POLICY_INVALID')
        require(self.capital_policy == 'RESET_ORIGINAL_SNAPSHOT_EACH_WINDOW'
                and self.engine_version == ENGINE_VERSION, 'STATISTICAL_MODEL_UNSUPPORTED')


@dataclass(frozen=True, slots=True)
class ValidationRequest(StatisticalRecord):
    SCHEMA = 'trading.core_v3.statistics.request'
    request_id: str
    plan_sha256: str
    policy_sha256: str
    exposure_count: int
    exposure_sha256: str
    source_pins: tuple[BacktestRequest, ...]

    def __post_init__(self):
        StatisticalRecord.__post_init__(self)
        require(0 <= self.exposure_count <= 128, 'EXPOSURE_LIMIT')
        require(1 <= len(self.source_pins) <= 4, 'STATISTICAL_SOURCE_PINS_REQUIRED')


@dataclass(frozen=True, slots=True)
class BacktestObservation(StatisticalRecord):
    SCHEMA = 'trading.core_v3.statistics.observation'
    observation_id: str
    candidate_id: str
    window_id: str
    partition: Partition
    scenario_id: str | None
    manifest_sha256: str
    evaluated_from: datetime
    evaluated_until: datetime
    warmup_bars: int
    dataset: SyntheticDataset
    policy: BacktestPolicy
    request: BacktestRequest
    result: BacktestResult
    result_sha256: str

    def __post_init__(self):
        StatisticalRecord.__post_init__(self)
        require(0 <= self.warmup_bars < len(self.dataset.bars)
                and self.dataset.bars[self.warmup_bars].opened_at == self.evaluated_from
                and self.dataset.bars[-1].closed_at == self.evaluated_until
                and self.evaluated_from < self.evaluated_until
                and self.request.dataset_sha256 == content_hash(self.dataset)
                and self.request.policy_sha256 == content_hash(self.policy)
                and self.result.request_sha256 == content_hash(self.request)
                and self.result_sha256 == content_hash(self.result), 'OBSERVATION_BINDING_INVALID')
        require(all(f.bar_index > self.warmup_bars for f in self.result.fills if f.role.value == 'ENTRY'),
                'WARMUP_TRADE_FORBIDDEN')


@dataclass(frozen=True, slots=True)
class ObservationRef(StatisticalRecord):
    SCHEMA = 'trading.core_v3.statistics.observation_ref'
    observation_id: str
    candidate_id: str
    window_id: str
    partition: Partition
    scenario_id: str | None
    observation_sha256: str
    result_sha256: str
    status: str
    trades: int | None


@dataclass(frozen=True, slots=True)
class StatisticalMetrics(StatisticalRecord):
    SCHEMA = 'trading.core_v3.statistics.metrics'
    trades: int
    winners: int
    losers: int
    breakeven: int
    gross: Money
    costs: Money
    net: Money
    average_win: Decimal | None
    average_loss: Decimal | None
    win_rate: Decimal | None
    profit_factor: Decimal | None
    expectancy: Decimal | None
    realized_reward_risk: Decimal | None
    sample_stddev: Decimal | None
    without_largest_absolute_trade: Decimal | None

    def __post_init__(self):
        StatisticalRecord.__post_init__(self)
        require(0 <= self.trades <= 256 and self.winners + self.losers + self.breakeven == self.trades
                and min(self.winners, self.losers, self.breakeven) >= 0
                and self.gross.currency == self.costs.currency == self.net.currency
                and self.gross.add(Money(self.costs.amount.copy_negate(), self.costs.currency)) == self.net,
                'STATISTICAL_AGGREGATE_INVALID')
        require(self.costs.amount >= 0 and (self.win_rate is None or 0 <= self.win_rate <= 1),
                'STATISTICAL_METRIC_INVALID')


@dataclass(frozen=True, slots=True)
class MetricGroup(StatisticalRecord):
    SCHEMA = 'trading.core_v3.statistics.metric_group'
    candidate_id: str
    partition: str
    metrics: StatisticalMetrics
    excluded_overlapping_trades: int
    coverage_complete: bool
    worst_window_realized_drawdown: Money
    worst_window_mark_drawdown: Money


@dataclass(frozen=True, slots=True)
class WindowMetrics(StatisticalRecord):
    SCHEMA = 'trading.core_v3.statistics.window_metrics'
    observation_id: str
    net: Money
    initial_capital: Money
    final_realized_capital: Money
    final_mark_capital: Money
    return_fraction: Decimal | None
    realized_drawdown: Money
    mark_drawdown: Money
    complete: bool


@dataclass(frozen=True, slots=True)
class UncertaintyEstimate(StatisticalRecord):
    SCHEMA = 'trading.core_v3.statistics.uncertainty'
    lower: Decimal | None
    upper: Decimal | None
    independent_units: int | None
    observed_windows: int
    dependence: Dependence
    replicas: int
    seed: int
    confidence_bps: int
    family_size: int
    reason: str
    estimand: str = 'MEAN_NET_PER_EQUAL_DURATION_TEST_WINDOW'

    def __post_init__(self):
        StatisticalRecord.__post_init__(self)
        require(0 <= self.observed_windows <= 12 and 32 <= self.replicas <= 512
                and 5000 <= self.confidence_bps <= 9900 and 1 <= self.family_size <= 256,
                'INTERVAL_POLICY_INVALID')
        require((self.lower is None) == (self.upper is None), 'INTERVAL_INVALID')
        require(self.lower is not None or self.independent_units is None, 'INDEPENDENT_UNITS_NOT_ESTABLISHED')
        if self.lower is not None:
            require(self.lower <= self.upper and self.dependence is Dependence.IID_WINDOW_BLOCKS_ASSUMED
                    and self.independent_units == self.observed_windows >= 2
                    and self.reason == 'CONDITIONAL_IID_BLOCK_PERCENTILE_INTERVAL', 'INTERVAL_INVALID')


@dataclass(frozen=True, slots=True)
class CandidateUncertainty(StatisticalRecord):
    SCHEMA = 'trading.core_v3.statistics.candidate_uncertainty'
    candidate_id: str
    currency: str
    estimate: UncertaintyEstimate


@dataclass(frozen=True, slots=True)
class RobustnessMetrics(StatisticalRecord):
    SCHEMA = 'trading.core_v3.statistics.robustness'
    observation_id: str
    scenario_id: str
    scenario_sha256: str
    method: str
    proof_sha256: str | None
    net: Money | None
    realized_drawdown: Money | None
    mark_drawdown: Money | None
    fragile: bool | None
    reason: str

    def __post_init__(self):
        StatisticalRecord.__post_init__(self)
        require(self.method in ('RERUN_V36', 'PROVEN_SINGLE_TRADE_EQUIVALENCE', 'NOT_ESTABLISHED'),
                'ROBUSTNESS_METHOD_INVALID')
        if self.proof_sha256 is not None:
            _hash(self.proof_sha256)
        require((self.net is None) == (self.method == 'NOT_ESTABLISHED'), 'ROBUSTNESS_PROOF_REQUIRED')


@dataclass(frozen=True, slots=True)
class ExposureRecord(StatisticalRecord):
    SCHEMA = 'trading.core_v3.statistics.exposure'
    plan_sha256: str
    instrument_sha256: str
    timeframe: Timeframe
    window_id: str
    partition: Partition
    read_from: datetime
    read_until: datetime
    reuse_declared: bool


@dataclass(frozen=True, slots=True)
class ValidationEvidence(StatisticalRecord):
    SCHEMA = 'trading.core_v3.statistics.evidence'
    request: ValidationRequest
    plan: ExperimentPlan
    policy: ValidationPolicy
    observations: tuple[ObservationRef, ...]
    exposures: tuple[ExposureRecord, ...]
    previous_test_reused: bool
    oos_status: str
    actual_backtests: int
    exploratory: bool = True
    exposure_scope: str = 'THIS_COORDINATOR_INSTANCE_ONLY'
    engine_version: str = ENGINE_VERSION

    def __post_init__(self):
        StatisticalRecord.__post_init__(self)
        require(self.request.plan_sha256 == content_hash(self.plan)
                and self.request.policy_sha256 == content_hash(self.policy)
                and self.oos_status in ('OOS_NOT_ESTABLISHED', 'RETROSPECTIVE_SPLIT_ONLY')
                and self.exploratory is True and self.exposure_scope == 'THIS_COORDINATOR_INSTANCE_ONLY'
                and self.engine_version == ENGINE_VERSION and self.actual_backtests == len(self.observations) <= 64,
                'VALIDATION_EVIDENCE_INVALID')


@dataclass(frozen=True, slots=True)
class ValidationResult(StatisticalRecord):
    SCHEMA = 'trading.core_v3.statistics.result'
    request_sha256: str
    status: Status
    reasons: tuple[str, ...]
    evidence: ValidationEvidence | None
    groups: tuple[MetricGroup, ...] = ()
    windows: tuple[WindowMetrics, ...] = ()
    uncertainty: tuple[CandidateUncertainty, ...] = ()
    robustness: tuple[RobustnessMetrics, ...] = ()
    scope: str = 'SYNTHETIC_EXPLORATORY_STATISTICAL_RESEARCH_ONLY'
    trading_decision: str = 'NO_TRADE'
    execution_authority: bool = False
    paper_execution_eligible: bool = False
    live_enabled: bool = False
    statistically_validated: bool = False

    def __post_init__(self):
        StatisticalRecord.__post_init__(self)
        require(self.status is not Status.COMPLETE or self.evidence is not None, 'VALIDATION_PROVENANCE_REQUIRED')
        require(1 <= len(self.reasons) <= 32 and all(re.fullmatch('[A-Z][A-Z0-9_]{0,79}', r)
                for r in self.reasons), 'STATISTICAL_REASON_INVALID')
        require(self.scope == 'SYNTHETIC_EXPLORATORY_STATISTICAL_RESEARCH_ONLY'
                and self.trading_decision == 'NO_TRADE'
                and all(v is False for v in (self.execution_authority, self.paper_execution_eligible,
                                            self.live_enabled, self.statistically_validated)),
                'STATISTICAL_AUTHORITY_FORBIDDEN')
        require(self.status is not Status.REJECTED or not (self.groups or self.windows or self.uncertainty
                                                          or self.robustness), 'REJECTED_METRICS_FORBIDDEN')


@dataclass(frozen=True, slots=True)
class ExperimentRun:
    """In-memory archive: each observation has a bounded independent wire document."""
    result: ValidationResult
    observations: tuple[BacktestObservation, ...]
    proofs: tuple[str, ...] = ()
