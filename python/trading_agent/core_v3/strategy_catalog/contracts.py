"""V3.5 closed catalog contracts and bounded behavioral fingerprints."""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import re

from ..contracts import content_hash, identifier, require, utc
from ..economic_contracts import EconomicRecord, EconomicResult, EconomicStatus, _hash, _typed
from ..research_contracts import BudgetPolicy, ResearchInputs, ResearchRequest, ResearchResult, ResearchState
from ..strategy_v34.contracts import Operator, Strategy, Timeframe


class Action(str, Enum):
    REGISTER = 'REGISTER'
    REVALIDATE = 'REVALIDATE'


class State(str, Enum):
    REQUESTED = 'REQUESTED'
    PREPARED = 'PREPARED'
    RECORDED = 'RECORDED'
    VALIDATED = 'VALIDATED'
    REJECTED = 'REJECTED'
    DUPLICATE = 'DUPLICATE'
    INVALIDATED = 'INVALIDATED'
    RECOVERY_REQUIRED = 'RECOVERY_REQUIRED'


TERMINAL = frozenset((State.VALIDATED, State.REJECTED, State.DUPLICATE, State.INVALIDATED))


def semantic_hash(strategy: Strategy) -> str:
    require(type(strategy) is Strategy, 'STRATEGY_REQUIRED')
    def rules(values):
        normalized = {}
        for rule in values:
            left, right, operator = rule.left, rule.right, rule.operator
            if operator in (Operator.LT, Operator.CROSS_BELOW):
                left, right = right, left
                operator = Operator.GT if operator is Operator.LT else Operator.CROSS_ABOVE
            value = dict(left=left, operator=operator, right=right)
            normalized[content_hash(value)] = value
        return [normalized[key] for key in sorted(normalized)]
    scenario = strategy.scenario
    return content_hash(dict(namespace='CORE_V35_SEMANTIC_V1', instrument=strategy.instrument,
        timeframe=strategy.timeframe, direction=scenario.direction, quantity=scenario.quantity,
        entry=scenario.entry, stop=scenario.stop, target=scenario.target, horizon_hours=scenario.horizon_hours,
        max_holding_bars=strategy.max_holding_bars, entry_rules=rules(strategy.entry_rules), exit_rules=rules(strategy.exit_rules)))


@dataclass(frozen=True, slots=True)
class CatalogRequest(EconomicRecord):
    SCHEMA = 'trading.core_v3.catalog.request'
    operation_id: str
    idempotency_key: str
    action: Action
    catalog_id: str
    version: int
    parent_sha256: str | None
    source_id: str
    research_request_id: str
    timeframe: Timeframe
    strategy: Strategy

    def __post_init__(self):
        _typed(self)
        for value in (self.operation_id, self.idempotency_key, self.catalog_id, self.source_id, self.research_request_id):
            identifier(value)
        require(1 <= self.version <= 1024, 'CATALOG_VERSION_INVALID')
        require((self.parent_sha256 is None) == (self.version == 1), 'CATALOG_PARENT_REQUIRED')
        if self.parent_sha256 is not None:
            _hash(self.parent_sha256)


@dataclass(frozen=True, slots=True)
class SourceProof(EconomicRecord):
    SCHEMA = 'trading.core_v3.catalog.source_proof'
    source_id: str
    request: ResearchRequest
    result: ResearchResult
    budget: BudgetPolicy
    received_sequence: int
    received_sha256: str
    terminal_sequence: int
    terminal_sha256: str
    prefix_sequence: int
    prefix_sha256: str

    def __post_init__(self):
        _typed(self)
        identifier(self.source_id)
        for value in (self.received_sha256, self.terminal_sha256, self.prefix_sha256):
            _hash(value)
        require(1 < self.received_sequence < self.terminal_sequence <= self.prefix_sequence <= 2049,
                'SOURCE_SEQUENCE_INVALID')
        require(self.result.state is ResearchState.CANDIDATE_RECORDED
                and self.result.request_id == self.request.request_id
                and self.result.request_sha256 == content_hash(self.request)
                and self.result.budget_policy_sha256 == content_hash(self.budget)
                and self.result.instrument == self.request.instrument
                and self.result.charge.consumed_requests == 1 and self.result.charge.reserved_requests == 0,
                'SETTLED_RESEARCH_REQUIRED')


