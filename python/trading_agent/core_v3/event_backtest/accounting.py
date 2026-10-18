"""Adverse executable prices, exact financial sums and explicit conservative rounding."""
from decimal import Context, Decimal, ROUND_CEILING, ROUND_FLOOR, localcontext

from ..contracts import Money, Price, require
from .contracts import CostBreakdown, Role, Side, SimulatedFill


def fraction(numerator, denominator, rounding):
    """Only rates/time allocations are rounded: 12 decimal places, declared direction."""
    with localcontext(Context(prec=160)):
        return (numerator / denominator).quantize(Decimal('.000000000001'), rounding=rounding)


class ExecutionMath:
    def __init__(self, context, quantity):
        self.context, self.quantity = context, quantity
        self.instrument = context.market.instrument
        self.fx = Decimal(1) if self.instrument.quote_currency == context.portfolio.account_currency else context.fx.rate

    def money(self, quote_amount):
        with localcontext(Context(prec=160)):
            return Money(quote_amount*self.fx, self.context.portfolio.account_currency)

    def account(self, amount):
        return Money(amount, self.context.portfolio.account_currency)

    def execution_price(self, mid, side):
        with localcontext(Context(prec=160)):
            spread = self.context.market.ask.amount-self.context.market.bid.amount
            slip = self.context.costs.slippage_per_side.money.amount
            sign = 1 if side is Side.BUY else -1
            raw = mid.amount + sign*(spread/2 + slip)
            tick = self.instrument.tick.amount
            amount = (raw/tick).to_integral_value(rounding=ROUND_CEILING if sign == 1 else ROUND_FLOOR)*tick
            price = Price(amount, mid.currency, mid.per_unit)
            self.instrument.check_terms(self.quantity, price)
            return price, spread/2, slip, abs(amount-raw)

    def commission(self, role):
        with localcontext(Context(prec=160)):
            costs = self.context.costs
            minimum = costs.opening_minimum if role is Role.ENTRY else costs.closing_minimum
            per_unit = costs.opening_per_unit if role is Role.ENTRY else costs.closing_per_unit
            return self.money(max(minimum.amount, self.quantity.amount*per_unit.money.amount))

    def fill(self, order, index, at, mid):
        with localcontext(Context(prec=160)):
            price, half_spread, slip, rounding = self.execution_price(mid, order.side)
            scale = self.quantity.amount*self.instrument.multiplier
            return SimulatedFill('fill-'+order.order_id, order.order_id, order.role, order.side, self.quantity,
                index, at, mid, price, self.commission(order.role), self.money(scale*half_spread),
                self.money(scale*slip), self.money(scale*rounding))

    def financing(self, opened_at, at):
        with localcontext(Context(prec=160)):
            elapsed = at-opened_at
            require(elapsed.days >= 0 and elapsed.microseconds == 0, 'BACKTEST_FINANCING_TIME')
            seconds = Decimal(elapsed.days*86400+elapsed.seconds)
            costs = self.context.costs
            fixed = costs.financing_fixed.amount*self.fx
            variable = self.quantity.amount*costs.financing_per_unit_per_hour.money.amount*self.fx
            return self.account(fraction(fixed*3600+variable*seconds, Decimal(3600), ROUND_CEILING))

    def gross(self, entry, exit_fill):
        with localcontext(Context(prec=160)):
            sign = 1 if entry.side is Side.BUY else -1
            return self.money(sign*(exit_fill.mid_price.amount-entry.mid_price.amount)
                              *self.quantity.amount*self.instrument.multiplier)

    def costs(self, entry, exit_fill, financing):
        spread = entry.spread_cost.add(exit_fill.spread_cost)
        slip = entry.slippage_cost.add(exit_fill.slippage_cost)
        rounding = entry.rounding_cost.add(exit_fill.rounding_cost)
        total = entry.commission.add(exit_fill.commission).add(spread).add(slip).add(rounding).add(financing)
        return CostBreakdown(entry.commission, exit_fill.commission, spread, slip, rounding, financing, total)
