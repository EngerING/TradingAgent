"""Fixed simulated declarative output with zero provider use and no plugins."""
from dataclasses import dataclass

from ..contracts import content_hash, require
from ..economic_contracts import Direction
from .contracts import Indicator, Operand, Operator, Rule, Strategy, Timeframe
from .validation import economic_basis, validate


def _expected(request, timeframe, *, now):
    require(type(timeframe) is Timeframe, 'TIMEFRAME_REQUIRED')
    before = economic_basis(request, now=now)
    above = before.witness.direction is Direction.LONG
    left, right = Operand(Indicator.CLOSE, 1, 0), Operand(Indicator.SMA, 3, 0)
    entry = Rule(left, Operator.CROSS_ABOVE if above else Operator.CROSS_BELOW, right)
    exit_rule = Rule(left, Operator.CROSS_BELOW if above else Operator.CROSS_ABOVE, right)
    fingerprint = content_hash(dict(request=request, timeframe=timeframe, designer='SIMULATED_V34_V1'))
    return Strategy('strategy-' + fingerprint[:32], content_hash(request), request.instrument, timeframe,
                    before.witness, (entry,), (exit_rule,), before.witness.horizon_hours * 3600 // timeframe.seconds)


@dataclass(frozen=True, slots=True)
class SimulatedStrategyDesigner:
    proposal_json: str | None = None

    def __post_init__(self):
        require(self.proposal_json is None or (type(self.proposal_json) is str
                and len(self.proposal_json.encode('utf-8', errors='surrogatepass')) <= 32768),
                'SIMULATED_OUTPUT_LIMIT')

    def propose(self, request, timeframe, *, now):
        return self.proposal_json if self.proposal_json is not None else _expected(request, timeframe, now=now).to_json()


def design(request, timeframe, designer: SimulatedStrategyDesigner, *, now):
    require(type(designer) is SimulatedStrategyDesigner, 'OFFLINE_DESIGNER_REQUIRED')
    expected = _expected(request, timeframe, now=now)
    value = Strategy.from_json(designer.propose(request, timeframe, now=now))
    require(value == expected, 'SIMULATED_OUTPUT_MISMATCH')
    validate(value, request, timeframe, now=now)
    return value
