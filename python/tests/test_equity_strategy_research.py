from datetime import datetime,timedelta,timezone
from decimal import Decimal
import unittest
from unittest.mock import patch
from trading_agent.equity_strategy_research import (Ledger,RATES,FAMILY_TESTS,FAMILIES,
    commission,costs,size,validated_bars,signals,features,exit_price,simulate,candidate_versions,evidence_checks)


def bars(n=80):
    start=datetime(2026,8,3,13,30,tzinfo=timezone.utc)
    return [dict(opened_at=(start+timedelta(hours=i)).isoformat(),closed_at=(start+timedelta(hours=i+1)).isoformat(),
        open=10.,high=10.4,low=9.8,close=10.,volume=1000.,minutes=60) for i in range(n)]


class EquityStrategyResearchTests(unittest.TestCase):
    def test_separate_frozen_versions_and_exact_risk_grid(self):
        self.assertEqual((1,2,3,5,7.5,10,12.5,15),RATES);self.assertEqual(192,FAMILY_TESTS)
        vs=candidate_versions();self.assertEqual(set(FAMILIES),set(vs));self.assertEqual(vs,candidate_versions())
        self.assertEqual(4,len(set(vs.values())));self.assertTrue(all(len(v)==64 for v in vs.values()))

    def test_commission_minimum_cap_and_extra_fee_reserve(self):
        self.assertEqual(Decimal('.38'),commission(1,50,'TIERED_BASE'))
        self.assertEqual(Decimal('.13'),commission(1,10,'TIERED_BASE'))
        self.assertEqual(Decimal('1.03'),commission(1,200,'FIXED_FEE_STRESS'))
        with self.assertRaises(ValueError):commission(0,50,'TIERED_BASE')

    def test_whole_share_sizing_never_uses_paper_million_or_fractional_fallback(self):
        l=Ledger();p,why=size(200,198,210,15,l,'TIERED_BASE',None)
        self.assertIsNone(p);self.assertIn('WHOLE_SHARE',why)
        p,_=size(10,9,12,15,l,'TIERED_BASE',None)
        self.assertIsNotNone(p);self.assertIsInstance(p['quantity'],int)
        self.assertLessEqual(p['notional'],100);self.assertLessEqual(p['risk'],15)
        with self.assertRaises(ValueError):size(10,9,12,16,l,'TIERED_BASE',None)

    def test_costs_and_gap_are_inside_risk_and_target_filter(self):
        l=Ledger();p,_=size(10,9,12,15,l,'TIERED_BASE',None)
        q=p['quantity'];expected=q*(1+p['spread']+2*p['slippage_each']+p['gap_reserved']+2*p['rounding_reserve_each'])+p['fees_reserved']
        self.assertAlmostEqual(expected,p['risk']);self.assertGreater(p['target_net'],0)
        self.assertIsNone(size(10,9,10.01,15,l,'TIERED_BASE',None)[0])
        self.assertIsNone(size(10,9,12,1,l,'TIERED_BASE',None)[0])

    def test_stress_does_not_hide_spread_slippage_or_gap(self):
        base=costs(10,'TIERED_BASE',.002);stress=costs(10,'TIERED_SPREAD_SLIPPAGE_STRESS',.002)
        self.assertEqual(2*base[0],stress[0]);self.assertEqual(3*base[1],stress[1]);self.assertEqual(2*base[2],stress[2])

    def test_win_loss_and_break_even_day_policy_uses_santo_domingo(self):
        l=Ledger();t='2026-08-04T03:59:00Z'
        l.begin('a',10);l.settle('a',4,14,t,'2026-08-04');self.assertIsNone(l.gate(t))
        l.begin('b',10);l.settle('b',-3,7,t,'2026-08-04');self.assertEqual('DAILY_FIRST_LOSS_STOP',l.gate(t))
        self.assertIsNone(l.gate('2026-08-04T04:00:00Z'))
        l.begin('c',10);l.settle('c',0,10,'2026-08-04T04:01:00Z','2026-08-05')
        self.assertEqual('DAILY_BREAK_EVEN_STOP',l.gate('2026-08-04T05:00:00Z'))

    def test_pending_commission_partial_or_uncertain_result_never_counts_as_win(self):
        l=Ledger();l.begin('a',20)
        self.assertFalse(l.settle('a',5,25,'2026-08-03T15:00:00Z','2026-08-04',definitive=False))
        self.assertEqual(Decimal('100'),l.equity)
        self.assertEqual('PREVIOUS_TRADE_NOT_RECONCILED',l.gate('2026-08-04T15:00:00Z'))
        with self.assertRaises(ValueError):l.begin('b',1)
        with self.assertRaises(ValueError):l.settle('unknown',0,20,'2026-08-03T15:00:00Z',None)

    def test_snapshot_keeps_consumed_loss_and_pending_inventory_after_restart(self):
        l=Ledger();l.begin('a',20);l.settle('a',-10,10,'2026-08-03T15:00:00Z','2026-08-04')
        l=Ledger(l.snapshot());self.assertEqual('DAILY_FIRST_LOSS_STOP',l.gate('2026-08-03T16:00:00Z'))
        l.begin('b',10);l.settle('b',20,30,'2026-08-04T15:00:00Z','2026-08-05')
        self.assertEqual(Decimal('10'),l.consumed);self.assertEqual(Decimal('110'),l.equity)
        l.begin('c',10);l=Ledger(l.snapshot());self.assertEqual('PREVIOUS_TRADE_NOT_RECONCILED',l.gate('2026-08-05T15:00:00Z'))

    def test_t_plus_one_does_not_make_winning_proceeds_available_same_day(self):
        l=Ledger();l.begin('a',90);l.settle('a',5,95,'2026-08-07T15:00:00Z','2026-08-10')
        self.assertEqual(Decimal('10'),l.available('2026-08-07T16:00:00Z'))
        self.assertEqual(Decimal('10'),l.available('2026-08-09T16:00:00Z'))
        self.assertEqual(Decimal('105'),l.available('2026-08-10T13:30:00Z'))
        with self.assertRaises(ValueError):l.begin('a',106)

    def test_unknown_settlement_does_not_release_proceeds(self):
        l=Ledger();l.begin('a',90);l.settle('a',5,95,'2026-08-07T15:00:00Z',None)
        self.assertEqual(Decimal('10'),l.available('2026-09-07T15:00:00Z'))

    def test_total_loss_budget_survives_new_days_and_wins_do_not_restore_it(self):
        l=Ledger()
        for day in (3,4):
            l.begin(str(day),10);l.settle(str(day),-10,0,f'2026-08-0{day}T15:00:00Z',None)
        self.assertEqual('CUMULATIVE_LOSS_OR_CAPITAL_STOP',l.gate('2026-08-05T15:00:00Z'))
        self.assertEqual(Decimal('20'),Ledger(l.snapshot()).consumed)

    def test_features_and_signals_are_causal_under_future_price_changes(self):
        original=bars();changed=bars()
        for row in changed[65:]:row.update(open=100,high=120,low=90,close=110)
        self.assertEqual(features(original)[:65],features(changed)[:65])
        for family in FAMILIES:
            a,_=signals(original,family);b,_=signals(changed,family)
            self.assertEqual([s for s in a if s['index']<65],[s for s in b if s['index']<65])

    def test_bad_overlapping_bars_and_naive_times_fail_closed(self):
        rows=bars(2);rows[1]['opened_at']=rows[0]['opened_at']
        with self.assertRaises(ValueError):validated_bars(rows)
        rows=bars(1);rows[0]['opened_at']='2026-08-03T09:30:00'
        with self.assertRaises(ValueError):validated_bars(rows)

    def test_stop_first_when_bar_touches_target_and_adverse_gap_not_clamped(self):
        rows=bars(2);fs=features(rows);s=dict(stop=9,target=11)
        rows[0].update(high=12,low=8)
        self.assertEqual((0,9,'STOP_FIRST_IF_AMBIGUOUS',rows[0]['closed_at']),exit_price(rows,fs,s,0,'EQ_MEAN_REVERSION_R0'))
        rows[0]['open']=7
        self.assertEqual('STOP_GAP',exit_price(rows,fs,s,0,'EQ_MEAN_REVERSION_R0')[2])
        self.assertEqual(7,exit_price(rows,fs,s,0,'EQ_MEAN_REVERSION_R0')[1])

    def test_rule_exit_uses_previous_closed_features_at_next_open(self):
        rows=bars(3);fs=features(rows);fs[0]['fast']=5;fs[0]['slow']=10
        result=exit_price(rows,fs,dict(stop=9,target=11),0,'EQ_TREND_R0')
        self.assertEqual((1,10.,'RULE_NEXT_OPEN',rows[1]['opened_at']),result)
        self.assertIsNone(exit_price(rows,fs,dict(stop=9,target=11),0,'EQ_MEAN_REVERSION_R0'))

    def test_no_trade_and_missing_exit_are_never_fabricated_winners(self):
        rows=bars(3);s=dict(index=0,entry_index=1,at=rows[0]['closed_at'],stop=9,target=12,indicators={},reason='TEST')
        with patch('trading_agent.equity_strategy_research.signals',return_value=([],features(rows))):
            result=simulate({'TEST':rows},'EQ_MEAN_REVERSION_R0',15,'TIERED_BASE',rows[0]['opened_at'],rows[-1]['closed_at'])
            self.assertEqual(0,result['metrics']['admitted']);self.assertIsNone(result['metrics']['win_rate'])
        with patch('trading_agent.equity_strategy_research.signals',return_value=([s],features(rows))):
            result=simulate({'TEST':rows},'EQ_MEAN_REVERSION_R0',15,'TIERED_BASE',rows[0]['opened_at'],rows[-1]['closed_at'])
            self.assertEqual(0,result['metrics']['admitted']);self.assertIsNotNone(result['metrics']['pending_position'])
            self.assertLess(result['metrics']['settled_cash'],100)

    def test_insufficient_evidence_never_promotes_or_authorizes(self):
        rows=bars(3)
        result=simulate({'TEST':rows},'EQ_TREND_R0',15,'TIERED_BASE',rows[0]['opened_at'],rows[-1]['closed_at'])
        selection=evidence_checks(result,[result]*3)
        self.assertEqual('NO_VIABLE_STRATEGY_FOUND',selection['status']);self.assertFalse(selection['execution_authorized'])
        self.assertIn('INSUFFICIENT_OOS_SAMPLE',selection['reasons']);self.assertFalse(selection['live_approved'])

    def test_precomputed_causal_features_produce_identical_simulation(self):
        rows=bars(80);series={'TEST':rows}
        args=(series,'EQ_TREND_R0',15,'TIERED_BASE',rows[0]['opened_at'],rows[-1]['closed_at'])
        self.assertEqual(simulate(*args),simulate(*args,prepared={'TEST':signals(rows,'EQ_TREND_R0')}))
