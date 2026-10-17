"""Owner recovery policy, simulated fills and SDK serialization; no broker connections."""
import copy
import hashlib
import os
import unittest
import uuid
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from trading_agent.paper_lab import Authorization,PaperLab,DotnetJournal,num,stamp
from trading_agent.paper_recovery_close import RecoveryAuthorization,RecoveryClose
from trading_agent.paper_execution_wire import execution_wire
import test_paper_lab as f
import test_paper_eur_reconciliation as e

class RecoveryWire(e.ExceptionWire):
    def __init__(self,clock):
        super().__init__(clock);self.eur_cash='0';self.q=num(0);self.service=None;self.sell_size=100;self.late_fee=False;self.timeout=False
    def row(self):return {'contract_id':12087792,'security_type':'CASH','currency':'USD','quantity':str(self.q)}
    def snapshot(self,**kwargs):
        s=super().snapshot(**kwargs);s['positions']=[self.row()];return s
    def additional_exposure(self):return {**e.additional(self.clock()),'positions':[self.row()]}
    def quote(self):return {**super().quote(),'available_for_execution':True,'market_status':'OPEN'}
    observe_quote=quote
    def recovery_close(self,r,a):
        self.service.authorize_transport(r,'RECOVERY_CLOSE',r['order_id'],num(r['quantity']))
        self.calls.append(('recovery_close',r['order_id'],r['quantity']))
        if self.timeout:raise TimeoutError('SYNTHETIC_SEND_TIMEOUT')
        n=min(num(self.sell_size),num(r['quantity']));self.q-=n;self.eur_cash=str(self.q);self.orders=[]
        if n:self.events.append(dict(kind='fill',exec_id='sell-'+str(r['order_id']),order_id=r['order_id'],perm_id=200+r['order_id'],client_id=82,contract_id=12087792,side='SELL',quantity=str(n),price=r['price'],broker_time_raw='SYNTHETIC',at=stamp(self.clock())))
        if n and not self.late_fee:self.events.append(dict(kind='commission',exec_id='sell-'+str(r['order_id']),amount='2',currency='USD',at=stamp(self.clock())))
        self.events.append(dict(kind='completed_order',order_id=r['order_id'],perm_id=200+r['order_id'],client_id=82,contract_id=12087792,side='SELL',parent_id=0,reference=r['reference'],status='Filled' if self.q==0 else 'Cancelled',at=stamp(self.clock())))

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.now=f.NOW;self.old=f.grant();self.j=f.Journal();self.w=RecoveryWire(lambda:self.now)
        old_auth=Authorization(lambda:copy.deepcopy(self.old),lambda *args:True,lambda:self.now)
        lab=PaperLab(old_auth,self.j,self.w,clock=lambda:self.now);o=lab.begin(f.INTENT,100,self.w.quote())
        lab.ingest([dict(kind='fill',exec_id='buy',order_id=10,perm_id=100,client_id=82,contract_id=12087792,side='BUY',quantity='100',price='1.1001',broker_time_raw='SYNTHETIC',at=stamp(self.now)),dict(kind='commission',exec_id='buy',amount='2',currency='USD',at=stamp(self.now))])
        lab.ingest([dict(kind='completed_order',order_id=10+i,perm_id=100+i,client_id=82,contract_id=12087792,side='BUY' if i==0 else 'SELL',parent_id=0 if i==0 else 10,reference=o['intent'],status='Filled' if i==0 else 'Cancelled',at=stamp(self.now)) for i in range(3)])
        self.w.q=num(100);self.w.eur_cash='100';self.w.orders=[];self.w.calls=[]
        source=RecoveryClose(old_auth,self.j,self.w,clock=lambda:self.now).source()
        self.a={**source,'schema_version':1,'mode':'RecoveryClose','scope':'RECOVERY_CLOSE_ONLY','authorized':True,'revoked':False,
            'environment':'PAPER_TRADING','live_enabled':False,'account':self.old['account'],'port':7497,'client_id':82,
            'tws_pid':1,'tws_start_filetime':'1','session_id':'b'*32,'paper_checked':True,'identity_manual_match':True,
            'read_only_disabled_checked':True,'forex_permission_checked':True,'single_use':True,'emergency_retained':True,
            'contract_id':12087792,'instrument':'EUR/USD CASH IDEALPRO','side':'SELL','order_types':['LMT'],'tif':'IOC','max_quantity':'100',
            'confirmed_at':stamp(self.now),'expires_at':stamp(self.now+timedelta(minutes=15))}
        self.auth=RecoveryAuthorization(lambda:copy.deepcopy(self.a),lambda *args:True,lambda:self.now)
        self.restart()
    def restart(self):
        self.s=RecoveryClose(self.auth,self.j,self.w,clock=lambda:self.now);self.w.service=self.s
    def execute(self):return self.s.execute(sleep=lambda _:None,max_polls=1)
    def test_only_remaining_long_closed_and_net_costs_settled(self):
        result=self.execute();self.assertEqual('CLOSED',result['recovery_result']);self.assertEqual('0',result['quantity_eur'])
        self.assertEqual('-4.0100',result['net_pnl_usd']);self.assertEqual('0',result['reserved_usd']);self.assertTrue(self.j.state['emergency'])
        self.assertEqual(1,self.j.state['sessions'][self.old['session_id']]['count']);self.assertNotIn(self.a['session_id'],self.j.state['sessions'])
        self.assertEqual('100',self.j.state['strategy_capital']['equity']);self.assertEqual('RECOVERY_CLOSE_ONLY',self.j.state['experiences'][f.INTENT]['closing_reason'])
        self.assertEqual(1,len(self.w.calls));self.assertEqual('100',self.w.calls[0][2])
    def test_partial_ioc_leaves_reserve_and_requires_new_owner_permit(self):
        self.w.sell_size=40;result=self.execute();self.assertEqual('60',result['quantity_eur']);self.assertEqual('PARTIAL_OR_NO_FILL_RECONCILED',result['recovery_result']);self.assertEqual('10',result['reserved_usd'])
        self.restart()
        with self.assertRaisesRegex(PermissionError,'RECOVERY_AUTHORIZATION_ALREADY_USED'):self.execute()
        self.assertEqual(1,len(self.w.calls))
        self.a['session_id']='c'*32;self.a['max_quantity']='60';self.w.sell_size=60;self.restart();result=self.execute()
        self.assertEqual('CLOSED',result['recovery_result']);self.assertEqual('60',self.w.calls[1][2]);self.assertEqual(1,self.j.state['sessions'][self.old['session_id']]['count'])
    def test_late_sell_commission_retains_reserve_until_read_only_reconciliation(self):
        self.w.late_fee=True;result=self.execute();self.assertEqual('FLAT_COMMISSION_PENDING',result['recovery_result']);self.assertEqual('PENDING',result['sell_commission_status']);self.assertIsNone(result['net_pnl_usd']);self.assertEqual('10',result['reserved_usd'])
        r=next(iter(self.s.o['recovery_orders'].values()));self.w.events=[dict(kind='commission',exec_id='sell-'+str(r['order_id']),amount='2',currency='USD',at=stamp(self.now))]
        self.restart();snapshot,q=self.s.reconcile();result=self.s.report(snapshot,q)
        self.assertEqual('0',result['reserved_usd']);self.assertEqual('-4.0100',result['net_pnl_usd']);self.assertTrue(self.j.state['emergency']);self.assertEqual(1,len(self.w.calls))
    def test_flat_after_completed_close_never_sends_a_second_sell(self):
        self.execute();self.restart();result=self.execute();self.assertEqual(0,result['orders_sent']);self.assertEqual(1,len(self.w.calls))
    def test_unexplained_flat_quantity_does_not_send_or_release_reserve(self):
        self.w.q=num(0);self.w.eur_cash='0'
        with self.assertRaisesRegex(PermissionError,'RECOVERY_POSITION_NOT_OWNED_REMAINING_LONG'):self.execute()
        self.assertEqual([],self.w.calls);self.assertEqual('10',self.j.state['sessions'][self.old['session_id']]['reserved'])
    def test_negative_larger_or_unexplained_reduced_position_blocks(self):
        for q in (-1,101,60):
            self.w.q=num(q);self.w.eur_cash=str(q)
            with self.assertRaisesRegex(PermissionError,'RECOVERY_POSITION_NOT_OWNED_REMAINING_LONG'):self.execute()
            self.assertEqual([],self.w.calls)
    def test_source_perm_signature_intent_and_cap_cannot_change(self):
        original=copy.deepcopy(self.a)
        for k,v in (('opening_perm_id',999),('source_signature','d'*64),('opening_order_id',2),('max_quantity','99')):
            self.a=copy.deepcopy(original);self.a[k]=v
            with self.assertRaises(PermissionError):self.execute()
            self.assertEqual([],self.w.calls)
    def test_unknown_orders_account_reads_and_positions_mismatch_block(self):
        original=self.w.additional_exposure
        self.w.additional_exposure=lambda:{**original(),'status':'INCOMPLETE'}
        with self.assertRaisesRegex(PermissionError,'RECOVERY_ACCOUNT_RECONCILIATION_INCOMPLETE'):self.execute()
        self.w.additional_exposure=lambda:{**original(),'positions':[{**self.w.row(),'quantity':'99'}]}
        with self.assertRaises(PermissionError):self.execute()
        self.w.additional_exposure=original;self.w.orders=[dict(order_id=999)]
        with self.assertRaisesRegex(PermissionError,'RECOVERY_UNKNOWN_ORDER'):self.execute()
        self.assertEqual([],self.w.calls)
    def test_unknown_eur_never_uses_initial_exception(self):
        self.w.eur_cash=None
        with self.assertRaisesRegex(PermissionError,'RECOVERY_ACCOUNT_RECONCILIATION_INCOMPLETE'):self.execute()
        self.assertEqual([],self.w.calls)
    def test_current_identity_must_match_exactly_not_just_suffix(self):
        self.w.accounts=['DUR99995678']
        with self.assertRaisesRegex(PermissionError,'EXACT_IDENTITY_MISMATCH'):self.execute()
        self.assertEqual([],self.w.calls)
    def test_timeout_consumes_recovery_permit_and_never_retransmits(self):
        self.w.timeout=True
        with self.assertRaises(TimeoutError):self.execute()
        self.assertIn(self.a['session_id'],self.j.state['recovery_authorizations']);self.restart()
        with self.assertRaisesRegex(PermissionError,'RECOVERY_AUTHORIZATION_ALREADY_USED'):self.execute()
        self.a['session_id']='c'*32;self.restart()
        with self.assertRaisesRegex(PermissionError,'RECOVERY_PREVIOUS_SEND_UNCERTAIN'):self.execute()
        self.assertEqual(1,len(self.w.calls));self.assertEqual('10',self.j.state['sessions'][self.old['session_id']]['reserved'])
    def test_quote_unavailable_stale_or_wrong_market_blocks_before_send(self):
        quote=self.w.quote
        for values in ({'type':'DELAYED'},{'at':stamp(self.now-timedelta(seconds=6))},{'available_for_execution':False}):
            self.w.quote=lambda:{**quote(),**values}
            self.w.validate_quote=execution_wire(self.auth,lambda **kw:None).validate_quote
            with self.assertRaises(PermissionError):self.execute()
            self.assertNotIn('recovery_authorizations',self.j.state);self.assertEqual([],self.w.calls)
    def test_gates_refresh_after_quote_and_before_send_pending(self):
        quote=self.w.quote
        def changed():self.w.q=num(0);self.w.eur_cash='0';return quote()
        self.w.quote=changed
        with self.assertRaises(PermissionError):self.execute()
        self.assertNotIn('recovery_authorizations',self.j.state);self.assertEqual([],self.w.calls)
    def test_unconfirmed_original_bracket_cannot_be_replaced_with_sell(self):
        self.s.o['completed_orders'].pop('12')
        with self.assertRaisesRegex(PermissionError,'RECOVERY_ORIGINAL_BRACKET_UNRESOLVED'):self.execute()
        self.assertEqual([],self.w.calls)
    def test_journal_conflict_suspends_before_recovery_send(self):
        self.s.reconcile();self.j.revision+=1
        with self.assertRaisesRegex(PermissionError,'JOURNAL_CHANGED_RECONCILE_REQUIRED'):self.s.gate()
    def test_preview_is_read_only_and_keeps_emergency(self):
        result=self.s.preview();self.assertTrue(result['ready']);self.assertEqual('100',result['quantity_to_close'])
        self.assertTrue(result['emergency']);self.assertEqual([],self.w.calls);self.assertNotIn('recovery_authorizations',self.j.state)
    def test_expired_diagnostic_grant_is_not_a_recovery_authorization(self):
        self.old['expires_at']=stamp(self.now-timedelta(seconds=1))
        with self.assertRaisesRegex(PermissionError,'RECOVERY_AUTHORIZATION_REQUIRED'):RecoveryAuthorization(lambda:self.old,lambda *args:True,lambda:self.now).read()
        self.assertEqual('CLOSED',self.execute()['recovery_result'])
    def test_recovery_grant_live_expiry_process_buy_and_expanded_quantity_rejected(self):
        original=copy.deepcopy(self.a)
        for k,v in (('live_enabled',True),('environment','LIVE_TRADING'),('side','BUY'),('max_quantity','101'),('mode','ExecutionDiagnostics'),('tif','GTC'),('single_use',False),('expires_at',stamp(self.now-timedelta(seconds=1)))):
            self.a=copy.deepcopy(original);self.a[k]=v
            with self.assertRaises(PermissionError):self.auth.read()
        self.a=original;self.auth.session_alive=lambda *args:False
        with self.assertRaises(PermissionError):self.auth.read()
    def test_sdk_serializes_one_scoped_ioc_sell_and_blocks_short_expansion(self):
        calls=[];w=execution_wire(self.auth,self.s.gate,intent_guard=self.s.authorize_transport)
        w.expected=self.a['account'];w.verified=True
        original=self.w.recovery_close
        def serialize(r,a):
            w.recovery_close(r,a)
            with self.assertRaisesRegex(PermissionError,'RECOVERY_ALREADY_ATTEMPTED'):w.recovery_close(r,a)
            return original(r,a)
        self.w.recovery_close=serialize
        with patch('trading_agent.paper_execution_wire.utc',side_effect=lambda:self.now),patch.object(w.client,'isConnected',return_value=True),patch.object(w.client,'serverVersion',return_value=226),patch.object(w.client,'useProtoBuf',return_value=True),patch.object(w.client,'sendMsgProtoBuf',side_effect=lambda *args:calls.append(args)),patch.object(w.client,'sendMsg',side_effect=lambda *args:calls.append(args)):
            self.execute()
        self.assertEqual(1,len(calls));self.assertEqual({},w.approved)
    def test_forged_recovery_sell_cannot_pass_intent_guard(self):
        self.execute();record=next(iter(self.s.o['recovery_orders'].values()));forged=copy.deepcopy(record);forged['quantity']='101'
        with self.assertRaises(PermissionError):self.s.authorize_transport(forged,'RECOVERY_CLOSE',record['order_id'],101)
    def test_sdk_rejects_buy_excess_quantity_and_changed_price_before_serialization(self):
        for field,value in (('action','BUY'),('totalQuantity',num(101)),('lmtPrice',.5),('tif','GTC'),('parentId',10),('orderRef','foreign')):
            self.setUp();calls=[];w=execution_wire(self.auth,self.s.gate,intent_guard=self.s.authorize_transport)
            w.expected=self.a['account'];w.verified=True;original=w.client.placeOrder
            def altered(id,c,r):setattr(r,field,value);return original(id,c,r)
            self.w.recovery_close=w.recovery_close
            with patch('trading_agent.paper_execution_wire.utc',side_effect=lambda:self.now),patch.object(w.client,'isConnected',return_value=True),patch.object(w.client,'placeOrder',side_effect=altered),patch.object(w.client,'sendMsg',side_effect=lambda *args:calls.append(args)),patch.object(w.client,'sendMsgProtoBuf',side_effect=lambda *args:calls.append(args)):
                with self.assertRaises(PermissionError):self.execute()
            self.assertEqual([],calls);self.assertTrue(self.j.state['emergency']);self.assertIn(self.a['session_id'],self.j.state['recovery_authorizations'])
    def test_wrong_fee_currency_keeps_reserve_and_net_unknown(self):
        self.w.late_fee=True;result=self.execute();record=next(iter(self.s.o['recovery_orders'].values()))
        self.w.events=[dict(kind='commission',exec_id='sell-'+str(record['order_id']),amount='2',currency='EUR',at=stamp(self.now))]
        with self.assertRaises(PermissionError):self.s.reconcile()
        self.assertEqual('10',self.j.state['sessions'][self.old['session_id']]['reserved']);self.assertIsNone(result['net_pnl_usd'])
    def test_remaining_after_known_exit_uses_real_lower_quantity(self):
        self.w.sell_size=40;self.execute();self.a['session_id']='c'*32;self.a['max_quantity']='60';self.restart()
        result=self.s.preview();self.assertEqual('60',result['quantity_to_close']);self.assertEqual('100',result['opening_quantity'])
    def test_fill_before_disconnect_is_durable_and_does_not_release_reserve(self):
        self.w.timeout=True
        with self.assertRaises(TimeoutError):self.execute()
        record=next(iter(self.s.o['recovery_orders'].values()))
        events=[dict(kind='fill',exec_id='late-sell',order_id=record['order_id'],perm_id=200+record['order_id'],client_id=82,contract_id=12087792,side='SELL',quantity='40',price=record['price'],broker_time_raw='SYNTHETIC',at=stamp(self.now)),dict(kind='disconnect',at=stamp(self.now))]
        with self.assertRaisesRegex(PermissionError,'RECOVERY_BROKER_UNAVAILABLE'):self.s.ingest(events)
        self.assertIn('late-sell',self.j.state['orders'][f.INTENT]['fills']);self.assertEqual('10',self.j.state['sessions'][self.old['session_id']]['reserved']);self.assertTrue(self.j.state['emergency'])
    def test_working_recovery_requires_unchanged_ioc_price_quantity_and_reference(self):
        self.w.timeout=True
        with self.assertRaises(TimeoutError):self.execute()
        r=next(iter(self.s.o['recovery_orders'].values()))
        row=dict(order_id=r['order_id'],client_id=82,contract_id=12087792,side='SELL',order_type='LMT',parent_id=0,reference=r['reference'],tif='IOC',quantity=r['quantity'],limit_price=r['price'])
        self.w.orders=[row];self.s.reconcile()
        row['tif']='GTC'
        with self.assertRaisesRegex(PermissionError,'RECOVERY_UNKNOWN_ORDER'):self.s.reconcile()

