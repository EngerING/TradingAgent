"""Independent causal examples, not profit simulations."""
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal, localcontext
import unittest

from test_core_v3_research_contracts import AT, request
from test_core_v34_contracts import close, sma
from trading_agent.core_v3.contracts import ContractError, SourceKind, content_hash
from trading_agent.core_v3.economic_contracts import Direction
from trading_agent.core_v3.strategy_v34.contracts import Operator, Rule, Timeframe
from trading_agent.core_v3.strategy_v34.designer import SimulatedStrategyDesigner, design
from trading_agent.core_v3.strategy_v34.signals import Candle, CandleSeries, SignalResult, evaluate


def case(*, stock=False, direction=Direction.LONG, timeframe=Timeframe.M1, offsets=(0, -2, -2, 2)):
    req = request(stock=stock, direction=direction)
    strategy = design(req, timeframe, SimulatedStrategyDesigner(), now=AT)
    instrument = req.inputs.context.market.instrument
    base, tick = strategy.scenario.entry, instrument.tick.amount
    bars = []
    for index, offset in enumerate(offsets):
        end = AT - timedelta(seconds=(len(offsets)-1-index)*timeframe.seconds)
        price = replace(base, amount=base.amount + tick*offset)
        bars.append(Candle(end, end, price, price, price, price))
    return req, strategy, CandleSeries(req.instrument, timeframe, tuple(bars))


