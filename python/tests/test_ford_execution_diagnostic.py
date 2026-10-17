import copy
from contextlib import ExitStack
from datetime import timedelta
from decimal import Decimal
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from ibapi.order import Order
from trading_agent import ford_execution_diagnostic as d
from trading_agent.ford_whatif import whatif_wire,order_state
from trading_agent.broker import PaperOptions
from test_paper_account_capabilities import CapClient
from test_stock_paper_forward import BASE

ROOT=Path(__file__).resolve().parents[2];TRIAL='ford-diag-'+'e'*32;REF='FDIAG-'+'e'*32

def quote():return dict(bid='12.28',ask='12.29',received_at=BASE.isoformat(),market_data_type=1,field_received_at=dict(bid=BASE.isoformat(),ask=BASE.isoformat()))
def plan():
    p=d.scenario(quote(),d.EXPECTED,True)
    p.update(at=BASE.isoformat(),intent=REF,signal_key=TRIAL,trial_id=TRIAL,diagnostic_scope=d.SCOPE,
        classification='EXECUTION_DIAGNOSTICS',strategy_version=None,side='BUY',signal={'diagnostic':True},
        con_id=9599491,order_ids=[10,11,12],entry_session=BASE.isoformat(),cash='100',
        opening_deadline=(BASE+timedelta(seconds=30)).isoformat())
    return p
def order(oid,status='Submitted',filled='0'):
    p=plan()
    return dict(order_id=oid,order_ref=REF,perm_id=oid+100,status=status,quantity='1',filled=filled,
        side='BUY' if oid==10 else 'SELL',con_id=9599491,symbol='F',security_type='STK',currency='USD',
        parent_id=10 if oid in (11,12) else 0,oca_group=REF if oid in (11,12) else '',oca_type=2 if oid in (11,12) else 0,
        order_type='STP' if oid==12 else 'LMT',limit_price=p['entry'] if oid==10 else p['target'] if oid==11 else '12.30',stop_price=p['stop'] if oid==12 else '0')
def fill(oid,e,q='1',price='12.31'):
    return dict(order_id=oid,order_ref=REF,perm_id=oid+100,exec_id=e,con_id=9599491,side='BUY' if oid==10 else 'SELL',quantity=q,price=price,at=BASE.isoformat())
def fee(e):return dict(exec_id=e,currency='USD',commission='.16')
def snap(q='0',orders=None,execs=None,fees=None,completed=None):
    return dict(at=BASE.isoformat(),identity_verified=True,connected=True,complete=True,positions=[] if Decimal(q)==0 else [dict(con_id=9599491,symbol='F',security_type='STK',currency='USD',quantity=q)],
        open_orders=orders or [],completed_orders=completed or [],executions=execs or [],commissions=fees or [],quote=quote(),
        active_session=dict(start=BASE.isoformat(),end=(BASE+timedelta(hours=6)).isoformat()),
        contract=dict(con_id=9599491,symbol='F',security_type='STK',currency='USD'),
        declared_protection=dict(order_types='LMT,STP,OCA'),
        capabilities={k:dict(status='UNKNOWN',compatible=False) for k in d.stock.CAPABILITIES},
        next_session_start=(BASE+timedelta(days=1)).isoformat())

class PreviewClient(CapClient):
    def placeOrder(self,oid,c,o):
        self.wrapper.openOrder(oid,c,o,SimpleNamespace(status='PreSubmitted',initMarginBefore='0',initMarginChange='6.15',initMarginAfter='6.15',
            maintMarginBefore='0',maintMarginChange='3.69',maintMarginAfter='3.69',equityWithLoanBefore='1000000',equityWithLoanChange='-.15',equityWithLoanAfter='999999.85',
            commissionAndFees=.15,minCommissionAndFees=1.7976931348623157e308,maxCommissionAndFees=1.7976931348623157e308,commissionAndFeesCurrency='USD',marginCurrency='USD'))

