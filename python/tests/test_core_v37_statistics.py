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
