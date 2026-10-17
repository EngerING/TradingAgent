import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from trading_agent.progressive_risk_research import (
    choose, commission_only_upper_bound, cost_evidence, date, selection_checks,
    uncertainty, walk_forward, wilson,
)


ROOT = Path(__file__).resolve().parents[2]


def strong_evidence():
    metrics = dict(admitted=200, winRate=.95, netPnl=200, netExpectancy=1,
                   netProfitFactor=4, intrabarDrawdownBound=.05, meanQuantity=80)
    ci = dict(sample_trade_days=40, win_wilson_family_adjusted=[.85, .99],
              block_bootstrap_win_ci=[.86, .99], block_bootstrap_expectancy_ci=[.2, 2])
    folds = [dict(metrics=dict(admitted=60, netPnl=50)) for _ in range(3)]
    return metrics, ci, folds


class ProgressiveRiskStatisticsTests(unittest.TestCase):
    def test_empty_sample_is_unknown_not_success(self):
        self.assertIsNone(wilson(0, 0))
        ci = uncertainty([], 'empty')
        self.assertEqual(0, ci['sample_trades'])
        self.assertIsNone(ci['win_wilson_family_adjusted'])
        self.assertIsNone(ci['block_bootstrap_expectancy_ci'])

    def test_family_interval_is_wider_than_single_comparison(self):
        ordinary = wilson(95, 100)
        simultaneous = wilson(95, 100, .05 / 24)
        self.assertLess(simultaneous[0], ordinary[0])
        self.assertGreater(simultaneous[1], ordinary[1])
        self.assertAlmostEqual(.9630065, wilson(100, 100)[0], places=6)

    def test_invalid_samples_rejected(self):
        for wins, n, alpha in [(2, 1, .05), (-1, 2, .05), (0, -1, .05), (1, 1, 0)]:
            with self.subTest(wins=wins, n=n, alpha=alpha), self.assertRaises(ValueError):
                wilson(wins, n, alpha)

    def test_confidence_groups_trades_by_santo_domingo_day(self):
        ci = uncertainty([dict(exitAt='2026-08-05T00:30:00Z', netPnl=1),
                          dict(exitAt='2026-08-04T23:00:00Z', netPnl=-2)], 'local-day')
        self.assertEqual(1, ci['sample_trade_days'])
        self.assertEqual(2, ci['sample_trades'])
        self.assertIsNone(ci['block_bootstrap_win_ci'])

    def test_block_bootstrap_is_reproducible_and_includes_losses(self):
        start = datetime(2026, 8, 4, 12, tzinfo=timezone.utc)
        trades = [dict(exitAt=(start + timedelta(days=i)).isoformat(), netPnl=1 if i % 6 else -3)
                  for i in range(40)]
        a = uncertainty(trades, 'fixed-study', repetitions=300)
        self.assertEqual(a, uncertainty(trades, 'fixed-study', repetitions=300))
        self.assertLess(a['block_bootstrap_win_ci'][1], 1)
        self.assertLess(a['block_bootstrap_expectancy_ci'][0], 1)

    def test_walk_forward_uses_past_only_expanding_training(self):
        split = dict(start='2026-04-03T00:00:00Z', validation_start='2026-08-03T00:00:00Z',
                     end='2026-10-03T00:00:00Z')
        folds = walk_forward(split)
        self.assertEqual(3, len(folds))
        self.assertEqual(date(split['validation_start']), date(folds[0]['test_start']))
        self.assertEqual(date(split['end']), date(folds[-1]['test_end']))
        for i, fold in enumerate(folds):
            self.assertEqual(timedelta(minutes=15), date(fold['test_start']) - date(fold['training_end']))
            self.assertFalse(fold['parameters_refitted'])
            if i:
                self.assertEqual(folds[i-1]['test_end'], fold['test_start'])
                self.assertGreater(date(fold['training_end']), date(folds[i-1]['training_end']))

    def test_walk_forward_rejects_invalid_partition(self):
        with self.assertRaisesRegex(ValueError, 'INVALID_FROZEN_SPLIT'):
            walk_forward(dict(start='2026-08-04T00:00:00Z', validation_start='2026-08-03T00:00:00Z',
                              end='2026-10-03T00:00:00Z'))

    def test_optimistic_target_bound_still_funds_fees_from_own_equity(self):
        s = dict(reasons=[], entryAt='2026-08-04T12:00:00Z', signalAt='2026-08-04T11:45:00Z',
                 entryMidpoint='1.2', takeProfitDistance='.002')
        b = commission_only_upper_bound([s], dict(openingCommission='2', closingCommission='2'))
        self.assertEqual(80, b['best_target_bound']['quantity_eur'])
        self.assertEqual(96, b['best_target_bound']['notional_usd'])
        self.assertAlmostEqual(-3.84, b['best_target_bound']['net_target_usd'])
        self.assertFalse(b['execution_authorized'])

    def test_no_trade_not_in_target_bound(self):
        b = commission_only_upper_bound([dict(reasons=['NO_TRADE'], entryAt=None)],
                                       dict(openingCommission='2', closingCommission='2'))
        self.assertEqual(0, b['eligible_signals'])
        self.assertIsNone(b['best_target_bound'])


