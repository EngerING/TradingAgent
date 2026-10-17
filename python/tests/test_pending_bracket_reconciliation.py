"""Synthetic broker sequences only; no network or order transmission."""
import copy
import io
import json
import os
import tempfile
import unittest
import uuid
from contextlib import redirect_stdout
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from trading_agent.paper_lab import PaperLab, stamp
from test_paper_lab import INTENT
import test_paper_eur_reconciliation as exception_fixtures

class PendingBracketTests(unittest.TestCase):
    setUp=exception_fixtures.ExceptionalLifecycleTests.setUp
    begin=exception_fixtures.ExceptionalLifecycleTests.begin
    def ack(self):
        o=self.lab.state['orders'][INTENT]
        events=[]
        for n,r in enumerate(self.w.orders):
            r['perm_id']=100+n
            events.append(dict(kind='open_order',order_id=r['order_id'],perm_id=100+n,status='Submitted',at=stamp(self.now)))
        self.lab.ingest(events)
        return o
    def fill(self,q=100):
        return dict(kind='fill',exec_id='buy',order_id=10,perm_id=100,client_id=82,contract_id=12087792,
                    side='BUY',quantity=str(q),price='1.1001',broker_time_raw='SYNTHETIC',at=stamp(self.now))
    def cancelled(self,index):
        o=self.lab.state['orders'][INTENT]
        return dict(kind='completed_order',order_id=10+index,perm_id=100+index,client_id=82,contract_id=12087792,
                    side='BUY' if index==0 else 'SELL',parent_id=0 if index==0 else 10,reference=o['intent'],
                    status='Cancelled',completed_status_raw='Cancelled by Trader',at=stamp(self.now))
    def test_transmitted_zero_fills_retains_null_exception_and_reserve(self):
        self.begin();o=self.ack();self.lab.connect_and_reconcile()
        self.assertEqual('ACKNOWLEDGED',o['state']);self.assertEqual('OWNED_PREFILL_EUR_ABSENCE',self.lab.reconciliation_kind)
        self.assertIsNone(o['prefill_reconciliation']['evidence']['eur_balance'])
        self.assertFalse(o['prefill_reconciliation']['evidence']['new_entry_allowed'])
        self.assertEqual('10',self.j.state['sessions'][self.a['session_id']]['reserved'])
        self.assertNotIn('close_deadline_at',o);self.assertEqual(1,len(self.w.calls))
    def test_suspension_after_ack_and_restart_never_retransmits(self):
        self.begin();self.ack();self.lab.stop('SYNTHETIC_ACK_SUSPENSION')
        restarted=PaperLab(self.auth,self.j,self.w,clock=lambda:self.now,eur_exception=self.exc)
        restarted.connect_and_reconcile();restarted.begin(INTENT,100,self.w.quote())
        self.assertTrue(restarted.state['emergency']);self.assertEqual(1,len(self.w.calls))
        with self.assertRaisesRegex(PermissionError,'DIAGNOSTIC_ALREADY_ATTEMPTED'):restarted.begin('c'*64,100,self.w.quote())
    def test_partial_and_full_fill_require_strict_eur_cash(self):
        for q in (40,100):
            with self.subTest(q=q):
                self.setUp();self.begin();self.ack();self.lab.ingest([self.fill(q)])
                self.assertFalse(self.lab.reconciled)
                with self.assertRaisesRegex(PermissionError,'EUR_CASH_RECONCILIATION_UNAVAILABLE'):self.lab.connect_and_reconcile()
                self.assertEqual('PARTIALLY_FILLED' if q==40 else 'FILLED',self.lab.state['orders'][INTENT]['state'])
                self.assertEqual('STRICT_REQUIRED_AFTER_FIRST_FILL',self.lab.state['eur_absence_consumed'][self.e['record_id']]['phase'])
                self.assertEqual(1,len(self.w.calls));self.assertEqual('10',self.j.state['sessions'][self.a['session_id']]['reserved'])
    def test_partial_fill_with_matching_cash_and_proportional_stop_reconciles(self):
        self.begin();self.ack();self.lab.ingest([self.fill(40)]);self.w.eur_cash='40';self.w.orders[2]['quantity']='40'
        self.lab.connect_and_reconcile();self.assertTrue(self.lab.reconciled);self.assertEqual('STRICT',self.lab.reconciliation_kind)
    def test_complete_fill_with_matching_cash_reconciles_strictly(self):
        self.begin();self.ack();self.lab.ingest([self.fill()]);self.w.eur_cash='100'
        self.lab.connect_and_reconcile();self.assertEqual('STRICT',self.lab.reconciliation_kind)
    def test_late_fill_is_archived_before_cash_error_even_after_local_cancel(self):
        self.begin();o=self.ack();self.lab.ingest([dict(kind='status',order_id=10,status='ApiCancelled',perm_id=0,at=stamp(self.now))])
        self.assertEqual('CANCELLED_NO_FILL',o['state']);self.w.orders=[];self.w.events=[self.fill(),dict(kind='commission',exec_id='buy',amount='2',currency='USD',at=stamp(self.now))]
        with self.assertRaisesRegex(PermissionError,'EUR_CASH_RECONCILIATION_UNAVAILABLE'):self.lab.connect_and_reconcile()
        self.assertEqual('FILLED',self.j.state['orders'][INTENT]['state']);self.assertEqual('2',self.j.state['orders'][INTENT]['commissions']['buy']['amount'])
        self.assertIn('LATE_FILL_AFTER_CANCEL',o['incidents']);self.assertTrue(self.j.state['emergency'])
    def test_local_cancel_does_not_release_reserved_budget_even_with_prior_ack(self):
        self.begin();self.ack();self.w.orders=[]
        self.lab.ingest([dict(kind='status',order_id=10+n,status='ApiCancelled',perm_id=0,at=stamp(self.now)) for n in range(3)])
        self.lab.connect_and_reconcile();self.assertEqual('10',self.j.state['sessions'][self.a['session_id']]['reserved'])
        self.assertNotIn('cancellation_reconciled_at',self.lab.state['orders'][INTENT])
    def test_all_three_server_cancellations_and_flat_reads_release_only_reserve(self):
        self.begin();self.ack();self.w.orders=[];self.lab.ingest([self.cancelled(n) for n in range(3)])
        self.lab.connect_and_reconcile();o=self.lab.state['orders'][INTENT]
        self.assertIn('cancellation_reconciled_at',o);self.assertEqual('0',self.j.state['sessions'][self.a['session_id']]['reserved'])
        self.assertIn(self.e['record_id'],self.lab.state['eur_absence_consumed']);self.assertEqual(1,self.j.state['sessions'][self.a['session_id']]['count'])
        with self.assertRaisesRegex(PermissionError,'STRICT_FLAT_REVIEW_REQUIRED'):self.lab.review_flat()
    def test_fill_after_reconciled_cancel_restores_reserve_and_emergency(self):
        self.begin();self.ack();self.w.orders=[];self.lab.ingest([self.cancelled(n) for n in range(3)]);self.lab.connect_and_reconcile()
        self.lab.ingest([self.fill()]);self.assertEqual('10',self.j.state['sessions'][self.a['session_id']]['reserved']);self.assertTrue(self.j.state['emergency'])
    def test_foreign_order_or_incomplete_reads_block_pending_reconciliation(self):
        for change in ('foreign','incomplete','position'):
            with self.subTest(change=change):
                self.setUp();self.begin();self.ack()
                if change=='foreign':self.w.orders.append(dict(order_id=999))
                elif change=='position':
                    self.w.additional_exposure=lambda:{'status':'COMPLETE','positions':[{'quantity':'1'}],'errors':[],'received_at':stamp(self.now)}
                else:self.w.additional_exposure=lambda:{'status':'INCOMPLETE','positions':[],'errors':[],'received_at':stamp(self.now)}
                with self.assertRaises(PermissionError):self.lab.connect_and_reconcile()
                self.assertEqual(1,len(self.w.calls))
    def test_pre_send_gates_refreshed_after_contract_read(self):
        def contract():self.w.orders=[dict(order_id=999)];return {}
        self.w.contract_details=contract
        with self.assertRaises(PermissionError):self.begin()
        self.assertEqual([],self.w.calls);self.assertEqual({},self.j.state['orders']);self.assertEqual({},self.j.state['sessions'])
        self.assertNotIn(self.e['record_id'],self.j.state.get('eur_absence_consumed',{}))
        self.assertFalse(any(e['event']=='INTENT_RESERVED_BEFORE_TRANSMISSION' for e in self.j.events))
    def test_stale_quote_or_expired_exception_fails_before_send_pending(self):
        for seconds in (6,901):
            self.setUp()
            def contract():self.now+=timedelta(seconds=seconds);return {}
            self.w.contract_details=contract
            with self.assertRaises(PermissionError):self.begin()
            self.assertEqual([],self.w.calls);self.assertEqual({},self.j.state['orders']);self.assertEqual({},self.j.state['sessions'])
    def test_no_ack_cannot_blindly_cancel_after_timeout(self):
        self.begin();self.now+=timedelta(seconds=11)
        with self.assertRaisesRegex(PermissionError,'ACK_UNCONFIRMED_RECONCILE_REQUIRED'):self.lab.supervise()
        self.assertEqual(1,len(self.w.calls));self.assertTrue(self.j.state['emergency'])
    def test_acknowledged_pending_bracket_reconciles_before_scoped_cancel(self):
        self.begin();self.ack();self.now+=timedelta(seconds=11);self.lab.supervise()
        self.assertEqual(('cancel_parent',10),self.w.calls[-1]);self.assertIn('prefill_reconciliation',self.j.state['orders'][INTENT])
        self.assertEqual('10',self.j.state['sessions'][self.a['session_id']]['reserved'])
    def test_completed_callback_normalizes_server_status_and_validates_binding(self):
        from trading_agent.paper_execution_wire import execution_wire
        w=execution_wire(self.auth,lambda **kw:None,read_only=True);w.expected=self.a['account']
        self.begin();self.ack()
        order=SimpleNamespace(account=self.a['account'],orderId=10,permId=100,clientId=82,action='BUY',parentId=0,orderRef=INTENT,ocaGroup='',ocaType=0)
        w.completedOrder(SimpleNamespace(conId=12087792),order,SimpleNamespace(completedStatus='Filled Size: 100',status='Filled'))
        event=w.drain()[0];self.assertEqual('Filled',event['status']);self.lab.ingest([event]);self.assertEqual('Filled',self.lab.state['orders'][INTENT]['statuses']['10'])
        event['reference']='foreign';event['order_id']=11
        with self.assertRaisesRegex(PermissionError,'COMPLETED_ORDER_LINK_UNVERIFIED'):self.lab.ingest([event])
    def test_read_only_diagnose_archives_late_fill_without_orders_or_clearing_emergency(self):
        from trading_agent.paper_lab_diagnostics import inspect
        self.begin();self.ack();self.lab.ingest([dict(kind='status',order_id=10,status='ApiCancelled',perm_id=0,at=stamp(self.now))]);self.lab.stop('SYNTHETIC_SUSPENSION')
        self.w.eur_cash='100';self.w.orders=[];self.w.events=[self.fill(),dict(kind='commission',exec_id='buy',amount='2',currency='USD',at=stamp(self.now))]
        self.w.client=SimpleNamespace(serverVersion=lambda:226);self.w.trading_session={};self.w.api_events=[]
        self.w.observe_quote=lambda:{'type':'LIVE','reasons':[]};self.w.read_diagnostics=lambda:{};self.w.disconnect=lambda:None
        self.w.session=SimpleNamespace(binding=SimpleNamespace(masked_account='***5678'))
        before=copy.deepcopy(self.w.calls)
        base=Path(__file__).resolve().parents[2]/'artifacts'
        with tempfile.TemporaryDirectory(dir=base) as directory:
            root=Path(directory);(root/'.local').mkdir();grant=root/'.local/paper-lab-authorization.dpapi';grant.write_bytes(b'unchanged grant')
            emergency=root/'.local/paper-lab.emergency';emergency.write_bytes(b'emergency retained')
            with patch('trading_agent.paper_lab_diagnostics.InspectionAuthorization',return_value=self.auth),patch('trading_agent.paper_lab_diagnostics.DotnetJournal',return_value=self.j),patch('trading_agent.paper_lab_diagnostics.execution_wire',return_value=self.w) as factory,patch('trading_agent.ibkr_session.session_guard',return_value=self.w.session),redirect_stdout(io.StringIO()):inspect(root)
            report=json.loads((root/'artifacts/paper-lab/data-diagnostics.json').read_text())
            self.assertTrue(factory.call_args.kwargs['read_only']);self.assertEqual(before,self.w.calls)
            self.assertEqual('BLOCKED',report['owned_reconciliation']['status']);self.assertEqual('PROTECTION_UNCONFIRMED',report['owned_reconciliation']['reason'])
            self.assertEqual('FILLED',self.j.state['orders'][INTENT]['state']);self.assertEqual('2',self.j.state['orders'][INTENT]['commissions']['buy']['amount'])
            self.assertEqual('10',report['reserved_usd']);self.assertTrue(self.j.state['emergency'])
            self.assertEqual(b'unchanged grant',grant.read_bytes());self.assertEqual(b'emergency retained',emergency.read_bytes())

