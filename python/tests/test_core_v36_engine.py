"""Causal event simulations with independently checked long/short cash outcomes."""
from dataclasses import replace
from decimal import Decimal, localcontext
import unittest

from test_core_v35_contracts import AT
from test_core_v36_binding import registered, bound
from test_core_v36_contracts import dataset, policy
from trading_agent.core_v3.contracts import Price, content_hash
from trading_agent.core_v3.economic_contracts import Direction
from trading_agent.core_v3.strategy_v34.contracts import Timeframe
from trading_agent.core_v3.event_backtest.contracts import BacktestResult, EventKind, Role, Status
from trading_agent.core_v3.event_backtest.engine import run


def trade_data(cmd, *, mode='TARGET', stock=False):
    direction = cmd.strategy.scenario.direction
    offsets = (0, -2, -2, 2, 2, 2) if direction is Direction.LONG else (0, 2, 2, -2, -2, -2)
    data = dataset(stock=stock, timeframe=cmd.timeframe, offsets=offsets)
    scenario = cmd.strategy.scenario
    bar = data.bars[4]
    prices = [bar.close, scenario.entry]
    if mode in ('TARGET', 'BOTH'):
        prices.append(scenario.target)
    if mode in ('STOP', 'BOTH'):
        prices.append(scenario.stop)
    changed = replace(bar, open=scenario.entry, high=max(prices, key=lambda p:p.amount),
                      low=min(prices, key=lambda p:p.amount))
    return replace(data, bars=data.bars[:4]+(changed,)+data.bars[5:])


