import copy
from datetime import datetime,timezone,timedelta
from decimal import Decimal
import hashlib
import os
from unittest.mock import patch
import unittest
from trading_agent.paper_lab import Authorization,PaperLab,num,stamp

NOW=datetime(2026,10,4,19,0,tzinfo=timezone.utc)
IDENTITY='DUR12345678'
INTENT=hashlib.sha256(b'synthetic-intent').hexdigest()
def grant():return {'schema_version':1,'account':IDENTITY,'authorized':True,'environment':'PAPER_TRADING','live_enabled':False,
    'paper_checked':True,'read_only_disabled_checked':True,'identity_manual_match':True,'forex_permission_checked':True,'port':7497,'client_id':82,
    'tws_pid':1,'tws_start_filetime':'1','instruments':['EUR/USD'],'order_types':['LMT','STP'],'mode':'ExecutionDiagnostics',
    'max_experiments':1,'max_quantity':100,'max_notional_usd':150,'max_hold_seconds':60,'diagnostic_loss_budget':10,
    'confirmed_at':stamp(NOW),'expires_at':stamp(NOW+timedelta(minutes=30)),'session_id':'a'*32,'emergency':False,'revoked':False,
    'manage_owned_positions_after_stop':True}
class Journal:
    def __init__(self):self.revision=0;self.state=None;self.events=[];self.risk_allowed=False
    def load(self,scope):return {'revision':self.revision,'state':copy.deepcopy(self.state)}
    def commit(self,scope,revision,state,event):
        if revision!=self.revision:raise RuntimeError('CAS_CONFLICT')
        self.revision+=1;self.state=copy.deepcopy(state);self.events.append(event);return self.revision
    def strategy_initial(self):return {'equity':100,'capital':{'consumedLoss':0}}
    def strategy_mark(self,a):return a
    def strategy_risk(self,a,r):return {'allowed':self.risk_allowed,'quantity':50,'estimatedLoss':'.1'}
    def strategy_settle(self,a,net,fees):return {'equity':num(a['equity'])+net,'capital':{'consumedLoss':num(a['capital']['consumedLoss'])+max(0,-net)}}
class Wire:
    def __init__(self,clock):self.clock=clock;self.connected=False;self.accounts=[IDENTITY];self.next_order_id=10;self.calls=[];self.events=[];self.orders=[];self.eur_cash='0';self.fail_send=False;self.foreign_positions=[]
    def connect(self,a):self.connected=True;return self.accounts
    def contract_details(self):return {'account_restrictions_verified':False}
    def quote(self):return {'type':'LIVE','bid':'1.1000','ask':'1.1001','at':stamp(self.clock())}
    def validate_quote(self,q):
        if q['type']!='LIVE':raise PermissionError('QUOTE_UNUSABLE')
    def snapshot(self):return {'orders':copy.deepcopy(self.orders),'events':self.drain(),'eur_cash':self.eur_cash,'foreign_positions':self.foreign_positions,
        'initial_margin':{'value':'0','currency':'USD','at':stamp(self.clock())},'positions':[],'portfolio':[],
        'exposure_reads_complete':True,'received_at':stamp(self.clock()),'cash_reconciliation':{
            'state':'CONFIRMED_ZERO' if self.eur_cash=='0' else 'CONFIRMED_NONZERO','query_status':'COMPLETE','account_ready':True}}
    def bracket(self,o,a):
        self.calls.append(('bracket',o['order_ids'][:]))
        if self.fail_send:self.connected=False;raise ConnectionError()
        self.orders=[{'order_id':i,'status':'Submitted','order_type':'STP' if n==2 else 'LMT','side':'BUY' if n==0 else 'SELL',
            'quantity':o['quantity'],'oca_type':2,'oca_group':o['intent'],'client_id':82,'contract_id':12087792,'parent_id':o['order_ids'][0],
            'reference':o['intent']} for n,i in enumerate(o['order_ids'])]
    def cancel_parent(self,o):self.calls.append(('cancel_parent',o['order_ids'][0]))
    def close_owned(self,o,qty,q,a):self.calls.append(('close_owned',str(qty),o['order_ids'][1]))
    def drain(self):result=self.events;self.events=[];return result
