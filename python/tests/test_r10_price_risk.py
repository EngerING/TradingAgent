from copy import deepcopy
from datetime import datetime,timedelta,timezone
from pathlib import Path
import json
import unittest
from trading_agent.r10_price_risk import assess,configuration,Experiment,paper_plan,sha,N

ROOT=Path(__file__).resolve().parents[2]
class Memory:
    experiment='r10-price-'+'a'*32
    def __init__(self):self.head=dict(revision=0,hash='',payload=None)
    def load(self):return deepcopy(self.head)
    def commit(self,r,previous,payload):
        if r!=self.head['revision']+1 or previous!=self.head['hash']:raise RuntimeError('CAS')
        self.head=dict(revision=r,hash=sha([r,payload,previous]),payload=json.dumps(payload));return self.load()

class PriceRiskTests(unittest.TestCase):
    def setUp(self):
        self.c=configuration(ROOT);self.at=datetime(2026,10,8,14,tzinfo=timezone.utc)
        self.q=dict(type='LIVE',bid='.9999',ask='1.0001',at=self.at.isoformat(),market_status='OPEN',available_for_execution=True)
        self.signal=dict(strategy_id='trend',side='BUY',signal_at=self.at.isoformat(),stop_distance='.2',take_profit_distance='.5',reasons=[])
        self.j=Memory();self.e=Experiment(self.j,lambda:self.at);self.e.prepare(self.c,ROOT)
    def observation(self):return dict(at=self.at.isoformat(),quote=self.q,analysis=dict(normalized={'15':[]},candidates=[self.signal],exit_signals=[]))
    def test_price_risk_ten_and_fees_separate(self):
        d=assess(self.c,self.q,self.signal);self.assertEqual(N(10),N(d['price_risk']));self.assertEqual(N(4),N(d['estimated_fees']));self.assertGreater(N(d['estimated_all_in_loss']),14);self.assertLessEqual(N(d['estimated_all_in_loss']),15)
    def test_capital_funding_without_leverage(self):
        self.signal['stop_distance']='.0006';d=assess(self.c,self.q,self.signal);self.assertLessEqual(N(d['capital_reserved']),100);self.assertLess(N(d['price_risk']),N('.1'))
    def test_stop_target_remain_technical(self):
        d=assess(self.c,self.q,self.signal);self.assertEqual(N('.8'),N(d['stop']));self.assertEqual(N('1.5'),N(d['target']))
    def test_reduced_equity_does_not_increase_price_budget(self):
        self.assertEqual(N(9),N(assess(self.c,self.q,self.signal,'90')['price_risk_budget']))
    def test_unknown_fee_rejects(self):
        self.c['opening_fee_usd']=None;self.assertFalse(assess(self.c,self.q,self.signal)['admitted'])
    def test_no_favorable_minimum_round_up(self):
        self.c['minimum_quantity']='20000';self.assertEqual('CAPITAL_OR_MINIMUM_QUANTITY',assess(self.c,self.q,self.signal)['reason'])
    def test_increment_rounds_down(self):
        self.c['quantity_increment']='3';d=assess(self.c,self.q,self.signal);self.assertEqual(0,N(d['quantity'])%3);self.assertLessEqual(N(d['price_risk']),10)
    def test_cost_cap_rejects_unbounded_fees(self):
        self.c['opening_fee_usd']='6';self.assertFalse(assess(self.c,self.q,self.signal)['admitted'])
    def test_target_below_cost_rejected(self):
        self.signal.update(stop_distance='.0006',take_profit_distance='.001');self.assertEqual('TARGET_DOES_NOT_COVER_COSTS',assess(self.c,self.q,self.signal)['reason'])
    def test_slippage_and_spread_separate(self):
        d=assess(self.c,self.q,self.signal);self.assertEqual(N(d['estimated_all_in_loss']),sum(N(d[k]) for k in ('price_risk','estimated_fees','spread_cost','slippage_cost','gap_reserve','financing_reserve')))
    def test_negative_price_geometry_rejected(self):
        self.signal['stop_distance']='2';self.assertFalse(assess(self.c,self.q,self.signal)['admitted'])
    def test_short_prohibited(self):
        self.signal['side']='SELL';self.assertEqual('LONG_ONLY',assess(self.c,self.q,self.signal)['reason'])
    def test_signal_rejection_never_fills(self):
        self.signal['reasons']=['NO_SIGNAL'];self.e.consume(self.observation());self.assertIsNone(self.e.state['active'])
    def test_stale_quote_does_not_fill(self):
        self.at+=timedelta(seconds=6);self.e.consume(self.observation());self.assertIsNone(self.e.state['active'])
    def test_future_quote_rejected(self):
        self.q['at']=(self.at+timedelta(seconds=1)).isoformat();self.e.consume(self.observation());self.assertIsNone(self.e.state['active'])
    def test_shadow_never_claims_broker_fill(self):
        self.e.consume(self.observation());self.assertEqual('SIMULATED_SHADOW',self.e.state['active']['classification']);self.assertEqual('SIMULATED_ONLY',self.e.state['active']['protection'])
    def test_restart_retains_inventory_and_prevents_duplicate(self):
        self.e.consume(self.observation());r=Experiment(self.j,lambda:self.at);r.consume(self.observation());self.assertEqual(1,len(r.state['seen']));self.assertIsNotNone(r.state['active'])
    def test_loss_stops_day_and_cannot_restore_by_restart(self):
        self.e.consume(self.observation());self.e.close(N('.8'),self.q,self.at.isoformat(),'STOP');r=Experiment(self.j,lambda:self.at);r.consume(self.observation());self.assertIsNone(r.state['active']);self.assertTrue(r.state['daily_stops']);self.assertGreater(N(r.state['consumed_loss']),10)
    def test_gap_in_price_not_deducted_twice(self):
        self.e.consume(self.observation());d=self.e.state['active']['assessment'];self.e.close(N('.7'),self.q,self.at.isoformat(),'GAP');t=self.e.state['trades'][0]
        self.assertEqual(N(t['gross_pnl'])-N(d['estimated_fees'])-N(t['realized_spread_model'])-N(d['slippage_cost'])-N(d['financing_reserve']),N(t['realized_all_in_pnl']))
    def test_stop_manages_existing_virtual_position(self):
        self.e.consume(self.observation());self.e.consume(self.observation(),stop=True);self.assertIsNone(self.e.state['active']);self.assertEqual('OPERATOR_STOP',self.e.state['trades'][0]['reason'])
    def test_paper_requires_new_independent_authorization(self):
        plan=paper_plan(assess(self.c,self.q,self.signal));self.assertTrue(plan['single_use']);self.assertEqual(1,plan['max_openings']);self.assertFalse(plan['broker_orders_enabled']);self.assertFalse(plan['live_enabled']);self.assertIn('NEW_PROFILE_SPECIFIC_AUTHORIZATION_REQUIRED',plan['blockers'])
    def test_both_barriers_stop_first(self):
        self.e.consume(self.observation());entry=self.at;self.at+=timedelta(minutes=31);self.q['at']=self.at.isoformat();o=self.observation();o['analysis']['normalized']['15']=[dict(opened_at=(entry+timedelta(minutes=15)).isoformat(),open='1',low='.7',high='1.6')];self.e.consume(o);self.assertEqual('STOP_OR_GAP',self.e.state['trades'][0]['reason'])
    def test_no_future_bar_exit(self):
        self.e.consume(self.observation());o=self.observation();o['analysis']['normalized']['15']=[dict(opened_at=self.at.isoformat(),open='1',low='.7',high='1.6')];self.e.consume(o);self.assertIsNotNone(self.e.state['active'])
    def test_stop_unknown_quote_keeps_inventory_and_reserve(self):
        self.e.consume(self.observation());reserve=self.e.state['reserved'];self.q['type']='MISSING';self.e.consume(self.observation(),stop=True);self.assertIsNotNone(self.e.state['active']);self.assertEqual(reserve,self.e.state['reserved'])
    def test_new_day_reopens_only_with_new_authentic_signal(self):
        self.e.consume(self.observation());self.e.close(N('.8'),self.q,self.at.isoformat(),'STOP');self.at+=timedelta(days=1);self.q['at']=self.at.isoformat();self.signal['signal_at']=self.at.isoformat();self.e.consume(self.observation());self.assertEqual('CUMULATIVE_BUDGET_INSUFFICIENT',self.e.state['events'][-1]['detail']['reason'])
