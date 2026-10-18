"""Closed immutable V3.4 vocabulary. There are no source-code operands."""
from dataclasses import dataclass
from enum import Enum

from ..contracts import content_hash, identifier, require
from ..economic_contracts import EconomicRecord, Scenario, _hash, _typed
from ..research_contracts import InstrumentIdentity


class Timeframe(str, Enum):
    M1 = 'M1'
    M5 = 'M5'
    H1 = 'H1'

    @property
    def seconds(self):
        return {Timeframe.M1: 60, Timeframe.M5: 300, Timeframe.H1: 3600}[self]


class Indicator(str, Enum):
    CLOSE = 'CLOSE'
    SMA = 'SMA'


class Operator(str, Enum):
    GT = 'GT'
    LT = 'LT'
    CROSS_ABOVE = 'CROSS_ABOVE'
    CROSS_BELOW = 'CROSS_BELOW'


@dataclass(frozen=True, slots=True)
class Operand(EconomicRecord):
    SCHEMA = 'trading.core_v3.strategy_v34.operand'
    indicator: Indicator
    period: int
    lag: int

    def __post_init__(self):
        _typed(self)
        require((self.period == 1 if self.indicator is Indicator.CLOSE else 2 <= self.period <= 200)
                and 0 <= self.lag <= 32, 'INDICATOR_PARAMETERS_INVALID')


@dataclass(frozen=True, slots=True)
class Rule(EconomicRecord):
    SCHEMA = 'trading.core_v3.strategy_v34.rule'
    left: Operand
    operator: Operator
    right: Operand

    def __post_init__(self):
        _typed(self)
        require(self.left != self.right, 'IDENTICAL_OPERANDS')

    @property
    def required_bars(self):
        previous = int(self.operator in (Operator.CROSS_ABOVE, Operator.CROSS_BELOW))
        return max(v.period + v.lag for v in (self.left, self.right)) + previous


@dataclass(frozen=True, slots=True)
class Strategy(EconomicRecord):
    SCHEMA = 'trading.core_v3.strategy_v34.strategy'
    strategy_id: str
    request_sha256: str
    instrument: InstrumentIdentity
    timeframe: Timeframe
    scenario: Scenario
    entry_rules: tuple[Rule, ...]
    exit_rules: tuple[Rule, ...]
    max_holding_bars: int
    scope: str = 'DECLARATIVE_SYNTHETIC_RESEARCH_ONLY'
    trading_decision: str = 'NO_TRADE'
    execution_authority: bool = False
    paper_execution_eligible: bool = False
    live_enabled: bool = False
    statistically_validated: bool = False

    def __post_init__(self):
        _typed(self)
        identifier(self.strategy_id)
        _hash(self.request_sha256)
        for rules in (self.entry_rules, self.exit_rules):
            require(1 <= len(rules) <= 8 and len({content_hash(r) for r in rules}) == len(rules),
                    'RULE_COLLECTION_INVALID')
        require(1 <= self.max_holding_bars <= 43200
                and self.max_holding_bars * self.timeframe.seconds == self.scenario.horizon_hours * 3600,
                'STRATEGY_HORIZON_MISMATCH')
        require(self.scope == 'DECLARATIVE_SYNTHETIC_RESEARCH_ONLY' and self.trading_decision == 'NO_TRADE'
                and all(v is False for v in (self.execution_authority, self.paper_execution_eligible,
                                            self.live_enabled, self.statistically_validated)),
                'STRATEGY_AUTHORITY_FORBIDDEN')
