import copy
from datetime import timedelta
from decimal import Decimal
import json
import os
import uuid
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from ibapi.order import Order
from test_paper_account_capabilities import CapClient
from trading_agent.broker import PaperOptions
from trading_agent import ford_execution_diagnostic as d
from trading_agent.ford_diagnostic_evidence import PostgresMirror,completed_receipt
from trading_agent.ai_strategy_researcher import execution_memory as memory
from trading_agent.ai_strategy_researcher.memory import build,compact
from test_ford_execution_diagnostic import ROOT,TRIAL,BASE,quote,plan,order,fill,fee,snap
import test_ford_execution_diagnostic as fixtures


class R10Tests(unittest.TestCase):
    def setUp(self):
        self.token=d.PROFILE.set(d.R10_SCOPE);self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.path=self.root/d.FOLDER/TRIAL/'journal.sqlite3';self.j=d.Journal(self.path,'binding',TRIAL);self.l=d.Ledger(self.j)
        self.c=d.configuration(ROOT);self.p=plan();self.p.update(d.scenario(quote(),self.c),diagnostic_scope=d.R10_SCOPE)
    def tearDown(self):self.j.close();self.tmp.cleanup();d.PROFILE.reset(self.token)
    def test_explicit_scope_and_budget(self):self.assertEqual(self.c['risk_budget_usd'],10);self.assertEqual(self.l.state['scope'],d.R10_SCOPE)
    def test_full_minima_numeric_pass(self):self.assertEqual(self.p['risk'],'3.533090');self.assertTrue(self.p['fits_budget']);self.assertEqual(self.p['budget'],'10')
    def test_cap_not_assumed(self):self.assertFalse(self.p['cap_confirmed']);self.assertEqual(self.p['fees'],'3.08')
    def test_r10_never_increases_quantity(self):self.assertEqual(self.p['quantity'],1);self.assertEqual(self.c['maximum_quantity'],1)
    def test_inventory_tail_can_exceed_ten(self):self.assertGreater(Decimal(self.p['adverse_scenarios']['total_inventory_loss']),10)
    def test_r10_does_not_fix_unknown_execution(self):self.assertIn('STOCK_PERMISSION_UNKNOWN_OR_RESTRICTED',d.blockers(snap(),self.c,bootstrap=True,clock=lambda:BASE))
    def test_delayed_data_still_blocks(self):
        s=snap();s['quote']['market_data_type']=3;self.assertIn('LIVE_BID_ASK_UNAVAILABLE_OR_STALE',d.blockers(s,self.c,bootstrap=True,clock=lambda:BASE))
    def test_no_budget_increase_after_loss(self):
        self.l.state['consumed_loss']='1';self.l.state['equity']='99'
        with self.assertRaisesRegex(PermissionError,'ALLOCATION_ALREADY_USED'):d.risk(ROOT,self.l.state,self.p,snap())
    def test_short_denied(self):
        self.p['side']='SELL'
        with self.assertRaises(PermissionError):self.l.reserve(self.p)
    def test_two_shares_denied(self):
        self.p['quantity']=2
        with self.assertRaises(PermissionError):self.l.reserve(self.p)
    def test_risk_over_ten_denied(self):
        self.p['risk']='10.01'
        with self.assertRaises(PermissionError):self.l.reserve(self.p)
    def test_cash_plus_costs_over_hundred_denied(self):
        self.p['entry']='99';self.p['target']='100'
        with self.assertRaises(PermissionError):self.l.reserve(self.p)
    def test_legacy_scope_plan_cannot_use_r10(self):
        self.p['diagnostic_scope']=d.SCOPE
        with self.assertRaises(PermissionError):self.l.reserve(self.p)
    def test_legacy_journal_cannot_be_reopened_as_r10(self):
        token=d.PROFILE.set(d.SCOPE)
        try:
            with self.assertRaises(PermissionError):d.Journal(self.path,'binding',TRIAL)
        finally:d.PROFILE.reset(token)
    def test_request_is_explicit_ten_percent_diagnostic(self):
        r=d.request(self.p,snap());self.assertEqual(r['proposedRisk'],Decimal('.10'));self.assertEqual(r['execution']['source'],d.R10_SCOPE);self.assertIsNone(r['execution']['takeProfit'])
    def test_legacy_grant_does_not_authorize_r10(self):
        f=fixtures.DiagnosticGuardTests();f.setUp()
        try:
            with self.assertRaisesRegex(PermissionError,'SCOPE'):f.guard.grant()
        finally:f.tearDown()
    def test_recovery_scope_is_independent(self):self.assertNotEqual(d.recovery_scope(),d.RECOVERY_SCOPE)
    def test_profile_change_invalidates_receipts(self):
        p=self.root/'receipt.json';p.write_text(json.dumps(dict(scope=d.SCOPE,binding_id='binding',environment='PAPER_TRADING')))
        with self.assertRaises(PermissionError):d.receipts(self.root,p,'binding')
    def test_full_minima_core_allows_only_simulation(self):
        s=snap()
        for k in ('stock_permission','account_restrictions','contract_margin','whole_share_minimum','quantity_increment','effective_fees'):
            s['capabilities'][k]=dict(status='VERIFIED',compatible=True,value=1)
        with patch.object(d.stock,'now',return_value=BASE):
            # Core wall-clock quote must be fresh, not the fixture's date.
            stamp=d.stock.now().isoformat();self.p['at']=stamp
        current=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()
        self.p['at']=current;s['at']=current;s['quote']['received_at']=current
        s['quote']['field_received_at']={'bid':current,'ask':current};s['quote']['market_data_type']=1
        r=d.risk(ROOT,self.l.state,self.p,s);self.assertTrue(r['allowed']);self.assertEqual(r['decision'],'ALLOW_SIMULATION');self.assertEqual(r['quantity'],1)
    def test_database_failure_before_opening_means_zero_send(self):
        self.l.reserve(self.p);self.j.mirror=PostgresMirror(self.root,self.j,lambda v:(_ for _ in ()).throw(OSError('private connection')))
        calls=[]
        with self.assertRaisesRegex(PermissionError,'POSTGRES'):
            self.l.pre_send(10);calls.append('placeOrder')
        self.assertEqual(calls,[]);self.assertEqual(self.l.state['intent']['state'],'SEND_PENDING');self.assertNotEqual(self.l.state['reservation'],'0')
        with self.assertRaises(PermissionError):self.l.pre_send(10)
    def test_database_failure_does_not_prevent_protective_leg(self):
        self.l.reserve(self.p);self.l.pre_send(10)
        self.j.mirror=PostgresMirror(self.root,self.j,lambda v:(_ for _ in ()).throw(OSError()))
        self.l.pre_send(11);self.assertTrue(self.j.mirror.pending);self.assertIn(11,self.l.state['intent']['attempted'])
    def test_no_research_receipt_for_pending_inventory(self):
        self.l.reserve(self.p);mirror=PostgresMirror(self.root,self.j)
        self.assertIsNone(completed_receipt(self.root,self.j,mirror))
    def test_postgres_failure_at_sdk_boundary_has_zero_place_order(self):
        self.j.mirror=PostgresMirror(self.root,self.j,lambda v:(_ for _ in ()).throw(OSError()))
        w=d.execution_wire(PaperOptions('DU123',paper_mode_attested=True,timeout=.02,read_only=False),
            (CapClient,object,SimpleNamespace,Order,SimpleNamespace,SimpleNamespace));w.connect()
        w.bind_execution(SimpleNamespace(admission=lambda *a:None,grant=lambda **kw:{}),self.l)
        try:
            with patch.object(CapClient,'placeOrder',create=True) as sdk:
                with self.assertRaisesRegex(PermissionError,'POSTGRES'):w.bracket(snap(),self.p)
                sdk.assert_not_called()
            self.assertTrue(self.l.state['suspended']);self.assertEqual(self.l.state['intent']['attempted'],[10])
        finally:w.disconnect()
    def test_other_diagnostic_reservation_blocks_new_allocation(self):
        self.l.reserve(self.p)
        with self.assertRaisesRegex(PermissionError,'ANOTHER_EXPERIMENTAL'):d.other_reservations(self.root)


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.token=d.PROFILE.set(d.R10_SCOPE);self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.j=d.Journal(self.root/d.FOLDER/TRIAL/'journal.sqlite3','binding',TRIAL);self.l=d.Ledger(self.j)
        self.rows={};self.calls=0
        def invoke(v):
            self.calls+=1
            for e in v['events']:
                if e['revision'] in self.rows:self.assertEqual(self.rows[e['revision']],e['hash'])
                else:self.rows[e['revision']]=e['hash']
            n=max(self.rows,default=0);return dict(revision=n,hash=self.rows.get(n,''))
        self.mirror=PostgresMirror(self.root,self.j,invoke);self.j.mirror=self.mirror
        p=plan();p.update(d.scenario(quote(),d.configuration(ROOT)),diagnostic_scope=d.R10_SCOPE);self.l.reserve(p)
    def tearDown(self):self.j.close();self.tmp.cleanup();d.PROFILE.reset(self.token)
    def finish(self,closing_fee=True):
        if not self.l.state['intent']['attempted']:self.l.pre_send(10)
        self.l.reconcile(snap('1',orders=[order(11),order(12)],execs=[fill(10,'buy')],fees=[fee('buy')],completed=[order(10,'Filled','1')]))
        s=snap('0',execs=[fill(10,'buy'),fill(11,'sell',price='12.56')],fees=[fee('buy')]+([fee('sell')] if closing_fee else []),
            completed=[order(10,'Filled','1'),order(11,'Filled','1'),order(12,'Cancelled')])
        self.l.reconcile(s);return s
    def test_outbox_replay_is_idempotent(self):
        self.mirror.sync(True);rows=copy.deepcopy(self.rows);again=PostgresMirror(self.root,self.j,self.mirror.invoke);again.sync(True);self.assertEqual(self.rows,rows)
    def test_foreign_database_head_blocks(self):
        self.mirror.invoke=lambda v:dict(revision=999,hash='0'*64)
        with self.assertRaises(PermissionError):self.mirror.sync(True)
    def test_pending_commission_keeps_reservation_and_no_learning(self):
        self.finish(False);self.assertNotEqual(self.l.state['reservation'],'0');self.assertIsNone(completed_receipt(self.root,self.j,self.mirror));self.assertEqual(memory.load(self.root),[])
    def test_complete_cycle_exports_observed_simulated_evidence(self):
        self.finish();v=memory.load(self.root)[0];self.assertEqual(v['observed']['BUY']['commissions'],'0.16');self.assertEqual(v['observed']['SELL']['price'],'12.56');self.assertFalse(v['profitability_evidence']);self.assertFalse(v['strategy_success'])
    def test_receipt_replay_does_not_duplicate(self):
        self.finish();completed_receipt(self.root,self.j,self.mirror);self.assertEqual(len(memory.load(self.root)),1)
    def test_nonpositive_close_records_daily_stop(self):
        self.finish();self.assertIn('DAILY_FIRST_LOSS_STOP',self.l.state['stopped_days'].values());self.assertEqual(self.l.entry_block(BASE.isoformat()),'ONE_DIAGNOSTIC_ONLY')
    def test_resolved_late_fee_can_export_on_readonly_reconcile(self):
        s=self.finish(False);self.assertEqual(memory.load(self.root),[]);s['commissions'].append(fee('sell'));self.l.reconcile(s);self.assertEqual(len(memory.load(self.root)),1)
    def test_learning_waits_for_postgres_recovery(self):
        self.l.pre_send(10);original=self.mirror.invoke;self.mirror.invoke=lambda v:(_ for _ in ()).throw(OSError());self.finish()
        self.assertEqual(memory.load(self.root),[]);self.mirror.invoke=original;self.l.reconcile(snap());self.assertEqual(len(memory.load(self.root)),1)
    def test_evidence_integrity_failure_not_silently_ignored(self):
        self.finish();p=next((self.root/memory.DIRECTORY).glob('*.json'));p.write_text('{}')
        with self.assertRaises(ValueError):memory.load(self.root)
    def test_source_journal_tampering_blocks_memory(self):
        self.finish();self.j.db.execute("UPDATE events SET kind='tampered' WHERE revision=1");self.j.db.commit()
        with self.assertRaises(ValueError):memory.load(self.root)
    def test_diagnostic_in_prompt_but_not_strategy_sample(self):
        self.finish();package=dict(limitations=[],broker_constraints={})
        full=build(self.root,[],package,'0'*64);summary=compact(full)
        self.assertEqual(summary['total_records'],0);self.assertEqual(summary['execution_observations'][0]['strategy_sample_size'],0)
        self.assertEqual(summary['execution_observation_count'],1);self.assertFalse(full['execution_authorized'])
    def test_diagnostic_never_invokes_openai(self):
        with patch('trading_agent.ai_strategy_researcher.providers.request_body',side_effect=AssertionError('OpenAI path')):self.finish()
        self.assertEqual(memory.load(self.root)[0]['openai_requests'],0)

class PostgresBridgeTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('TRADING_TEST_DB'),'Disposable PostgreSQL required')
    def test_python_canonical_chain_through_real_dotnet_postgres(self):
        token=d.PROFILE.set(d.R10_SCOPE)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                trial='ford-diag-'+uuid.uuid4().hex;j=d.Journal(Path(tmp)/'journal.sqlite3','bridge-binding',trial)
                try:
                    with patch.dict(os.environ,{'TRADING_LAB_DB':os.environ['TRADING_TEST_DB']}):
                        mirror=PostgresMirror(ROOT,j);self.assertTrue(mirror.sync(True))
                        state=j.load()[1];j.commit(1,state,'BRIDGE_TEST',dict(text='USD costos conservadores'))
                        self.assertTrue(mirror.sync(True));self.assertEqual(mirror.revision,2)
                        restarted=PostgresMirror(ROOT,j);self.assertTrue(restarted.sync(True));self.assertEqual(mirror.hash,restarted.hash)
                finally:j.close()
        finally:d.PROFILE.reset(token)

if __name__=='__main__':unittest.main()
