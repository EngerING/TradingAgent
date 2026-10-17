"""Synthetic scope/calendar tests, never a broker authorization."""
import copy
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch
import unittest
from trading_agent.paper_eur_reconciliation import AbsentEurAuthorization,initial_absence_evidence
from trading_agent.paper_calendar import broker_calendar
from trading_agent.paper_lab import stamp
from trading_agent.research_analysis import digest
from test_paper_eur_reconciliation import snapshot,additional,state,exception,NOW
from test_paper_lab import grant
import test_paper_execution_wire as execution_tests
import test_strategy_continuous as continuous_tests
from test_paper_eur_reconciliation import ExceptionWire
from trading_agent.paper_lab import PaperLab
from trading_agent.paper_strategy import validate_plan

class StrategyEurScopeTests(unittest.TestCase):
    def setUp(self):
        self.a=grant();self.a.update(mode='StrategyPaper',risk_profile='PAPER_EXPERIMENTAL_10_PERCENT',strategy_versions=['d'*64],strategy_plan={'synthetic':'only'})
        self.e=exception();self.e.update(mode='StrategyPaper',scope='INITIAL_STRATEGY_PAPER_EUR_ABSENCE',risk_profile=self.a['risk_profile'],
            strategy_version='d'*64,plan_hash=digest(self.a['strategy_plan']),execution_session_id=self.a['session_id'],review_session_id='e'*32,
            maximum_exposure=1,risk_ceiling=10,loss_allowance=20,diagnostic_loss_budget=0)
        self.a['eur_absence_exception_id']=self.e['record_id'];self.auth=AbsentEurAuthorization(lambda:self.e,lambda:NOW)
    def test_same_exact_strategy_plan_and_session_required(self):
        self.assertEqual(self.e,self.auth.read(self.a))
        for k,v in (('session_id','f'*32),('strategy_versions',['f'*64]),('strategy_plan',{'changed':True}),('mode','ExecutionDiagnostics'),('environment','LIVE_TRADING'),('live_enabled',True)):
            a=copy.deepcopy(self.a);a[k]=v
            with self.assertRaises(PermissionError):self.auth.read(a)
    def test_review_is_distinct_and_cannot_bind_old_session_to_execution(self):
        a=grant();a['session_id']='e'*32
        self.assertEqual(self.e,self.auth.read(a,for_review=True))
        with self.assertRaises(PermissionError):self.auth.read(a)
    def test_scope_expiry_and_exposure_cannot_expand(self):
        for field,value in (('maximum_exposure',2),('risk_ceiling',11),('loss_allowance',21),('expires_at',stamp(NOW+timedelta(minutes=31))),('plan_hash','')):
            e=self.e;self.e=copy.deepcopy(e);self.e[field]=value
            with self.assertRaises(PermissionError):self.auth.read(self.a)
            self.e=e
    def test_zero_bookmarks_are_allowed_only_strategy_and_never_become_cash_zero(self):
        s=snapshot();s['positions']=[{'quantity':'0'}];a=additional();a['positions']=[{'quantity':'0'}]
        current=state();current['strategy_capital']={'equity':'100','consumed_loss':'0'}
        self.assertFalse(initial_absence_evidence(s,a,current,NOW)['eligible'])
        result=initial_absence_evidence(s,a,current,NOW,strategy=True)
        self.assertTrue(result['eligible']);self.assertIsNone(result['eur_balance']);self.assertFalse(result['absence_of_exposure_proven'])
        s['positions'][0]['quantity']='.01';self.assertFalse(initial_absence_evidence(s,a,current,NOW,strategy=True)['eligible'])
    def test_pending_reservation_unknown_fee_missing_query_and_consumed_loss_block(self):
        s=snapshot();a=additional();current=state();current['strategy_capital']={'equity':'100','consumed_loss':'0'}
        for k,v in (('unavailable_commissions',{'e':{}}),('strategy_account',{'capital':{'equity':100},'reservationId':'pending'}),('strategy_capital',{'equity':100,'consumed_loss':1})):
            c=copy.deepcopy(current);c[k]=v
            self.assertFalse(initial_absence_evidence(s,a,c,NOW,strategy=True)['eligible'])
        s['cash_reconciliation']['query_status']='INCOMPLETE';self.assertFalse(initial_absence_evidence(s,a,current,NOW,strategy=True)['eligible'])

