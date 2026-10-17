import copy
from decimal import Decimal
import unittest
from trading_agent.ai_strategy_researcher.simulation import (Ledger,size,signals,validated,exit_event,
    simulate,evaluate,commission,wilson,confidence)
from trading_agent.ai_strategy_researcher.contracts import MODELS
from ai_research_fixtures import candidate,bars


class AIStrategySimulationTests(unittest.TestCase):
    def test_audited_fee_reserve_does_not_reduce_legacy_unknown_cost_allowance(self):
        from trading_agent.equity_strategy_research import commission as previous
        for model in MODELS:
            for q,p in [(1,10),(8,12),(1,700)]:self.assertGreaterEqual(commission(q,p,model),previous(q,p,model))

    def test_win_to_continue_first_loss_and_zero_stop_without_quota(self):
        l=Ledger();t='2022-01-04T14:30:00Z'
        for net in (4,3):l.begin(10);l.finish(net,10+net,t,'2022-01-05');self.assertIsNone(l.gate(t))
        l.begin(10);l.finish(-10,0,t,'2022-01-05');self.assertEqual('DAILY_FIRST_LOSS_STOP',l.gate(t))
        l=Ledger();l.begin(10);l.finish(0,10,t,'2022-01-05');self.assertEqual('DAILY_BREAK_EVEN_STOP',l.gate(t))

    def test_first_loss_stops_day_and_santo_domingo_reset_is_not_utc_midnight(self):
        l=Ledger();l.begin(10);l.finish(-2,8,'2022-01-05T03:59:00Z','2022-01-05')
        self.assertEqual('DAILY_FIRST_LOSS_STOP',l.gate('2022-01-05T03:59:59Z'))
        self.assertIsNone(l.gate('2022-01-05T04:00:00Z'))

    def test_pending_cost_or_partial_result_never_counts_as_win(self):
        l=Ledger();l.begin(10)
        self.assertFalse(l.finish(5,15,'2022-01-04T14:30:00Z','2022-01-05',False))
        self.assertEqual(Decimal(100),l.equity);self.assertEqual('PREVIOUS_RESULT_NOT_DEFINITIVE',l.gate('2022-01-06T14:30:00Z'))
        with self.assertRaises(ValueError):l.begin(1)

    def test_gains_do_not_restore_loss_budget_and_funds_require_next_session(self):
        l=Ledger();l.begin(90);l.finish(-10,80,'2022-01-04T14:30:00Z','2022-01-05')
        self.assertEqual(Decimal(10),l.available('2022-01-04T20:00:00Z'))
        self.assertEqual(Decimal(90),l.available('2022-01-05T14:30:00Z'))
        l.begin(20);l.finish(20,40,'2022-01-05T14:30:00Z','2022-01-06');self.assertEqual(Decimal(10),l.losses)
        l.begin(10);l.finish(-10,0,'2022-01-06T14:30:00Z','2022-01-07')
        self.assertEqual('CUMULATIVE_LOSS_STOP',l.gate('2022-01-07T14:30:00Z'))

    def test_sizing_includes_both_fees_spread_slippage_gap_and_never_fractional_leverage(self):
        p,_=size(10,9,13,15,Ledger(),'TIERED_BASE',.002)
        self.assertIsInstance(p['quantity'],int);self.assertLessEqual(p['quantity']*p['paid_entry'],100)
        expected=p['quantity']*(Decimal(1)+p['spread']+2*p['slip']+p['gap']+Decimal('.02'))+p['fees']
        self.assertEqual(expected,p['risk']);self.assertLessEqual(p['risk'],15)
        self.assertIsNone(size(700,690,730,15,Ledger(),'TIERED_BASE')[0])
        self.assertIsNone(size(10,9,10.01,15,Ledger(),'TIERED_BASE')[0])

    def test_no_trade_is_a_rejection_not_a_win(self):
        c=candidate();r=bars(3,'2022-01-04T14:30:00+00:00')
        s=dict(index=0,signal_at=r[0]['opened_at'],stop=9,target=10.01,indicators={})
        result=simulate(r,c,'TIERED_BASE','2022-01-01','2023-01-01',prepared=([s],[{}]*3))
        self.assertEqual(0,result['metrics']['admitted']);self.assertIsNone(result['metrics']['win_rate'])
        self.assertEqual(1,result['metrics']['rejected'])

    def test_ambiguous_bar_stop_first_and_adverse_gap_is_not_clamped(self):
        c=candidate();r=bars(2,'2022-01-04T14:30:00+00:00');s=dict(index=0,stop=9,target=11)
        r[0].update(high=12,low=8)
        self.assertEqual('STOP_FIRST_IF_AMBIGUOUS',exit_event(r,[{}]*2,s,c)[2])
        r[0]['open']=7;self.assertEqual(7,exit_event(r,[{}]*2,s,c)[1])

    def test_signals_cannot_change_when_future_bars_change(self):
        c=candidate();r=bars(100);changed=copy.deepcopy(r)
        for b in changed[80:]:b.update(open=20,high=21,low=19,close=20)
        a,fs=signals(r,c);b,other=signals(changed,c)
        self.assertEqual(fs[:80],other[:80]);self.assertEqual([x for x in a if x['index']<=80],[x for x in b if x['index']<=80])

    def test_actual_gap_loss_exceeding_planned_budget_is_recorded_and_stops_day(self):
        c=candidate();c['risk_percent']=3;r=bars(2,'2022-01-04T14:30:00+00:00')
        r[1].update(open=6,high=6.5,low=5,close=6.1)
        s=dict(index=0,signal_at=r[0]['opened_at'],stop=9,target=13,indicators={})
        prepared=([s],[dict(fast=11,slow=10)]*2)
        out=simulate(r,c,'TIERED_BASE','2022-01-01','2023-01-01',prepared=prepared)
        self.assertEqual(1,out['metrics']['risk_breaches']);t=out['trades'][0]
        self.assertLess(t['net_pnl'],-t['risk_budget']);self.assertEqual('DAILY_FIRST_LOSS_STOP',t['decision'])

    def test_unclosed_partition_position_is_not_a_trade_or_winning_result(self):
        c=candidate();r=bars(2,'2022-01-04T14:30:00+00:00')
        s=dict(index=0,signal_at=r[0]['opened_at'],stop=9,target=13,indicators={})
        out=simulate(r,c,'TIERED_BASE','2022-01-01','2023-01-01',prepared=([s],[dict(fast=11,slow=10)]*2))
        self.assertTrue(out['metrics']['pending_position']);self.assertEqual(0,out['metrics']['admitted'])
        self.assertIsNone(out['metrics']['win_rate'])

    def test_bad_bars_and_final_holdout_are_rejected(self):
        r=bars(2);r[1]['opened_at']=r[0]['opened_at']
        with self.assertRaises(ValueError):validated(r)
        with self.assertRaisesRegex(ValueError,'SEALED'):
            evaluate(dict(candidate=candidate(),rows=bars(100,'2025-01-02T14:30:00+00:00'),family_comparisons=200,limitations=[]))

    def test_fold_results_reproducible_never_authorize_insufficient_zero_trade_sample(self):
        payload=dict(candidate=candidate(),rows=bars(100),family_comparisons=201,limitations=['EXPLORATORY'])
        a=evaluate(payload);self.assertEqual(a,evaluate(payload));self.assertEqual(15,a['backtests'])
        self.assertEqual('DISCARDED_RESEARCH_EVIDENCE',a['status']);self.assertIn('INSUFFICIENT_SAMPLE',a['rejection_reasons'])
        self.assertFalse(a['final_holdout_evaluated']);self.assertFalse(a['live_approved']);self.assertFalse(a['execution_authorized'])

    def test_confidence_retains_sample_and_multiple_comparison_penalty(self):
        self.assertIsNone(wilson(0,0));self.assertLess(wilson(90,100,200)[0],wilson(90,100,1)[0])
        self.assertIsNone(confidence([],1,200)['net_expectancy_block_bootstrap_95'])
