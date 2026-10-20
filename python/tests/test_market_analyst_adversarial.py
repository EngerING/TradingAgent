from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, Inexact, localcontext
import json
import unittest

from trading_agent.market import Candle
from trading_agent.research_indicators import calculate, settings
from trading_agent.market_analyst.contracts import AnalystError, MarketAssessment, Policy
from trading_agent.market_analyst.evaluator import evaluate
from trading_agent.market_analyst.fixtures import FixtureRecipe, SyntheticFixture, make_fixture
from test_market_analyst_evaluation import BASE, assessment, fixture


class AdversarialTests(unittest.TestCase):
    def test_reference_indicators_have_known_seeds_and_wilder_smoothing(self):
        policy = Policy(ema_fast=2, ema_slow=3, rsi=2, atr=2, macd_fast=2, macd_slow=3,
                        macd_signal=2, volatility=2)
        data = fixture(4, base_price=Decimal('10'), step=Decimal('1'), half_range=Decimal('.1'))
        result = assessment(data, policy=policy, cutoff=BASE + timedelta(hours=4))
        values = {i.name: i.value for i in result.indicators}
        self.assertEqual(result.status, 'COMPLETE')
        self.assertAlmostEqual(float(values['ema_fast']), 12.5)
        self.assertAlmostEqual(float(values['ema_slow']), 12)
        self.assertAlmostEqual(float(values['macd']), .5)
        self.assertAlmostEqual(float(values['macd_signal']), .5)
        self.assertAlmostEqual(float(values['atr']), .9875)
        self.assertEqual(values['rsi'], 100)

    def test_reused_calculation_matches_all_measures_without_extra_imports(self):
        data = fixture()
        bars = [Candle(b.opened_at, b.minutes, float(b.open), float(b.high), float(b.low), float(b.close))
                for b in data.bars]
        reference = calculate(bars, settings())[-1]
        result = assessment(data)
        for metric in result.indicators:
            self.assertEqual(metric.value, Decimal(str(reference[metric.name])))
        self.assertEqual(result.trend, reference['trend'])

    def test_fake_handle_copy_or_serialized_assessment_cannot_authenticate_data(self):
        source = fixture()
        fake = SyntheticFixture(source.recipe, source.bars)
        for candidate in (fake, assessment().to_dict(), assessment().to_json()):
            result = evaluate(candidate, cutoff=BASE)
            self.assertEqual(result.status, 'UNVERIFIED_PROVENANCE')
        changed = replace(source.bars[0], close=Decimal('1.10001'))
        forged = replace(source, bars=(changed,) + source.bars[1:])
        self.assertIn('MA_FIXTURE_CONTENT_MISMATCH', assessment(forged).quality.reasons)

    def test_bad_ohlc_price_alignment_and_availability_have_specific_reasons(self):
        data = fixture()
        original = data.bars[20]
        for changes, code in (
            ({'close': original.high + 1}, 'MA_OHLC'),
            ({'low': Decimal('-1')}, 'MA_PRICE_RANGE'),
            ({'opened_at': original.opened_at + timedelta(seconds=1)}, 'MA_BAR_ALIGNMENT'),
            ({'available_at': original.opened_at}, 'MA_AVAILABILITY_BEFORE_CLOSE'),
            ({'minutes': 15}, 'MA_TIMEFRAME_MISMATCH'),
        ):
            bar = replace(original, **changes)
            result = assessment(replace(data, bars=data.bars[:20] + (bar,) + data.bars[21:]))
            self.assertEqual(result.status, 'VALIDATION_ERROR')
            self.assertIn(code, result.quality.reasons)

    def test_unknowns_are_null_while_real_zero_metrics_remain_zero(self):
        empty = assessment(fixture(0), cutoff=BASE)
        self.assertTrue(all(i.value is None for i in empty.indicators))
        self.assertIsNone(empty.quality.age_seconds)
        self.assertIsNone(empty.last_closed_at)
        flat = assessment(fixture(pattern='FLAT'))
        metrics = {i.name: i for i in flat.indicators}
        self.assertEqual(metrics['log_return_std'].value, 0)
        self.assertEqual(metrics['rsi'].value, 50)

    def test_naive_offset_bool_nonfinite_and_overflowing_inputs_rejected(self):
        for cutoff in (BASE.replace(tzinfo=None), BASE.astimezone(timezone(timedelta(hours=1))), True):
            with self.assertRaises(AnalystError):
                evaluate(fixture(), cutoff=cutoff)
        for changes in ({'count': True}, {'minutes': True}, {'count': 4097},
                        {'base_price': Decimal('NaN')}, {'step': Decimal('Infinity')},
                        {'half_range': 0.01}, {'start': BASE.replace(tzinfo=None)},
                        {'availability_lag_seconds': -1}):
            with self.subTest(changes=changes), self.assertRaises(AnalystError):
                FixtureRecipe(start=BASE, **changes) if 'start' not in changes else FixtureRecipe(**changes)

    def test_stale_boundary_is_explicit_and_does_not_use_host_clock(self):
        cutoff = BASE + timedelta(hours=81)
        self.assertEqual(assessment(cutoff=cutoff).status, 'COMPLETE')
        result = assessment(cutoff=cutoff + timedelta(microseconds=1))
        self.assertEqual(result.status, 'STALE_DATA')
        self.assertEqual(result.quality.age_seconds, Decimal('3600.000001'))

    def test_all_future_or_unavailable_input_is_insufficient(self):
        data = fixture(80, availability_lag_seconds=86400)
        result = assessment(data, cutoff=BASE + timedelta(hours=1))
        self.assertEqual(result.status, 'INSUFFICIENT_DATA')
        self.assertEqual(result.quality.evaluated_bars, 0)
        self.assertIsNone(result.available_at)

    def test_late_interior_bar_is_not_silently_skipped_to_use_later_bars(self):
        source = fixture()
        late = replace(source.bars[20], available_at=BASE + timedelta(days=9))
        data = replace(source, bars=source.bars[:20] + (late,) + source.bars[21:])
        result = assessment(data)
        self.assertEqual(result.status, 'VALIDATION_ERROR')
        self.assertIn('MA_MISSING_BARS', result.quality.reasons)

    def test_forged_contract_authority_versions_or_inconclusive_regime_rejected(self):
        result = assessment()
        for mutate in (
            lambda d: d['authority'].update(execution_authorized=True),
            lambda d: d['source'].update(provider_authenticated=True),
            lambda d: d.update(engine_version='forged'),
            lambda d: d.update(policy_sha256='0' * 64),
            lambda d: d.update(status='VALIDATION_ERROR'),
            lambda d: d.update(cutoff=BASE.isoformat()),
        ):
            doc = result.to_dict()
            mutate(doc)
            with self.assertRaises(AnalystError):
                MarketAssessment.from_json(json.dumps(doc))

    def test_policy_binds_thresholds_and_resource_bounds(self):
        source = fixture()
        result = assessment(source, policy=Policy(max_bars=79))
        self.assertEqual(result.status, 'VALIDATION_ERROR')
        self.assertIn('MA_BAR_LIMIT', result.quality.reasons)
        self.assertNotEqual(assessment().to_json(), assessment(policy=Policy(version='v1b')).to_json())

    def test_leading_and_trailing_missing_bars_are_counted_against_recipe(self):
        source = fixture()
        for bars in (source.bars[1:], source.bars[:-1]):
            result = assessment(replace(source, bars=bars))
            self.assertEqual(result.status, 'VALIDATION_ERROR')
            self.assertEqual(result.quality.missing_bars, 1)
            self.assertIn('MA_MISSING_BARS', result.quality.reasons)

    def test_extreme_bar_timestamp_is_a_structured_validation_error(self):
        source = fixture()
        bar = replace(source.bars[-1], opened_at=datetime.max.replace(tzinfo=timezone.utc))
        result = assessment(replace(source, bars=source.bars[:-1] + (bar,)))
        self.assertEqual(result.status, 'VALIDATION_ERROR')
        self.assertIn('MA_BAR_TIME_RANGE', result.quality.reasons)

    def test_decimal_validation_does_not_depend_on_callers_rounding_traps(self):
        source = fixture(step=Decimal('0.0001234567890123456789'))
        expected = assessment(source).to_json()
        with localcontext() as context:
            context.prec = 6
            context.traps[Inexact] = True
            actual = assessment(source).to_json()
        self.assertEqual(expected, actual)

    def test_indicator_units_and_ranges_cannot_be_forged(self):
        result = assessment()
        values = list(result.indicators)
        rsi_index = next(i for i, item in enumerate(values) if item.name == 'rsi')
        with self.assertRaises(AnalystError):
            replace(values[rsi_index], value=Decimal('101'))
        values[0] = replace(values[0], unit='DIMENSIONLESS')
        with self.assertRaises(AnalystError):
            replace(result, indicators=tuple(values))

    def test_future_prices_or_future_identity_do_not_change_historical_document(self):
        data = fixture(100)
        cutoff = BASE + timedelta(hours=60)
        extreme = replace(data.bars[-1], open=Decimal('90'), high=Decimal('100'),
                          low=Decimal('80'), close=Decimal('95'))
        changed = replace(data, bars=data.bars[:-1] + (extreme,))
        self.assertEqual(assessment(data, cutoff=cutoff).to_json(),
                         assessment(changed, cutoff=cutoff).to_json())

    def test_maximum_supported_capture_is_bounded_and_serializable(self):
        source = fixture(4096, pattern='ALTERNATING')
        result = assessment(source, cutoff=BASE + timedelta(hours=4096))
        self.assertEqual(result.status, 'COMPLETE')
        self.assertEqual(result.quality.evaluated_bars, 4096)
        self.assertLess(len(result.to_json()), 131072)

    def test_unpaired_surrogate_json_is_rejected_with_fixed_error(self):
        with self.assertRaises(AnalystError):
            Policy.from_json('\ud800')

    def test_complete_contract_requires_a_complete_fresh_period(self):
        result = assessment()
        for changes in (
            {'quality': replace(result.quality, missing_bars=1)},
            {'quality': replace(result.quality, age_seconds=Decimal('9000'))},
            {'window_start': None, 'window_end': None, 'last_closed_at': None, 'available_at': None},
        ):
            with self.subTest(changes=changes), self.assertRaises(AnalystError):
                replace(result, **changes)


if __name__ == '__main__':
    unittest.main()