@dataclass(frozen=True, slots=True)
class CatalogCheck(EconomicRecord):
    SCHEMA = 'trading.core_v3.catalog.check'
    inputs: ResearchInputs
    at: datetime
    valid: bool
    reason: str
    postflight: EconomicResult | None

    def __post_init__(self):
        _typed(self)
        object.__setattr__(self, 'at', utc(self.at))
        require(re.fullmatch('[A-Z][A-Z0-9_]{0,79}', self.reason) is not None, 'REASON_INVALID')
        require((self.postflight is not None and self.postflight.stage == 'POSTFLIGHT'
                 and self.postflight.status is EconomicStatus.FEASIBLE) if self.valid else self.postflight is None,
                'CATALOG_CHECK_INVALID')


@dataclass(frozen=True, slots=True)
class CatalogVersion(EconomicRecord):
    SCHEMA = 'trading.core_v3.catalog.version'
    registration: CatalogRequest
    source: SourceProof
    semantic_sha256: str
    recorded_at: datetime

    def __post_init__(self):
        _typed(self)
        require(self.registration.action is Action.REGISTER, 'REGISTRATION_REQUIRED')
        require(self.registration.source_id == self.source.source_id
                and self.registration.research_request_id == self.source.request.request_id
                and self.registration.strategy.request_sha256 == content_hash(self.source.request), 'SOURCE_BINDING_MISMATCH')
        require(self.semantic_sha256 == semantic_hash(self.registration.strategy), 'SEMANTIC_HASH_MISMATCH')
        object.__setattr__(self, 'recorded_at', utc(self.recorded_at))

    @property
    def record_sha256(self):
        return content_hash(self)


@dataclass(frozen=True, slots=True)
class CatalogRef(EconomicRecord):
    SCHEMA = 'trading.core_v3.catalog.reference'
    catalog_id: str
    version: int
    record_sha256: str

    def __post_init__(self):
        _typed(self)
        identifier(self.catalog_id)
        require(1 <= self.version <= 1024, 'CATALOG_VERSION_INVALID')
        _hash(self.record_sha256)

    @classmethod
    def of(cls, version):
        require(type(version) is CatalogVersion, 'CATALOG_VERSION_REQUIRED')
        return cls(version.registration.catalog_id, version.registration.version, version.record_sha256)


@dataclass(frozen=True, slots=True)
class CatalogOutcome(EconomicRecord):
    SCHEMA = 'trading.core_v3.catalog.outcome'
    operation_id: str
    command_sha256: str
    state: State
    reason: str
    at: datetime
    target: CatalogRef | None
    check: CatalogCheck | None
    scope: str = 'DURABLE_DECLARATIVE_RESEARCH_ONLY'
    trading_decision: str = 'NO_TRADE'
    execution_authority: bool = False
    paper_execution_eligible: bool = False
    live_enabled: bool = False
    statistically_validated: bool = False

    def __post_init__(self):
        _typed(self)
        identifier(self.operation_id)
        _hash(self.command_sha256)
        require(re.fullmatch('[A-Z][A-Z0-9_]{0,79}', self.reason) is not None, 'REASON_INVALID')
        object.__setattr__(self, 'at', utc(self.at))
        require(self.scope == 'DURABLE_DECLARATIVE_RESEARCH_ONLY' and self.trading_decision == 'NO_TRADE'
                and all(v is False for v in (self.execution_authority, self.paper_execution_eligible,
                                            self.live_enabled, self.statistically_validated)), 'CATALOG_AUTHORITY_FORBIDDEN')
        if self.state is State.VALIDATED:
            require(self.target is not None and self.check is not None and self.check.valid, 'CATALOG_VALIDATION_REQUIRED')
