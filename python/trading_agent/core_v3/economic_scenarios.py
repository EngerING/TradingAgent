"""Finite technical domain. Never moves a target in response to economics."""
from dataclasses import dataclass
from decimal import Context, ROUND_FLOOR, localcontext
from typing import Iterator

from .contracts import ContractError, Price, Quantity
from .economic_contracts import Direction, EconomicContext, ResearchPolicy, Scenario


@dataclass(frozen=True, slots=True)
class Geometry:
    hypothesis_id: str
    direction: Direction
    entry: Price
    stop: Price
    target: Price
    horizon_hours: int


@dataclass(frozen=True, slots=True)
class SearchDomain:
    quantity_points: int
    geometries: tuple[Geometry, ...]
    geometry_rejections: tuple[str, ...]

    @property
    def size(self):
        unresolved_geometries = self.geometry_rejections.count('NUMERIC_RANGE_UNRESOLVED')
        return self.quantity_points * (len(self.geometries) + unresolved_geometries)


@dataclass(frozen=True, slots=True)
class ScenarioTrial:
    hypothesis_id: str
    quantity_index: int
    scenario: Scenario | None
    reason: str | None


def prepare_domain(context: EconomicContext, policy: ResearchPolicy) -> SearchDomain:
    instrument = context.market.instrument
    minimum, step = instrument.minimum_quantity.amount, instrument.quantity_step.amount
    geometries, rejected = [], []
    with localcontext(Context(prec=160)):
        points = (int(((policy.max_quantity.amount - minimum) / step).to_integral_value(rounding=ROUND_FLOOR)) + 1
                  if policy.max_quantity.amount >= minimum else 0)
        midpoint = (context.market.bid.amount + context.market.ask.amount) / 2
        for hypothesis in context.hypotheses:
            reasons = []
            if hypothesis.target_distance.amount > min(hypothesis.plausible_move.amount, policy.max_target_distance.amount):
                reasons.append('TARGET_OUTSIDE_TECHNICAL_DOMAIN')
            if hypothesis.stop_distance.amount > policy.max_stop_distance.amount:
                reasons.append('STOP_OUTSIDE_TECHNICAL_DOMAIN')
            if hypothesis.horizon_hours > policy.max_horizon_hours:
                reasons.append('HORIZON_OUTSIDE_TECHNICAL_DOMAIN')
            if abs(hypothesis.entry.amount - midpoint) > policy.max_entry_deviation.money.amount:
                reasons.append('ENTRY_OUTSIDE_TECHNICAL_DOMAIN')
            sign = 1 if hypothesis.direction is Direction.LONG else -1
            stop = hypothesis.entry.amount - sign * hypothesis.stop_distance.amount
            target = hypothesis.entry.amount + sign * hypothesis.target_distance.amount
            if min(stop, target) <= 0:
                reasons.append('NONPOSITIVE_EXIT_PRICE')
            if reasons:
                rejected.extend(reasons)
                continue
            try:
                prices = tuple(Price(v, instrument.quote_currency, instrument.quantity_unit)
                               for v in (hypothesis.entry.amount, stop, target))
                for price in prices:
                    instrument.check_terms(instrument.minimum_quantity, price)
            except ContractError as exc:
                rejected.append('NUMERIC_RANGE_UNRESOLVED' if str(exc) == 'DECIMAL_LIMIT' else 'GEOMETRY_OFF_GRID')
                continue
            geometries.append(Geometry(hypothesis.hypothesis_id, hypothesis.direction, *prices, hypothesis.horizon_hours))
    return SearchDomain(points, tuple(geometries), tuple(rejected))


def scenarios(domain: SearchDomain, context: EconomicContext, policy: ResearchPolicy,
              context_hash: str, policy_hash: str) -> Iterator[ScenarioTrial]:
    """At most max_evaluations objects, even for an enormous declared quantity grid."""
    instrument = context.market.instrument
    emitted = 0
    for geometry in domain.geometries:
        for index in range(min(domain.quantity_points, policy.max_evaluations - emitted)):
            with localcontext(Context(prec=160)):
                amount = instrument.minimum_quantity.amount + index * instrument.quantity_step.amount
                try:
                    scenario = Scenario(geometry.hypothesis_id, geometry.direction, Quantity(amount, instrument.quantity_unit),
                        geometry.entry, geometry.stop, geometry.target, geometry.horizon_hours, context_hash, policy_hash)
                except ContractError:
                    trial = ScenarioTrial(geometry.hypothesis_id, index, None, 'NUMERIC_RANGE_UNRESOLVED')
                else:
                    trial = ScenarioTrial(geometry.hypothesis_id, index, scenario, None)
            emitted += 1
            yield trial
        if emitted >= policy.max_evaluations:
            break
