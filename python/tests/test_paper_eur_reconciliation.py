"""All balances, authorizations and fills here are synthetic; no broker connection."""
import copy
import unittest
from datetime import timedelta
from unittest.mock import patch
from trading_agent.paper_lab import Authorization,PaperLab,stamp
from trading_agent.paper_data_diagnostics import account_value,currency_cash
from trading_agent.paper_eur_reconciliation import AbsentEurAuthorization,initial_absence_evidence,validate_review_permit
from test_paper_lab import NOW,IDENTITY,INTENT,Journal,Wire,grant

SOURCES={'SUMMARY_1','SUMMARY_2','ACCOUNT_UPDATES','ACCOUNT_UPDATES_MULTI'}

def cash(value=None):
    rows=[account_value('SUMMARY_2','NetLiquidation','1000000','USD'),account_value('ACCOUNT_UPDATES','AccountReady','true',''),
          account_value('ACCOUNT_UPDATES','CashBalance','1000000','USD'),
          account_value('SUMMARY_2','InitMarginReq','0','USD'),account_value('SUMMARY_2','MaintMarginReq','0','USD')]
    if value is not None:rows.append(account_value('ACCOUNT_UPDATES','CashBalance',value,'EUR'))
    return {**currency_cash(rows,SOURCES,expected_sources=SOURCES),'errors':[],'observations':rows}

def snapshot(at=NOW):return {'cash_reconciliation':cash(),'eur_cash':None,'orders':[],'positions':[],'portfolio':[],
    'foreign_positions':[],'foreign_currency_balances':[],'events':[],'exposure_reads_complete':True,'received_at':stamp(at)}
def additional(at=NOW):return {'status':'COMPLETE','positions':[],'errors':[],'received_at':stamp(at)}
def state():return {'orders':{},'experiences':{},'sessions':{},'emergency':True}
def exception():return {'schema_version':1,'record_id':'b'*32,'account':IDENTITY,'environment':'PAPER_TRADING','live_enabled':False,
    'mode':'ExecutionDiagnostics','scope':'INITIAL_DIAGNOSTIC_EUR_ABSENCE','contract_id':12087792,'tws_pid':1,'tws_start_filetime':'1',
    'manual_uncertainty_accepted':True,'paper_checked':True,'identity_manual_match':True,'observed_state':'EUR_ROW_ABSENT',
    'confirmed_at':stamp(NOW),'expires_at':stamp(NOW+timedelta(minutes=15)),
    'max_experiments':1,'max_quantity':100,'max_notional_usd':150,'diagnostic_loss_budget':10,'max_hold_seconds':60}