class WhatIfTests(unittest.TestCase):
    def setUp(self):
        self.w=whatif_wire(PaperOptions('DU123',paper_mode_attested=True,timeout=.02),
            (PreviewClient,object,SimpleNamespace,Order,SimpleNamespace,SimpleNamespace));self.w.connect()
    def tearDown(self):self.w.disconnect()
    def preview(self,s=None):return self.w.preview(s or snap(),'12.29',lambda v:None)
    def test_credit_preview_has_margin_and_estimated_fee(self):
        v=self.preview();self.assertEqual(v['initMarginChange'],'6.15');self.assertEqual(v['commissionAndFees'],'0.15');self.assertIn('ESTIMATED',v['classification']);self.assertEqual(self.w.preview_calls,1)
    def test_sentinel_max_and_min_are_unknown(self):
        v=self.preview();self.assertIsNone(v['minCommissionAndFees']);self.assertIsNone(v['maxCommissionAndFees'])
    def test_legacy_field_names_supported(self):self.assertEqual(order_state(SimpleNamespace(commission=.35,commissionCurrency='USD'))['commissionAndFees'],'0.35')
    def test_missing_fee_not_zero(self):self.assertIsNone(order_state(SimpleNamespace())['commissionAndFees'])
    def test_zero_without_currency_and_warning_is_not_usable(self):
        v=order_state(SimpleNamespace(commissionAndFees=0,warningText='Preview incomplete'))
        self.assertEqual(v['commissionAndFees'],'0');self.assertFalse(v['commission_estimate_usable']);self.assertFalse(v['margin_estimates_usable'])
    def test_warning_account_is_redacted(self):
        v=order_state(SimpleNamespace(warningText='Account DU12345 and U777 cannot preview'),'DU12345')
        self.assertNotIn('DU12345',v['warning_sanitized']);self.assertNotIn('U777',v['warning_sanitized'])
    def test_nan_and_infinity_not_estimates(self):
        for x in ('NaN','Infinity','1e308'):self.assertIsNone(order_state(SimpleNamespace(commission=x))['commissionAndFees'])
    def test_normal_order_has_zero_sdk_calls(self):
        with self.assertRaises(PermissionError):self.w._client.placeOrder(1,SimpleNamespace(),Order())
        self.assertEqual(self.w.preview_calls,0)
    def test_raw_protobuf_denied(self):
        with self.assertRaises(PermissionError):self.w._client.placeOrderProtoBuf(SimpleNamespace())
    def test_cancel_denied(self):
        with self.assertRaises(PermissionError):self.w._client.cancelOrder(1,None)
    def test_bind_execution_denied(self):
        with self.assertRaises(PermissionError):self.w.bind_execution(None,None)
    def test_preview_cannot_repeat(self):
        self.preview()
        with self.assertRaises(PermissionError):self.preview()
        self.assertEqual(self.w.preview_calls,1)
    def test_no_fallback_on_timeout(self):
        with patch.object(PreviewClient,'placeOrder',lambda *a:None):
            with self.assertRaisesRegex(TimeoutError,'NO_RETRY'):self.preview()
        self.assertEqual(self.w.preview_calls,1)
    def test_no_fallback_on_ibkr_error(self):
        with patch.object(PreviewClient,'placeOrder',lambda client,oid,*a:self.w.error(oid,201,'private message')):
            with self.assertRaisesRegex(RuntimeError,'IBKR_WHAT_IF_201'):self.preview()
        self.assertEqual(self.w.preview_calls,1)
    def test_flat_required(self):
        with self.assertRaises(PermissionError):self.preview(snap(q='1'))
        self.assertEqual(self.w.preview_calls,0)
    def test_open_orders_block(self):
        with self.assertRaises(PermissionError):self.preview(snap(orders=[order(10)]))
    def test_incomplete_queries_block(self):
        s=snap();s['complete']=False
        with self.assertRaises(PermissionError):self.preview(s)
    def test_wrong_account_block(self):
        self.w.managedAccounts('U123')
        with self.assertRaises(PermissionError):self.preview()
    def test_capital_limit_even_for_preview(self):
        with self.assertRaises(PermissionError):self.w.preview(snap(),101,lambda v:None)
    def test_only_true_whatif_sent(self):
        sent=[]
        def inspect(client,oid,c,o):
            sent.append((o.whatIf,o.transmit,o.action,o.totalQuantity,c.symbol));PreviewClient.placeOrder_original(client,oid,c,o)
        with patch.object(PreviewClient,'placeOrder_original',PreviewClient.placeOrder,create=True),patch.object(PreviewClient,'placeOrder',inspect):self.preview()
        self.assertEqual(sent,[(True,True,'BUY',Decimal(1),'F')])

class DiagnosticLedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'journal.sqlite3'
        self.j=d.Journal(self.path,'binding',TRIAL);self.consumed=0
        def consume():self.consumed+=1
        self.l=d.Ledger(self.j,consume)
    def tearDown(self):self.j.close();self.tmp.cleanup()
    def reserve(self):self.l.reserve(plan())
    def test_no_h40_identity_in_journal(self):self.assertIsNone(self.l.state['strategy_version']);self.assertEqual(self.l.state['classification'],'EXECUTION_DIAGNOSTICS')
    def test_reserve_before_one_use_before_send(self):
        self.reserve();self.assertEqual(self.consumed,0);self.l.pre_send(10);self.assertEqual(self.consumed,1);self.l.pre_send(11);self.l.pre_send(12);self.assertEqual(self.consumed,1)
    def test_duplicate_send_refused(self):
        self.reserve();self.l.pre_send(10)
        with self.assertRaises(PermissionError):self.l.pre_send(10)
    def test_restart_cannot_clear_consumption(self):
        self.reserve();self.l.pre_send(10);again=d.Ledger(self.j)
        self.assertEqual(again.entry_block(BASE.isoformat()),'ONE_DIAGNOSTIC_ONLY')
    def test_wrong_diagnostic_scope_denied(self):
        p=plan();p['diagnostic_scope']='H40'
        with self.assertRaises(PermissionError):self.l.reserve(p)
    def test_h40_identity_denied(self):
        p=plan();p['strategy_version']=d.stock.VERSION
        with self.assertRaises(PermissionError):self.l.reserve(p)
    def test_risk_above_three_denied(self):
        p=plan();p['risk']='3.01'
        with self.assertRaises(PermissionError):self.l.reserve(p)
    def test_two_shares_denied(self):
        p=plan();p['quantity']=2
        with self.assertRaises(PermissionError):self.l.reserve(p)
    def test_cash_includes_fees(self):
        p=plan();p['entry']='99';p['target']='101'
        with self.assertRaises(PermissionError):self.l.reserve(p)
    def test_no_sell_opening(self):
        p=plan();p['side']='SELL'
        with self.assertRaises(PermissionError):self.l.reserve(p)
    def test_filled_ack_without_execution_keeps_reserve(self):
        self.reserve()
        with self.assertRaisesRegex(PermissionError,'FILL_DETAILS_PENDING'):self.l.reconcile(snap(completed=[order(10,'Filled','1')]))
        self.assertGreater(Decimal(self.l.state['reservation']),0)
    def test_fractional_partial_is_uncertain_never_winner(self):
        self.reserve()
        with self.assertRaisesRegex(PermissionError,'INVALID_STOCK_FILL'):self.l.fill(fill(10,'partial','.5'))
        self.assertGreater(Decimal(self.l.state['reservation']),0);self.assertFalse(self.l.state['completed'])
    def test_exact_owned_fill_and_protection(self):
        self.reserve();self.l.reconcile(snap('1',orders=[order(11),order(12)],execs=[fill(10,'buy')],completed=[order(10,'Filled','1')]))
        self.assertEqual(self.l.state['intent']['position'],'1')
    def test_foreign_position_refused(self):
        self.reserve();s=snap('1',execs=[fill(10,'buy')]);s['positions'][0]['con_id']=99
        with self.assertRaises(PermissionError):self.l.reconcile(s)
    def test_sell_cannot_exceed_bought(self):
        self.reserve();self.l.state['intent']['close_id']=13
        with self.assertRaisesRegex(PermissionError,'SHORT'):self.l.fill(fill(13,'sell'))
    def test_late_commission_holds_reserve_after_flat(self):
        self.reserve();self.l.state['intent'].update(close_id=13,close_limit_expected='12.30')
        s=snap(execs=[fill(10,'buy'),fill(13,'sell',price='12.30')],completed=[order(10,'Filled','1'),order(11,'Cancelled'),order(12,'Cancelled'),order(13,'Filled','1')],fees=[fee('buy')])
        self.l.reconcile(s);self.assertEqual(self.l.state['intent']['state'],'FLAT_COMMISSION_PENDING');self.assertGreater(Decimal(self.l.state['reservation']),0)
        s['commissions'].append(fee('sell'));self.l.reconcile(s);self.assertEqual(self.l.state['reservation'],'0');self.assertIsNone(self.l.state['intent'])
        kind,payload=self.j.db.execute('SELECT kind,payload FROM events ORDER BY revision DESC LIMIT 1').fetchone();report=json.loads(payload)['details']
        self.assertEqual(kind,'DIAGNOSTIC_CYCLE_SETTLED');self.assertIsNone(report['strategy_version']);self.assertFalse(report['strategy_success']);self.assertEqual(report['commission_evidence'],'OBSERVED_SIMULATED_PAPER_EXECUTION')
    def test_open_child_prevents_release(self):
        self.reserve();self.l.reconcile(snap(orders=[order(12)],completed=[order(10,'Cancelled')]))
        self.assertGreater(Decimal(self.l.state['reservation']),0)
    def test_disconnected_snapshot_refused(self):
        s=snap();s['connected']=False
        with self.assertRaises(PermissionError):self.l.reconcile(s)
    def test_tamper_journal_rejected(self):
        self.j.db.execute("UPDATE events SET hash='x'");self.j.db.commit()
        with self.assertRaises(PermissionError):self.j.load()
    def test_other_trial_cannot_adopt_journal(self):
        with self.assertRaises(PermissionError):d.Journal(self.path,'binding','ford-diag-'+'f'*32)
    def test_full_diag_bracket_reuses_guarded_adapter_without_h40(self):
        w=d.execution_wire(PaperOptions('DU123',paper_mode_attested=True,timeout=.02,read_only=False),
            (CapClient,object,SimpleNamespace,Order,SimpleNamespace,SimpleNamespace));w.connect();sent=[]
        guard=SimpleNamespace(admission=lambda *a:None,grant=lambda **kw:{})
        w.bind_execution(guard,self.l)
        try:
            with patch.object(CapClient,'placeOrder',lambda client,oid,c,o:sent.append((oid,o.action,o.parentId,o.transmit,o.orderRef,o.goodTillDate)),create=True):w.bracket(snap(),plan())
            self.assertEqual([x[:4] for x in sent],[(10,'BUY',0,False),(11,'SELL',10,False),(12,'SELL',10,True)])
            self.assertTrue(all(x[4]==REF for x in sent));self.assertEqual(sent[0][5],'20270104-14:30:30');self.assertEqual(self.consumed,1)
        finally:w.disconnect()
    def test_preflight_failure_has_zero_reserve_and_zero_sdk(self):
        w=d.execution_wire(PaperOptions('DU123',paper_mode_attested=True,timeout=.02,read_only=False),
            (CapClient,object,SimpleNamespace,Order,SimpleNamespace,SimpleNamespace));w.connect()
        def deny(*a):raise PermissionError('PRE_FLIGHT_FAILED')
        w.bind_execution(SimpleNamespace(admission=deny),self.l)
        try:
            with patch.object(CapClient,'placeOrder',create=True) as sdk:
                with self.assertRaises(PermissionError):w.bracket(snap(),plan())
                sdk.assert_not_called()
            self.assertIsNone(self.l.state['intent']);self.assertEqual(self.consumed,0)
        finally:w.disconnect()
    def test_full_fill_close_cancels_before_independent_sell(self):
        self.reserve();self.l.reconcile(snap('1',orders=[order(11),order(12)],execs=[fill(10,'buy')],completed=[order(10,'Filled','1')]))
        calls=[];w=SimpleNamespace(cancel_owned=lambda oid:calls.append(('cancel',oid)),close_owned=lambda *a:calls.append(('sell',a[1])))
        s=snap('1',orders=[order(11),order(12)])
        s['quote']['field_received_at']={k:(BASE+timedelta(seconds=30)).isoformat() for k in ('bid','ask')}
        self.assertEqual(d.manage(w,self.l,s,d.EXPECTED,lambda:BASE+timedelta(seconds=30)),'CANCEL_PENDING_RECONCILE_BEFORE_CLOSE')
        self.assertEqual(calls,[('cancel',11),('cancel',12)])
        next_snapshot=snap('1');next_snapshot['quote']=s['quote']
        d.manage(w,self.l,next_snapshot,d.EXPECTED,lambda:BASE+timedelta(seconds=32));self.assertEqual(calls[-1][0],'sell')
    def test_missing_protection_suspends_without_sell(self):
        self.reserve();self.l.reconcile(snap('1',execs=[fill(10,'buy')],completed=[order(10,'Filled','1')]))
        w=SimpleNamespace(close_owned=lambda *a:self.fail('blind unprotected sell'),cancel_owned=lambda *a:self.fail('cancel'))
        self.assertEqual(d.manage(w,self.l,snap('1'),d.EXPECTED,lambda:BASE+timedelta(seconds=30)),'SUSPENDED');self.assertTrue(self.l.state['suspended'])
    def test_pending_buy_cancellation_is_parent_only(self):
        self.reserve();self.l.reconcile(snap(orders=[order(10),order(11),order(12)]));calls=[]
        w=SimpleNamespace(cancel_owned=calls.append,close_owned=lambda *a:self.fail('sell'))
        d.manage(w,self.l,snap(orders=[order(10),order(11),order(12)]),d.EXPECTED,lambda:BASE+timedelta(seconds=31));self.assertEqual(calls,[10])
    def test_late_close_deadline_is_persistent_suspension(self):
        self.reserve();s=snap('1',orders=[order(11),order(12)],execs=[fill(10,'buy')],completed=[order(10,'Filled','1')]);self.l.reconcile(s)
        w=SimpleNamespace(cancel_owned=lambda *a:self.fail('cancel after uncertain deadline'),close_owned=lambda *a:self.fail('sell'))
        d.manage(w,self.l,s,d.EXPECTED,lambda:BASE+timedelta(seconds=61));self.assertEqual(self.l.state['suspended'],'DIAGNOSTIC_CLOSE_DEADLINE_MISSED')
    def test_stop_type_changed_never_counts_as_protection(self):
        self.reserve();o=order(12);o['order_type']='MKT'
        with self.assertRaisesRegex(PermissionError,'PROTECTION_TYPE'):self.l.order(o)
    def test_stop_price_changed_never_counts_as_protection(self):
        self.reserve();o=order(12);o['stop_price']='1'
        with self.assertRaisesRegex(PermissionError,'PROTECTION_TYPE'):self.l.order(o)
    def test_missing_ack_price_is_unknown_and_blocked(self):
        self.reserve();o=order(11);del o['limit_price']
        with self.assertRaises(PermissionError):self.l.order(o)
    def test_changed_target_never_counts_as_accepted(self):
        self.reserve();o=order(11);o['limit_price']='100'
        with self.assertRaises(PermissionError):self.l.order(o)
    def test_exit_does_not_remove_protection_with_delayed_quote(self):
        self.reserve();s=snap('1',orders=[order(11),order(12)],execs=[fill(10,'buy')],completed=[order(10,'Filled','1')]);self.l.reconcile(s);s['quote']['market_data_type']=3
        w=SimpleNamespace(cancel_owned=lambda *a:self.fail('remove protection'),close_owned=lambda *a:self.fail('sell'))
        d.manage(w,self.l,s,d.EXPECTED,lambda:BASE+timedelta(seconds=30));self.assertEqual(self.l.state['suspended'],'DIAGNOSTIC_EXIT_MARKET_UNUSABLE_KEEP_PROTECTION')
    def test_exit_does_not_remove_protection_outside_rth(self):
        self.reserve();s=snap('1',orders=[order(11),order(12)],execs=[fill(10,'buy')],completed=[order(10,'Filled','1')]);self.l.reconcile(s);s['active_session']=None
        w=SimpleNamespace(cancel_owned=lambda *a:self.fail('remove protection'),close_owned=lambda *a:self.fail('sell'))
        d.manage(w,self.l,s,d.EXPECTED,lambda:BASE+timedelta(seconds=30));self.assertTrue(self.l.state['suspended'])

class DiagnosticGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.dir=self.root/d.FOLDER/TRIAL;self.dir.mkdir(parents=True)
        (self.dir/'protocol.json').write_text('{}');(self.root/'.local').mkdir()
        self.g=dict(scope=d.SCOPE,trial_id=TRIAL,account='DU123',binding_id='binding',environment='PAPER_TRADING',live_enabled=False,
            source_hashes={},protocol_sha256=d.stock.sha(self.dir/'protocol.json'),read_only_disabled_checked=True,
            tws_pid=1,tws_start_filetime='1',issued_at=(BASE-timedelta(minutes=1)).isoformat(),expires_at=(BASE+timedelta(minutes=29)).isoformat(),
            revoked=False,supervised_protection_bootstrap=True,tail_risk_acknowledged=True)
        self.stack=ExitStack();self.stack.enter_context(patch.object(d,'protocol',return_value={}));self.stack.enter_context(patch.object(d,'binding',return_value=SimpleNamespace(account='DU123',binding_id='binding')))
        self.stack.enter_context(patch.object(d,'sources',return_value={}));self.stack.enter_context(patch.object(d.SessionConfiguration,'load',return_value=SimpleNamespace(matches=lambda g:None)))
        self.stack.enter_context(patch.object(d,'same_process',return_value=True))
        self.guard=d.Guard(self.root,TRIAL,None,clock=lambda:BASE,loader=lambda:self.g)
    def tearDown(self):self.stack.close();self.tmp.cleanup()
    def test_independent_one_use_grant_shape(self):self.assertEqual(self.guard.grant()['scope'],d.SCOPE)
    def test_emergency_prevents_entry(self):
        (self.root/'.local/paper-lab.emergency').write_text('active')
        with self.assertRaisesRegex(PermissionError,'EMERGENCY'):self.guard.grant()
    def test_expired_cannot_open(self):
        self.g['expires_at']=BASE.isoformat()
        with self.assertRaisesRegex(PermissionError,'EXPIRED'):self.guard.grant()
    def test_old_h40_consent_denied(self):
        self.g['scope']='H40_R3_SUPERVISED_SINGLE_PAPER_TRIAL'
        with self.assertRaisesRegex(PermissionError,'SCOPE'):self.guard.grant()
    def test_identity_change_denied(self):
        self.g['binding_id']='other'
        with self.assertRaises(PermissionError):self.guard.grant()
    def test_tws_restart_denied(self):
        with patch.object(d,'same_process',return_value=False):
            with self.assertRaises(PermissionError):self.guard.grant()
    def test_revoke_marker_prevents_opening(self):
        (self.dir/'revoked.json').write_text('{}')
        with self.assertRaisesRegex(PermissionError,'REVOKED'):self.guard.grant()
    def test_global_consumption_prevents_fresh_run(self):
        (self.root/'.local/ford-diagnostic-consumed.dpapi').write_bytes(b'test')
        with self.assertRaisesRegex(PermissionError,'GLOBAL'):self.guard.grant()
    def test_consumption_does_not_block_remaining_bracket_legs(self):
        (self.root/'.local/ford-diagnostic-consumed.dpapi').write_bytes(b'test')
        self.guard.ledger=SimpleNamespace(state=dict(opening_consumed=True,intent={'intent':REF},suspended=None))
        self.assertEqual(self.guard.grant()['scope'],d.SCOPE)
    def test_suspension_requires_independent_recovery(self):
        self.guard.ledger=SimpleNamespace(state=dict(suspended='uncertain'))
        with self.assertRaisesRegex(PermissionError,'RECOVERY'):self.guard.grant(management=True)
    def test_suspended_parent_cancel_can_reduce_pending_risk(self):
        self.guard.ledger=SimpleNamespace(state=dict(suspended='uncertain'));self.guard.cancel_only=True
        self.assertEqual(self.guard.grant(management=True)['scope'],d.SCOPE)
        with self.assertRaisesRegex(PermissionError,'CANNOT_OPEN'):self.guard.admission(None,None)
    def test_management_can_only_reduce_after_emergency(self):
        (self.root/'.local/paper-lab.emergency').write_text('active');self.guard.ledger=SimpleNamespace(state=dict(suspended=None))
        self.assertEqual(self.guard.grant(management=True)['scope'],d.SCOPE)
    def test_recovery_grant_cannot_open(self):
        self.guard.recovery=True;self.g['scope']=d.RECOVERY_SCOPE
        with self.assertRaisesRegex(PermissionError,'RECOVERY_CANNOT_OPEN'):self.guard.grant()

