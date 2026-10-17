"""No broker orders: session fakes, official SDK serialization and persisted fakes."""
import copy
import json
from pathlib import Path
import unittest
import uuid
from unittest.mock import patch

from trading_agent.ibkr_session import (AccountBinding,ExecutionMode,IbkrSessionGuard,
    SessionConfiguration,SessionReconnect,StructuredSessionEvents)
from trading_agent.paper_lab import Authorization,PaperLab
from trading_agent.paper_identity import discover
from trading_agent.paper_lab_runner import paper_auto_ready
from trading_agent.paper_lab_diagnostics import pending_journal_orders
import test_paper_lab as fixture
import test_paper_execution_wire as sdk_fixture
import test_strategy_continuous as continuous_fixture


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.a=fixture.grant();self.binding=AccountBinding.from_attestation(self.a)
        self.root=Path(__file__).resolve().parents[2]/'.local/session-tests'/uuid.uuid4().hex
        self.root.mkdir(parents=True);(self.root/'.local').mkdir()
    def tearDown(self):
        # Every target belongs to this unique fixture; no recursive shell delete.
        for p in sorted(self.root.rglob('*'),reverse=True):
            p.rmdir() if p.is_dir() else p.unlink()
        self.root.rmdir()
    def anchor(self,a=None,name='paper-lab-authorization.dpapi'):
        (self.root/'.local'/name).write_text(json.dumps(a or self.a))
    def load(self):
        return AccountBinding.load_or_migrate(self.root,loader=lambda p:json.loads(p.read_bytes()),
                                             sealer=lambda data:data)
    def test_correct_account_selected_by_full_identity(self):
        self.assertEqual(self.a['account'],self.binding.select([self.a['account']]))
    def test_same_suffix_different_account_hard_stops(self):
        with self.assertRaisesRegex(PermissionError,'UNAVAILABLE'):
            self.binding.select(['DU00005678'])
    def test_no_accounts_hard_stops(self):
        with self.assertRaisesRegex(PermissionError,'NO_MANAGED_ACCOUNTS'):self.binding.select([])
    def test_multiple_and_duplicate_accounts_hard_stop(self):
        for accounts in ([self.a['account'],'DU99999999'],[self.a['account']]*2):
            with self.assertRaisesRegex(PermissionError,'AMBIGUOUS'):self.binding.select(accounts)
    def test_live_identity_never_selected(self):
        with self.assertRaises(PermissionError):self.binding.select(['U12345678'])
        a={**self.a,'environment':'LIVE_TRADING'}
        with self.assertRaises(PermissionError):AccountBinding.from_attestation(a)
    def test_persistent_binding_survives_restart_without_renewing_expired_grant(self):
        self.anchor();before=(self.root/'.local/paper-lab-authorization.dpapi').read_bytes()
        first=self.load();second=self.load()
        self.assertEqual(first.binding_id,second.binding_id)
        self.assertEqual(before,(self.root/'.local/paper-lab-authorization.dpapi').read_bytes())
        with self.assertRaises(PermissionError):
            Authorization(lambda:self.a,lambda *a:True).read()
    def test_missing_attestation_does_not_adopt_candidate(self):
        self.anchor({**self.a,'paper_checked':False},'ibkr-paper-candidate.dpapi')
        with self.assertRaisesRegex(PermissionError,'MISSING_PROTECTED_IDENTITY'):self.load()
    def test_ambiguous_protected_anchors_rejected(self):
        self.anchor();self.anchor({**self.a,'account':'DU99999999'},'ibkr-paper-authorized.dpapi')
        with self.assertRaisesRegex(PermissionError,'AMBIGUOUS_ATTESTATIONS'):self.load()
    def test_existing_binding_never_replaced_on_identity_change(self):
        self.anchor();self.load();path=self.root/'.local/ibkr-account-binding.dpapi';before=path.read_bytes()
        self.anchor({**self.a,'account':'DU99999999'})
        with self.assertRaisesRegex(PermissionError,'ATTESTATION_CHANGED'):self.load()
        self.assertEqual(before,path.read_bytes())
    def test_binding_tampering_and_revocation_rejected(self):
        for changes in ({'account':'DU99999999'},{'revoked':True},{'live_enabled':True},{'environment':'LIVE_TRADING'}):
            with self.assertRaises(PermissionError):AccountBinding({**self.binding._record,**changes})
    def test_sealing_failure_leaves_no_identity_file(self):
        self.anchor()
        def fail(data):raise OSError('sealed failure')
        with self.assertRaises(OSError):
            AccountBinding.load_or_migrate(self.root,loader=lambda p:json.loads(p.read_bytes()),sealer=fail)
        self.assertFalse((self.root/'.local/ibkr-account-binding.dpapi').exists())
    def test_migration_lock_cannot_be_removed_by_another_migrator(self):
        self.anchor();lock=self.root/'.local/ibkr-account-binding.migration.lock';lock.write_bytes(b'')
        with self.assertRaisesRegex(PermissionError,'MIGRATION_IN_PROGRESS'):self.load()
        self.assertTrue(lock.exists())
    def test_discovery_checks_binding_before_writing_candidate(self):
        class Wire:
            server_version=226
            def connect(self):return ['DU00005678']
            def disconnect(self):pass
        target=self.root/'.local/candidate.dpapi'
        with self.assertRaises(PermissionError):discover(target,lambda *a,**k:Wire(),lambda b:b,binding=self.binding)
        self.assertFalse(target.exists())
    def test_durable_structured_events_mask_account(self):
        target=self.root/'events.jsonl';guard=IbkrSessionGuard(self.binding,mode='PaperAuto',emit=StructuredSessionEvents(target))
        guard.verify_connected(self.a,[self.a['account']]);guard.disconnected()
        text=target.read_text();self.assertNotIn(self.a['account'],text)
        self.assertEqual(['IBKR_CONNECTED','PAPER_ACCOUNT_VERIFIED','IBKR_DISCONNECTED'],
                         [json.loads(line)['event'] for line in text.splitlines()])


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.a=fixture.grant();self.events=[]
        self.guard=IbkrSessionGuard(AccountBinding.from_attestation(self.a),mode='PaperAuto',emit=self.events.append)
        self.guard.verify_connected(self.a,[self.a['account']])
    def test_paper_auto_permitted_after_exact_verification(self):
        self.guard.authorize_mutation(self.a,connected=True)
        self.assertEqual('PaperAuto',self.guard.mode.value)
    def test_research_and_live_approval_cannot_transmit(self):
        for mode in ('Research','LiveApproval'):
            self.guard.mode=ExecutionMode(mode)
            with self.assertRaises(PermissionError):self.guard.authorize_mutation(self.a,connected=True)
    def test_live_auto_is_not_a_mode(self):
        with self.assertRaises(ValueError):ExecutionMode('LiveAuto')
    def test_changed_endpoint_or_live_grant_rejected(self):
        for changes in ({'host':'::1'},{'port':7496},{'account':'U12345678'},{'live_enabled':True},{'environment':'LIVE_TRADING'}):
            with self.assertRaises(PermissionError):self.guard.authorize_mutation({**self.a,**changes},connected=True)
    def test_disconnect_requires_fresh_identity_before_resume(self):
        self.guard.disconnected()
        with self.assertRaises(ConnectionError):self.guard.authorize_mutation(self.a,connected=True)
        self.guard.verify_connected(self.a,[self.a['account']]);self.guard.authorize_mutation(self.a,connected=True)
    def test_read_only_error_stays_blocked_after_reconnect(self):
        self.guard.detected_read_only();self.guard.disconnected();self.guard.verify_connected(self.a,[self.a['account']])
        with self.assertRaisesRegex(PermissionError,'PAPER_AUTO_BLOCKED: TWS API is read-only.'):
            self.guard.authorize_mutation(self.a,connected=True)
        self.assertNotIn(self.a['account'],str(self.events))
    def test_unknown_api_permission_blocks(self):
        with self.assertRaisesRegex(PermissionError,'read-only'):
            self.guard.authorize_mutation({**self.a,'read_only_disabled_checked':False},connected=True)
    def test_configurable_endpoint_requires_matching_protected_grant(self):
        endpoint=SessionConfiguration('::1',4002)
        guard=IbkrSessionGuard(self.guard.binding,endpoint,'PaperAuto')
        with self.assertRaises(PermissionError):guard.verify_connected(self.a,[self.a['account']])
        a={**self.a,'host':'::1','port':4002};guard.verify_connected(a,[a['account']])
        Authorization(lambda:a,lambda *a:True,lambda:fixture.NOW,endpoint=endpoint).read()
        guard.authorize_mutation(a,connected=True)
    def test_remote_or_invalid_endpoint_rejected(self):
        for host,port in [('192.0.2.1',7497),('127.0.0.1',0),('127.0.0.1',True),('127.0.0.1',65536)]:
            with self.assertRaises(PermissionError):SessionConfiguration(host,port)
    def test_binding_reload_detects_revocation_or_account_change(self):
        self.guard.binding_loader=lambda:AccountBinding.from_attestation({**self.a,'account':'DU99999999'})
        with self.assertRaisesRegex(PermissionError,'ACCOUNT_BINDING_CHANGED'):
            self.guard.authorize_mutation(self.a,connected=True)
    def test_inspection_does_not_become_order_authorization(self):
        with self.assertRaisesRegex(PermissionError,'INSPECTION_ONLY'):
            self.guard.authorize_mutation({**self.a,'inspection_only':True},connected=True)


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.a=fixture.grant();self.auth=Authorization(lambda:self.a,lambda *a:True,lambda:fixture.NOW)
        self.j=fixture.Journal();self.w=fixture.Wire(lambda:fixture.NOW)
        self.w.disconnect=lambda:setattr(self.w,'connected',False)
        self.lab=PaperLab(self.auth,self.j,self.w,lambda:fixture.NOW)
        self.lab.connect_and_reconcile()
    def test_research_rejected_before_intent_reserve_or_transport(self):
        def block(a):raise PermissionError('RESEARCH_NO_ORDERS')
        self.w.assert_mutation_allowed=block
        with self.assertRaisesRegex(PermissionError,'RESEARCH_NO_ORDERS'):
            self.lab.begin(fixture.INTENT,100,self.w.quote())
        self.assertEqual({},self.lab.state['orders']);self.assertEqual({},self.lab.state['sessions']);self.assertEqual([],self.w.calls)
    def test_persisted_duplicate_after_restart_is_not_retransmitted(self):
        self.lab.begin(fixture.INTENT,100,self.w.quote());before=len(self.w.calls)
        restarted=PaperLab(self.auth,self.j,self.w,lambda:fixture.NOW)
        restarted.begin(fixture.INTENT,100,self.w.quote())
        self.assertEqual(before,len(self.w.calls));self.assertEqual('UNKNOWN',restarted.state['orders'][fixture.INTENT]['state'])
    def test_bounded_reconnection_reconciles_without_transmitting(self):
        original=self.w.connect;calls=[]
        def connect(a):
            calls.append(1)
            if len(calls)<3:raise ConnectionError('lost')
            return original(a)
        self.w.connect=connect
        SessionReconnect(self.lab,sleep=lambda _:None).reconcile()
        self.assertEqual(3,len(calls));self.assertTrue(self.lab.reconciled);self.assertEqual([],self.w.calls)
    def test_reconnection_never_clears_emergency(self):
        self.lab.stop('BROKER_DISCONNECTED')
        SessionReconnect(self.lab,sleep=lambda _:None).reconcile()
        self.assertTrue(self.lab.state['emergency'])
        with self.assertRaisesRegex(PermissionError,'EMERGENCY_STOP'):self.lab.check()
    def test_identity_failure_has_no_reconnect_retry(self):
        self.w.accounts=['U12345678'];calls=[]
        old=self.w.connect
        self.w.connect=lambda a:(calls.append(1),old(a))[1]
        with self.assertRaises(PermissionError):SessionReconnect(self.lab,sleep=lambda _:None).reconcile()
        self.assertEqual(1,len(calls));self.assertFalse(self.lab.reconciled);self.assertEqual([],self.w.calls)
    def test_exhausted_reconnect_latches_emergency(self):
        self.w.connect=lambda a:(_ for _ in ()).throw(TimeoutError('timeout'))
        with self.assertRaises(TimeoutError):SessionReconnect(self.lab,sleep=lambda _:None).reconcile()
        self.assertTrue(self.lab.state['emergency']);self.assertFalse(self.lab.reconciled)
    def strategy(self):
        self.a.update(mode='StrategyPaper',strategy_versions=['v1'],strategy_requirements_verified=True,
            execution_requirements={'execution':{},'availableMargin':'100'})
        self.lab=PaperLab(self.auth,self.j,self.w,lambda:fixture.NOW)
        self.lab.connect_and_reconcile()
    def test_risk_rejection_occurs_before_sdk_or_intent(self):
        self.strategy()
        proposal={'strategy_version':'v1','signal_at':fixture.stamp(fixture.NOW),'stop':'1.099',
                  'target':'1.1016','market_context':{}}
        result=self.lab.strategy_proposal(proposal,self.w.quote())
        self.assertEqual('STRATEGY_REJECTED',result['state']);self.assertEqual([],self.w.calls)
        self.assertEqual('ORDER_BLOCKED_BY_RISK',self.j.events[-1]['structured_event'])
    def test_twenty_dollars_consumed_prevents_ready_and_preserves_budget(self):
        self.strategy();self.lab.state['strategy_account']['capital'].update(consumedLoss=20,remainingLoss=0)
        before=copy.deepcopy(self.lab.state['strategy_account'])
        with self.assertRaisesRegex(PermissionError,'CUMULATIVE_LOSS_LIMIT'):paper_auto_ready(self.lab)
        self.assertEqual(before,self.lab.state['strategy_account']);self.assertEqual([],self.w.calls)
    def test_ready_requires_strategy_evidence_and_all_existing_gates(self):
        self.strategy();self.lab.state['strategy_account']['capital']['remainingLoss']=20
        paper_auto_ready(self.lab)
        self.assertEqual('PAPER_AUTO_READY',self.j.events[-1]['event'])
        self.lab.stop('BROKER_DISCONNECTED')
        with self.assertRaises(PermissionError):paper_auto_ready(self.lab)


