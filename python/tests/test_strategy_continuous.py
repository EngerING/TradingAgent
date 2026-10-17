"""Real C# arithmetic with simulated execution; no IBKR connection or orders."""
import copy
from datetime import datetime,timezone,timedelta
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch
import unittest
from trading_agent.paper_lab import Authorization,PaperLab,DotnetJournal,EXPERIMENTAL,num,stamp
from trading_agent.paper_lab_runner import strategy_cycle,continuous_strategy,review_authorization
from trading_agent.paper_strategy import validate_plan,signal,ENGINE
from trading_agent.research_indicators import DEFAULTS
from test_paper_lab import grant,Journal,Wire,IDENTITY

ROOT=Path(__file__).resolve().parents[2]

def plan(now):
    # Synthetic evidence, confined to test fixtures, never written to a real grant.
    return {'schema_version':1,'engine':ENGINE,'strategy_version':'synthetic-v1','strategy_id':'mean_reversion',
        'name':'Synthetic mean reversion','instrument':'EUR/USD','side':'BUY','exit_policy':'BRACKET_OR_TIME_LIMIT',
        'indicators':DEFAULTS.copy(),'calendar':{'timezone':'UTC','coverage_start':now.date().isoformat(),
            'coverage_end':now.date().isoformat(),'grid_timezone':'UTC','status':'VERIFIED_EXPLICIT_SESSIONS',
            'source':'SYNTHETIC_TEST_ONLY','sessions':[{'start':stamp(now-timedelta(days=1)),'end':stamp(now+timedelta(days=1))}]},
        'evidence_at':stamp(now-timedelta(minutes=1)),'evidence_expires_at':stamp(now+timedelta(minutes=30)),
        'execution_requirements':{'quoteToAccountFx':1,'multiplier':1,'minQuantity':1,'quantityStep':1,
            'marginRate':1,'availableMargin':100,'commissionFixedRoundTrip':'.1','commissionPerUnitRoundTrip':0,
            'slippagePerUnit':'.0136','adverseGapPerUnit':0,'execution':{'source':'SYNTHETIC_TEST_ONLY',
                'environment':'PAPER_TRADING','mode':'ODD_LOT','openingCommission':'.05','closingCommission':'.05',
                'costsReliable':True,'marginReliable':True,'contractReliable':True,'brokerPermitsEntry':True,
                'equivalentRealAccount':{'minimumQuantity':1,'quantityStep':1,'marginRate':1,'maximumLeverage':1,
                    'instrumentPermitted':True,'executionModePermitted':True,'accountEligible':True}}}}

class ArithmeticJournal(Journal):
    def __init__(self):super().__init__();self.core=DotnetJournal(ROOT,EXPERIMENTAL)
    def strategy_initial(self):return self.core.strategy_initial()
    def strategy_mark(self,a):return self.core.strategy_mark(a)
    def strategy_risk(self,a,r):return self.core.strategy_risk(a,r)
    def strategy_reserve(self,a,r,intent):return self.core.strategy_reserve(a,r,intent)
    def strategy_settle(self,a,net,fees,intent):return self.core.strategy_settle(a,net,fees,intent)
    def strategy_release_unfilled(self,a,intent):return self.core.strategy_release_unfilled(a,intent)

class ContinuousPaperTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime.now(timezone.utc);self.plan=plan(self.now);self.a=grant()
        self.a.update(mode='StrategyPaper',risk_profile=EXPERIMENTAL,continuous=True,max_experiments=1,max_quantity=80,
            confirmed_at=stamp(self.now),expires_at=stamp(self.now+timedelta(minutes=30)),strategy_versions=['synthetic-v1'],
            strategy_requirements_verified=True,strategy_plan=self.plan,execution_requirements=self.plan['execution_requirements'])
        self.auth=Authorization(lambda:copy.deepcopy(self.a),lambda *args:True,lambda:self.now)
        self.j=ArithmeticJournal();self.w=Wire(lambda:self.now);self.lab=PaperLab(self.auth,self.j,self.w,clock=lambda:self.now)
        self.w.contract_details=lambda:{'minimum_size_metadata':'1','size_increment_metadata':'1'}
        self.lab.connect_and_reconcile();self.signal_number=0
    def proposal(self):
        self.signal_number+=1
        return {'strategy_version':'synthetic-v1','signal_at':stamp(self.now-timedelta(microseconds=self.signal_number)),
            'stop':'.99000','target':'1.50010','market_context':{'strategy_name':'Synthetic','signal_at':stamp(self.now),
                'signal_reason':'synthetic signal','indicators':{'rsi':25},'timeframe':'15m'}}
    def enter(self):return self.lab.strategy_proposal(self.proposal(),self.w.quote())
    def close(self,o,net,fees=True):
        q=num(o['quantity']);price=num(o['entry'])+(num(net)+Decimal('.1'))/q
        def fill(index,side,id,p):return {'kind':'fill','exec_id':id,'order_id':o['order_ids'][index],
            'perm_id':index+1,'client_id':82,'contract_id':12087792,'side':side,'quantity':str(q),'price':str(p),
            'broker_time_raw':'SYNTHETIC','at':stamp(self.now)}
        events=[fill(0,'BUY',o['intent']+'in',o['entry']),{'kind':'status','order_id':o['order_ids'][0],'status':'Filled'},
                fill(1,'SELL',o['intent']+'out',price)]
        if fees:events += [{'kind':'commission','exec_id':o['intent']+side,'amount':'.05','currency':'USD'} for side in ('in','out')]
        self.w.orders=[];self.w.eur_cash='0';self.lab.ingest(events)
    def test_day_a_wins_continue_past_one_experiment_loss_only_blocks_entries(self):
        for net in (4,3,-10):
            o=self.enter();self.assertNotEqual('STRATEGY_REJECTED',o['state']);self.close(o,net)
        self.assertEqual(3,len(self.w.calls));self.assertFalse(self.lab.state['emergency'])
        result=strategy_cycle(self.lab,self.plan,{},self.w.quote())
        self.assertEqual('DAILY_FIRST_LOSS_STOP',result['reason']);self.assertEqual(3,len(self.w.calls))
        e=self.lab.state['experiences'][o['intent']]
        self.assertEqual('DAILY_FIRST_LOSS_STOP',e['continuation_decision']);self.assertEqual(97,num(e['equity_after']))
        self.assertEqual(Decimal(10),num(self.lab.state['strategy_account']['capital']['consumedLoss']))
        self.assertTrue({'strategy_version','signal_at','indicators','stop','target','commissions','gross_usd','net_usd','equity_after','remaining_loss_after','closing_reason'}<=set(e))
    def test_day_b_first_loss_survives_worker_restart_and_new_session(self):
        self.close(self.enter(),-10);self.a['session_id']='b'*32
        restarted=PaperLab(self.auth,self.j,self.w,clock=lambda:self.now);restarted.connect_and_reconcile()
        self.assertEqual('DAILY_FIRST_LOSS_STOP',strategy_cycle(restarted,self.plan,{},self.w.quote())['reason'])
        self.assertEqual(1,len(self.w.calls));self.assertEqual(Decimal(10),num(restarted.state['strategy_account']['capital']['consumedLoss']))
    def test_day_c_zero_after_win_prevents_third_entry(self):
        self.close(self.enter(),2);self.close(self.enter(),0)
        self.assertEqual('DAILY_WIN_REQUIRED',strategy_cycle(self.lab,self.plan,{},self.w.quote())['reason'])
        self.assertEqual(2,len(self.w.calls))
    def test_day_d_pending_commission_blocks_until_final_positive_result(self):
        self.close(self.enter(),5);o=self.enter();self.close(o,3,False)
        self.assertEqual('AWAITING_COMMISSIONS',o['state'])
        self.lab=PaperLab(self.auth,self.j,self.w,clock=lambda:self.now);self.lab.connect_and_reconcile()
        self.assertEqual('PAPER_RESULT_UNRESOLVED',strategy_cycle(self.lab,self.plan,{},self.w.quote())['reason'])
        self.lab.ingest([{'kind':'commission','exec_id':o['intent']+side,'amount':'.05','currency':'USD'} for side in ('in','out')])
        self.assertEqual('CLOSED',self.lab.state['orders'][o['intent']]['state']);self.assertEqual(108,num(self.lab.state['strategy_account']['equity']))
        self.enter();self.assertEqual(3,len(self.w.calls))
    def test_quantity_is_auto_exposure_bound_and_rounded_entry_is_priced_in_risk(self):
        self.a['max_quantity']=100;self.plan['execution_requirements']['slippagePerUnit']=0
        self.w.quote=lambda:{'type':'LIVE','bid':'1.12534','ask':'1.12536','at':stamp(self.now)}
        proposal=self.proposal();proposal.update(stop='1.12430',target='1.15000')
        o=self.lab.strategy_proposal(proposal,self.w.quote());self.assertEqual('1.12540',o['entry'])
        self.assertLess(num(o['quantity']),100);self.assertLessEqual(num(o['quantity'])*num(o['entry']),100)
        self.assertLessEqual(num(o['reserve']),10)
    def test_unknown_fees_or_partial_position_never_enable_new_order(self):
        o=self.enter();self.lab.state['unavailable_commissions']={'unresolved':{}}
        self.assertEqual('PAPER_RESULT_UNRESOLVED',strategy_cycle(self.lab,self.plan,{},self.w.quote())['reason'])
        self.assertEqual(1,len(self.w.calls));self.assertIsNotNone(self.lab.state['strategy_account']['reservationId'])
    def test_monitor_without_signal_never_forces_quota(self):
        with patch('trading_agent.paper_strategy.signal',return_value=None):
            for _ in range(3):self.assertEqual('NO_VALID_APPROVED_SIGNAL',strategy_cycle(self.lab,self.plan,{},self.w.quote())['reason'])
        self.assertEqual([],self.w.calls)
    def test_expired_grant_never_authorizes_an_entry(self):
        self.a['expires_at']=stamp(self.now-timedelta(seconds=1))
        with self.assertRaises(PermissionError):self.enter()
        self.assertEqual([],self.w.calls)
    def test_continuous_worker_keeps_collecting_market_while_daily_entries_are_stopped(self):
        self.close(self.enter(),-10);reads=[]
        self.w.history=lambda m:reads.append(('history',m)) or []
        self.w.observe_quote=lambda:reads.append(('quote',)) or self.w.quote()
        self.w.calendar=lambda:self.plan['calendar']
        continuous_strategy(self.lab,self.a,sleep=lambda _:None,monotonic=lambda:0,max_cycles=2)
        self.assertEqual(2,reads.count(('quote',)));self.assertEqual(1,len(self.w.calls))
        events=[e for e in self.j.events if e['event']=='STRATEGY_MARKET_MONITOR']
        self.assertEqual('DAILY_FIRST_LOSS_STOP',events[-1]['data']['entry_block'])
    def test_cancelled_unfilled_reservation_is_only_released_after_snapshot_has_no_orders(self):
        o=self.enter();self.lab.ingest([{'kind':'reject','order_id':o['order_ids'][0],'code':201}])
        self.assertIsNotNone(self.lab.state['strategy_account']['reservationId'])
        self.w.orders=[];self.lab.connect_and_reconcile()
        self.assertIsNone(self.lab.state['strategy_account']['reservationId']);self.assertEqual(0,self.lab.state['strategy_account']['paperContinuation']['closedTrades'])
    def test_plan_is_separate_from_diagnostics_and_live(self):
        for field,value in (('mode','ExecutionDiagnostics'),('live_enabled',True),('strategy_requirements_verified',False)):
            original=self.a[field];self.a[field]=value
            with self.assertRaises(PermissionError):self.auth.read()
            self.a[field]=original