class DiagnosticReadinessTests(unittest.TestCase):
    def test_near_close_entry_is_blocked(self):
        s=snap();s['active_session']['end']=(BASE+timedelta(seconds=179)).isoformat()
        self.assertIn('DIAGNOSTIC_TOO_NEAR_RTH_CLOSE',d.blockers(s,d.EXPECTED,bootstrap=True,clock=lambda:BASE))
    def test_session_end_unknown_blocks_entry(self):
        s=snap();del s['active_session']['end']
        self.assertIn('DIAGNOSTIC_SESSION_END_UNKNOWN',d.blockers(s,d.EXPECTED,bootstrap=True,clock=lambda:BASE))
    def test_physical_writer_uses_existing_exclusive_ford_slot(self):
        e=SimpleNamespace(host='127.0.0.1',port=7497);b=SimpleNamespace(account='DU123')
        with patch.object(d.SessionConfiguration,'load',return_value=e),patch.object(d,'execution_wire') as writer,patch.object(d,'whatif_wire') as preview:
            d.wire_for(ROOT,b,mutable=True);self.assertEqual(writer.call_args.args[0].client_id,93)
            d.wire_for(ROOT,b,preview=True);self.assertEqual(preview.call_args.args[0].client_id,94)
    def test_no_cap_costs_exceed_budget(self):
        p=d.scenario(quote(),d.EXPECTED);self.assertFalse(p['fits_budget']);self.assertGreater(Decimal(p['fees']),3)
    def test_cap_model_not_execution_verification(self):
        p=d.scenario(quote(),d.EXPECTED,True);self.assertTrue(p['fits_budget']);self.assertIn('ESTIMATED',p['status']);self.assertFalse(p['strategy_success'])
    def test_total_loss_not_bounded_by_stop(self):
        p=d.scenario(quote(),d.EXPECTED);self.assertGreater(Decimal(p['adverse_scenarios']['total_inventory_loss']),3)
    def test_permission_settled_cash_unknown_block(self):
        b=d.blockers(snap(),d.EXPECTED,bootstrap=True,clock=lambda:BASE)
        for key in ('STOCK_PERMISSION','SETTLED_CASH','EFFECTIVE_FEES'):self.assertTrue(any(key in x for x in b))
    def test_no_h40_signal_or_risk_block_in_diagnostic(self):self.assertFalse(any('H40' in x for x in d.blockers(snap(),d.EXPECTED,bootstrap=True,clock=lambda:BASE)))
    def test_delayed_block(self):
        s=snap();s['quote']['market_data_type']=3;self.assertIn('LIVE_BID_ASK_UNAVAILABLE_OR_STALE',d.blockers(s,d.EXPECTED,bootstrap=True,clock=lambda:BASE))
    def test_bootstrap_cannot_hide_prior_protection_rejection(self):
        s=snap();s['capabilities']['protection_acceptance']=dict(status='VERIFIED',compatible=False)
        self.assertIn('PROTECTION_PREVIOUSLY_RESTRICTED',d.blockers(s,d.EXPECTED,bootstrap=True,clock=lambda:BASE))
    def test_bootstrap_requires_declared_oca(self):
        s=snap();s['declared_protection']['order_types']='LMT,STP'
        self.assertIn('DECLARED_PROTECTIVE_TYPES_UNAVAILABLE',d.blockers(s,d.EXPECTED,bootstrap=True,clock=lambda:BASE))
    def test_h40_receipt_cannot_authorize_diagnostic(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'r.json';p.write_text(json.dumps(dict(environment='PAPER_TRADING',binding_id='b',scope='H40_R3_SUPERVISED_SINGLE_PAPER_TRIAL')))
            with self.assertRaises(PermissionError):d.receipts(ROOT,p,'b')
    def test_whatif_is_not_cap_confirmation(self):self.assertFalse(d.cap_confirmed({'what_if':{'commissionAndFees':'.15'}}))
    def test_risk_request_uses_diagnostic_scope_without_h40_target(self):
        r=d.request(plan(),snap());self.assertIsNone(r['execution']['takeProfit']);self.assertEqual(r['execution']['source'],d.SCOPE);self.assertEqual(r['proposedRisk'],Decimal('.03'))
    def test_preregistered_limits_cannot_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'config';p.mkdir();c=copy.deepcopy(d.EXPECTED);c['risk_budget_usd']=10;(p/'ford-execution-diagnostic.json').write_text(json.dumps(c))
            with self.assertRaises(PermissionError):d.configuration(Path(tmp))
    def test_source_consent_is_no_replace(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'p.json';d.save_new(p,{'x':1})
            with self.assertRaises(FileExistsError):d.save_new(p,{'x':2})
            self.assertEqual(json.loads(p.read_text()),{'x':1})
    def test_foreign_inventory_blocks_even_with_contract(self):
        self.assertIn('EXISTING_POSITION_OR_ORDER_REQUIRES_REVIEW',d.blockers(snap('1'),d.EXPECTED,bootstrap=True,clock=lambda:BASE))

if __name__=='__main__':unittest.main()
