"""One diagnostic: synthetic broker/SDK serialization; never an IBKR connection."""
import copy
from datetime import datetime,timezone,timedelta
import hashlib
import os
from pathlib import Path
from unittest.mock import patch
import unittest
import uuid
import test_paper_lab as fixtures
from trading_agent.paper_lab import Authorization,PaperLab,DotnetJournal,stamp,num
from trading_agent.paper_execution_wire import execution_wire,broker_timestamp
from trading_agent.paper_diagnostic_evidence import evidence

class DiagnosticCycleTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.PaperLabTests();self.f.setUp();self.o=self.f.begin()
    def buy(self,q=100,terminal='Filled'):
        self.f.lab.ingest([self.f.fill(0,q,'buy','1.10009'),self.f.event('status',status=terminal)])
        self.f.w.eur_cash=str(q)
    def finish(self,fees=True):
        q=self.f.lab.inventory(self.o)
        self.f.lab.ingest([self.f.fill(1,q,'sell','1.10000')])
        self.f.w.eur_cash='0';self.f.w.orders=[]
        if fees:self.f.lab.ingest([{'kind':'commission','exec_id':id,'amount':'2','currency':'USD'} for id in ('buy','sell')])
    def test_one_buy_one_existing_sell_child_close_and_final_evidence(self):
        self.buy();self.f.lab.supervise()
        self.assertEqual(('close_owned','100',self.o['order_ids'][1]),self.f.w.calls[-1])
        self.finish();self.assertEqual('AWAITING_POST_RECONCILIATION',self.o['state'])
        self.assertEqual('10',self.f.lab.state['sessions'][self.f.a['session_id']]['reserved'])
        self.f.lab.supervise();self.assertEqual('CLOSED',self.o['state'])
        e=self.f.lab.state['experiences'][fixtures.INTENT]['execution_diagnostic']
        self.assertEqual('100',e['requested_quantity_eur']);self.assertEqual('100',e['buy']['executed_quantity_eur'])
        self.assertEqual('1.10009',e['buy']['executed_vwap']);self.assertEqual('1.10000',e['sell']['executed_vwap'])
        self.assertEqual('2',e['buy']['commission']);self.assertEqual('USD',e['sell']['commission_currency'])
        self.assertEqual([],e['final_open_orders']);self.assertEqual('0',e['position_after_close']['eur_cash'])
        self.assertEqual(num('-.009'),num(e['gross_pnl_usd']));self.assertEqual(num('-4.009'),num(e['net_pnl_usd']))
        self.assertEqual(100,num(self.f.lab.state['strategy_capital']['equity']))
    def test_new_session_or_intent_cannot_repeat_the_diagnostic(self):
        self.f.a['session_id']='c'*32
        restarted=PaperLab(self.f.auth,self.f.j,self.f.w,clock=lambda:self.f.now)
        with self.assertRaisesRegex(PermissionError,'DIAGNOSTIC_ALREADY_ATTEMPTED'):
            restarted.begin(hashlib.sha256(b'new attempt').hexdigest(),100,self.f.w.quote())
        self.assertEqual(1,len(self.f.w.calls))
    def test_partial_fill_cancels_remainder_and_only_closes_confirmed_quantity(self):
        self.buy(40,'Submitted');self.f.w.orders[2]['quantity']='40'
        self.f.lab.supervise();self.assertEqual(('cancel_parent',10),self.f.w.calls[-1])
        self.assertFalse(any(c[0]=='close_owned' for c in self.f.w.calls))
        self.f.lab.ingest([self.f.event('status',status='Cancelled')]);self.f.w.orders[1]['quantity']='40'
        self.f.lab.supervise();self.assertEqual(('close_owned','40',11),self.f.w.calls[-1])
    def test_uncertain_partial_protection_suspends_without_sell(self):
        self.buy(40,'Submitted')
        with self.assertRaisesRegex(PermissionError,'PROTECTION_UNCONFIRMED'):self.f.lab.supervise()
        self.assertTrue(self.f.lab.state['emergency']);self.assertFalse(self.f.lab.reconciled)
        self.assertFalse(any(c[0]=='close_owned' for c in self.f.w.calls))
    def test_partial_sell_uses_remaining_owned_inventory(self):
        self.buy();self.f.lab.ingest([self.f.fill(1,30,'partial-sell','1.10000')]);self.f.w.eur_cash='70'
        self.f.w.orders[2]['quantity']='70';self.f.lab.supervise()
        self.assertEqual(('close_owned','70',11),self.f.w.calls[-1]);self.assertEqual(3,len(self.o['order_ids']))
    def test_foreign_order_appearing_after_open_blocks_close(self):
        self.buy();self.f.w.orders.append({'order_id':999})
        with self.assertRaisesRegex(PermissionError,'FOREIGN_OR_UNRECONCILED_ORDER'):self.f.lab.supervise()
        self.assertFalse(any(c[0]=='close_owned' for c in self.f.w.calls));self.assertTrue(self.f.lab.state['emergency'])
    def test_changed_parent_reference_or_oca_blocks_close(self):
        self.buy();self.f.w.orders[1]['parent_id']=999
        with self.assertRaisesRegex(PermissionError,'CLOSE_CHILD_UNCONFIRMED'):self.f.lab.supervise()
        self.assertFalse(any(c[0]=='close_owned' for c in self.f.w.calls))
    def test_late_commissions_keep_reserve_until_fresh_final_reconciliation(self):
        self.buy();self.f.lab.supervise();self.finish(False)
        self.f.lab.connect_and_reconcile();self.assertEqual('AWAITING_COMMISSIONS',self.o['state'])
        self.assertIsNone(evidence(self.o)['net_pnl_usd']);self.assertIsNone(evidence(self.o)['buy']['commission'])
        self.f.lab.ingest([{'kind':'commission','exec_id':id,'amount':'2','currency':'USD'} for id in ('buy','sell')])
        self.assertEqual('AWAITING_POST_RECONCILIATION',self.o['state']);self.f.lab.supervise()
        self.assertEqual('CLOSED',self.o['state']);self.assertEqual('0',self.f.lab.state['sessions'][self.f.a['session_id']]['reserved'])
    def test_foreign_commission_currency_is_recorded_without_inventing_usd_net(self):
        self.buy();self.finish(False)
        self.f.lab.ingest([{'kind':'commission','exec_id':id,'amount':'2','currency':'EUR'} for id in ('buy','sell')])
        e=evidence(self.o);self.assertEqual('EUR',e['buy']['commission_currency']);self.assertIsNone(e['net_pnl_usd'])
        self.assertTrue(self.f.lab.state['emergency']);self.assertEqual('10',self.f.lab.state['sessions'][self.f.a['session_id']]['reserved'])
    def test_close_is_not_repeated_after_timeout_or_restart(self):
        self.buy();self.f.lab.supervise();calls=len(self.f.w.calls)
        restarted=PaperLab(self.f.auth,self.f.j,self.f.w,clock=lambda:self.f.now);restarted.connect_and_reconcile();restarted.supervise()
        self.assertEqual(calls,len(self.f.w.calls));self.assertTrue(restarted.state['orders'][fixtures.INTENT]['timeout_close_sent'])
    def test_deadline_failure_suspends_without_new_sell(self):
        self.buy();self.f.now+=timedelta(seconds=61)
        with self.assertRaisesRegex(TimeoutError,'DIAGNOSTIC_CLOSE_DEADLINE_EXPIRED'):self.f.lab.supervise()
        self.assertTrue(self.f.lab.state['emergency']);self.assertFalse(any(c[0]=='close_owned' for c in self.f.w.calls))
    def test_unknown_or_incomplete_final_position_cannot_complete(self):
        self.buy();self.finish();self.f.w.eur_cash='1'
        with self.assertRaises(PermissionError):self.f.lab.supervise()
        self.assertEqual('AWAITING_POST_RECONCILIATION',self.o['state']);self.assertEqual({},self.f.lab.state['experiences'])
    def test_final_working_stop_prevents_release(self):
        self.buy();self.finish();self.f.w.orders=[{'order_id':12}]
        self.f.lab.supervise();self.assertEqual('AWAITING_POST_RECONCILIATION',self.o['state'])
        self.assertEqual('10',self.f.lab.state['sessions'][self.f.a['session_id']]['reserved'])
    def test_uncorrelated_commission_blocks_final_release_and_review(self):
        self.buy();self.finish();self.f.lab.ingest([{'kind':'commission','exec_id':'unrecognized-fee','amount':'2','currency':'USD'}])
        self.f.lab.supervise();self.assertEqual('AWAITING_POST_RECONCILIATION',self.o['state'])
        self.assertEqual('10',self.f.lab.state['sessions'][self.f.a['session_id']]['reserved'])
        with self.assertRaisesRegex(PermissionError,'NOT_FLAT_OR_COSTS_UNRESOLVED'):self.f.lab.review_flat()
    def test_evidence_compares_fill_quantities_numerically(self):
        self.buy();self.finish();self.o['fills']['sell']['quantity']='100.0'
        self.assertEqual(num('-4.009'),num(evidence(self.o)['net_pnl_usd']))
    def test_disconnect_stops_transport_even_if_inventory_was_known(self):
        self.buy();self.f.w.connected=False
        with self.assertRaises(PermissionError):self.f.lab.supervise()
        self.assertTrue(self.f.lab.state['emergency']);self.assertFalse(any(c[0]=='close_owned' for c in self.f.w.calls))
    def test_unrecognized_fill_is_durable_uncertainty(self):
        e=self.f.fill(0,1,'foreign','1.1');e['order_id']=999
        with self.assertRaisesRegex(PermissionError,'UNRECOGNIZED_EXECUTION'):self.f.lab.ingest([e])
        self.assertIn('foreign',self.f.j.state['unresolved_executions']);self.assertFalse(self.f.lab.reconciled)
    def test_journal_conflict_blocks_mutations(self):
        self.buy();self.f.j.revision+=1
        with self.assertRaisesRegex(PermissionError,'JOURNAL_CHANGED'):self.f.lab.supervise()
        self.assertFalse(any(c[0]=='close_owned' for c in self.f.w.calls))
    def test_unrecognized_fill_cannot_be_cleared_by_flat_owner_review(self):
        e=self.f.fill(0,1,'foreign','1.1');e['order_id']=999
        with self.assertRaises(PermissionError):self.f.lab.ingest([e])
        restarted=PaperLab(self.f.auth,self.f.j,self.f.w,clock=lambda:self.f.now)
        with self.assertRaisesRegex(PermissionError,'UNRECOGNIZED_EXECUTION_REVIEW_REQUIRED'):restarted.review_flat()
        self.assertTrue(restarted.state['emergency'])
    def test_flat_late_fee_reconciliation_is_not_limited_by_close_deadline(self):
        self.buy();self.f.lab.supervise();self.finish(False)
        self.f.now+=timedelta(seconds=90)
        self.f.lab.ingest([{'kind':'commission','exec_id':id,'amount':'2','currency':'USD'} for id in ('buy','sell')])
        self.f.w.operation_deadline_at=self.o['close_deadline_at'];self.f.lab.supervise()
        self.assertIsNone(self.f.w.operation_deadline_at);self.assertEqual('CLOSED',self.o['state'])
    def test_close_deadline_uses_first_broker_fill_and_never_resets_on_partial_fill(self):
        self.f.now+=timedelta(seconds=5)
        e=self.f.fill(0,40,'buy','1.10009');e['broker_at']=stamp(self.f.now)
        self.f.lab.ingest([e]);deadline=self.o['close_deadline_at']
        self.assertEqual(stamp(self.f.now+timedelta(seconds=60)),deadline)
        self.f.now+=timedelta(seconds=10);e=self.f.fill(0,60,'second','1.10009');e['broker_at']=stamp(self.f.now)
        self.f.lab.ingest([e]);self.assertEqual(deadline,self.o['close_deadline_at'])
    def test_transport_requires_exact_persisted_intent(self):
        changed=copy.deepcopy(self.o);changed['order_ids'][1]=999
        with self.assertRaisesRegex(PermissionError,'ORDER_NOT_DURABLY_REGISTERED'):
            self.f.lab.authorize_transport(changed,'BRACKET_ENTRY',10,100)
    def test_transport_rejects_unowned_sell_without_buy_fills(self):
        self.o['timeout_close_sent']=True;self.f.lab.persist('SYNTHETIC_CLOSE_REQUEST')
        with self.assertRaisesRegex(PermissionError,'NO_EXACT_OWNED_POSITION_TO_CLOSE'):
            self.f.lab.authorize_transport(self.o,'OWNED_CLOSE',11,100)

