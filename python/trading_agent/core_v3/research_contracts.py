"""Immutable V3.3 research contracts. Research resources are never trading capital."""
from dataclasses import dataclass, fields
from datetime import datetime
from decimal import Context, Decimal, localcontext
from enum import Enum
import re
from types import UnionType
from typing import get_args, get_origin

from .contracts import Instrument, Money, content_hash, identifier, require, utc
from .economic_contracts import EconomicContext, EconomicRecord, EconomicResult, ResearchPolicy, Scenario


def _types(record):
    for field in fields(record):
        value, kind = getattr(record, field.name), field.type
        if get_origin(kind) is UnionType:
            require(value is None or type(value) is next(t for t in get_args(kind) if t is not type(None)),
                    'RESEARCH_TYPE_INVALID')
        else:
            require(type(value) is kind, 'RESEARCH_TYPE_INVALID')


def _hash(value):
    require(type(value) is str and re.fullmatch('[a-f0-9]{64}', value) is not None, 'HASH_INVALID')


def _funds(value):
    require(value.currency == 'USD' and value.amount >= 0, 'RESEARCH_FUNDS_INVALID')


class ResearchState(str, Enum):
    RECEIVED = 'RECEIVED'
    VALIDATION_REJECTED = 'VALIDATION_REJECTED'
    ECONOMIC_BLOCKED = 'ECONOMIC_BLOCKED'
    BUDGET_BLOCKED = 'BUDGET_BLOCKED'
    BUDGET_RESERVED = 'BUDGET_RESERVED'
    DESIGNING = 'DESIGNING'
    DESIGN_RECEIVED = 'DESIGN_RECEIVED'
    POSTFLIGHT_PENDING = 'POSTFLIGHT_PENDING'
    CANDIDATE_RECORDED = 'CANDIDATE_RECORDED'
    FAILED = 'FAILED'
    INTERRUPTED = 'INTERRUPTED'


TERMINAL = frozenset((ResearchState.VALIDATION_REJECTED, ResearchState.ECONOMIC_BLOCKED,
    ResearchState.BUDGET_BLOCKED, ResearchState.CANDIDATE_RECORDED, ResearchState.FAILED, ResearchState.INTERRUPTED))


@dataclass(frozen=True, slots=True)
class InstrumentIdentity(EconomicRecord):
    SCHEMA = 'trading.core_v3.research.instrument_identity'
    instrument_id: str
    specification_version: int
    content_sha256: str

    def __post_init__(self):
        _types(self)
        identifier(self.instrument_id)
        require(1 <= self.specification_version <= 2147483647, 'SPECIFICATION_VERSION_INVALID')
        _hash(self.content_sha256)

    @classmethod
    def of(cls, instrument: Instrument):
        require(type(instrument) is Instrument, 'INSTRUMENT_REQUIRED')
        return cls(instrument.instrument_id, instrument.specification_version, content_hash(instrument))


@dataclass(frozen=True, slots=True)
class ResearchInputs(EconomicRecord):
    SCHEMA = 'trading.core_v3.research.inputs'
    context: EconomicContext
    policy: ResearchPolicy

    def __post_init__(self):
        _types(self)


@dataclass(frozen=True, slots=True)
class ResearchAllowance(EconomicRecord):
    SCHEMA = 'trading.core_v3.research.allowance'
    max_input_tokens: int
    max_output_tokens: int
    max_cost: Money

    def __post_init__(self):
        _types(self)
        require(0 <= self.max_input_tokens <= 1000000 and 0 <= self.max_output_tokens <= 1000000,
                'RESEARCH_TOKEN_LIMIT_INVALID')
        _funds(self.max_cost)

    @property
    def tokens(self):
        return self.max_input_tokens + self.max_output_tokens


@dataclass(frozen=True, slots=True)
class BudgetPolicy(EconomicRecord):
    SCHEMA = 'trading.core_v3.research.budget_policy'
    budget_id: str
    revision: int
    max_requests: int
    max_tokens: int
    max_cost: Money

    def __post_init__(self):
        _types(self)
        identifier(self.budget_id)
        require(self.revision >= 1 and 0 <= self.max_requests <= 256
                and 0 <= self.max_tokens <= 1000000000, 'RESEARCH_BUDGET_INVALID')
        _funds(self.max_cost)