class BaselineEvidenceTests(unittest.TestCase):
    def test_absent_row_can_be_exception_candidate_without_proving_zero(self):
        result=initial_absence_evidence(snapshot(),additional(),state(),NOW)
        self.assertTrue(result['eligible']);self.assertFalse(result['absence_of_exposure_proven']);self.assertIsNone(result['eur_balance'])
    def test_zero_absent_unknown_and_nonzero_are_distinct(self):
        self.assertEqual('EUR_ZERO_CONFIRMED',cash('0')['balance_classification'])
        self.assertEqual('EUR_ROW_ABSENT',cash()['balance_classification'])
        self.assertEqual('EUR_NONZERO_CONFIRMED',cash('1')['balance_classification'])
        self.assertEqual('EUR_BALANCE_UNKNOWN',currency_cash([],set())['balance_classification'])
    def test_zero_and_positive_or_negative_balances_never_use_absence_exception(self):
        for value in ('0','100','-100'):
            s=snapshot();s['cash_reconciliation']=cash(value);s['eur_cash']=value
            self.assertFalse(initial_absence_evidence(s,additional(),state(),NOW)['eligible'])
    def test_any_position_portfolio_order_or_nonbase_currency_blocks_candidate(self):
        for field in ('positions','portfolio','orders','foreign_positions','foreign_currency_balances'):
            s=snapshot();s[field]=[{'quantity':'0'}]
            self.assertFalse(initial_absence_evidence(s,additional(),state(),NOW)['eligible'])
        a=additional();a['positions']=[{'quantity':'100'}]
        self.assertFalse(initial_absence_evidence(snapshot(),a,state(),NOW)['eligible'])
    def test_missing_markers_errors_not_ready_and_stale_data_block_candidate(self):
        for field,value in (('query_status','INCOMPLETE'),('account_ready',False),('errors',['321']),('expected_sources',[])):
            s=snapshot();s['cash_reconciliation'][field]=value
            self.assertFalse(initial_absence_evidence(s,additional(),state(),NOW)['eligible'])
        for a in (additional(NOW-timedelta(seconds=31)),{'status':'INCOMPLETE','positions':[],'received_at':stamp(NOW)}):
            self.assertFalse(initial_absence_evidence(snapshot(),a,state(),NOW)['eligible'])
    def test_pending_costs_historical_intents_and_durable_consumption_block_candidate(self):
        for field in ('pending_commissions','orders','experiences','eur_absence_consumed'):
            current=state();current[field]={'previous':{}}
            self.assertFalse(initial_absence_evidence(snapshot(),additional(),current,NOW)['eligible'])
    def test_previous_diagnostic_count_loss_or_reservation_blocks_candidate(self):
        for field,value in (('count',1),('reserved','10'),('consumed_loss','1')):
            current=state();current['sessions']={'session':{field:value}}
            self.assertFalse(initial_absence_evidence(snapshot(),additional(),current,NOW)['eligible'])
    def test_conflicting_usd_cash_or_unexplained_margin_blocks_candidate(self):
        for tag,value in (('CashBalance','999999'),('InitMarginReq','1'),('MaintMarginReq','1')):
            s=snapshot();s['cash_reconciliation']['observations'].append(account_value('ACCOUNT_UPDATES',tag,value,'USD'))
            self.assertFalse(initial_absence_evidence(s,additional(),state(),NOW)['eligible'])
    def test_missing_cash_margin_or_exposure_fields_block_candidate(self):
        s=snapshot();s['cash_reconciliation']['observations']=[]
        self.assertFalse(initial_absence_evidence(s,additional(),state(),NOW)['eligible'])
        s=snapshot();del s['foreign_currency_balances']
        self.assertFalse(initial_absence_evidence(s,additional(),state(),NOW)['eligible'])

class ExceptionalAuthorizationTests(unittest.TestCase):
    def setUp(self):self.a=grant();self.e=exception();self.a['eur_absence_exception_id']=self.e['record_id'];self.auth=AbsentEurAuthorization(lambda:copy.deepcopy(self.e),lambda:NOW)
    def test_protected_record_must_bind_to_execution_session(self):
        self.assertEqual(self.e,self.auth.read(self.a))
        del self.a['eur_absence_exception_id']
        with self.assertRaises(PermissionError):self.auth.read(self.a)
        self.assertEqual(self.e,self.auth.read(self.a,for_review=True))
    def test_strategy_live_different_account_or_process_cannot_use_exception(self):
        for field,value in (('mode','StrategyPaper'),('environment','LIVE_TRADING'),('live_enabled',True),('account','DUR99995678'),('tws_start_filetime','2')):
            a=copy.deepcopy(self.a);a[field]=value
            with self.assertRaises(PermissionError):self.auth.read(a,for_review=True)
    def test_expired_future_or_long_lived_exception_is_invalid_even_for_review(self):
        for start,end in ((NOW-timedelta(minutes=16),NOW-timedelta(minutes=1)),(NOW+timedelta(seconds=1),NOW+timedelta(minutes=15)),(NOW,NOW+timedelta(minutes=31))):
            self.e.update(confirmed_at=stamp(start),expires_at=stamp(end))
            with self.assertRaises(PermissionError):self.auth.read(self.a,for_review=True)
    def test_owner_acknowledgement_scope_and_caps_are_required(self):
        original=copy.deepcopy(self.e)
        for field,value in (('manual_uncertainty_accepted',False),('scope','ANY_BALANCE'),('observed_state','EUR_BALANCE_UNKNOWN'),('max_experiments',2),('diagnostic_loss_budget',20)):
            self.e=copy.deepcopy(original);self.e[field]=value
            with self.assertRaises(PermissionError):self.auth.read(self.a)
    def test_execution_authorization_limits_cannot_be_expanded_by_exception(self):
        for field,value in (('max_experiments',2),('max_quantity',101),('max_notional_usd',151),('max_hold_seconds',61),('diagnostic_loss_budget',20)):
            a=copy.deepcopy(self.a);a[field]=value
            with self.assertRaises(PermissionError):self.auth.read(a)

