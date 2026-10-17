"""Synthetic scenarios only. No effective broker costs or trading authority."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import unittest

from trading_agent.forex_research.economics import assess

AT = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)


def context():
    return dict(
        schema='FOREX_ECONOMIC_CONTEXT_V1', source='SYNTHETIC_TEST_ONLY',
        evidence_id='synthetic-scenario-1', observed_at=AT.isoformat(),
        valid_until=(AT + timedelta(seconds=30)).isoformat(),
        mid_usd_per_eur='1.10', equity_usd='100', free_margin_usd='100',
        remaining_risk_usd='10', remaining_exposure_usd='100',
        liquidity_quantity_eur='100', minimum_quantity_eur='1',
        quantity_step_eur='1', initial_margin_fraction='1',
        minimum_net_profit_usd='0.01', gap_reserve_usd='1',
        costs=dict(status='ESTIMATED_RESEARCH_ONLY', evidence_id='synthetic-fees',
                   valid_until=(AT + timedelta(minutes=5)).isoformat(),
                   opening_min_usd='0.50', closing_min_usd='0.50',
                   opening_per_eur_usd='0', closing_per_eur_usd='0',
                   spread_usd_per_eur='0.0002',
                   slippage_per_side_usd_per_eur='0.0001', financing_usd='0.10'))


def plan(direction='LONG'):
    return dict(schema='FOREX_ECONOMIC_PLAN_V1', evidence_id='synthetic-scenario-1',
                direction=direction, quantity_eur='50', entry_mid_usd_per_eur='1.10',
                stop_mid_usd_per_eur='1.08' if direction == 'LONG' else '1.12',
                target_mid_usd_per_eur='1.14' if direction == 'LONG' else '1.06')


class EconomicsTests(unittest.TestCase):
    def test_long_and_short_apply_each_cost_once(self):
        for side in ('LONG', 'SHORT'):
            with self.subTest(side=side):
                result = assess(context(), plan(side), now=AT)
                self.assertTrue(result['admitted'], result)
                self.assertEqual('1.1200', result['metrics']['round_trip_cost_usd'])
                self.assertEqual(Decimal('0.88'), Decimal(result['metrics']['net_target_usd']))
                self.assertEqual(Decimal('3.12'), Decimal(result['metrics']['stop_loss_with_costs_usd']))
                self.assertFalse(result['execution_authority'])

    def test_commission_exhausting_target_blocks_even_with_affordable_stop(self):
        c = context()
        c['costs'].update(opening_min_usd='2', closing_min_usd='2')
        result = assess(c, plan(), now=AT)
        self.assertIn('NONPOSITIVE_NET_TARGET', result['reasons'])
        self.assertFalse(result['admitted'])

    def test_zero_net_target_and_positive_below_minimum_are_rejected(self):
        c = context()
        c['costs'].update(opening_min_usd='1.88', closing_min_usd='0')
        self.assertIn('NONPOSITIVE_NET_TARGET', assess(c, plan(), now=AT)['reasons'])
        c = context()
        c['minimum_net_profit_usd'] = '1'
        self.assertIn('NET_PROFIT_BELOW_MINIMUM', assess(c, plan(), now=AT)['reasons'])

    def test_unknown_costs_never_become_zero(self):
        for field in context()['costs']:
            with self.subTest(field=field):
                c = context()
                c['costs'][field] = None
                self.assertFalse(assess(c, plan(), now=AT)['admitted'])
        c = context()
        c['costs']['status'] = 'UNKNOWN'
        self.assertIn('COSTS_UNKNOWN', assess(c, plan(), now=AT)['reasons'])

    def test_limits_quantity_geometry_and_reference_are_enforced(self):
        changes = [('free_margin_usd', '10', 'MARGIN_INSUFFICIENT'),
                   ('remaining_risk_usd', '2', 'RISK_BUDGET_EXCEEDED'),
                   ('remaining_exposure_usd', '50', 'EXPOSURE_EXCEEDED'),
                   ('liquidity_quantity_eur', '49', 'LIQUIDITY_EXCEEDED')]
        for field, value, reason in changes:
            c = context()
            c[field] = value
            self.assertIn(reason, assess(c, plan(), now=AT)['reasons'])
        for field, value in [('quantity_eur', '0.5'), ('quantity_eur', '50.5'),
                             ('stop_mid_usd_per_eur', '1.11'),
                             ('target_mid_usd_per_eur', '1.09'),
                             ('entry_mid_usd_per_eur', '1.12'),
                             ('evidence_id', 'other')]:
            p = plan()
            p[field] = value
            self.assertFalse(assess(context(), p, now=AT)['admitted'])

    def test_invalid_numbers_missing_fields_and_technical_exception_fail_closed(self):
        for value in (None, True, 1.1, 'NaN', 'Infinity', '-1', '1e999999'):
            c = context()
            c['equity_usd'] = value
            self.assertFalse(assess(c, plan(), now=AT)['admitted'])
        c = context()
        del c['gap_reserve_usd']
        self.assertFalse(assess(c, plan(), now=AT)['admitted'])
        c = context()
        c['purpose'] = 'TECHNICAL_VALIDATION'
        self.assertFalse(assess(c, plan(), now=AT)['admitted'])

    def test_expired_future_naive_or_overlong_snapshot_is_rejected(self):
        for field, value in [('valid_until', AT.isoformat()),
                             ('observed_at', (AT + timedelta(seconds=1)).isoformat()),
                             ('observed_at', AT.replace(tzinfo=None).isoformat()),
                             ('valid_until', (AT + timedelta(days=1)).isoformat())]:
            c = context()
            c[field] = value
            self.assertFalse(assess(c, plan(), now=AT)['admitted'])
        c = context()
        c['costs']['valid_until'] = AT.isoformat()
        self.assertFalse(assess(c, plan(), now=AT)['admitted'])

    def test_current_equity_is_dynamic_and_inputs_are_not_mutated(self):
        c, p = context(), plan()
        saved = deepcopy((c, p))
        original = assess(c, p, now=AT)
        self.assertEqual(saved, (c, p))
        c['equity_usd'] = '120'
        changed = assess(c, p, now=AT)
        self.assertTrue(changed['admitted'])
        self.assertNotEqual(original['input_sha256'], changed['input_sha256'])


if __name__ == '__main__':
    unittest.main()
