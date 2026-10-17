import copy
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import patch
import unittest
import test_strategy_continuous as fixtures
from trading_agent.paper_lab import DotnetJournal,stamp,num
from trading_agent.paper_strategy import exit_decision,signal,validate_plan
from trading_agent.paper_exit_evidence import verified_equivalence
from trading_agent.paper_lab_runner import continuous_strategy

ROOT=Path(__file__).resolve().parents[2]

class ExactExitTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,10,5,12,30,tzinfo=timezone.utc)
        self.plan=fixtures.plan(self.now);self.plan.update(strategy_id='trend',exit_policy='RESEARCH_D_V1')
        self.position={'strategyId':'trend','side':'BUY','entry':'1','stop':'.99','target':'1.02',
                       'entryAt':stamp(self.now-timedelta(minutes=30))}
        self.core=DotnetJournal(ROOT)
    def decide(self,exits,quote=None,now=None):
        with patch('trading_agent.paper_strategy.analyze',return_value={'exit_signals':exits}):
            return exit_decision(self.plan,{},quote or {'bid':'.99999','ask':'1.00001'},now or self.now,self.position,self.core)
    def test_closed_opposite_cross_exits_at_next_open(self):
        result=self.decide([{'strategy_id':'trend','side':'BUY','at':stamp(self.now)}])
        self.assertEqual('RULE_EXIT_NEXT_OPEN',result['reason']);self.assertEqual(1,num(result['price']))
        self.assertEqual(stamp(self.now),result['at']);self.assertEqual(0,result['lateness_seconds'])
    def test_context_invalidation_same_original_rule_signal(self):
        result=self.decide([{'strategy_id':'trend','side':'BUY','at':stamp(self.now-timedelta(minutes=15))}])
        self.assertEqual('RULE_EXIT_NEXT_OPEN',result['reason'])
    def test_future_other_side_and_preentry_exits_are_ignored(self):
        self.assertIsNone(self.decide([{'strategy_id':'trend','side':'BUY','at':stamp(self.now+timedelta(minutes=15))},
            {'strategy_id':'trend','side':'SELL','at':stamp(self.now)},
            {'strategy_id':'trend','side':'BUY','at':self.position['entryAt']}]))
    def test_original_stop_and_target_thresholds(self):
        self.assertEqual('STOP',self.decide([],{'bid':'.98999','ask':'.99001'})['reason'])
        self.assertEqual('TAKE_PROFIT',self.decide([],{'bid':'1.01999','ask':'1.02001'})['reason'])
    def test_delayed_poll_records_actual_observation_and_never_claims_next_open_fill(self):
        result=self.decide([{'strategy_id':'trend','side':'BUY','at':stamp(self.now)}],now=self.now+timedelta(seconds=17))
        self.assertEqual(17,result['lateness_seconds']);self.assertNotIn('executed_price',result)
    def test_model_proof_alone_never_clears_execution_equivalence_block(self):
        self.assertFalse(verified_equivalence())
        with self.assertRaisesRegex(PermissionError,'STRATEGY_EXIT_SEMANTICS_NOT_EQUIVALENT'):
            validate_plan(self.plan,self.now,['synthetic-v1'])
    def test_original_atr_geometry_is_not_rounded_to_improve_results(self):
        candidate={'strategy_id':'trend','side':'BUY','signal_at':stamp(self.now),'stop_distance':'.00101',
            'take_profit_distance':'.0015','reasons':['NO_NEXT_CLOSED_BAR'],'context':{}}
        result={'indicator_points':{'15':[{'closed_at':stamp(self.now)}]},'candidates':[candidate],
                'strategies':[{'id':'trend','entry_rule':'synthetic'}]}
        with patch('trading_agent.paper_exit_evidence.verified_equivalence',return_value=True),patch('trading_agent.paper_strategy.analyze',return_value=result):
            with self.assertRaisesRegex(PermissionError,'STRATEGY_PRICE_GRID_NOT_EQUIVALENT'):
                signal(self.plan,{}, {'bid':'1.119975','ask':'1.120025'},self.now)
            candidate.update(stop_distance='.001',take_profit_distance='.0015')
            proposal=signal(self.plan,{}, {'bid':'1.119975','ask':'1.120025'},self.now)
            self.assertEqual(num(proposal['stop']),num('1.119'));self.assertEqual(num(proposal['target']),num('1.1215'))

class ExactRunnerTests(unittest.TestCase):
    def setUp(self):
        self.proof=patch('trading_agent.paper_exit_evidence.verified_equivalence',return_value=True);self.proof.start();self.addCleanup(self.proof.stop)
        self.f=fixtures.ContinuousPaperTests();self.f.setUp();self.f.plan['exit_policy']='RESEARCH_D_V1'
        self.o=self.f.enter();q=self.o['quantity'];self.f.w.eur_cash=q
        self.f.lab.ingest([{'kind':'fill','exec_id':'entry','order_id':self.o['order_ids'][0],'perm_id':1,
            'client_id':82,'contract_id':12087792,'side':'BUY','quantity':q,'price':self.o['entry'],'broker_time_raw':'SYNTHETIC','at':stamp(self.f.now)},
            {'kind':'status','order_id':self.o['order_ids'][0],'status':'Filled'}])
        self.o['payload']['context']['research_position']={'strategyId':'trend','side':'BUY','entry':self.o['entry'],
            'stop':self.o['stop'],'target':self.o['target'],'entryAt':self.o['sent_at']}
    def test_exact_mode_does_not_apply_legacy_60_second_time_exit(self):
        self.f.now+=timedelta(seconds=61);self.f.lab.supervise()
        self.assertFalse(any(c[0]=='close_owned' for c in self.f.w.calls))
    def test_rule_exit_modifies_only_existing_protected_child_once(self):
        decision={'exit':True,'reason':'RULE_EXIT_NEXT_OPEN','at':stamp(self.f.now)}
        self.f.lab.research_close(self.o,decision);self.f.lab.research_close(self.o,decision)
        self.assertEqual(1,sum(c[0]=='close_owned' for c in self.f.w.calls))
        self.assertEqual('RESEARCH_EXIT_MODIFICATION_PENDING',self.f.j.events[-1]['event'])
        self.assertEqual(self.o['order_ids'][1],self.f.w.calls[-1][2]);self.assertFalse(any(c[0]=='cancel_parent' for c in self.f.w.calls))
    def test_runner_keeps_evaluating_rules_while_position_is_open(self):
        self.f.w.history=lambda m:[];self.f.w.observe_quote=self.f.w.quote;self.f.w.calendar=lambda:self.f.plan['calendar']
        with patch('trading_agent.paper_strategy.exit_decision',return_value={'exit':True,'reason':'RULE_EXIT_NEXT_OPEN','at':stamp(self.f.now)}) as evaluator:
            continuous_strategy(self.f.lab,self.f.a,sleep=lambda _:None,monotonic=lambda:0,max_cycles=1)
        self.assertEqual(1,evaluator.call_count);self.assertEqual('close_owned',self.f.w.calls[-1][0])
    def test_diagnostic_mode_cannot_use_research_exit(self):
        self.f.lab.experimental=False
        with self.assertRaises(PermissionError):
            self.f.lab.research_close(self.o,{'exit':True,'reason':'RULE_EXIT_NEXT_OPEN'})