class AuthenticCalendarTests(unittest.TestCase):
    def contract(self,hours='20260928:1715-20260929:1700'):
        return {'hours':hours,'timezone':'US/Eastern','received_at':stamp(NOW)}
    def test_received_contract_intervals_convert_to_utc_without_template(self):
        c=broker_calendar([],self.contract(),NOW)
        self.assertEqual('IBKR_AUTHENTIC_SESSIONS',c['status']);self.assertEqual('2026-09-28T21:15:00+00:00',c['sessions'][0]['start'])
    def test_stale_absent_malformed_and_ambiguous_dst_fail_closed(self):
        for c in (self.contract(''),self.contract('provisional'),self.contract('20261101:0100-20261101:0300'),{**self.contract(),'received_at':stamp(NOW-timedelta(seconds=301))}):
            with self.assertRaises((PermissionError,ValueError)):broker_calendar([],c,NOW)
    def test_conflicting_schedule_contract_and_overlapping_intervals_fail(self):
        schedules=[{'time_zone':'US/Eastern','sessions':[{'start':'20260928-17:15:00','end':'20260929-16:00:00'}]}]
        with self.assertRaises(PermissionError):broker_calendar(schedules,self.contract(),NOW)
        with self.assertRaises(ValueError):broker_calendar([],self.contract('20260928:1715-20260929:1700;20260929:1600-20260930:1700'),NOW)

class StrategyExceptionLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.f=continuous_tests.ContinuousPaperTests();self.f.setUp();f=self.f
        f.a['strategy_versions']=['d'*64];f.plan['strategy_version']='d'*64
        self.e=exception();self.e.update(mode='StrategyPaper',scope='INITIAL_STRATEGY_PAPER_EUR_ABSENCE',risk_profile=f.a['risk_profile'],
            strategy_version='d'*64,plan_hash=digest(f.plan),execution_session_id=f.a['session_id'],review_session_id='e'*32,
            maximum_exposure=1,risk_ceiling=10,loss_allowance=20,confirmed_at=stamp(f.now),expires_at=stamp(f.now+timedelta(minutes=15)))
        f.a['eur_absence_exception_id']=self.e['record_id'];self.exc=AbsentEurAuthorization(lambda:self.e,lambda:f.now)
        f.w=ExceptionWire(lambda:f.now);f.w.contract_details=lambda:{'minimum_size_metadata':'1','size_increment_metadata':'1'}
        f.lab=PaperLab(f.auth,f.j,f.w,clock=lambda:f.now,eur_exception=self.exc);f.lab.connect_and_reconcile()
    def enter(self):
        p=self.f.proposal();p['strategy_version']='d'*64
        return self.f.lab.strategy_proposal(p,self.f.w.quote())
    def test_strategy_consumes_exception_durably_before_send_and_first_fill_requires_strict(self):
        f=self.f;o=self.enter();self.assertIsNone(o['initial_eur_uncertainty']['eur_balance'])
        self.assertEqual(o['intent'],f.j.state['eur_absence_consumed'][self.e['record_id']]['intent'])
        f.lab.ingest([{'kind':'fill','exec_id':'first','order_id':o['order_ids'][0],'perm_id':1,'client_id':82,
            'contract_id':12087792,'side':'BUY','quantity':'1','price':o['entry'],'at':stamp(f.now)}])
        with self.assertRaisesRegex(PermissionError,'STRICT_RECONCILIATION_REQUIRED_AFTER_FIRST_FILL'):f.lab.check()
        restarted=PaperLab(f.auth,f.j,f.w,clock=lambda:f.now,eur_exception=self.exc)
        with self.assertRaises(PermissionError):restarted.connect_and_reconcile()
        self.assertIsNotNone(restarted.state['strategy_account']['reservationId']);self.assertEqual(1,len(f.w.calls))
    def test_roundtrip_unknown_cash_cannot_release_risk_but_strict_zero_and_fees_can(self):
        f=self.f;o=self.enter();f.close(o,3)
        self.assertEqual('AWAITING_POST_RECONCILIATION',o['state'])
        self.assertIsNotNone(f.lab.state['strategy_account']['reservationId'])
        f.w.eur_cash='0';f.lab.supervise()
        self.assertEqual('CLOSED',o['state']);self.assertEqual(103,continuous_tests.num(f.lab.state['strategy_account']['equity']))
    def test_new_exception_record_cannot_erase_consumed_history(self):
        f=self.f;self.enter();self.e['record_id']='f'*32;f.a['eur_absence_exception_id']='f'*32
        restarted=PaperLab(f.auth,f.j,f.w,clock=lambda:f.now,eur_exception=self.exc)
        with self.assertRaises(PermissionError):restarted.connect_and_reconcile()
        self.assertIn('b'*32,restarted.state['eur_absence_consumed']);self.assertEqual(1,len(f.w.calls))

