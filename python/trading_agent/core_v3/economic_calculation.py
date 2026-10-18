"""One-scenario Decimal arithmetic. Validated inputs only; no gate or side effects."""
from decimal import Context, Decimal, Inexact, localcontext

from .contracts import Money
from .economic_contracts import Direction, EconomicContext, Evaluation, ResearchPolicy, Scenario, StressOutcome


def calculate(context: EconomicContext, policy: ResearchPolicy, scenario: Scenario) -> Evaluation:
    with localcontext(Context(prec=160)) as arithmetic:
        # Bounded finite decimal inputs fit exactly; never accept a rounded decision.
        arithmetic.traps[Inexact] = True
        market, portfolio, costs, margin = context.market, context.portfolio, context.costs, context.margin
        instrument = market.instrument
        q, multiplier = scenario.quantity.amount, instrument.multiplier
        fx = Decimal(1) if instrument.quote_currency == portfolio.account_currency else context.fx.rate
        money = lambda value: Money(value * fx, portfolio.account_currency)
        opening = max(costs.opening_minimum.amount, q * costs.opening_per_unit.money.amount)
        closing = max(costs.closing_minimum.amount, q * costs.closing_per_unit.money.amount)
        spread = q * multiplier * (market.ask.amount - market.bid.amount)
        slippage = 2 * q * multiplier * costs.slippage_per_side.money.amount
        financing = costs.financing_fixed.amount + q * costs.financing_per_unit_per_hour.money.amount * scenario.horizon_hours
        total = opening + closing + spread + slippage + financing
        notional = q * multiplier * scenario.entry.amount
        stop_distance = abs(scenario.entry.amount - scenario.stop.amount)
        gross_target = q * multiplier * abs(scenario.target.amount - scenario.entry.amount)
        stop_loss = q * multiplier * stop_distance + total
        required_margin = notional * margin.initial_fraction + total
        available = min(portfolio.equity.amount, portfolio.allocation_available.amount)
        risk_limit = min(portfolio.remaining_risk.amount, policy.max_loss.amount)
        reasons, outcomes = [], []
        net = money(gross_target - total)
        if net.amount <= 0:
            reasons.append('NONPOSITIVE_NET_TARGET')
        if net.amount < policy.minimum_net_target.amount:
            reasons.append('NET_TARGET_BELOW_MINIMUM')
        if money(notional).amount > portfolio.remaining_exposure.amount:
            reasons.append('EXPOSURE_EXCEEDED')
        if money(required_margin).amount > min(available, portfolio.free_margin.amount):
            reasons.append('INITIAL_MARGIN_INSUFFICIENT')
        if money(stop_loss).amount > risk_limit:
            reasons.append('RISK_BUDGET_EXCEEDED')

        sign = 1 if scenario.direction is Direction.LONG else -1
        worst = money(stop_loss).amount
        # Base stop is always tested, independently of the additional approved shocks.
        checks = [('BASE_STOP', Decimal(0), Decimal(0), margin.maintenance_fraction)]
        checks += [(s.stress_id, s.adverse_gap.money.amount, s.extra_slippage_per_side.money.amount,
                    s.maintenance_fraction) for s in policy.stresses]
        for name, gap, extra_slip, maintenance_fraction in checks:
            adverse_price = scenario.stop.amount - sign * gap
            loss = money(stop_loss + q * multiplier * (gap + 2 * extra_slip))
            post_equity = Money(available - loss.amount, portfolio.account_currency)
            post_margin = Money(min(available, portfolio.free_margin.amount) - loss.amount, portfolio.account_currency)
            maintenance = money(q * multiplier * max(Decimal(0), adverse_price) * maintenance_fraction)
            if adverse_price <= 0:
                reasons.append('STRESS_PRICE_INVALID')
            if loss.amount > risk_limit:
                reasons.append('STRESS_RISK_BUDGET_EXCEEDED')
            if money(q * multiplier * max(Decimal(0), adverse_price)).amount > portfolio.remaining_exposure.amount:
                reasons.append('STRESS_EXPOSURE_EXCEEDED')
            if post_margin.amount <= 0 or maintenance.amount > post_margin.amount:
                reasons.append('STRESS_MAINTENANCE_INSUFFICIENT')
            worst = max(worst, loss.amount)
            outcomes.append(StressOutcome(name, loss, maintenance, post_equity, post_margin))
        return Evaluation(tuple(sorted(set(reasons))), money(opening), money(closing), money(spread),
            money(slippage), money(financing), money(total), net, money(stop_loss),
            Money(worst, portfolio.account_currency), money(notional), money(required_margin), tuple(outcomes))