class SessionSdkTests(unittest.TestCase):
    def setUp(self):sdk_fixture.ExecutionWireTests.setUp(self)
    def tearDown(self):sdk_fixture.ExecutionWireTests.tearDown(self)
    def guard(self,mode):
        guard=IbkrSessionGuard(AccountBinding.from_attestation(self.a),mode=mode)
        guard.verify_connected(self.a,[self.a['account']]);self.w.session=guard
        return guard
    def test_paper_auto_serializes_only_scoped_orders_without_network(self):
        self.guard('PaperAuto');self.w.bracket(self.o,self.a)
        self.assertEqual(3,len(self.calls))
    def test_other_modes_block_sdk_and_raw_protobuf(self):
        for mode in ('Research','LiveApproval'):
            self.w.bracket_attempts.clear();self.guard(mode)
            with self.assertRaises(PermissionError):self.w.bracket(self.o,self.a)
            with self.assertRaises(PermissionError):self.w.client.placeOrderProtoBuf(None)
        self.assertEqual([],self.calls)
    def test_read_only_callback_blocks_serialization_without_message_leak(self):
        self.guard('PaperAuto');self.w.error(10,0,321,'API read-only; '+self.a['account'])
        with self.assertRaisesRegex(PermissionError,'PAPER_AUTO_BLOCKED: TWS API is read-only.'):
            self.w.bracket(self.o,self.a)
        self.assertEqual([],self.calls);self.assertNotIn(self.a['account'],str(self.w.drain()))
    def test_builder_cannot_change_risk_quantity_or_stop(self):
        self.guard('PaperAuto');old=self.w.make_order
        def altered(o,index,a,*args):
            order,fields=old(o,index,a,*args);order.totalQuantity=101;return order,fields
        self.w.make_order=altered
        with self.assertRaisesRegex(PermissionError,'QUANTITY_PRICE_OR_TRANSMISSION_CHANGED'):
            self.w.bracket(self.o,self.a)
        self.assertEqual([],self.calls)
    def test_disconnect_blocks_send_until_identity_is_reverified(self):
        guard=self.guard('PaperAuto');guard.disconnected()
        with self.assertRaises(ConnectionError):self.w.bracket(self.o,self.a)
        self.assertEqual([],self.calls)
    def test_order_timeout_does_not_retry_bracket_after_reconnect(self):
        guard=self.guard('PaperAuto')
        with patch.object(self.w.client,'sendMsgProtoBuf',side_effect=TimeoutError('timeout')),patch.object(self.w.client,'sendMsg',side_effect=TimeoutError('timeout')):
            with self.assertRaisesRegex(ConnectionError,'SEND_UNCERTAIN_RECONCILE_REQUIRED'):self.w.bracket(self.o,self.a)
        guard.disconnected();guard.verify_connected(self.a,[self.a['account']])
        with self.assertRaisesRegex(PermissionError,'ALREADY_ATTEMPTED'):self.w.bracket(self.o,self.a)
        self.assertEqual([],self.calls)
    def test_managed_account_changes_after_ack_block_all_mutations(self):
        self.guard('PaperAuto');self.w.managedAccounts('U12345678')
        self.assertFalse(self.w.connected)
        with self.assertRaises(ConnectionError):self.w.bracket(self.o,self.a)
        self.assertEqual([],self.calls)


