"""Missing information, adverse execution and deterministic resource failure scenarios."""
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
import unittest
from unittest.mock import patch

from test_core_v3_economic_contracts import sealed
from test_core_v35_contracts import request
from test_core_v36_binding import registered, bound
from test_core_v36_contracts import dataset, policy
from test_core_v36_engine import trade_data
from trading_agent.core_v3.contracts import Price, Quantity, content_hash
from trading_agent.core_v3.economic_contracts import Direction
from trading_agent.core_v3.research_contracts import InstrumentIdentity
from trading_agent.core_v3.strategy_v34.contracts import Timeframe
from trading_agent.core_v3.event_backtest.contracts import Status
from trading_agent.core_v3.event_backtest.engine import run


def bar_open(data, index, price):
    bar = data.bars[index]
    changed = replace(bar, open=price, high=max((bar.high, price), key=lambda p:p.amount),
                      low=min((bar.low, price), key=lambda p:p.amount))
    return replace(data, bars=data.bars[:index]+(changed,)+data.bars[index+1:])


class AdversarialBacktestTests(unittest.TestCase):
    def test_exit_rule_fills_next_open_instead_of_known_close(self):
        with registered() as (_, _, catalog, journal):
            request, data, rules = bound(catalog, journal, dataset(offsets=(0, -2, -2, 2, 2, -2, -2)))
            result = run(request, catalog, journal, data, rules)
            self.assertEqual('EXIT_RULE', result.trades[0].reason)
            self.assertEqual(5, result.orders[-1].signal_bar)
            self.assertEqual(6, result.trades[0].exit.bar_index)

    def test_horizon_closes_on_admissible_open_and_does_not_need_an_exit_signal(self):
        with registered(timeframe=Timeframe.H1) as (_, cmd, catalog, journal):
            request, data, rules = bound(catalog, journal, dataset(timeframe=Timeframe.H1))
            result = run(request, catalog, journal, data, rules)
            self.assertEqual('HORIZON', result.trades[0].reason)
            self.assertEqual(timedelta(hours=1), result.trades[0].exit.at-result.trades[0].entry.at)

    def test_stop_gap_is_worse_than_stop_and_target_gap_gets_no_favorable_improvement(self):
        for direction in Direction:
            with self.subTest(direction=direction), registered(direction=direction) as (_, cmd, catalog, journal):
                sign = 1 if direction is Direction.LONG else -1
                base = trade_data(cmd, mode='NONE')
                for reason, level in [('STOP_GAP', cmd.strategy.scenario.stop), ('TARGET_GAP', cmd.strategy.scenario.target)]:
                    change = Decimal('-.01') if reason == 'STOP_GAP' else Decimal('.01')
                    price = replace(level, amount=level.amount+sign*change)
                    data = bar_open(base, 5, price)
                    request, _, rules = bound(catalog, journal, data)
                    result = run(request, catalog, journal, data, rules)
                    trade = result.trades[0]
                    self.assertEqual(reason, trade.reason)
                    self.assertEqual(price if reason == 'STOP_GAP' else level, trade.exit.mid_price)
                    if reason == 'STOP_GAP':
                        self.assertLess(trade.net.amount, Decimal('-1.2678'))

    def test_entry_gap_outside_original_geometry_is_rejected_without_a_fill(self):
        with registered() as (_, cmd, catalog, journal):
            data = bar_open(dataset(), 4, replace(cmd.strategy.scenario.target, amount=Decimal('1.15')))
            request, _, rules = bound(catalog, journal, data)
            result = run(request, catalog, journal, data, rules)
            self.assertEqual(0, len(result.fills))
            self.assertEqual(1, result.metrics.rejected_entries)
            self.assertTrue(any(e.reason == 'ENTRY_GAP_GEOMETRY' for e in result.events))
            self.assertEqual(Decimal(0), result.metrics.net.amount)

    def test_actual_entry_margin_and_exposure_are_rechecked(self):
        for field, amount, reason in [('free_margin', '29.8', 'INITIAL_MARGIN_LIMIT'),
                                      ('remaining_exposure', '29', 'EXPOSURE_LIMIT')]:
            original = request()
            portfolio = original.inputs.context.portfolio
            portfolio = sealed(replace(portfolio, **{field: replace(getattr(portfolio, field), amount=Decimal(amount))}))
            changed = replace(original, inputs=replace(original.inputs, context=replace(original.inputs.context, portfolio=portfolio)))
            with self.subTest(field=field), registered(req=changed) as (_, cmd, catalog, journal):
                data = bar_open(dataset(), 4, replace(cmd.strategy.scenario.entry, amount=Decimal('1.13')))
                request_value, _, rules = bound(catalog, journal, data)
                result = run(request_value, catalog, journal, data, rules)
                self.assertEqual(0, len(result.fills))
                self.assertTrue(any(e.reason == reason for e in result.events), result.reason)
                self.assertEqual(Decimal(0), result.metrics.peak_exposure.amount)

    def test_financing_and_fx_are_bound_to_original_source_and_charged_once(self):
        original = request(account_currency='EUR')
        costs = original.inputs.context.costs
        rate = replace(costs.financing_per_unit_per_hour, money=replace(costs.financing_per_unit_per_hour.money, amount=Decimal('.01')))
        costs = sealed(replace(costs, financing_fixed=replace(costs.financing_fixed, amount=Decimal('.1')), financing_per_unit_per_hour=rate))
        changed = replace(original, inputs=replace(original.inputs, context=replace(original.inputs.context, costs=costs)))
        with registered(req=changed, timeframe=Timeframe.H1) as (_, cmd, catalog, journal):
            request_value, data, rules = bound(catalog, journal, trade_data(cmd))
            result = run(request_value, catalog, journal, data, rules)
            trade = result.trades[0]
            self.assertEqual(Decimal('38'), trade.entry.quantity.amount)
            self.assertEqual(Decimal('.576'), trade.costs.financing.amount)
            self.assertEqual(Decimal('1.824'), trade.gross.amount)
            self.assertEqual(Decimal('1.78968'), trade.costs.total.amount)
            self.assertEqual(Decimal('.03432'), trade.net.amount)
            self.assertEqual('EUR', trade.net.currency)

    def test_delayed_or_insufficient_data_is_inconclusive_and_cannot_create_a_fill(self):
        with registered() as (_, _, catalog, journal):
            base = dataset()
            short = replace(base, bars=base.bars[:3])
            delayed = replace(base.bars[3], available_at=base.bars[3].closed_at+timedelta(seconds=1))
            missing = replace(base, bars=base.bars[:3]+(delayed,)+base.bars[4:])
            for data, reason in [(short, 'WARMUP_COVERAGE_REQUIRED'), (missing, 'DELAYED_BAR_UNRESOLVED')]:
                request_value, _, rules = bound(catalog, journal, data)
                result = run(request_value, catalog, journal, data, rules)
                self.assertEqual(Status.INCONCLUSIVE, result.status)
                self.assertEqual(reason, result.reason)
                self.assertEqual(0, len(result.fills))

    def test_limits_fail_explicitly_without_silent_truncation_or_fake_completion(self):
        with registered() as (_, cmd, catalog, journal):
            data = trade_data(cmd)
            for rules, state, reason in [(policy(max_bars=2), Status.REJECTED, 'BACKTEST_INPUT_LIMIT'),
                                        (policy(max_events=1), Status.INCONCLUSIVE, 'EVENT_LIMIT'),
                                        (policy(max_result_bytes=4096), Status.REJECTED, 'BACKTEST_RESULT_SIZE_LIMIT')]:
                request_value, _, _ = bound(catalog, journal, data, rules)
                result = run(request_value, catalog, journal, data, rules)
                self.assertEqual((state, reason), (result.status, result.reason))
                self.assertLessEqual(len(result.to_json().encode()), rules.max_result_bytes)

    def test_interruption_has_no_side_effects_and_replay_restores_identical_result(self):
        from trading_agent.core_v3.event_backtest.simulation import Simulation
        with registered() as (_, cmd, catalog, journal):
            request_value, data, rules = bound(catalog, journal, trade_data(cmd))
            histories = catalog.history(), journal.history()
            with patch.object(Simulation, 'valuation', side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    run(request_value, catalog, journal, data, rules)
            self.assertEqual(histories, (catalog.history(), journal.history()))
            result = run(request_value, catalog, journal, data, rules)
            self.assertEqual(result, run(request_value, catalog, journal, data, rules))

    def test_realized_drawdown_includes_opening_fee_even_with_profitable_same_bar_exit(self):
        with registered() as (_, cmd, catalog, journal):
            request_value, data, rules = bound(catalog, journal, trade_data(cmd))
            result = run(request_value, catalog, journal, data, rules)
            self.assertEqual(Decimal('.5'), result.metrics.max_realized_drawdown.amount)
            self.assertGreater(result.metrics.net.amount, 0)

    def test_trade_limit_preserves_previous_operations_without_opening_another(self):
        with registered() as (_, cmd, catalog, journal):
            data = dataset(offsets=(0, -2, -2, 2, 2, -2, -2, 2, 2))
            target_bar = trade_data(cmd).bars[4]
            data = replace(data, bars=data.bars[:4]+(target_bar,)+data.bars[5:])
            rules = policy(max_trades=1)
            request_value, _, _ = bound(catalog, journal, data, rules)
            result = run(request_value, catalog, journal, data, rules)
            self.assertEqual((Status.INCONCLUSIVE, 'TRADE_LIMIT'), (result.status, result.reason))
            self.assertEqual(1, len(result.trades))
            self.assertEqual(2, len(result.fills))

    def test_no_signal_is_not_a_winner_and_has_zero_closed_trade_metrics(self):
        with registered() as (_, _, catalog, journal):
            request_value, data, rules = bound(catalog, journal, dataset(offsets=(0, 0, 0, 0, 0)))
            result = run(request_value, catalog, journal, data, rules)
            self.assertEqual(Status.COMPLETE, result.status)
            self.assertEqual((0, 0, 0), (result.metrics.closed_trades, result.metrics.winners, result.metrics.losers))
            self.assertEqual(Decimal(0), result.metrics.net.amount)
            self.assertFalse(result.statistically_validated)

    def test_final_entry_signal_is_explicitly_rejected_when_policy_closes_the_window(self):
        with registered() as (_, _, catalog, journal):
            data = dataset(offsets=(0, -2, -2, 2))
            request_value, _, rules = bound(catalog, journal, data, policy(close_at_end=True))
            result = run(request_value, catalog, journal, data, rules)
            self.assertEqual(Status.COMPLETE, result.status)
            self.assertEqual(1, result.metrics.rejected_entries)
            self.assertTrue(any(e.reason == 'ENTRY_AFTER_WINDOW' for e in result.events))
            self.assertFalse(result.fills or result.pending_orders)

    def test_actual_entry_risk_is_rechecked_without_resizing_the_catalog_quantity(self):
        original = request()
        portfolio = original.inputs.context.portfolio
        portfolio = sealed(replace(portfolio, remaining_risk=replace(portfolio.remaining_risk, amount=Decimal('1.4'))))
        changed = replace(original, inputs=replace(original.inputs, context=replace(original.inputs.context, portfolio=portfolio)))
        with registered(req=changed) as (_, cmd, catalog, journal):
            data = bar_open(dataset(), 4, replace(cmd.strategy.scenario.entry, amount=Decimal('1.13')))
            request_value, _, rules = bound(catalog, journal, data)
            result = run(request_value, catalog, journal, data, rules)
            self.assertEqual(0, len(result.fills))
            self.assertTrue(any(e.reason == 'RISK_LIMIT' for e in result.events))
            self.assertEqual(cmd.strategy.scenario.quantity, result.orders[0].quantity)

    def test_open_position_marks_exit_friction_and_has_distinct_mark_drawdown(self):
        with registered() as (_, _, catalog, journal):
            data = dataset()
            price = Price(Decimal('1.095'), 'USD', 'EUR')
            last = replace(data.bars[4], close=price, low=price)
            data = replace(data, bars=data.bars[:4]+(last,))
            request_value, _, rules = bound(catalog, journal, data)
            result = run(request_value, catalog, journal, data, rules)
            self.assertEqual(Status.INCONCLUSIVE, result.status)
            self.assertEqual(Decimal('99.5'), result.metrics.final_realized_capital.amount)
            self.assertEqual(Decimal('1.10025'), result.open_position.entry.price.amount)
            self.assertEqual(Decimal('98.8596'), result.metrics.final_mark_capital.amount)
            self.assertGreater(result.metrics.max_mark_drawdown.amount, result.metrics.max_realized_drawdown.amount)

    def test_valid_source_can_still_reject_unrepresentable_half_spread_without_rounding_profit(self):
        original = request()
        context = original.inputs.context
        instrument = replace(context.market.instrument, tick=Price(Decimal('.000000000001'), 'USD', 'EUR'),
                             minimum_quantity=Quantity(Decimal('27'), 'EUR'))
        market = sealed(replace(context.market, instrument=instrument, bid=Price(Decimal('1.1'), 'USD', 'EUR'),
                                ask=Price(Decimal('1.100000000001'), 'USD', 'EUR')))
        ideas = tuple(sealed(replace(h, instrument_sha256=content_hash(instrument))) for h in context.hypotheses)
        context = replace(context, market=market, hypotheses=ideas)
        economic_policy = replace(original.inputs.policy, max_entry_deviation=replace(original.inputs.policy.max_entry_deviation,
            money=replace(original.inputs.policy.max_entry_deviation.money, amount=Decimal('.000000000001'))))
        changed = replace(original, instrument=InstrumentIdentity.of(instrument),
                          inputs=replace(original.inputs, context=context, policy=economic_policy))
        with registered(req=changed) as (_, _, catalog, journal):
            data = replace(dataset(), instrument=changed.instrument)
            request_value, _, rules = bound(catalog, journal, data)
            result = run(request_value, catalog, journal, data, rules)
            self.assertEqual((Status.REJECTED, 'DECIMAL_LIMIT'), (result.status, result.reason))
            self.assertIsNone(result.metrics)
