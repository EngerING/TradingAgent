"""Independent cash examples for execution frictions and currency conversion."""
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal, localcontext
import unittest

from test_core_v3_economic_contracts import AT, fixture
from trading_agent.core_v3.contracts import Quantity, ContractError, Price
from trading_agent.core_v3.event_backtest.contracts import Role, Side, SimulatedOrder
from trading_agent.core_v3.event_backtest.accounting import ExecutionMath


class ExecutionAccountingTests(unittest.TestCase):
    def test_spread_slippage_rounding_and_commissions_are_counted_once(self):
        context, _ = fixture()
        quantity = Quantity(Decimal('50'), 'EUR')
        model = ExecutionMath(context, quantity)
        entry = SimulatedOrder('entry', Role.ENTRY, Side.BUY, quantity, 3, 1, AT, 'ENTRY_RULE')
        exit_order = SimulatedOrder('exit', Role.EXIT, Side.SELL, quantity, 4, 2, AT, 'TARGET')
        first = model.fill(entry, 4, AT, Price(Decimal('1.10'), 'USD', 'EUR'))
        last = model.fill(exit_order, 5, AT+timedelta(hours=1), Price(Decimal('1.14'), 'USD', 'EUR'))
        self.assertEqual(Decimal('1.10015'), first.price.amount)
        self.assertEqual(Decimal('1.13985'), last.price.amount)
        costs = model.costs(first, last, model.financing(AT, last.at))
        self.assertEqual(Decimal('2'), model.gross(first, last).amount)
        self.assertEqual(Decimal('.01'), costs.spread.amount)
        self.assertEqual(Decimal('.005'), costs.slippage.amount)
        self.assertEqual(Decimal('1.015'), costs.total.amount)
        self.assertEqual(Decimal('.985'), model.gross(first, last).amount-costs.total.amount)
        self.assertEqual(Decimal('1.985'), (last.price.amount-first.price.amount)*quantity.amount)

    def test_short_is_symmetric_and_rounding_is_adverse_to_each_side(self):
        context, _ = fixture(stock=True)
        quantity = Quantity(Decimal('8'), 'SHARE')
        model = ExecutionMath(context, quantity)
        for side, expected in ((Side.BUY, '10.02'), (Side.SELL, '9.98')):
            order = SimulatedOrder('order', Role.ENTRY, side, quantity, 0, 1, AT, 'ENTRY_RULE')
            fill = model.fill(order, 1, AT, Price(Decimal('10'), 'EUR', 'SHARE'))
            self.assertEqual(Decimal(expected), fill.price.amount)
        changed = replace(context, market=replace(context.market,
            ask=Price(Decimal('10.02'), 'EUR', 'SHARE')))
        fill = ExecutionMath(changed, quantity).fill(order, 1, AT, Price(Decimal('10'), 'EUR', 'SHARE'))
        self.assertEqual(Decimal('9.97'), fill.price.amount)
        self.assertEqual(Decimal('.04'), fill.rounding_cost.amount)

    def test_financing_is_elapsed_time_rounded_up_and_fx_is_applied_once(self):
        context, _ = fixture(account_currency='EUR')
        unit_cost = replace(context.costs.financing_per_unit_per_hour,
                            money=replace(context.costs.financing_per_unit_per_hour.money, amount=Decimal('.01')))
        context = replace(context, costs=replace(context.costs, financing_fixed=replace(context.costs.financing_fixed,
                                            amount=Decimal('.2')), financing_per_unit_per_hour=unit_cost))
        model = ExecutionMath(context, Quantity(Decimal('50'), 'EUR'))
        self.assertEqual(Decimal('.84'), model.financing(AT, AT+timedelta(hours=1)).amount)
        self.assertEqual(Decimal('.250000000000'), model.financing(AT, AT+timedelta(minutes=1)).amount)
        with localcontext() as arithmetic:
            arithmetic.prec = 2
            self.assertEqual(Decimal('.84'), model.financing(AT, AT+timedelta(hours=1)).amount)

    def test_precision_overflow_is_a_controlled_error(self):
        context, _ = fixture()
        model = ExecutionMath(context, Quantity(Decimal('50'), 'EUR'))
        with self.assertRaises(ContractError):
            model.money(Decimal('1e30'))