class ReadinessHistoryTests(unittest.TestCase):
    def setUp(self):
        self.state={'orders':{'done':{'state':'CLOSED'}},'sessions':{'s':{'reserved':'0'}}}
        self.proof={'status':'RECONCILED_WITH_EMERGENCY_RETAINED'}
    def test_reconciled_closed_history_is_not_pending_but_not_deleted(self):
        self.assertEqual({},pending_journal_orders(self.state,self.proof))
        self.assertIn('done',self.state['orders'])
    def test_closed_label_alone_or_unknown_fees_never_prove_flat_journal(self):
        self.assertTrue(pending_journal_orders(self.state,{}))
        self.state['pending_commissions']={'late':{}}
        self.assertTrue(pending_journal_orders(self.state,self.proof))
    def test_remaining_reserve_and_uncertain_intention_block_readiness(self):
        self.state['sessions']['s']['reserved']='10'
        self.assertTrue(pending_journal_orders(self.state,self.proof))
        self.state['sessions']['s']['reserved']='0';self.state['orders']['done']['state']='UNKNOWN'
        self.assertTrue(pending_journal_orders(self.state,self.proof))


class ContinuousReconnectionTests(unittest.TestCase):
    def setUp(self):
        continuous_fixture.ContinuousPaperTests.setUp(self)
        self.w.disconnect=lambda:setattr(self.w,'connected',False)
        self.w.observe_quote=lambda:self.w.quote();self.w.calendar=lambda:self.plan['calendar']
    def test_history_disconnect_recovers_state_before_observing_again_without_order(self):
        calls=[]
        def history(minutes):
            calls.append(minutes)
            if len(calls)==1:raise ConnectionError('lost during market read')
            return []
        self.w.history=history
        with patch('trading_agent.paper_strategy.signal',return_value=None):
            continuous_fixture.continuous_strategy(self.lab,self.a,sleep=lambda _:None,monotonic=lambda:0,max_cycles=1)
        self.assertTrue(self.lab.reconciled);self.assertEqual([60,60,240,15],calls)
        self.assertEqual([],self.w.calls);self.assertEqual(100,self.lab.state['strategy_account']['equity'])
    def test_permission_gate_in_market_read_hard_stops_without_reconnect(self):
        self.w.history=lambda m:(_ for _ in ()).throw(PermissionError('ACCOUNT_BINDING_FAILED'))
        with patch('trading_agent.paper_lab_runner.SessionReconnect') as reconnect:
            with self.assertRaises(PermissionError):
                continuous_fixture.continuous_strategy(self.lab,self.a,sleep=lambda _:None,max_cycles=1)
        reconnect.assert_not_called();self.assertEqual([],self.w.calls)


if __name__=='__main__':unittest.main()