class PlanAndReviewTests(unittest.TestCase):
    def test_unknown_costs_calendar_strategy_or_expired_evidence_are_blocked(self):
        now=datetime.now(timezone.utc);p=plan(now)
        self.assertEqual(p,validate_plan(p,now,['synthetic-v1']))
        for mutation in ('costs','calendar','version','expiry','real'):
            q=copy.deepcopy(p)
            if mutation=='costs':q['execution_requirements']['execution']['costsReliable']=False
            if mutation=='calendar':q['calendar']['status']='PROVISIONAL_REGULAR_TEMPLATE'
            if mutation=='version':q['strategy_version']='different'
            if mutation=='expiry':q['evidence_expires_at']=stamp(now-timedelta(seconds=1))
            if mutation=='real':q['execution_requirements']['execution']['equivalentRealAccount']['accountEligible']=False
            with self.assertRaises(PermissionError):validate_plan(q,now,['synthetic-v1'])
    def test_new_review_permit_rebinds_read_only_scope_without_renewing_old_grant(self):
        now=datetime.now(timezone.utc);old=grant();saved=copy.deepcopy(old)
        p={'schema_version':1,'scope':'OWNER_REVIEW_CLEAR_EMERGENCY','record_id':'c'*32,
            'environment':'PAPER_TRADING','live_enabled':False,'account':IDENTITY,'session_id':old['session_id'],
            'tws_pid':2,'tws_start_filetime':'2','confirmed_at':stamp(now),'expires_at':stamp(now+timedelta(minutes=2)),
            'exception_id':None,'current_paper_review_attested':True}
        a=review_authorization(old,p,now);auth=Authorization(lambda:a,lambda *args:True,lambda:now)
        self.assertEqual(saved,old);self.assertEqual(2,auth.read(management=True)['tws_pid'])
        with self.assertRaisesRegex(PermissionError,'REVIEW_ONLY'):auth.read()
        p['account']='DU99995678'
        with self.assertRaises(PermissionError):review_authorization(old,p,now)
    def test_late_or_future_signal_cannot_be_promoted_to_current_entry(self):
        now=datetime.now(timezone.utc);p=plan(now)
        fake={'indicator_points':{'15':[{'closed_at':stamp(now-timedelta(minutes=15))}]}}
        with patch('trading_agent.paper_strategy.analyze',return_value=fake):self.assertIsNone(signal(p,{}, {},now))
        fake['indicator_points']['15'][0]['closed_at']=stamp(now+timedelta(seconds=1))
        with patch('trading_agent.paper_strategy.analyze',return_value=fake):self.assertIsNone(signal(p,{}, {},now))

    def test_fresh_buy_signal_uses_closed_indicators_and_conservative_grid_geometry(self):
        now=datetime.now(timezone.utc);p=plan(now)
        candidate={'strategy_id':'mean_reversion','side':'BUY','signal_at':stamp(now),'stop_distance':.00101,
            'take_profit_distance':.0015,'reasons':['NO_NEXT_CLOSED_BAR'],'context':{'15':{'rsi':31}}}
        result={'indicator_points':{'15':[{'closed_at':stamp(now)}]},'candidates':[candidate],
            'strategies':[{'id':'mean_reversion','entry_rule':'synthetic closed RSI cross'}]}
        quote={'bid':'1.12071','ask':'1.12074'}
        with patch('trading_agent.paper_strategy.analyze',return_value=result):proposal=signal(p,{},quote,now)
        self.assertEqual(stamp(now),proposal['signal_at']);self.assertLess(num(proposal['stop']),num(quote['bid']))
        self.assertGreater(num(proposal['target']),num(quote['ask']));self.assertEqual(0,num(proposal['stop'])%Decimal('.00005'))
        candidate['reasons']=['MULTITIMEFRAME_CONTRADICTION']
        with patch('trading_agent.paper_strategy.analyze',return_value=result):self.assertIsNone(signal(p,{},quote,now))