@dataclass(frozen=True, slots=True)
class ResearchRequest(EconomicRecord):
    SCHEMA = 'trading.core_v3.research.request'
    request_id: str
    idempotency_key: str
    instrument: InstrumentIdentity
    inputs: ResearchInputs
    allowance: ResearchAllowance

    def __post_init__(self):
        _types(self)
        identifier(self.request_id)
        identifier(self.idempotency_key)


@dataclass(frozen=True, slots=True)
class DesignRequest(EconomicRecord):
    SCHEMA = 'trading.core_v3.research.design_request'
    request: ResearchRequest
    preflight: EconomicResult

    def __post_init__(self):
        _types(self)
        require(self.preflight.stage == 'PREFLIGHT' and self.preflight.witness is not None,
                'FEASIBLE_PREFLIGHT_REQUIRED')


@dataclass(frozen=True, slots=True)
class ResearchProposal(EconomicRecord):
    SCHEMA = 'trading.core_v3.research.proposal'
    candidate_id: str
    request_sha256: str
    instrument_sha256: str
    scenario: Scenario
    designer_version: str = 'SIMULATED_V1'
    scope: str = 'FIXED_SCENARIO_HYPOTHESIS'
    execution_authority: bool = False

    def __post_init__(self):
        _types(self)
        identifier(self.candidate_id)
        _hash(self.request_sha256)
        _hash(self.instrument_sha256)
        require(self.designer_version == 'SIMULATED_V1' and self.scope == 'FIXED_SCENARIO_HYPOTHESIS'
                and self.execution_authority is False, 'RESEARCH_PROPOSAL_AUTHORITY_FORBIDDEN')


@dataclass(frozen=True, slots=True)
class DesignReceipt(EconomicRecord):
    SCHEMA = 'trading.core_v3.research.design_receipt'
    output_sha256: str
    proposal: ResearchProposal | None
    # A response from the fixed simulated adapter always has known zero API usage.
    input_tokens: int = 0
    output_tokens: int = 0
    api_cost: Money = Money(Decimal('0'), 'USD')

    def __post_init__(self):
        _types(self)
        _hash(self.output_sha256)
        _funds(self.api_cost)
        require(self.input_tokens == self.output_tokens == 0 and self.api_cost.amount == 0,
                'SIMULATED_USAGE_REQUIRED')


@dataclass(frozen=True, slots=True)
class ResearchCharge(EconomicRecord):
    SCHEMA = 'trading.core_v3.research.charge'
    reserved_requests: int
    consumed_requests: int
    reserved_tokens: int
    reserved_cost: Money

    def __post_init__(self):
        _types(self)
        require(self.reserved_requests in (0, 1) and self.consumed_requests in (0, 1)
                and self.reserved_requests + self.consumed_requests <= 1
                and 0 <= self.reserved_tokens <= 2000000, 'RESEARCH_CHARGE_INVALID')
        _funds(self.reserved_cost)
        require(self.reserved_requests == 1 or (self.reserved_tokens == 0 and self.reserved_cost.amount == 0),
                'RESEARCH_CHARGE_INVALID')


@dataclass(frozen=True, slots=True)
class BudgetStatus(EconomicRecord):
    SCHEMA = 'trading.core_v3.research.budget_status'
    policy: BudgetPolicy
    reserved_requests: int
    consumed_requests: int
    remaining_requests: int
    reserved_tokens: int
    consumed_tokens: int
    remaining_tokens: int
    reserved_cost: Money
    consumed_cost: Money
    remaining_cost: Money

    def __post_init__(self):
        _types(self)
        for value in (self.reserved_requests, self.consumed_requests, self.remaining_requests,
                      self.reserved_tokens, self.consumed_tokens, self.remaining_tokens):
            require(value >= 0, 'RESEARCH_BUDGET_INVALID')
        for value in (self.reserved_cost, self.consumed_cost, self.remaining_cost):
            _funds(value)
        with localcontext(Context(prec=160)):
            require(self.reserved_requests + self.consumed_requests + self.remaining_requests == self.policy.max_requests
                    and self.reserved_tokens + self.consumed_tokens + self.remaining_tokens == self.policy.max_tokens
                    and self.reserved_cost.amount + self.consumed_cost.amount + self.remaining_cost.amount
                        == self.policy.max_cost.amount, 'RESEARCH_BALANCE_INCONSISTENT')


