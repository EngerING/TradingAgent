"""Independent arithmetic and conditional inference examples."""
from decimal import Decimal as D
import unittest

from trading_agent.core_v3.statistical_validation.statistics import describe, bootstrap
from trading_agent.core_v3.statistical_validation.contracts import Dependence


class StatisticsTests(unittest.TestCase):
    def test_net_metrics_include_costs_and_undefined_values(self):
        value = describe((D('2'), D('-1'), D('0')), (D('3'), D('0'), D('1')), 'USD')
        self.assertEqual((3, 1, 1, 1), (value.trades, value.winners, value.losers, value.breakeven))
        self.assertEqual(D('1'), value.net.amount)
        self.assertEqual(D('3'), value.costs.amount)
        self.assertEqual(D('2'), value.profit_factor)
        self.assertEqual(D('0.333333333333'), value.expectancy)
        self.assertIsNone(describe((), (), 'USD').profit_factor)
        self.assertIsNone(describe((D('1'),), (D('2'),), 'USD').profit_factor)

    def test_bootstrap_requires_independence_not_exchangeability(self):
        value = bootstrap((D('1'), D('2'), D('3')), dependence=Dependence.UNKNOWN,
                          seed=7, replicas=200, confidence_bps=9000, family_size=1)
        self.assertIsNone(value.lower)
        self.assertIsNone(value.independent_units)

    def test_seeded_window_bootstrap_and_declared_family_resolution(self):
        kwargs = dict(dependence=Dependence.IID_WINDOW_BLOCKS_ASSUMED, seed=7,
                      replicas=200, confidence_bps=9000, family_size=1)
        first = bootstrap((D('-1'), D('2'), D('3')), **kwargs)
        self.assertEqual(first, bootstrap((D('-1'), D('2'), D('3')), **kwargs))
        self.assertEqual(3, first.independent_units)
        self.assertLessEqual(first.lower, first.upper)
        kwargs['family_size'] = 256
        self.assertEqual('BOOTSTRAP_RESOLUTION_INSUFFICIENT',
                         bootstrap((D('1'), D('2'), D('3')), **kwargs).reason)

    def test_zero_trades_has_no_winner_rate_expectancy_or_dispersion(self):
        result = describe((), (), 'EUR')
        self.assertEqual(D(0), result.net.amount)
        self.assertIsNone(result.win_rate)
        self.assertIsNone(result.expectancy)
        self.assertIsNone(result.sample_stddev)

    def test_realized_reward_risk_dispersion_and_extreme_sensitivity(self):
        result = describe((D('2'), D('-2'), D('20')), (D('3'), D('-1'), D('21')), 'USD')
        self.assertEqual(D('5.5'), result.realized_reward_risk)
        self.assertEqual(D(0), result.without_largest_absolute_trade)
        self.assertGreater(result.sample_stddev, D(10))

    def test_costs_cannot_be_negative_and_samples_are_bounded(self):
        from trading_agent.core_v3.contracts import ContractError
        for net, gross in (((D('1'),), (D('0'),)), ((D(0),)*257, (D(0),)*257)):
            with self.assertRaises(ContractError):
                describe(net, gross, 'USD')

    def test_ambient_decimal_precision_does_not_change_statistics(self):
        from decimal import localcontext
        expected = describe((D('.0322'), D('-1.2678')), (D('1.04'), D('-.26')), 'USD')
        with localcontext() as context:
            context.prec = 3
            actual = describe((D('.0322'), D('-1.2678')), (D('1.04'), D('-.26')), 'USD')
        self.assertEqual(expected, actual)