@unittest.skipUnless(os.environ.get('TRADING_TEST_DB'),'Disposable PostgreSQL required')
class ExperimentalPostgresTests(ContinuousPaperTests):
    # Run the same operational scenarios against the real journal as well as the in-memory journal.
    def setUp(self):
        super().setUp()
        import uuid
        self.a['account']='DUR'+str(uuid.uuid4().int);self.w.accounts=[self.a['account']]
        self.env=patch.dict(os.environ,{'TRADING_LAB_DB':os.environ['TRADING_TEST_DB']});self.env.start();self.addCleanup(self.env.stop)
        self.j=DotnetJournal(ROOT,EXPERIMENTAL);self.lab=PaperLab(self.auth,self.j,self.w,clock=lambda:self.now)
        self.lab.connect_and_reconcile()
    def test_continuous_worker_keeps_collecting_market_while_daily_entries_are_stopped(self):
        # Event access in the base fixture is in-memory; exercise persistence via the public journal instead.
        self.close(self.enter(),-10)
        self.w.history=lambda m:[];self.w.observe_quote=self.w.quote
        self.w.calendar=lambda:self.plan['calendar']
        continuous_strategy(self.lab,self.a,sleep=lambda _:None,monotonic=lambda:0,max_cycles=2)
        saved=self.j.load(self.lab.scope)['state']
        self.assertTrue(saved['strategy_account']['paperContinuation']['firstLossStopped']);self.assertEqual(1,len(self.w.calls))