class CausalSignalTests(unittest.TestCase):
    def test_crosses_for_each_instrument_direction_timeframe(self):
        for stock in (False, True):
            for direction in Direction:
                for timeframe in Timeframe:
                    offsets = (0, -2, -2, 2) if direction is Direction.LONG else (0, 2, 2, -2)
                    with self.subTest(stock=stock, direction=direction, timeframe=timeframe):
                        req, strategy, series = case(stock=stock, direction=direction, timeframe=timeframe, offsets=offsets)
                        result = evaluate(strategy, req, series, as_of=AT)
                        self.assertTrue(result.entry_rules_met)
                        self.assertFalse(result.exit_rules_met)
                        self.assertEqual(AT, result.latest_close)
                        self.assertEqual(4, result.used_bars)
                        self.assertEqual(content_hash(strategy), result.strategy_sha256)
                        self.assertEqual(result, SignalResult.from_json(result.to_json()))
                        self.assertEqual(series, CandleSeries.from_json(series.to_json()))
                        self.assertEqual('NO_TRADE', result.trading_decision)
                        self.assertFalse(result.execution_authority)

    def test_exit_cross_is_distinct_from_entry(self):
        req, strategy, series = case(offsets=(0, 2, 2, -2))
        result = evaluate(strategy, req, series, as_of=AT)
        self.assertFalse(result.entry_rules_met)
        self.assertTrue(result.exit_rules_met)

    def test_future_suffix_cannot_change_prior_result_or_prefix_hash(self):
        req, strategy, series = case()
        original = evaluate(strategy, req, series, as_of=AT)
        for shift in (100, -100):
            last = series.bars[-1]
            price = replace(last.close, amount=last.close.amount + req.inputs.context.market.instrument.tick.amount*shift)
            end = AT + timedelta(minutes=1)
            future = Candle(end, end, price, price, price, price)
            extended = replace(series, bars=series.bars+(future,))
            self.assertEqual(original, evaluate(strategy, req, extended, as_of=AT))

    def test_not_yet_available_and_not_closed_cannot_be_used(self):
        req, strategy, series = case()
        delayed = replace(series.bars[-1], available_at=AT+timedelta(seconds=1))
        with self.assertRaisesRegex(ContractError, 'STALE_SYNTHETIC_SERIES'):
            evaluate(strategy, req, replace(series, bars=series.bars[:-1]+(delayed,)), as_of=AT)
        with self.assertRaisesRegex(ContractError, 'STALE_SYNTHETIC_SERIES'):
            evaluate(strategy, req, replace(series, bars=series.bars[:-1]), as_of=AT)

    def test_warmup_for_sma_cross_and_lag_is_exact(self):
        req, strategy, series = case()
        self.assertEqual(4, strategy.entry_rules[0].required_bars)
        short = replace(series, bars=series.bars[-3:])
        with self.assertRaisesRegex(ContractError, 'SIGNAL_WARMUP_REQUIRED'):
            evaluate(strategy, req, short, as_of=AT)
        lagged = replace(strategy, entry_rules=(Rule(close(1), Operator.GT, sma(3, 1)),))
        self.assertFalse(evaluate(lagged, req, series, as_of=AT).entry_rules_met)
        lagged = replace(strategy, entry_rules=(Rule(close(2), Operator.GT, sma(3, 2)),))
        with self.assertRaisesRegex(ContractError, 'SIGNAL_WARMUP_REQUIRED'):
            evaluate(lagged, req, series, as_of=AT)

    def test_equality_is_not_a_new_cross(self):
        req, strategy, series = case(offsets=(0, 0, 0, 0))
        result = evaluate(strategy, req, series, as_of=AT)
        self.assertFalse(result.entry_rules_met)
        self.assertFalse(result.exit_rules_met)

    def test_no_short_circuit_can_hide_missing_history(self):
        req, strategy, series = case(offsets=(0, 0, 0, 0))
        strategy = replace(strategy, entry_rules=strategy.entry_rules+(Rule(close(), Operator.GT, sma(200)),))
        with self.assertRaisesRegex(ContractError, 'SIGNAL_WARMUP_REQUIRED'):
            evaluate(strategy, req, series, as_of=AT)

    def test_rules_use_conjunction(self):
        req, strategy, series = case()
        strategy = replace(strategy, entry_rules=strategy.entry_rules+(Rule(close(1), Operator.GT, sma(3, 1)),))
        self.assertFalse(evaluate(strategy, req, series, as_of=AT).entry_rules_met)

    def test_conflicting_entry_and_exit_fail_closed(self):
        req, strategy, series = case()
        strategy = replace(strategy, exit_rules=strategy.entry_rules)
        with self.assertRaisesRegex(ContractError, 'CONFLICTING_RULES'):
            evaluate(strategy, req, series, as_of=AT)

    def test_arithmetic_independent_of_ambient_precision(self):
        req, strategy, series = case()
        expected = evaluate(strategy, req, series, as_of=AT)
        with localcontext() as context:
            context.prec = 2
            self.assertEqual(expected, evaluate(strategy, req, series, as_of=AT))

    def test_series_rejects_gaps_duplicates_reordering_alignment_and_mutability(self):
        _, _, series = case()
        for bars in [(), list(series.bars), series.bars*129, series.bars[::-1],
                     series.bars[:2]+series.bars[3:], series.bars+(series.bars[-1],),
                     series.bars[:-1]+(replace(series.bars[-1], closed_at=AT+timedelta(seconds=1),
                                               available_at=AT+timedelta(seconds=1)),)]:
            with self.subTest(length=len(bars)), self.assertRaises(ContractError):
                replace(series, bars=bars)

    def test_ohlc_units_prices_and_availability_are_validated(self):
        req, strategy, series = case()
        bar = series.bars[-1]
        for change in [dict(high=replace(bar.high, amount=bar.high.amount-1)),
                       dict(close=replace(bar.close, currency='GBP')),
                       dict(available_at=bar.closed_at-timedelta(seconds=1)),
                       dict(closed_at=bar.closed_at.replace(tzinfo=None))]:
            with self.subTest(change=change), self.assertRaises(ContractError):
                replace(bar, **change)
        offgrid = replace(bar.close, amount=bar.close.amount + Decimal('.000001'))
        invalid = replace(bar, open=offgrid, high=offgrid, low=offgrid, close=offgrid)
        with self.assertRaisesRegex(ContractError, 'PRICE_TICK_MISMATCH'):
            evaluate(strategy, req, replace(series, bars=series.bars[:-1]+(invalid,)), as_of=AT)

    def test_series_instrument_timeframe_and_authentic_labels_cannot_be_substituted(self):
        req, strategy, series = case()
        with self.assertRaises(ContractError):
            replace(series, source_kind=SourceKind.AUTHENTIC_CAPTURE)
        for changed in [replace(series, instrument=request(stock=True).instrument),
                        case(timeframe=Timeframe.M5)[2]]:
            with self.assertRaises(ContractError):
                evaluate(strategy, req, changed, as_of=AT)

    def test_result_flags_cannot_promote_signals(self):
        req, strategy, series = case()
        result = evaluate(strategy, req, series, as_of=AT)
        for key in ('execution_authority', 'paper_execution_eligible', 'live_enabled', 'statistically_validated'):
            with self.subTest(key=key), self.assertRaises(ContractError):
                SignalResult.from_dict(dict(result.to_dict(), **{key: True}))

    def test_maximum_indicator_window_roundtrips_above_32_bars(self):
        req, strategy, series = case(offsets=(0,)*233)
        strategy = replace(strategy, entry_rules=(Rule(close(32), Operator.CROSS_ABOVE, sma(200, 32)),))
        self.assertEqual(series, CandleSeries.from_json(series.to_json()))
        self.assertFalse(evaluate(strategy, req, series, as_of=AT).entry_rules_met)

    def test_all_io_is_forbidden_during_pure_evaluation(self):
        import sys
        req, strategy, series = case()
        enabled = [True]
        def deny(event, args):
            if enabled[0] and (event == 'open' or event.startswith('socket.') or event in ('subprocess.Popen', 'sqlite3.connect')):
                raise AssertionError('SIGNAL_EVALUATION_MUST_BE_PURE')
        sys.addaudithook(deny)
        try:
            self.assertTrue(evaluate(strategy, req, series, as_of=AT).entry_rules_met)
        finally:
            enabled[0] = False