class DiagnosticAuthorizationTests(unittest.TestCase):
    def test_scope_cannot_be_expanded_even_without_eur_exception(self):
        for field,value in (('max_experiments',2),('max_quantity',101),('max_notional_usd',151),('diagnostic_loss_budget',11),('max_hold_seconds',61),
            ('expires_at',stamp(fixtures.NOW+timedelta(minutes=31)))):
            a=fixtures.grant();a[field]=value
            with self.subTest(field=field),self.assertRaises(PermissionError):Authorization(lambda:a,lambda *args:True,lambda:fixtures.NOW).read()
    def test_broker_clock_is_utc_and_unknown_time_stays_unknown(self):
        self.assertEqual('2026-10-05T12:00:00+00:00',broker_timestamp('20261005 12:00:00 UTC'))
        self.assertIsNone(broker_timestamp('20261005 12:00:00'))
        self.assertIsNone(broker_timestamp('20261101 01:30:00 US/Eastern'))
    def test_safety_quote_rounded_notional_and_costs_are_checked(self):
        f=fixtures.PaperLabTests();f.setUp();f.a['max_notional_usd']=110.009
        quote=f.w.quote();quote.update(ask='1.10009')
        with self.assertRaisesRegex(PermissionError,'NOTIONAL_LIMIT'):f.lab.begin(fixtures.INTENT,100,quote)
        f.a['max_notional_usd']=150;quote.update(bid='1',ask='1.1')
        with self.assertRaisesRegex(PermissionError,'DIAGNOSTIC_ESTIMATED_RISK'):f.lab.begin(fixtures.INTENT,100,quote)
        self.assertEqual([],f.w.calls)

class BoundSdkDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.PaperLabTests();self.f.setUp();self.o=self.f.begin();self.calls=[]
        self.w=execution_wire(self.f.auth,lambda management=False:self.f.lab.check(management),intent_guard=self.f.lab.authorize_transport)
        self.w.expected=fixtures.IDENTITY;self.w.verified=True
        patches=[patch('trading_agent.paper_execution_wire.utc',side_effect=lambda:self.f.now),
            patch.object(self.w.client,'isConnected',return_value=True),patch.object(self.w.client,'serverVersion',return_value=226),
            patch.object(self.w.client,'useProtoBuf',return_value=True),patch.object(self.w.client,'sendMsg',side_effect=lambda *args:self.calls.append(args)),
            patch.object(self.w.client,'sendMsgProtoBuf',side_effect=lambda *args:self.calls.append(args))]
        for p in patches:p.start();self.addCleanup(p.stop)
    def buy(self):
        self.f.lab.ingest([self.f.fill(0,100,'buy','1.1001'),self.f.event('status',status='Filled')]);self.f.w.eur_cash='100'
    def test_real_sdk_buy_and_protective_sell_serialization_bound_to_journal(self):
        self.w.bracket(self.o,self.f.a);self.assertEqual(3,len(self.calls));self.assertEqual({},self.w.approved)
        actions=[self.w.make_order(self.o,i,self.f.a)[0].action for i in range(3)]
        self.assertEqual(['BUY','SELL','SELL'],actions)
        with self.assertRaisesRegex(PermissionError,'BRACKET_ALREADY_ATTEMPTED'):self.w.bracket(self.o,self.f.a)
    def test_close_exact_remaining_position_uses_same_child_with_no_short_entry(self):
        self.buy();self.f.lab.supervise()
        self.w.close_owned(self.o,num(100),self.f.w.quote(),self.f.a)
        self.assertEqual(1,len(self.calls));self.assertEqual({},self.w.approved)
        with self.assertRaisesRegex(PermissionError,'CLOSE_ALREADY_ATTEMPTED'):self.w.close_owned(self.o,num(100),self.f.w.quote(),self.f.a)
    def test_empty_or_excess_inventory_cannot_serialize_sell(self):
        with self.assertRaises(PermissionError):self.w.close_owned(self.o,num(100),self.f.w.quote(),self.f.a)
        self.buy()
        with self.assertRaises(PermissionError):self.w.close_owned(self.o,num(101),self.f.w.quote(),self.f.a)
        self.assertEqual([],self.calls)
    def test_unconfirmed_parent_or_forged_fill_cannot_close(self):
        self.buy();self.o['statuses']['10']='Submitted'
        with self.assertRaisesRegex(PermissionError,'PARENT_REMAINDER_UNRESOLVED'):self.w.close_owned(self.o,num(100),self.f.w.quote(),self.f.a)
        self.o['statuses']['10']='Filled';self.o['fills']['buy']['client_id']=999
        with self.assertRaisesRegex(PermissionError,'UNRECOGNIZED_CLOSE_INVENTORY'):self.w.close_owned(self.o,num(100),self.f.w.quote(),self.f.a)
        self.assertEqual([],self.calls)
    def test_sdk_send_timeout_cannot_reuse_registered_bracket(self):
        with patch.object(self.w.client,'placeOrder',side_effect=TimeoutError):
            with self.assertRaises(TimeoutError):self.w.bracket(self.o,self.f.a)
        self.assertEqual({},self.w.approved)
        with self.assertRaisesRegex(PermissionError,'BRACKET_ALREADY_ATTEMPTED'):self.w.bracket(self.o,self.f.a)
    def test_expired_close_deadline_bounds_read_wait(self):
        from unittest.mock import Mock
        event=Mock();event.wait.return_value=False;self.w.operation_deadline_at=stamp(self.f.now-timedelta(seconds=1))
        with self.assertRaises(TimeoutError):self.w.wait(event)
        event.wait.assert_called_once_with(0)
    def test_sdk_cancel_timeout_cannot_retry_parent(self):
        self.o['cancel_parent_sent']=True;self.f.lab.persist('SYNTHETIC_CANCEL_PENDING')
        with patch.object(self.w.client,'cancelOrder',side_effect=TimeoutError),self.assertRaises(TimeoutError):self.w.cancel_parent(self.o)
        self.assertEqual(set(),self.w.cancel_approved)
        with self.assertRaisesRegex(PermissionError,'CANCEL_ALREADY_ATTEMPTED'):self.w.cancel_parent(self.o)
    def test_sdk_missing_intent_binding_disallows_order_mutation(self):
        self.w=execution_wire(self.f.auth,lambda management=False:None);self.w.expected=fixtures.IDENTITY;self.w.verified=True
        with patch.object(self.w.client,'isConnected',return_value=True),self.assertRaisesRegex(PermissionError,'UNBOUND_EXECUTION_INTENT'):
            self.w.bracket(self.o,self.f.a)