class EventBacktesterTests(unittest.TestCase):
    def test_long_and_short_target_have_exact_gross_costs_net_and_no_authority(self):
        for direction in Direction:
            with self.subTest(direction=direction), registered(direction=direction) as (_, cmd, catalog, journal):
                request, data, rules = bound(catalog, journal, trade_data(cmd))
                result = run(request, catalog, journal, data, rules)
                self.assertEqual(Status.COMPLETE, result.status, result.reason)
                self.assertEqual(1, len(result.trades))
                trade = result.trades[0]
                self.assertEqual(Decimal('26'), trade.entry.quantity.amount)
                self.assertEqual('TARGET', trade.reason)
                self.assertEqual(Decimal('1.04'), trade.gross.amount)
                self.assertEqual(Decimal('1.0078'), trade.costs.total.amount)
                self.assertEqual(Decimal('.0322'), trade.net.amount)
                self.assertEqual(Decimal('100.0322'), result.metrics.final_mark_capital.amount)
                self.assertEqual(Decimal('29.6361') if direction is Direction.LONG else Decimal('28.5961'),
                                 result.metrics.peak_exposure.amount)
                self.assertFalse(result.execution_authority or result.live_enabled or result.statistically_validated)
                self.assertEqual('NO_TRADE', result.trading_decision)
                self.assertEqual(result, BacktestResult.from_json(result.to_json()))

    def test_long_short_stops_and_ambiguous_both_always_choose_stop(self):
        for direction in Direction:
            for mode in ('STOP', 'BOTH'):
                with self.subTest(direction=direction, mode=mode), registered(direction=direction) as (_, cmd, catalog, journal):
                    request, data, rules = bound(catalog, journal, trade_data(cmd, mode=mode))
                    result = run(request, catalog, journal, data, rules)
                    self.assertEqual('STOP', result.trades[0].reason)
                    self.assertEqual(Decimal('-1.2678'), result.trades[0].net.amount)

    def test_forex_and_equity_all_timeframes_use_the_same_engine(self):
        for stock, timeframe, direction in ((True, Timeframe.M5, Direction.SHORT),
                                            (True, Timeframe.H1, Direction.LONG),
                                            (False, Timeframe.H1, Direction.SHORT)):
            with self.subTest(stock=stock, timeframe=timeframe), registered(stock=stock, direction=direction, timeframe=timeframe) as (_, cmd, catalog, journal):
                request, data, rules = bound(catalog, journal, trade_data(cmd, stock=stock))
                result = run(request, catalog, journal, data, rules)
                self.assertEqual(Status.COMPLETE, result.status)
                self.assertEqual(timeframe, result.evidence.timeframe)
                self.assertEqual('TARGET', result.trades[0].reason)
                self.assertEqual('EUR' if stock else 'USD', result.trades[0].net.currency)

    def test_entry_uses_later_bar_open_and_signal_precedes_fill_event(self):
        with registered() as (_, cmd, catalog, journal):
            request, data, rules = bound(catalog, journal, trade_data(cmd))
            result = run(request, catalog, journal, data, rules)
            order, fill = result.orders[0], result.fills[0]
            self.assertEqual(3, order.signal_bar)
            self.assertEqual(4, fill.bar_index)
            self.assertEqual(data.bars[4].open, fill.mid_price)
            self.assertNotEqual(data.bars[3].close, fill.mid_price)
            self.assertGreater(next(e.sequence for e in result.events if e.kind is EventKind.FILL), order.signal_sequence)
            self.assertGreaterEqual(fill.at, order.decided_at)

    def test_future_suffix_cannot_change_earlier_events_or_fills(self):
        with registered() as (_, cmd, catalog, journal):
            original = trade_data(cmd)
            request, data, rules = bound(catalog, journal, original)
            first = run(request, catalog, journal, data, rules)
            changed = replace(original.bars[-1], high=Price(Decimal('2'), 'USD', 'EUR'))
            second_data = replace(original, bars=original.bars[:-1]+(changed,))
            second_request, _, _ = bound(catalog, journal, second_data)
            second = run(second_request, catalog, journal, second_data, rules)
            self.assertEqual(first.trades, second.trades)
            self.assertEqual(tuple(e for e in first.events if e.bar_index < 5),
                             tuple(e for e in second.events if e.bar_index < 5))

    def test_incomplete_coverage_open_position_and_pending_order_are_explicit(self):
        with registered() as (_, _, catalog, journal):
            request, data, rules = bound(catalog, journal)
            result = run(request, catalog, journal, data, rules)
            self.assertEqual(Status.INCONCLUSIVE, result.status)
            self.assertIsNotNone(result.open_position)
            self.assertEqual(0, result.metrics.closed_trades)
            pending_data = replace(data, bars=data.bars[:4])
            pending_request, _, _ = bound(catalog, journal, pending_data)
            pending = run(pending_request, catalog, journal, pending_data, rules)
            self.assertEqual(Status.INCONCLUSIVE, pending.status)
            self.assertEqual(1, len(pending.pending_orders))
            self.assertEqual(0, len(pending.fills))

    def test_explicit_end_close_does_not_fabricate_another_future_price(self):
        with registered() as (_, _, catalog, journal):
            request, data, rules = bound(catalog, journal, rules=policy(close_at_end=True))
            result = run(request, catalog, journal, data, rules)
            self.assertEqual(Status.COMPLETE, result.status)
            self.assertEqual('WINDOW_END', result.trades[0].reason)
            self.assertEqual(data.bars[-1].close, result.trades[0].exit.mid_price)
            self.assertEqual(data.bars[-1].closed_at, result.trades[0].exit.at)

    def test_duplicate_run_is_byte_identical_independent_of_decimal_context(self):
        with registered() as (_, cmd, catalog, journal):
            request, data, rules = bound(catalog, journal, trade_data(cmd))
            histories = catalog.history(), journal.history()
            first = run(request, catalog, journal, data, rules)
            with localcontext() as arithmetic:
                arithmetic.prec = 2
                again = run(request, catalog, journal, data, rules)
            self.assertEqual(first.to_json(), again.to_json())
            self.assertEqual(content_hash(first), content_hash(again))
            self.assertEqual(histories, (catalog.history(), journal.history()))