class PromotionAndRunnerTests(unittest.TestCase):
    def test_exact_research_version_cannot_be_promoted_with_missing_exit_semantics(self):
        p=continuous_tests.plan(NOW);p['promotion_evidence']={'promotion_target':'PAPER_EXPERIMENTAL',
            'risk_profile':'PAPER_EXPERIMENTAL_10_PERCENT','strategy_version':p['strategy_version'],'live_validated':False,
            'profitable':False,'entry_exit_equivalence_verified':False}
        with self.assertRaisesRegex(PermissionError,'STRATEGY_EXIT_SEMANTICS_NOT_EQUIVALENT'):validate_plan(p,NOW,[p['strategy_version']])
    def test_calendar_failure_blocks_runner_even_with_old_plan_template(self):
        f=continuous_tests.ContinuousPaperTests();f.setUp();f.w.history=lambda m:[];f.w.observe_quote=f.w.quote
        def unavailable():raise PermissionError('IBKR_CALENDAR_UNAVAILABLE')
        f.w.calendar=unavailable
        continuous_tests.continuous_strategy(f.lab,f.a,sleep=lambda _:None,monotonic=lambda:0,max_cycles=1)
        self.assertEqual([],f.w.calls);self.assertEqual('IBKR_CALENDAR_UNVERIFIED',f.j.events[-1]['data']['entry_block'])

class ScheduleWireTests(unittest.TestCase):
    setUp=execution_tests.ExecutionWireTests.setUp
    tearDown=execution_tests.ExecutionWireTests.tearDown
    def test_schedule_callback_isolated_and_read_error_is_not_order_rejection(self):
        self.w.active_schedule=6123
        self.w.historicalSchedule(6122,'s','e','UTC',[]);self.assertFalse(self.w.schedule_done.is_set())
        s=SimpleNamespace(startDateTime='20260928-17:15:00',endDateTime='20260929-17:00:00',refDate='20260929')
        self.w.historicalSchedule(6123,'s','e','UTC',[s]);self.assertTrue(self.w.schedule_done.is_set())
        self.w.error(6123,162,'data unavailable');self.assertEqual([],self.w.drain())
    def test_readonly_schedule_uses_sdk_data_request_without_any_order_gate(self):
        def receive(*args):self.w.historicalSchedule(args[0],'s','e','UTC',[SimpleNamespace(startDateTime='20260928-17:15:00',endDateTime='20260929-17:00:00',refDate='20260929')])
        with patch.object(self.w.client,'reqHistoricalData',side_effect=receive),patch.object(self.w.client,'cancelHistoricalData'):
            self.assertEqual(1,len(self.w.schedule()))
        self.assertEqual([],self.gates)