class PaperLabTests(unittest.TestCase):
    def setUp(self):
        self.now=NOW;self.a=grant();self.j=Journal();self.w=Wire(lambda:self.now)
        self.auth=Authorization(lambda:copy.deepcopy(self.a),lambda *args:True,lambda:self.now)
        self.lab=PaperLab(self.auth,self.j,self.w,clock=lambda:self.now);self.lab.connect_and_reconcile()
    def begin(self,q=100):return self.lab.begin(INTENT,q,self.w.quote())
    def event(self,kind,index=0,**kw):
        o=self.lab.state['orders'][INTENT]
        return dict(kind=kind,order_id=o['order_ids'][index],at=stamp(self.now),**kw)
    def fill(self,index,quantity,execution_id,price):return self.event('fill',index,exec_id=execution_id,perm_id=100+index,client_id=82,contract_id=12087792,side='BUY' if index==0 else 'SELL',quantity=str(quantity),price=str(price),broker_time_raw='SYNTHETIC')
    def full_roundtrip(self,fees=True):
        self.lab.ingest([self.fill(0,100,'in','1.1001'),self.event('status',status='Filled'),self.fill(1,100,'out','1.1011'),self.event('status',1,status='Filled'),self.event('status',2,status='Cancelled')])
        self.w.orders=[];self.w.eur_cash='0'
        if fees:self.lab.ingest([{'kind':'commission','exec_id':i,'amount':'2','currency':'USD','at':stamp(self.now)} for i in ('in','out')])
        if fees:self.lab.connect_and_reconcile()
    def test_authorized_paper_and_intent_durable_before_send(self):
        o=self.begin();self.assertEqual('SEND_PENDING',o['state']);self.assertEqual(3,len(o['order_ids']))
        self.assertEqual('10',self.j.state['sessions']['a'*32]['reserved']);self.assertEqual(100,self.j.state['strategy_capital']['initial'])
        self.assertEqual('INTENT_RESERVED_BEFORE_TRANSMISSION',self.j.events[-1]['event'])
    def test_live_and_same_suffix_identity_rejected(self):
        self.a['environment']='LIVE'
        with self.assertRaises(PermissionError):self.begin()
        self.a['environment']='PAPER_TRADING';self.w.accounts=['DUR99995678']
        with self.assertRaises(PermissionError):self.lab.connect_and_reconcile()
        self.assertEqual([],self.w.calls)
    def test_read_only_blocks_before_submission(self):
        self.a['read_only_disabled_checked']=False
        with self.assertRaises(PermissionError):self.begin()
        self.assertEqual([],self.w.calls)
    def test_expired_authorization_blocks_entry(self):
        self.now+=timedelta(minutes=31)
        with self.assertRaises(PermissionError):self.begin()
        self.assertEqual([],self.w.calls)
    def test_duplicate_intent_does_not_resend_and_conflict_is_rejected(self):
        self.begin();self.begin();self.assertEqual(1,len(self.w.calls))
        with self.assertRaises(PermissionError):self.begin(99)
    def test_parent_rejected_is_not_an_execution(self):
        self.begin();self.lab.ingest([self.event('reject',code=201)])
        self.assertEqual('REJECTED',self.lab.state['orders'][INTENT]['state']);self.assertEqual({},self.lab.state['experiences'])
    def test_partial_fill_preserves_reservation_and_cancels_only_remainder(self):
        self.begin();self.lab.ingest([self.fill(0,40,'part','1.1001'),self.event('status',status='Submitted')]);self.w.eur_cash='40'
        self.w.orders[2]['quantity']='40' # Simulated broker explicitly confirms proportional protection.
        self.lab.supervise();self.assertEqual('PARTIALLY_FILLED',self.lab.state['orders'][INTENT]['state'])
        self.assertEqual(('cancel_parent',10),self.w.calls[-1]);self.assertEqual('10',self.lab.state['sessions']['a'*32]['reserved'])
    def test_complete_execution_and_net_costs_settle_once(self):
        self.begin();self.full_roundtrip();self.assertEqual('CLOSED',self.lab.state['orders'][INTENT]['state'])
        e=self.lab.state['experiences'][INTENT];self.assertEqual('-3.9000',e['net_usd']);self.assertEqual('PAPER_DIAGNOSTIC',e['category'])
        self.lab.ingest([]);self.assertEqual('3.9000',self.lab.state['sessions']['a'*32]['consumed_loss'])
    def test_late_and_early_commissions_are_correlated_without_zero_fees(self):
        self.begin();self.full_roundtrip(False)
        self.assertEqual('AWAITING_COMMISSIONS',self.lab.state['orders'][INTENT]['state']);self.assertEqual({},self.lab.state['experiences'])
        self.lab.ingest([{'kind':'commission','exec_id':i,'amount':'2','currency':'USD','at':stamp(self.now)} for i in ('out','in')])
        self.lab.connect_and_reconcile()
        self.assertEqual('CLOSED',self.lab.state['orders'][INTENT]['state'])
    def test_disconnect_during_send_never_retries_blindly(self):
        self.w.fail_send=True
        with self.assertRaises(ConnectionError):self.begin()
        self.assertEqual('UNKNOWN',self.lab.state['orders'][INTENT]['state']);self.begin();self.assertEqual(1,len(self.w.calls))
    def test_reconnect_reconciles_acknowledged_intent_without_resend(self):
        self.begin();self.lab.stop('DISCONNECTED');self.lab.state['orders'][INTENT]['state']='UNKNOWN'
        self.w.events=[self.event('status',status='Submitted')];self.lab.connect_and_reconcile()
        self.assertTrue(self.lab.reconciled);self.begin();self.assertEqual(1,len(self.w.calls))
    def test_budget_loss_and_unknown_commission_currency_suspend(self):
        self.begin();self.full_roundtrip(False)
        self.lab.ingest([{'kind':'commission','exec_id':i,'amount':'6','currency':'USD','at':stamp(self.now)} for i in ('in','out')])
        self.lab.connect_and_reconcile()
        self.assertTrue(self.lab.state['emergency']);self.assertGreater(num(self.lab.state['sessions']['a'*32]['consumed_loss']),10)
    def test_protection_and_owned_close_never_naked_sell(self):
        self.begin();self.lab.ingest([self.fill(0,100,'in','1.1001'),self.event('status',status='Filled')]);self.w.eur_cash='100'
        self.now+=timedelta(seconds=5);self.lab.supervise()
        self.assertEqual(('close_owned','100',11),self.w.calls[-1]);self.assertNotIn(('cancel_parent',12),self.w.calls)
    def test_emergency_revocation_and_no_global_cancel(self):
        self.lab.stop('MANUAL');self.assertTrue(self.j.state['emergency'])
        with self.assertRaises(PermissionError):self.begin()
        self.assertEqual([],self.w.calls)
        self.a['revoked']=True
        with self.assertRaises(PermissionError):self.auth.read()
    def test_restart_preserves_ids_and_unknown_send_blocks(self):
        self.begin();self.w.orders=[]
        restarted=PaperLab(self.auth,self.j,self.w,clock=lambda:self.now)
        self.assertEqual(13,restarted.state['next_order_id'])
        with self.assertRaises(PermissionError):restarted.connect_and_reconcile()
        self.assertEqual(1,len(self.w.calls))
    def test_diagnostics_do_not_consume_or_reset_strategy_capital(self):
        self.begin();self.full_roundtrip();self.assertEqual('100',self.lab.state['strategy_capital']['equity']);self.assertEqual('0',self.lab.state['strategy_capital']['consumed_loss'])
        self.assertFalse(self.lab.state['experiences'][INTENT]['economically_viable_with_100_usd'])
    def test_duplicate_execution_callbacks_ignore_reception_timestamp(self):
        self.begin();e=self.fill(0,50,'part','1.1001');self.lab.ingest([e]);e['at']=stamp(NOW+timedelta(seconds=1));self.lab.ingest([e]);self.assertEqual(Decimal(50),self.lab.inventory(self.lab.state['orders'][INTENT]))
    def test_foreign_orders_and_unprotected_positions_block(self):
        self.w.orders=[{'order_id':999}]
        with self.assertRaises(PermissionError):self.lab.connect_and_reconcile()
        self.assertEqual([],self.w.calls)
    def test_strategy_requires_persisted_capital_and_existing_risk_gate(self):
        self.a['mode']='StrategyPaper';lab=PaperLab(self.auth,self.j,self.w,clock=lambda:self.now);lab.connect_and_reconcile()
        with self.assertRaises(PermissionError):lab.begin(INTENT,50,self.w.quote())
        request={'side':'BUY','bid':'1.1000','ask':'1.1001'}
        with self.assertRaises(PermissionError):lab.begin(INTENT,50,self.w.quote(),strategy_account=lab.state['strategy_account'],strategy_request=request)
        self.assertEqual([],self.w.calls);self.assertEqual('0',self.lab.state['strategy_capital']['consumed_loss'])
    def test_missing_budget_unknown_session_and_stale_quote_block(self):
        self.a['diagnostic_loss_budget']=0
        with self.assertRaises(PermissionError):self.begin()
        self.a['diagnostic_loss_budget']=10;q=self.w.quote();q['at']=stamp(NOW-timedelta(seconds=6))
        with self.assertRaises(PermissionError):self.lab.begin(INTENT,100,q)
        self.a['session_id']='b'*32
        with self.assertRaises(PermissionError):self.begin()
    def test_strategy_proposal_cannot_supply_its_own_fees_or_change_version(self):
        self.a.update(mode='StrategyPaper',strategy_requirements_verified=True,strategy_versions=['v1'],execution_requirements={'execution':{}})
        lab=PaperLab(self.auth,self.j,self.w,clock=lambda:self.now);lab.connect_and_reconcile()
        p={'strategy_version':'v1','signal_at':stamp(NOW),'stop':'1.099','target':'1.1016','market_context':{}}
        self.assertEqual('STRATEGY_REJECTED',lab.strategy_proposal(p,self.w.quote())['state']);self.assertEqual([],self.w.calls)
        p['commission']=0
        with self.assertRaises(PermissionError):lab.strategy_proposal(p,self.w.quote())
    def test_exit_received_during_snapshot_never_generates_another_sell(self):
        self.begin();self.lab.ingest([self.fill(0,100,'in','1.1001'),self.event('status',status='Filled')]);self.w.eur_cash='0'
        self.w.events=[self.fill(1,100,'out','1.1011'),self.event('status',1,status='Filled')];self.w.orders=[]
        self.now+=timedelta(seconds=61);self.lab.supervise()
        self.assertEqual([('bracket',[10,11,12])],self.w.calls)
        self.assertEqual('AWAITING_COMMISSIONS',self.lab.state['orders'][INTENT]['state'])
    def test_partial_oversized_or_held_stop_suspends_and_keeps_protection(self):
        self.begin();self.lab.ingest([self.fill(0,40,'part','1.1001'),self.event('status',status='Submitted')]);self.w.eur_cash='40'
        with self.assertRaises(PermissionError):self.lab.supervise()
        self.assertEqual(('cancel_parent',10),self.w.calls[-1]);self.assertTrue(self.lab.state['emergency'])
        self.assertFalse(any(c[0]=='close_owned' for c in self.w.calls))
    def test_unrelated_currency_exposure_blocks_owned_close(self):
        self.begin();self.lab.ingest([self.fill(0,100,'in','1.1001'),self.event('status',status='Filled')]);self.w.eur_cash='101'
        self.now+=timedelta(seconds=61)
        with self.assertRaises(PermissionError):self.lab.supervise()
        self.assertFalse(any(c[0]=='close_owned' for c in self.w.calls))
    def test_held_stop_is_not_confirmed_protection(self):
        self.begin();self.lab.ingest([self.fill(0,100,'in','1.1001'),self.event('status',status='Filled'),self.event('status',2,status='PreSubmitted',why_held=True)]);self.w.eur_cash='100'
        with self.assertRaises(PermissionError):self.lab.supervise()
        self.assertTrue(self.lab.state['emergency']);self.assertEqual(1,len(self.w.calls))