@unittest.skipUnless(os.environ.get('TRADING_TEST_DB'),'Disposable PostgreSQL required')
class RecoveryPostgresTests(unittest.TestCase):
    def test_recovery_permit_and_sell_execution_survive_restart_without_second_experiment(self):
        t=RecoveryTests();t.setUp();scope_account='DUR'+str(uuid.uuid4().int)
        state=copy.deepcopy(t.j.state)
        from trading_agent.paper_lab import key
        state['account_key']=key(scope_account);t.a['account']=scope_account;t.w.accounts=[scope_account]
        with patch.dict(os.environ,{'TRADING_LAB_DB':os.environ['TRADING_TEST_DB']}):
            t.j=DotnetJournal(Path(__file__).resolve().parents[2]);t.j.commit(key(scope_account),0,state,{'event':'SYNTHETIC_RECOVERY_SOURCE'})
            t.restart();t.w.late_fee=True;t.execute();t.restart();saved=t.j.load(t.s.lab.scope)['state']
            self.assertIn(t.a['session_id'],saved['recovery_authorizations']);self.assertEqual(1,saved['sessions'][t.old['session_id']]['count']);self.assertEqual('10',saved['sessions'][t.old['session_id']]['reserved'])
            self.assertEqual('AWAITING_COMMISSIONS',saved['orders'][f.INTENT]['state'])
            self.assertEqual(1,len([x for x in saved['orders'][f.INTENT]['fills'].values() if x['side']=='SELL']))
            snapshot,q=t.s.reconcile();self.assertEqual(0,q);self.assertEqual(1,len(t.w.calls))

if __name__=='__main__':unittest.main()