class ProgressiveRiskSelectionTests(unittest.TestCase):
    def test_selects_lowest_risk_only_after_all_gates(self):
        m, ci, folds = strong_evidence()
        gate = selection_checks(m, ci, folds, broker_verified=True, fresh_holdout=True)
        self.assertTrue(gate['eligible_for_further_review'])
        rows = [dict(strategy='trend', riskFraction=.15, metrics=dict(m, netExpectancy=50), selection=gate),
                dict(strategy='pullback', riskFraction=.05, metrics=m, selection=gate)]
        picked = choose(rows)
        self.assertEqual(5, picked['risk_percent'])
        self.assertEqual('pullback', picked['strategy'])
        self.assertFalse(picked['execution_authorized'])

    def test_no_candidate_is_not_forced(self):
        r = choose([])
        self.assertEqual('NO_VIABLE_STRATEGY_FOUND', r['status'])
        self.assertIsNone(r['strategy'])
        self.assertIsNone(r['risk_percent'])
        self.assertEqual(0, r['quantity'])

    def test_high_win_rate_cannot_hide_negative_expectancy(self):
        m, ci, folds = strong_evidence()
        m.update(netPnl=-100, netExpectancy=-.5)
        gate = selection_checks(m, ci, folds, True, True)
        self.assertFalse(gate['eligible_for_further_review'])
        self.assertIn('NET_EXPECTANCY_NOT_POSITIVE', gate['reasons'])

    def test_unknown_broker_and_examined_holdout_block_otherwise_good_results(self):
        m, ci, folds = strong_evidence()
        gate = selection_checks(m, ci, folds)
        self.assertEqual(['IBKR_EXECUTABILITY_UNKNOWN',
                          'PREVIOUSLY_EXAMINED_HOLDOUT_REQUIRES_NEW_CONFIRMATION'], gate['reasons'])
        self.assertFalse(gate['execution_authorized'])
        self.assertFalse(gate['live_approved'])

    def test_sample_confidence_and_every_fold_must_pass(self):
        m, ci, folds = strong_evidence()
        m.update(admitted=5, winRate=.8)
        ci.update(sample_trade_days=2, win_wilson_family_adjusted=[.4, .99])
        folds[1]['metrics']['netPnl'] = -1
        reasons = selection_checks(m, ci, folds, True, True)['reasons']
        for reason in ['INSUFFICIENT_OOS_TRADES', 'INSUFFICIENT_OOS_TRADING_DAYS',
                       'NET_WIN_RATE_NOT_ABOVE_80_PERCENT', 'WALK_FORWARD_EVIDENCE_INSUFFICIENT',
                       'WIN_RATE_CONFIDENCE_INSUFFICIENT_WIN_WILSON_FAMILY_ADJUSTED']:
            self.assertIn(reason, reasons)


