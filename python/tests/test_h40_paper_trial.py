import copy
from contextlib import ExitStack
from datetime import timedelta
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from trading_agent import h40_paper_trial as t
from trading_agent import stock_paper_forward as s
from test_stock_paper_forward import BASE,plan,snap,order,fill,fee

TRIAL='h40-trial-'+'a'*32
ROOT=Path(__file__).resolve().parents[2]

def capabilities():
    return {k:dict(status='VERIFIED',compatible=True,observed_at=BASE.isoformat(),source='IBKR_PAPER_TEST') for k in s.CAPABILITIES}
def market():
    v=snap();v['completed_orders']=[];v.update(capabilities=capabilities(),binding_id='binding',
        active_session=dict(start=BASE.isoformat(),end=(BASE+timedelta(hours=6)).isoformat()),
        declared_protection=dict(order_types='LMT,STP,OCA'),quote=dict(bid='10',ask='10.01',market_data_type=1,
            received_at=BASE.isoformat(),field_received_at=dict(bid=BASE.isoformat(),ask=BASE.isoformat())))
    return v

class TrialTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name);self.j=s.Journal(self.path/'journal.sqlite3','binding')
        self.l=t.TrialLedger(self.j,TRIAL);self.c=t.config(ROOT)
    def tearDown(self):self.j.close();self.tmp.cleanup()
    def p(self):
        p=plan();p.update(quantity=1,risk='1.5',fees='1',trial_id=TRIAL);return p
    def test_original_config_unchanged(self):self.assertEqual(s.CANDIDATE['risk_percent'],2);self.assertEqual(self.c['maximum_forecast_loss_usd'],10)
    def test_only_trial_can_reserve_original_two_percent(self):
        p=self.p();self.l.reserve(p);self.assertEqual(s.number(self.l.state['reservation']),11)
        ordinary=s.Ledger(s.Journal(self.path/'ordinary.sqlite3','binding'))
        try:
            with self.assertRaisesRegex(PermissionError,'PROTECTED_RISK_LIMIT'):ordinary.reserve(p)
        finally:ordinary.journal.close()
    def test_consume_persisted_before_send(self):
        calls=[];self.l.consumer=lambda:calls.append(self.l.state['intent']);self.l.reserve(self.p())
        self.assertEqual(calls,[None]);self.assertTrue(self.l.state['opening_consumed'])
    def test_failed_consumer_sends_nothing(self):
        self.l.consumer=lambda:(_ for _ in ()).throw(PermissionError('ALREADY_CONSUMED'))
        with self.assertRaises(PermissionError):self.l.reserve(self.p())
        self.assertIsNone(self.l.state['intent'])
    def test_risk_ten_does_not_override_h40_two(self):
        p=self.p();p['risk']='10'
        with self.assertRaisesRegex(PermissionError,'TRIAL_RISK'):self.l.reserve(p)
    def test_reserves_total_fees_under_cash_ceiling(self):
        p=self.p();p['entry']='99.1'
        with self.assertRaisesRegex(PermissionError,'CASH_SCOPE'):self.l.reserve(p)
    def test_two_shares_denied(self):
        p=self.p();p['quantity']=2
        with self.assertRaises(PermissionError):self.l.reserve(p)
    def test_short_denied(self):
        p=self.p();p['side']='SELL'
        with self.assertRaises(PermissionError):self.l.reserve(p)
    def test_trial_mismatch_denied(self):
        p=self.p();p['trial_id']='other'
        with self.assertRaises(PermissionError):self.l.reserve(p)
    def test_no_second_attempt_after_unfilled_cancel(self):
        self.l.reserve(self.p());v=market();v['completed_orders']=[{**order(oid,'Cancelled'),'quantity':'1'} for oid in (10,11,12)]
        self.l.reconcile(v)
        with self.assertRaisesRegex(PermissionError,'ONE_TRIAL'):self.l.reserve(self.p())
    def test_restart_never_erases_opening_consumption(self):
        self.l.reserve(self.p());self.l.pre_send(10);self.j.close();self.j=s.Journal(self.path/'journal.sqlite3','binding');self.l=t.TrialLedger(self.j,TRIAL)
        with self.assertRaisesRegex(PermissionError,'NO_BLIND'):self.l.pre_send(10)
        self.assertTrue(self.l.state['opening_consumed']);self.assertGreater(s.number(self.l.state['reservation']),0)
    def test_reference_now_no_trade_including_unknown_cost_contingency(self):
        v=t.size('12.29','11.59','12.96','.04',self.c);self.assertEqual(v['quantity'],0)
    def test_size_keeps_original_stop_and_outer_ceiling(self):
        v=t.size('10','9.99','15','.01',self.c)
        self.assertEqual(v['quantity'],1);self.assertLessEqual(s.number(v['risk']),2);self.assertLessEqual(s.number(v['reserved_cash']),100)
    def test_unknown_permissions_not_contract_inferred(self):
        v=market();v['capabilities']['stock_permission']['status']='UNKNOWN'
        self.assertIn('STOCK_PERMISSION_UNKNOWN_OR_RESTRICTED',t.blockers(v,self.c,stamp=BASE,bootstrap=True))
    def test_delayed_always_blocks(self):
        v=market();v['quote']['market_data_type']=3
        self.assertIn('LIVE_BID_ASK_UNAVAILABLE_OR_STALE',t.blockers(v,self.c,stamp=BASE,bootstrap=True))
    def test_unknown_protection_requires_specific_consent(self):
        v=market();v['capabilities']['protection_acceptance']['status']='UNKNOWN'
        self.assertIn('SPECIFIC_SUPERVISED_PROTECTION_CONSENT_REQUIRED',t.blockers(v,self.c,stamp=BASE))
        self.assertNotIn('PROTECTION_ACCEPTANCE_UNKNOWN_OR_RESTRICTED',t.blockers(v,self.c,stamp=BASE,bootstrap=True))
    def test_rejected_protection_cannot_be_bootstrapped(self):
        v=market();v['capabilities']['protection_acceptance'].update(status='VERIFIED',compatible=False)
        self.assertIn('PROTECTION_PREVIOUSLY_REJECTED',t.blockers(v,self.c,stamp=BASE,bootstrap=True))
    def test_receipt_cannot_override_restricted_callback(self):
        v=market();v['capabilities']['stock_permission']['compatible']=False
        receipt=dict(capabilities={'stock_permission':dict(status='VERIFIED',compatible=True)})
        self.assertIn('STOCK_PERMISSION_UNKNOWN_OR_RESTRICTED',t.blockers(v,self.c,receipt,BASE,True))
    def test_stale_receipt_blocks(self):
        v=market();v['capabilities']['stock_permission']['observed_at']=(BASE-timedelta(days=2)).isoformat()
        self.assertIn('STOCK_PERMISSION_EVIDENCE_EXPIRED',t.blockers(v,self.c,stamp=BASE,bootstrap=True))
    def test_no_ack_not_verified(self):
        self.l.reserve(self.p());self.l.pre_send(10);i=self.l.state['intent'];i['first_send_at']=BASE.isoformat()
        self.assertEqual(t.protection_state(self.l,market(),self.c,BASE),'AWAITING_ACK_NO_ACCEPTANCE_CLAIM')
        self.assertIn('RECOVERY_REQUIRED',t.protection_state(self.l,market(),self.c,BASE+timedelta(seconds=5)))
    def test_position_without_protection_suspends(self):
        self.l.reserve(self.p());self.l.state['intent'].update(position='1',first_send_at=BASE.isoformat())
        self.assertIn('RECOVERY_REQUIRED',t.protection_state(self.l,market(),self.c,BASE))
    def test_own_ack_quantity_perm_id_required(self):
        self.l.reserve(self.p());self.l.state['intent'].update(position='1',first_send_at=BASE.isoformat());v=market()
        v['open_orders']=[{**order(11),'quantity':'1'},{**order(12),'quantity':'1'}]
        self.assertIn('ACKNOWLEDGED',t.protection_state(self.l,v,self.c,BASE))
        v['open_orders'][0]['quantity']='2';self.assertIn('RECOVERY_REQUIRED',t.protection_state(self.l,v,self.c,BASE))
    def test_observer_and_trial_folders_are_separate(self):self.assertNotIn('observer',str(t.folder(ROOT,TRIAL)))
    def test_no_path_traversal(self):
        with self.assertRaises(PermissionError):t.folder(ROOT,'../paper-auto')
    def test_dpapi_record_never_overwritten(self):
        p=self.path/'auth.dpapi';t.seal_new(p,{'x':1},lambda b:b)
        with self.assertRaises(FileExistsError):t.seal_new(p,{'x':2},lambda b:b)
        self.assertEqual(json.loads(p.read_text()),{'x':1})
    def test_failed_sealing_leaves_no_empty_grant(self):
        p=self.path/'auth.dpapi'
        with self.assertRaises(RuntimeError):t.seal_new(p,{},lambda b:(_ for _ in ()).throw(RuntimeError()))
        self.assertFalse(p.exists())
    def test_live_receipt_rejected(self):
        p=self.path/'receipts.json';p.write_text(json.dumps(dict(environment='LIVE_TRADING',binding_id='binding',scope=t.SCOPE)))
        with self.assertRaisesRegex(PermissionError,'PAPER_ONLY'):t.evidence(ROOT,p,'binding',lambda:BASE)
    def test_contract_permission_source_rejected(self):
        p=self.path/'receipts.json';p.write_text(json.dumps(dict(environment='PAPER_TRADING',binding_id='binding',scope=t.SCOPE,
            capabilities={'stock_permission':dict(status='VERIFIED',compatible=True,value=True,source='IBKR_CONTRACT_DETAILS',reference='test',observed_at=BASE.isoformat())})))
        with self.assertRaisesRegex(PermissionError,'INVALID'):t.evidence(ROOT,p,'binding',lambda:BASE)
    def test_cost_consent_preserves_unknown_status(self):
        v=market();v['capabilities']['effective_fees']['status']='UNKNOWN';receipt=dict(cost_scenario=dict(status='ESTIMATED',model='FIXED_FEE_STRESS',effective_fees='UNKNOWN',contingency_usd=1,operator_accepts_uncertainty=True,source='https://www.interactivebrokers.com/en/pricing/commissions-stocks.php'))
        self.assertNotIn('EFFECTIVE_FEES_UNKNOWN_OR_RESTRICTED',t.blockers(v,self.c,receipt,BASE,True))
        self.assertEqual(v['capabilities']['effective_fees']['status'],'UNKNOWN')
    def test_identity_rechecked_not_fallback(self):
        b=SimpleNamespace(select=lambda a:(_ for _ in ()).throw(PermissionError('IDENTITY_CHANGED')))
        with self.assertRaises(PermissionError):t.snapshot_owned(SimpleNamespace(accounts=['different']),self.l,b)
    def test_recovery_guard_cannot_admit(self):
        with patch.object(t,'config',return_value=self.c):g=t.RecoveryGuard(ROOT,TRIAL,self.l)
        with self.assertRaisesRegex(PermissionError,'CANNOT_OPEN'):g.admission({},{} )

    def guard(self,stack,recovery=False):
        from trading_agent.ibkr_session import AccountBinding
        binding=AccountBinding.from_attestation(dict(schema_version=1,account='DU123',paper_checked=True,identity_manual_match=True))
        grant=dict(scope=t.SCOPE,trial_id=TRIAL,account=binding.account,binding_id=binding.binding_id,
            environment='PAPER_TRADING',live_enabled=False,supervised_protection_bootstrap=True,
            protocol_sha256='hash',source_hashes={'source':'hash'},read_only_disabled_checked=True,
            tws_pid=1,tws_start_filetime='1',issued_at=BASE.isoformat(),expires_at=(BASE+timedelta(minutes=30)).isoformat(),revoked=False,paper_evidence={})
        stack.enter_context(patch.object(t,'config',return_value=self.c));stack.enter_context(patch.object(t,'protocol'))
        stack.enter_context(patch.object(t,'hashes',return_value={'source':'hash'}));stack.enter_context(patch.object(s,'sha',return_value='hash'))
        stack.enter_context(patch.object(t,'same_process',return_value=True))
        stack.enter_context(patch.object(t.SessionConfiguration,'load',return_value=SimpleNamespace(matches=lambda g:None)))
        if recovery:
            self.l.reserve(self.p());self.l.fill(fill(10,q=1));self.l.state['intent']['position']='1'
            grant.update(scope=t.RECOVERY_SCOPE,intent='H40-a',con_id=100,quantity='1',buy_exec_ids=['b'],buy_perm_ids=[110])
            stack.enter_context(patch.object(t,'unseal',side_effect=lambda p:binding._record if p.name=='ibkr-account-binding.dpapi' else grant))
            g=t.RecoveryGuard(self.path,TRIAL,self.l,clock=lambda:BASE)
        else:
            stack.enter_context(patch.object(t,'unseal',return_value=binding._record))
            g=t.TrialGuard(self.path,TRIAL,self.l,loader=lambda:grant,clock=lambda:BASE)
        return g,grant
    def test_new_grant_is_independent_of_forex_and_forward(self):
        with ExitStack() as st:
            g,r=self.guard(st);self.assertEqual(g.grant()['scope'],t.SCOPE)
            r['scope']='H40_STOCK_PAPER_FORWARD_ONLY'
            with self.assertRaisesRegex(PermissionError,'INDEPENDENT'):g.grant()
    def test_emergency_blocks_entry_with_valid_consent(self):
        with ExitStack() as st:
            g,r=self.guard(st);p=self.path/'.local';p.mkdir();(p/'paper-lab.emergency').write_text('active')
            with self.assertRaisesRegex(PermissionError,'EMERGENCY'):g.grant()
            self.assertIsNone(self.l.state['intent']);self.assertEqual(self.l.state['reservation'],'0')
            self.assertEqual(g.grant(True)['scope'],t.SCOPE)
    def test_expired_new_grant_blocks_entry(self):
        with ExitStack() as st:
            g,r=self.guard(st);r['expires_at']=BASE.isoformat()
            with self.assertRaisesRegex(PermissionError,'EXPIRED'):g.grant()
    def test_longer_than_thirty_minutes_denied(self):
        with ExitStack() as st:
            g,r=self.guard(st);r['expires_at']=(BASE+timedelta(minutes=31)).isoformat()
            with self.assertRaisesRegex(PermissionError,'EXPIRED'):g.grant()
    def test_changed_binding_denied_even_management(self):
        with ExitStack() as st:
            g,r=self.guard(st);r['binding_id']='other'
            with self.assertRaises(PermissionError):g.grant(True)
    def test_changed_deployment_denied(self):
        with ExitStack() as st:
            g,r=self.guard(st);r['source_hashes']={}
            with self.assertRaises(PermissionError):g.grant()
    def test_no_bootstrap_without_explicit_protected_consent(self):
        with ExitStack() as st:
            g,r=self.guard(st);r['supervised_protection_bootstrap']=False
            with self.assertRaises(PermissionError):g.grant()
    def test_changed_tws_hard_stops(self):
        with ExitStack() as st:
            g,r=self.guard(st)
            with patch.object(t,'same_process',return_value=False):
                with self.assertRaisesRegex(PermissionError,'SESSION_CHANGED'):g.grant(True)
    def test_recovery_grant_independent_and_cannot_open(self):
        with ExitStack() as st:
            g,r=self.guard(st,True);self.assertEqual(g.grant(True)['scope'],t.RECOVERY_SCOPE)
            with self.assertRaisesRegex(PermissionError,'CANNOT_OPEN'):g.grant(False)
    def test_recovery_bound_to_buy_exec_and_permid(self):
        with ExitStack() as st:
            g,r=self.guard(st,True);r['buy_perm_ids']=[999]
            with self.assertRaisesRegex(PermissionError,'QUANTITY_CHANGED'):g.grant(True)
    def test_recovery_cannot_exceed_bound_remaining_long(self):
        with ExitStack() as st:
            g,r=self.guard(st,True);self.l.state['intent']['position']='2'
            with self.assertRaisesRegex(PermissionError,'QUANTITY_CHANGED'):g.grant(True)
    def test_recovery_emergency_remains_and_expired_diagnostic_irrelevant(self):
        with ExitStack() as st:
            g,r=self.guard(st,True);p=self.path/'.local';p.mkdir();e=p/'paper-lab.emergency';e.write_text('active')
            self.assertEqual(g.grant(True)['scope'],t.RECOVERY_SCOPE);self.assertEqual(e.read_text(),'active')
    def test_invalid_recovery_scope_denies(self):
        with ExitStack() as st:
            g,r=self.guard(st,True);r['scope']=t.SCOPE
            with self.assertRaises(PermissionError):g.grant(True)
    def test_ack_deadline_no_retries(self):
        self.l.reserve(self.p());wire=SimpleNamespace(connected=True,callback_events=__import__('queue').Queue())
        with patch.object(t.time,'monotonic',side_effect=[0,6]):self.assertFalse(t.wait_bracket_ack(wire,self.l,self.c))
        self.assertEqual(self.l.state['suspended'],'BRACKET_ACK_DEADLINE_RECONCILE_RECOVERY_REQUIRED')
        self.assertEqual(self.l.state['intent']['attempted'],[])
    def test_three_acks_do_not_claim_position_protection(self):
        self.l.reserve(self.p());self.l.state['intent']['orders']={str(oid):{**order(oid),'quantity':'1'} for oid in (10,11,12)}
        wire=SimpleNamespace(connected=True,callback_events=__import__('queue').Queue())
        self.assertTrue(t.wait_bracket_ack(wire,self.l,self.c));self.assertEqual(self.l.state['intent']['position'],'0')
    def test_pending_bracket_cancel_parent_first_keep_children(self):
        self.l.reserve(self.p());v=market();v['open_orders']=[{**order(oid),'quantity':'1'} for oid in (10,11,12)]
        self.assertEqual(t.pending_cancel_ids(self.l,v),[10])
    def test_pending_cancel_not_repeated(self):
        self.l.reserve(self.p());v=market();v['open_orders']=[order(10,'PendingCancel')]
        self.assertEqual(t.pending_cancel_ids(self.l,v),[])
    def test_cancel_children_only_flat_terminal_parent(self):
        self.l.reserve(self.p());self.l.state['intent']['orders']['10']=order(10,'Cancelled')
        v=market();v['open_orders']=[order(11),order(12)]
        self.assertEqual(t.pending_cancel_ids(self.l,v),[11,12])
    def test_long_keeps_protection_until_recovery(self):
        self.l.reserve(self.p());self.l.state['intent']['position']='1'
        with self.assertRaisesRegex(PermissionError,'KEEP_PROTECTION'):t.pending_cancel_ids(self.l,market())
    def test_missing_parent_ack_never_cancels_children(self):
        self.l.reserve(self.p());v=market();v['open_orders']=[order(11),order(12)]
        with self.assertRaisesRegex(PermissionError,'TERMINAL_RECONCILIATION'):t.pending_cancel_ids(self.l,v)
    def settled(self,price,with_fees=True):
        self.l.reserve(self.p());v=market();v['completed_orders']=[{**order(oid,'Filled' if oid in (10,11) else 'Cancelled'),'quantity':'1'} for oid in (10,11,12)]
        v['executions']=[fill(10,q=1),fill(11,'s',q=1,price=price)];v['commissions']=[fee('b'),fee('s')] if with_fees else []
        self.l.reconcile(v)
    def test_net_loss_stops_santo_domingo_day_and_never_refills_budget(self):
        self.settled(9.8);self.assertEqual(self.l.state['stopped_days'][BASE.date().isoformat()],'DAILY_FIRST_LOSS_STOP')
        self.assertEqual(s.number(self.l.state['consumed_loss']),s.number('.3'))
        self.j.close();self.j=s.Journal(self.path/'journal.sqlite3','binding');self.l=t.TrialLedger(self.j,TRIAL)
        self.assertEqual(s.number(self.l.state['consumed_loss']),s.number('.3'))
    def test_zero_net_also_stops_day(self):
        self.settled(10.1);self.assertEqual(self.l.state['stopped_days'][BASE.date().isoformat()],'DAILY_BREAK_EVEN_STOP')
    def test_positive_net_cannot_grant_second_single_trial(self):
        self.settled(11);self.assertFalse(self.l.state['stopped_days'])
        with self.assertRaisesRegex(PermissionError,'ONE_TRIAL'):self.l.reserve(self.p())
    def test_pending_fees_hold_reservation_and_never_win(self):
        self.settled(11,False);self.assertEqual(self.l.state['intent']['state'],'FLAT_COMMISSION_PENDING')
        self.assertEqual(self.l.state['realized_equity'],'100');self.assertGreater(s.number(self.l.state['reservation']),0)
    def test_guard_binds_actual_contract_next_open_gtd_and_dedup_identity(self):
        p=self.p();v=market();v['contract']=dict(symbol='F',security_type='STK',currency='USD',con_id=100)
        key=s.digest([s.VERSION,p['signal']['signal_at'],TRIAL]);p.update(signal_key=key,intent='H40-'+key[:32])
        t.plan_geometry(p,v,TRIAL)
        for k,value in (('con_id',999),('side','SELL'),('entry_session',(BASE+timedelta(days=1)).isoformat()),('intent','H40-wrong'),('signal_key','different'),('strategy_version','new'),('trial_id','different')):
            bad={**p,k:value}
            with self.subTest(field=k),self.assertRaisesRegex(PermissionError,'BINDING_CHANGED'):t.plan_geometry(bad,v,TRIAL)
    def test_filled_ack_without_execution_never_releases_as_no_trade(self):
        self.l.reserve(self.p());v=market();v['completed_orders']=[{**order(10,'Filled'),'quantity':'1'}]
        with self.assertRaisesRegex(PermissionError,'WITHOUT_EXECUTION'):self.l.reconcile(v)
        self.assertGreater(s.number(self.l.state['reservation']),0);self.assertTrue(self.l.state['intent'])
    def test_position_reconciliation_does_not_claim_effective_protection(self):
        self.l.reserve(self.p());v=market();v.update(positions=[dict(con_id=100,symbol='F',security_type='STK',currency='USD',quantity='1')],
            executions=[fill(10,q=1)],completed_orders=[{**order(10,'Filled'),'quantity':'1'}])
        self.l.reconcile(v);self.assertEqual(self.l.state['intent']['state'],'OPEN_REQUIRES_PROTECTION_ACK_REVIEW')

if __name__=='__main__':unittest.main()