class OwnerReviewPermitTests(unittest.TestCase):
    def permit(self):
        a=grant()
        return {'schema_version':1,'scope':'OWNER_REVIEW_CLEAR_EMERGENCY','record_id':'c'*32,'environment':'PAPER_TRADING','live_enabled':False,
            'account':a['account'],'session_id':a['session_id'],'tws_pid':a['tws_pid'],'tws_start_filetime':a['tws_start_filetime'],
            'exception_id':None,'confirmed_at':stamp(NOW),'expires_at':stamp(NOW+timedelta(minutes=2))}
    def test_protected_recent_review_is_bound_to_account_and_session(self):
        self.assertEqual('c'*32,validate_review_permit(self.permit(),grant(),NOW))
        for field,value in (('account','DUR99995678'),('session_id','d'*32),('tws_start_filetime','2'),('live_enabled',True)):
            p=self.permit();p[field]=value
            with self.assertRaises(PermissionError):validate_review_permit(p,grant(),NOW)
    def test_missing_or_expired_review_permit_cannot_clear_emergency(self):
        with self.assertRaises(PermissionError):validate_review_permit({},grant(),NOW)
        with self.assertRaises(PermissionError):validate_review_permit(self.permit(),grant(),NOW+timedelta(minutes=2))
    def test_exception_review_must_bind_to_same_protected_exception(self):
        p=self.permit();p['exception_id']='b'*32
        self.assertEqual('c'*32,validate_review_permit(p,grant(),NOW,exception_id='b'*32))
        with self.assertRaises(PermissionError):validate_review_permit(p,grant(),NOW)

class ExceptionWire(Wire):
    def __init__(self,clock):super().__init__(clock);self.eur_cash=None
    def snapshot(self,*,diagnostic=False):
        if self.eur_cash is None and not diagnostic:raise PermissionError('EUR_CASH_RECONCILIATION_UNAVAILABLE')
        s=snapshot(self.clock());s.update(orders=copy.deepcopy(self.orders),events=self.drain(),eur_cash=self.eur_cash,cash_reconciliation=cash(self.eur_cash))
        return s
    def additional_exposure(self):return additional(self.clock())

class ExceptionalLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.now=NOW;self.a=grant();self.e=exception();self.a['eur_absence_exception_id']=self.e['record_id'];self.j=Journal();self.w=ExceptionWire(lambda:self.now)
        self.auth=Authorization(lambda:copy.deepcopy(self.a),lambda *args:True,lambda:self.now)
        self.exc=AbsentEurAuthorization(lambda:copy.deepcopy(self.e),lambda:self.now)
        self.lab=PaperLab(self.auth,self.j,self.w,clock=lambda:self.now,eur_exception=self.exc)
    def begin(self):return self.lab.begin(INTENT,100,self.w.quote())
    def roundtrip_events(self):
        result=[]
        for index,side,exec_id,price in ((0,'BUY','in','1.1001'),(1,'SELL','out','1.1011')):
            result.extend([{'kind':'fill','exec_id':exec_id,'order_id':10+index,'perm_id':100+index,'client_id':82,'contract_id':12087792,'side':side,'quantity':'100','price':price,'broker_time_raw':'SYNTHETIC','at':stamp(self.now)},
                {'kind':'status','order_id':10+index,'status':'Filled','at':stamp(self.now)},
                {'kind':'commission','exec_id':exec_id,'amount':'2','currency':'USD','at':stamp(self.now)}])
        return result
    def test_initial_exception_preserves_null_balance_and_does_not_clear_emergency(self):
        self.lab.state['emergency']=True;self.lab.persist('SYNTHETIC_EMERGENCY')
        s=self.lab.connect_and_reconcile();self.assertIsNone(s['eur_cash']);self.assertTrue(self.lab.state['emergency'])
        self.assertEqual('EUR_ROW_ABSENT',self.lab.state['initial_eur_absence']['eur_state'])
        with self.assertRaises(PermissionError):self.begin()
        self.assertEqual([],self.w.calls)
    def test_reservation_consumes_exception_before_mock_send_and_keeps_strategy_capital(self):
        o=self.begin()
        self.assertIsNone(o['initial_eur_uncertainty']['eur_balance'])
        self.assertEqual(INTENT,self.j.state['eur_absence_consumed'][self.e['record_id']]['intent'])
        self.assertEqual('10',self.j.state['sessions'][self.a['session_id']]['reserved'])
        self.assertEqual('100',self.lab.state['strategy_capital']['equity'])
    def test_default_route_without_protected_exception_still_blocks_absent_row(self):
        self.lab.eur_exception=None
        with self.assertRaises(PermissionError):self.begin()
        self.assertEqual([],self.w.calls)
    def test_zero_reported_later_does_not_bypass_initial_specific_position_check(self):
        self.w.eur_cash='0';a=additional();a['positions']=[{'quantity':'100'}]
        with patch.object(self.w,'additional_exposure',return_value=a):
            with self.assertRaises(PermissionError):self.begin()
        self.assertEqual([],self.w.calls)
    def test_exception_expiry_after_reservation_blocks_further_mutation_checks(self):
        self.begin();self.now+=timedelta(minutes=16)
        with self.assertRaises(PermissionError):self.lab.check()
        self.assertEqual('10',self.j.state['sessions'][self.a['session_id']]['reserved'])
    def test_expired_regular_execution_grant_cannot_be_extended_by_exception(self):
        self.a.update(confirmed_at=stamp(NOW-timedelta(minutes=31)),expires_at=stamp(NOW-timedelta(minutes=1)))
        with self.assertRaises(PermissionError):self.begin()
        self.assertEqual([],self.w.calls)
    def test_expired_exception_and_tws_restart_block_before_mock_send(self):
        self.e['expires_at']=stamp(NOW)
        with self.assertRaises(PermissionError):self.begin()
        self.e=exception();self.auth.session_alive=lambda *args:False
        with self.assertRaises(PermissionError):self.begin()
        self.assertEqual([],self.w.calls)
    def test_worker_restart_does_not_reuse_consumed_exception(self):
        self.begin();calls=copy.deepcopy(self.w.calls)
        restarted=PaperLab(self.auth,self.j,self.w,clock=lambda:self.now,eur_exception=self.exc)
        restarted.connect_and_reconcile()
        self.assertEqual('OWNED_PREFILL_EUR_ABSENCE',restarted.reconciliation_kind)
        with self.assertRaises(PermissionError):restarted.check()
        self.assertIn(self.e['record_id'],restarted.state['eur_absence_consumed']);self.assertEqual(calls,self.w.calls)
    def test_stale_accepted_baseline_blocks_before_an_order_can_be_registered(self):
        self.lab.connect_and_reconcile();self.now+=timedelta(seconds=31)
        with self.assertRaises(PermissionError):self.lab.check()
        self.assertEqual({},self.lab.state['orders']);self.assertEqual([],self.w.calls)
    def test_send_uncertainty_retains_consumption_reserve_and_emergency(self):
        self.w.fail_send=True
        with self.assertRaises(ConnectionError):self.begin()
        self.assertTrue(self.lab.state['emergency']);self.assertEqual('10',self.j.state['sessions'][self.a['session_id']]['reserved'])
        self.assertEqual('UNKNOWN',self.lab.state['orders'][INTENT]['state'])
    def test_post_roundtrip_absence_does_not_release_reserve_or_certify_account_flat(self):
        self.begin();self.lab.ingest(self.roundtrip_events());self.w.orders=[]
        self.assertEqual('AWAITING_POST_RECONCILIATION',self.lab.state['orders'][INTENT]['state'])
        with self.assertRaises(PermissionError):self.lab.supervise()
        self.assertTrue(self.lab.state['emergency']);self.assertEqual('10',self.j.state['sessions'][self.a['session_id']]['reserved'])
        self.assertEqual({},self.lab.state['experiences'])
    def test_explicit_post_zero_and_costs_complete_release_only_own_diagnostic_reserve(self):
        self.begin();self.lab.ingest(self.roundtrip_events());self.w.orders=[];self.w.eur_cash='0';self.lab.supervise()
        self.assertEqual('CLOSED',self.lab.state['orders'][INTENT]['state']);self.assertEqual('0',self.j.state['sessions'][self.a['session_id']]['reserved'])
        self.assertIsNone(self.lab.state['experiences'][INTENT]['initial_eur_uncertainty']['eur_balance'])
        self.assertIsNotNone(self.lab.state['orders'][INTENT]['post_eur_reconciled_at']);self.assertEqual('100',self.lab.state['strategy_capital']['equity'])
        confirmed=self.lab.state['orders'][INTENT]['post_eur_reconciled_at'];experience=copy.deepcopy(self.lab.state['experiences'][INTENT])
        self.now+=timedelta(seconds=1);self.lab.connect_and_reconcile()
        self.assertEqual(confirmed,self.lab.state['orders'][INTENT]['post_eur_reconciled_at']);self.assertEqual(experience,self.lab.state['experiences'][INTENT])
    def test_post_nonzero_conflict_suspends_without_releasing_reserve(self):
        self.begin();self.lab.ingest(self.roundtrip_events());self.w.orders=[];self.w.eur_cash='0.01'
        with self.assertRaises(PermissionError):self.lab.supervise()
        self.assertTrue(self.lab.state['emergency']);self.assertEqual('10',self.j.state['sessions'][self.a['session_id']]['reserved'])
    def test_explicit_post_cash_zero_with_zero_quantity_fx_bookmark_can_complete(self):
        self.begin();self.lab.ingest(self.roundtrip_events());self.w.orders=[];self.w.eur_cash='0'
        original=self.w.snapshot
        def with_zero_bookmark(**kwargs):
            s=original(**kwargs);s['positions']=[{'quantity':'0','security_type':'CASH'}];return s
        with patch.object(self.w,'snapshot',side_effect=with_zero_bookmark):self.lab.supervise()
        self.assertEqual('CLOSED',self.lab.state['orders'][INTENT]['state'])
    def test_review_acceptance_is_distinct_from_flat_and_cannot_send(self):
        self.lab.exception_review=True;self.lab.state['emergency']=True;self.lab.persist('SYNTHETIC_EMERGENCY')
        result=self.lab.review_flat()
        self.assertEqual('INITIAL_BASELINE_EXCEPTION_REVIEWED',result['state']);self.assertIsNone(result['eur_balance'])
        with self.assertRaises(PermissionError):self.begin()
        self.assertEqual([],self.w.calls)
    def test_review_expiring_during_api_reads_keeps_emergency(self):
        self.lab.exception_review=True;self.lab.state['emergency']=True;self.lab.persist('SYNTHETIC_EMERGENCY')
        def expired():raise PermissionError('OWNER_REVIEW_EXPIRED')
        with self.assertRaises(PermissionError):self.lab.review_flat(expired)
        self.assertTrue(self.lab.state['emergency']);self.assertTrue(self.j.state['emergency']);self.assertEqual([],self.w.calls)
