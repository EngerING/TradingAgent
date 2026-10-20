from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
import unittest

from trading_agent.market_analyst.contracts import Instrument, MarketAssessment, Policy
from trading_agent.market_analyst.fixtures import FixtureRecipe, make_fixture
from trading_agent.market_analyst.evaluator import evaluate

BASE = datetime(2026, 1, 5, tzinfo=timezone.utc)


def fixture(count=80, **changes):
    return make_fixture(FixtureRecipe(start=BASE, count=count, **changes))


def assessment(data=None, **kwargs):
    data = fixture() if data is None else data
    return evaluate(data, cutoff=kwargs.pop('cutoff', BASE + timedelta(hours=80)), **kwargs)


class EvaluationTests(unittest.TestCase):
    def test_three_trends_and_three_volatility_regimes(self):
        for pattern, expected in (('RISING', 'UPTREND'), ('FALLING', 'DOWNTREND'),
                                  ('FLAT', 'SIDEWAYS')):
            result = assessment(fixture(pattern=pattern))
            self.assertEqual(result.status, 'COMPLETE')
            self.assertEqual(result.trend, expected)
            self.assertFalse(result.authority.execution_authorized)
        for width, expected in (('0.0001', 'LOW'), ('0.0005', 'NORMAL'), ('0.01', 'HIGH')):
            result = assessment(fixture(pattern='FLAT', half_range=Decimal(width)))
            self.assertEqual(result.volatility, expected)

    def test_short_series_preserves_per_indicator_warmup_and_unknown_regime(self):
        for count in (0, 1, 13, 14, 15, 20, 33, 34, 50):
            with self.subTest(count=count):
                result = assessment(fixture(count), cutoff=BASE + timedelta(hours=count))
                self.assertEqual(result.status, 'INSUFFICIENT_DATA')
                self.assertEqual((result.trend, result.volatility), ('UNKNOWN', 'UNKNOWN'))
                values = {i.name: i for i in result.indicators}
                self.assertEqual(values['rsi'].warmup_bars, 15)
                self.assertEqual(values['ema_slow_slope'].warmup_bars, 51)
                self.assertEqual(values['macd_signal'].warmup_bars, 34)
                self.assertEqual(values['rsi'].value is None, count < 15)
                self.assertEqual(values['atr'].value is None, count < 14)

    def test_future_extension_cannot_change_any_historical_bytes(self):
        cutoff = BASE + timedelta(hours=60)
        before = assessment(fixture(60), cutoff=cutoff)
        after = assessment(fixture(100), cutoff=cutoff)
        self.assertEqual(before.to_json(), after.to_json())
        self.assertLessEqual(after.available_at, cutoff)
        self.assertEqual(after.quality.evaluated_bars, 60)

    def test_bar_availability_is_distinct_from_close(self):
        data = fixture(80, availability_lag_seconds=120)
        cutoff = BASE + timedelta(hours=80)
        result = assessment(data, cutoff=cutoff)
        self.assertEqual(result.last_closed_at, cutoff - timedelta(hours=1))
        self.assertEqual(result.available_at, cutoff - timedelta(minutes=58))
        self.assertEqual(result.quality.age_seconds, Decimal('3600'))

    def test_stale_means_unknown_even_with_complete_indicators(self):
        result = assessment(cutoff=BASE + timedelta(hours=82))
        self.assertEqual(result.status, 'STALE_DATA')
        self.assertIn('MA_STALE_BAR', result.quality.reasons)
        self.assertEqual(result.trend, 'UNKNOWN')

    def test_duplicate_gap_and_reordering_rejected_without_sort_or_fill(self):
        original = fixture()
        cases = (
            (original.bars[:30] + original.bars[31:], 'MA_MISSING_BARS'),
            (original.bars[:30] + original.bars[29:], 'MA_DUPLICATE_BAR'),
            (original.bars[:30] + (original.bars[31], original.bars[30]) + original.bars[32:],
             'MA_BAR_ORDER'),
        )
        for bars, reason in cases:
            with self.subTest(reason=reason):
                result = assessment(replace(original, bars=bars))
                self.assertEqual(result.status, 'VALIDATION_ERROR')
                self.assertIn(reason, result.quality.reasons)
                self.assertTrue(all(i.value is None for i in result.indicators))

    def test_instrument_timeframe_and_contract_mismatch(self):
        gbp = Instrument('GBP/USD', 'fixture-GBPUSD-MID-v1', 'USD_PER_GBP')
        data = fixture()
        for kwargs, reason in (({'instrument': gbp}, 'MA_INSTRUMENT_MISMATCH'),
                               ({'minutes': 15}, 'MA_TIMEFRAME_MISMATCH')):
            result = assessment(data, **kwargs)
            self.assertEqual(result.status, 'VALIDATION_ERROR')
            self.assertIn(reason, result.quality.reasons)
        changed = replace(data.bars[20], instrument=gbp)
        result = assessment(replace(data, bars=data.bars[:20] + (changed,) + data.bars[21:]))
        self.assertIn('MA_INSTRUMENT_MISMATCH', result.quality.reasons)

    def test_json_or_claimed_authenticity_never_become_fixtures(self):
        for data in ({'source': 'SYNTHETIC_TEST_FIXTURE', 'authenticated': True},
                     {'source': 'IBKR', 'bars': []}, fixture().bars):
            result = evaluate(data, cutoff=BASE)
            self.assertEqual(result.status, 'UNVERIFIED_PROVENANCE')
            self.assertFalse(result.source.provider_authenticated)
            self.assertIsNone(result.source.data_sha256)
        result = evaluate(None, cutoff=BASE)
        self.assertEqual(result.status, 'SOURCE_UNAVAILABLE')

    def test_result_serialization_and_determinism_under_decimal_context(self):
        first = assessment()
        self.assertEqual(MarketAssessment.from_json(first.to_json()), first)
        with localcontext() as context:
            context.prec = 6
            again = assessment()
        self.assertEqual(first.to_json(), again.to_json())

    def test_all_supported_timeframes_and_gbp_have_explicit_units(self):
        gbp = Instrument('GBP/USD', 'fixture-GBPUSD-MID-v1', 'USD_PER_GBP')
        for minutes in (15, 60, 240):
            data = fixture(minutes=minutes, instrument=gbp)
            result = assessment(data, minutes=minutes, instrument=gbp,
                                cutoff=BASE + timedelta(minutes=80 * minutes))
            self.assertEqual(result.status, 'COMPLETE')
            self.assertEqual(result.indicators[0].unit, 'USD_PER_GBP')


if __name__ == '__main__':
    unittest.main()
