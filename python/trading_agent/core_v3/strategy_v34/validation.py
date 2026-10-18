"""Recompute economic evidence; input flags never stand for technical approval."""
from ..contracts import content_hash, require, utc
from ..economic_contracts import EconomicStatus
from ..economics import postflight, preflight
from ..research_contracts import InstrumentIdentity, ResearchRequest
from .contracts import Strategy, Timeframe


def economic_basis(request: ResearchRequest, *, now):
    require(type(request) is ResearchRequest, 'RESEARCH_REQUEST_REQUIRED')
    now = utc(now)
    require(request.instrument == InstrumentIdentity.of(request.inputs.context.market.instrument),
            'STRATEGY_INSTRUMENT_MISMATCH')
    before = preflight(request.inputs.context, request.inputs.policy, now=now)
    require(before.status is EconomicStatus.FEASIBLE and before.witness is not None,
            'FEASIBLE_ECONOMIC_BASIS_REQUIRED')
    return before


def validate(strategy: Strategy, request: ResearchRequest, timeframe: Timeframe, *, now):
    """Return a recalculated V3.2 postflight, never a promotion or execution permit."""
    require(type(strategy) is Strategy and type(request) is ResearchRequest
            and type(timeframe) is Timeframe, 'STRATEGY_TYPES_REQUIRED')
    require(strategy.request_sha256 == content_hash(request), 'STRATEGY_REQUEST_MISMATCH')
    require(strategy.instrument == request.instrument, 'STRATEGY_INSTRUMENT_MISMATCH')
    require(strategy.timeframe is timeframe, 'STRATEGY_TIMEFRAME_MISMATCH')
    before = economic_basis(request, now=now)
    require(strategy.scenario == before.witness, 'STRATEGY_GEOMETRY_MISMATCH')
    instrument = request.inputs.context.market.instrument
    for price in (strategy.scenario.entry, strategy.scenario.stop, strategy.scenario.target):
        instrument.check_terms(strategy.scenario.quantity, price)
    after = postflight(request.inputs.context, request.inputs.policy, strategy.scenario, before, now=now)
    require(after.status is EconomicStatus.FEASIBLE, 'STRATEGY_POSTFLIGHT_REJECTED')
    return after