@dataclass(frozen=True, slots=True)
class ResearchReferences(EconomicRecord):
    SCHEMA = 'trading.core_v3.research.references'
    context_sha256: str
    policy_sha256: str
    preflight_sha256: str | None
    proposal_sha256: str | None
    postflight_sha256: str | None

    def __post_init__(self):
        _types(self)
        for value in (self.context_sha256, self.policy_sha256, self.preflight_sha256,
                      self.proposal_sha256, self.postflight_sha256):
            if value is not None:
                _hash(value)


@dataclass(frozen=True, slots=True)
class ResearchResult(EconomicRecord):
    SCHEMA = 'trading.core_v3.research.result'
    request_id: str
    request_sha256: str
    budget_policy_sha256: str
    operation_id: str
    instrument: InstrumentIdentity
    references: ResearchReferences
    state: ResearchState
    reason: str
    at: datetime
    charge: ResearchCharge
    preflight: EconomicResult | None
    receipt: DesignReceipt | None
    postflight: EconomicResult | None
    scope: str = 'SIMULATED_RESEARCH_ONLY'
    trading_decision: str = 'NO_TRADE'
    execution_authority: bool = False
    paper_execution_eligible: bool = False
    live_enabled: bool = False
    statistically_validated: bool = False

    def __post_init__(self):
        _types(self)
        identifier(self.request_id)
        _hash(self.request_sha256)
        _hash(self.budget_policy_sha256)
        operation_hash = content_hash(dict(engine='CORE_V3_3_V1', request=self.request_sha256,
                                          budget=self.budget_policy_sha256))
        require(self.operation_id == 'op-' + operation_hash, 'OPERATION_ID_INVALID')
        require(re.fullmatch('[A-Z][A-Z0-9_]{0,79}', self.reason) is not None, 'REASON_INVALID')
        object.__setattr__(self, 'at', utc(self.at))
        proposal = self.receipt.proposal if self.receipt is not None else None
        for value, digest in ((self.preflight, self.references.preflight_sha256),
                              (proposal, self.references.proposal_sha256),
                              (self.postflight, self.references.postflight_sha256)):
            require(digest == (content_hash(value) if value is not None else None), 'RESEARCH_REFERENCE_MISMATCH')
        if self.preflight is not None:
            require(self.preflight.context_sha256 == self.references.context_sha256
                    and self.preflight.policy_sha256 == self.references.policy_sha256, 'RESEARCH_REFERENCE_MISMATCH')
        require(self.scope == 'SIMULATED_RESEARCH_ONLY' and self.trading_decision == 'NO_TRADE'
                and all(v is False for v in (self.execution_authority, self.paper_execution_eligible,
                                            self.live_enabled, self.statistically_validated)),
                'RESEARCH_AUTHORITY_FORBIDDEN')
        if self.state is ResearchState.CANDIDATE_RECORDED:
            require(self.preflight is not None and self.preflight.stage == 'PREFLIGHT'
                    and self.receipt is not None and self.receipt.proposal is not None
                    and self.postflight is not None and self.postflight.stage == 'POSTFLIGHT'
                    and self.postflight.witness is not None
                    and self.preflight.witness == self.receipt.proposal.scenario == self.postflight.witness
                    and self.receipt.proposal.request_sha256 == self.request_sha256
                    and self.receipt.proposal.instrument_sha256 == self.instrument.content_sha256,
                    'POSTFLIGHT_REQUIRED')