class ProgressiveRiskEvidenceTests(unittest.TestCase):
    def diagnostic(self, directory):
        path = Path(directory) / 'artifacts/paper-lab/data-diagnostics.json'
        path.parent.mkdir(parents=True)
        owned = dict(state='CLOSED', category='PAPER_DIAGNOSTIC', fills={}, commissions={}, net_pnl='-999')
        for side in ('BUY', 'SELL'):
            owned['fills'][side] = dict(side=side, quantity='100')
            owned['commissions'][side] = dict(amount='2', currency='USD', at='2026-10-06T00:00:00Z')
        d = dict(owned_orders=dict(original=owned), quote=dict(bid='1.1', ask='1.10001', at='2026-10-06T00:00:00Z'),
                 contract=dict(minimum_size_metadata='.01', size_increment_metadata='.01'))
        path.write_text(json.dumps(d), encoding='utf-8')
        return path, d

    def test_observed_fees_are_separate_from_strategy_pnl(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'artifacts/test-results') as directory:
            self.diagnostic(directory)
            costs, evidence = cost_evidence(Path(directory), dict(spread_values=['.00001', '.0001']))
        self.assertEqual('2', costs['openingCommission'])
        self.assertEqual('2', costs['closingCommission'])
        self.assertEqual('0.0001', costs['spread'])
        self.assertFalse(evidence['borrowed_strategy_results'])
        self.assertNotIn('net_pnl', str(evidence))
        self.assertTrue(evidence['margin_status'].startswith('UNKNOWN'))

    def test_missing_or_unclosed_fee_evidence_fails_closed(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'artifacts/test-results') as directory:
            path, d = self.diagnostic(directory)
            d['owned_orders']['original']['commissions']['SELL']['currency'] = 'EUR'
            path.write_text(json.dumps(d), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'OBSERVED_PAPER_ROUND_TRIP_FEES_REQUIRED'):
                cost_evidence(Path(directory), dict(spread_values=[]))
            d['owned_orders']['original']['state'] = 'OPEN'
            path.write_text(json.dumps(d), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'OBSERVED_PAPER_ROUND_TRIP_FEES_REQUIRED'):
                cost_evidence(Path(directory), dict(spread_values=[]))

    def payload(self):
        return dict(environment='SIMULATION', capital=100, lossAllowance=20, exposure=1,
                    liveEnabled=False, executionAuthorized=False, strategy='trend', bars=[], signals=[], exits=[],
                    costs=dict(spread='.00005', openingCommission='2', closingCommission='2',
                               commissionPerUnitRoundTrip='0', slippage='.00045', adverseGap='.00005',
                               minimumQuantity='.01', quantityStep='.01', marginRate='1', source='TEST_ONLY'))

    def invoke(self, payload):
        dll = ROOT / 'src/TradingAgent.ResearchLab/bin/Debug/net9.0/TradingAgent.ResearchLab.dll'
        r = subprocess.run(['dotnet', str(dll)], input=json.dumps(payload), capture_output=True,
                           text=True, cwd=ROOT, timeout=30)
        return r.returncode, json.loads(r.stdout)

    def test_standalone_rejects_operational_permissions_and_fictitious_capital(self):
        for field, value in [('capital', 1000000), ('exposure', 5), ('liveEnabled', True),
                             ('executionAuthorized', True), ('environment', 'PAPER_TRADING')]:
            p = copy.deepcopy(self.payload()); p[field] = value
            with self.subTest(field=field):
                code, result = self.invoke(p)
                self.assertNotEqual(0, code)
                self.assertEqual('ISOLATED_RESEARCH_SCOPE_REQUIRED', result['reason'])
                self.assertEqual(0, result['ordersSent'])
                self.assertFalse(result['liveEnabled'])

    def test_standalone_runs_only_fixed_eight_offline_rates(self):
        code, result = self.invoke(self.payload())
        self.assertEqual(0, code)
        self.assertEqual([.01, .02, .03, .05, .075, .1, .125, .15], [x['riskFraction'] for x in result])
        for row in result:
            self.assertFalse(row['executionAuthorized'])
            self.assertFalse(row['liveEnabled'])
            self.assertEqual(100, row['metrics']['finalEquity'])
            self.assertIsNone(row['metrics']['winRate'])


if __name__ == '__main__':
    unittest.main()