@unittest.skipUnless(os.environ.get('TRADING_TEST_DB'),'Disposable PostgreSQL required')
class PendingBracketPostgresTests(unittest.TestCase):
    def test_late_fill_after_suspend_is_durable_and_cannot_be_erased_by_restart(self):
        from trading_agent.paper_lab import DotnetJournal
        f=PendingBracketTests();f.setUp();f.a['account']='DUR'+str(uuid.uuid4().int);f.e['account']=f.a['account'];f.w.accounts=[f.a['account']]
        with patch.dict(os.environ,{'TRADING_LAB_DB':os.environ['TRADING_TEST_DB']}):
            f.j=DotnetJournal(Path(__file__).resolve().parents[2]);f.lab=PaperLab(f.auth,f.j,f.w,clock=lambda:f.now,eur_exception=f.exc)
            f.begin();f.ack();f.lab.ingest([dict(kind='status',order_id=10,status='ApiCancelled',perm_id=0,at=stamp(f.now))]);f.lab.stop('SYNTHETIC_CANCELLED_SUSPENSION')
            restarted=PaperLab(f.auth,f.j,f.w,clock=lambda:f.now,eur_exception=f.exc)
            f.w.orders=[];f.w.events=[f.fill(),dict(kind='commission',exec_id='buy',amount='2',currency='USD',at=stamp(f.now))]
            with self.assertRaisesRegex(PermissionError,'EUR_CASH_RECONCILIATION_UNAVAILABLE'):restarted.connect_and_reconcile()
            again=PaperLab(f.auth,f.j,f.w,clock=lambda:f.now,eur_exception=f.exc)
            self.assertEqual('FILLED',again.state['orders'][INTENT]['state']);self.assertEqual('100',again.state['orders'][INTENT]['fills']['buy']['quantity'])
            self.assertEqual('2',again.state['orders'][INTENT]['commissions']['buy']['amount']);self.assertTrue(again.state['emergency'])
            self.assertEqual('10',again.state['sessions'][f.a['session_id']]['reserved']);self.assertEqual(1,len(f.w.calls))

if __name__=='__main__':unittest.main()