@unittest.skipUnless(os.environ.get('TRADING_TEST_DB'),'Disposable PostgreSQL required')
class DiagnosticPostgresTests(unittest.TestCase):
    def test_late_commission_and_exact_close_survive_real_journal_restart(self):
        now=datetime.now(timezone.utc);a=fixtures.grant();a.update(account='DUR'+str(uuid.uuid4().int),confirmed_at=stamp(now),expires_at=stamp(now+timedelta(minutes=30)))
        auth=Authorization(lambda:a,lambda *args:True,lambda:now);w=fixtures.Wire(lambda:now);w.accounts=[a['account']]
        with patch.dict(os.environ,{'TRADING_LAB_DB':os.environ['TRADING_TEST_DB']}):
            journal=DotnetJournal(Path(__file__).resolve().parents[2]);lab=PaperLab(auth,journal,w,clock=lambda:now)
            intent=hashlib.sha256(uuid.uuid4().bytes).hexdigest();o=lab.begin(intent,100,w.quote())
            def fill(i,side,id,price):return {'kind':'fill','exec_id':id,'order_id':o['order_ids'][i],'perm_id':i+1,'client_id':82,'contract_id':12087792,
                'side':side,'quantity':'100','price':price,'broker_time_raw':'SYNTHETIC','at':stamp(now)}
            lab.ingest([fill(0,'BUY','in','1.1001'),{'kind':'status','order_id':o['order_ids'][0],'status':'Filled'}]);w.eur_cash='100'
            lab.supervise();lab.ingest([fill(1,'SELL','out','1.1000')]);w.orders=[];w.eur_cash='0'
            restarted=PaperLab(auth,journal,w,clock=lambda:now);restarted.connect_and_reconcile()
            self.assertEqual('10',journal.load(lab.scope)['state']['sessions'][a['session_id']]['reserved'])
            restarted.ingest([{'kind':'commission','exec_id':id,'amount':'2','currency':'USD'} for id in ('in','out')]);restarted.supervise()
            saved=journal.load(lab.scope)['state'];self.assertEqual('CLOSED',saved['orders'][intent]['state'])
            e=saved['experiences'][intent]['execution_diagnostic'];self.assertEqual([],e['final_open_orders']);self.assertEqual('-4.0100',e['net_pnl_usd'])
            self.assertEqual('100',saved['strategy_capital']['equity']);self.assertEqual(1,sum(c[0]=='close_owned' for c in w.calls))
