from contextlib import ExitStack
import copy
from datetime import timedelta
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from trading_agent import h40_paper_trial as t
from trading_agent import stock_paper_forward as s
from trading_agent.ibkr_session import AccountBinding
from test_stock_paper_forward import BASE,plan,order,fill,fee,snap

ROOT=Path(__file__).resolve().parents[2];TRIAL='h40-trial-'+'b'*32

class R3Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.c=t.config(ROOT,t.R3_PROFILE)
        self.j=s.Journal(self.root/'journal.sqlite3','binding');self.l=t.TrialLedger(self.j,TRIAL,profile_config=self.c)
    def tearDown(self):self.j.close();self.tmp.cleanup()
    def p(self):
        p=plan();p.update(quantity=1,risk='2.14368',fees='1.33',trial_id=TRIAL,experiment_profile=t.R3_PROFILE,
            variant_version=t.variant_version(self.c),trade_classification='H40_SIGNAL_PAPER_EXPERIMENT')
        return p
    def test_original_strategy_and_r2_configuration_unchanged(self):
        self.assertEqual(s.CANDIDATE['risk_percent'],2);self.assertEqual(t.selected_risk(t.config(ROOT)),2);self.assertEqual(t.selected_risk(self.c),3)
    def test_r3_size_includes_costs_gap_and_contingency(self):
        v=t.size('12.28','11.59','12.96','.01',self.c)
        self.assertEqual(v['quantity'],1);self.assertEqual(v['risk'],'2.148680');self.assertEqual(v['fees'],'1.33')
        self.assertEqual(v['reserved_cash'],'13.63');self.assertEqual(v['budget'],'3')
        self.assertLess(s.number(v['friction']['target_net']),0)
    def test_r2_still_denies_same_risk(self):self.assertEqual(t.size('12.28','11.59','12.96','.01',t.config(ROOT))['quantity'],0)
    def test_gap_can_make_r3_no_trade(self):self.assertEqual(t.size('12.28','10','15','.01',self.c)['quantity'],0)
    def test_no_expansion_from_wider_external_ceiling(self):
        self.assertEqual(t.size('10','9.99','15','.01',self.c)['quantity'],1);self.assertEqual(t.budget(self.c,100,0),3)
    def test_profit_cannot_raise_budget_over_three(self):self.assertEqual(t.budget(self.c,110,0),3)
    def test_equity_loss_reduces_budget_never_increases_it(self):self.assertEqual(t.budget(self.c,90,0),s.number('2.7'))
    def test_loss_room_limits_budget(self):self.assertEqual(t.budget(self.c,100,19),1)
    def test_unknown_cap_stress_is_reported_not_hidden(self):
        v=t.cap_unverified_stress('12.28','11.59','12.96','.01',self.c)
        self.assertEqual(v['estimated_loss'],'3.898680');self.assertFalse(v['fits_budget']);self.assertEqual(v['cap_application'],'UNKNOWN')
    def test_r3_variant_is_independent(self):self.assertNotEqual(t.variant_version(self.c),s.VERSION);self.assertEqual(len(t.variant_version(self.c)),64)
    def test_explicit_scope_differs_from_r2(self):self.assertNotEqual(t.entry_scope(self.c),t.SCOPE);self.assertNotEqual(t.recovery_scope(self.c),t.RECOVERY_SCOPE)
    def test_three_percent_request_does_not_modify_parent_request(self):
        p=self.p();p.update(target='15',opening_fee='.66',closing_fee='.67',cash='100',slippage_per_unit='.03228',gap_per_unit='.0614')
        v=dict(quote=dict(received_at=BASE.isoformat(),bid='12.27'))
        self.assertEqual(t.trial_request(p,v,self.c)['proposedRisk'],s.number('.03'));self.assertEqual(s.risk_request(p,v)['proposedRisk'],s.number('.02'))
    def test_r3_can_reserve_two_point_one_risk_under_three(self):self.l.reserve(self.p());self.assertEqual(s.number(self.l.state['reservation']),s.number('11.33'))
    def test_ten_dollar_outer_limit_cannot_enlarge_reservation(self):
        p=self.p();p['risk']='3.01'
        with self.assertRaisesRegex(PermissionError,'RISK_LIMIT'):self.l.reserve(p)
    def test_must_include_both_fees_in_cash(self):
        p=self.p();p['entry']='99'
        with self.assertRaisesRegex(PermissionError,'CASH_SCOPE'):self.l.reserve(p)
    def test_no_two_shares(self):
        p=self.p();p['quantity']=2
        with self.assertRaises(PermissionError):self.l.reserve(p)
    def test_diagnostic_cannot_become_strategy_trade(self):
        p=self.p();p['trade_classification']='EXECUTION_DIAGNOSTIC'
        with self.assertRaisesRegex(PermissionError,'MUST_BE_SEPARATE'):self.l.reserve(p)
    def test_r2_plan_cannot_consume_r3_grant(self):
        p=self.p();p.pop('variant_version')
        with self.assertRaises(PermissionError):self.l.reserve(p)
    def test_persistence_has_variant_and_source_without_altering_parent(self):
        self.l.reserve(self.p());self.j.close();self.j=s.Journal(self.root/'journal.sqlite3','binding');self.l=t.TrialLedger(self.j,TRIAL,profile_config=self.c)
        self.assertEqual(self.l.state['variant_version'],t.variant_version(self.c));self.assertEqual(self.l.state['strategy_version'],s.VERSION)
        self.assertTrue(self.l.state['opening_consumed'])
    def test_r3_journal_cannot_reopen_as_r2(self):
        with self.assertRaisesRegex(PermissionError,'PROFILE_JOURNAL'):t.TrialLedger(self.j,TRIAL)
    def test_r3_settlement_does_not_claim_profitable_strategy(self):
        self.l.reserve(self.p());v=snap(execs=[fill(10,q=1),fill(11,'s',q=1,price=11)],fees=[fee('b'),fee('s')])
        v['completed_orders']=[{**order(oid,'Filled' if oid in (10,11) else 'Cancelled'),'quantity':'1'} for oid in (10,11,12)]
        self.l.reconcile(v);payload=json.loads(self.j.db.execute("SELECT payload FROM events WHERE kind='TRADE_SETTLED'").fetchone()[0])
        self.assertEqual(payload['details']['experiment_profile'],t.R3_PROFILE);self.assertFalse(payload['details']['strategy_profitability_proven'])
    def test_r3_loss_stops_day_and_single_use_survives_day_change(self):
        self.l.reserve(self.p());v=snap(execs=[fill(10,q=1),fill(11,'s',q=1,price=9)],fees=[fee('b'),fee('s')])
        v['completed_orders']=[{**order(oid,'Filled' if oid in (10,11) else 'Cancelled'),'quantity':'1'} for oid in (10,11,12)]
        self.l.reconcile(v);self.assertEqual(self.l.state['stopped_days'][BASE.date().isoformat()],'DAILY_FIRST_LOSS_STOP')
        p=self.p();p['at']=(BASE+timedelta(days=1)).isoformat()
        with self.assertRaisesRegex(PermissionError,'ONE_TRIAL'):self.l.reserve(p)
    def test_profile_configuration_cannot_be_edited_to_four_percent(self):
        c=copy.deepcopy(self.c);c['experimental_risk_percent']=4
        with patch.object(s,'configuration'),patch.object(Path,'read_text',return_value=json.dumps(c)):
            with self.assertRaisesRegex(PermissionError,'LIMITS_CHANGED'):t.config(self.root,t.R3_PROFILE)
    def test_unknown_fee_consent_cannot_silently_unblock_r3(self):
        v=snap();v['capabilities']={k:dict(status='UNKNOWN',compatible=False,observed_at=BASE.isoformat()) for k in s.CAPABILITIES}
        receipt=dict(cost_scenario=dict(status='ESTIMATED',model='FIXED_FEE_STRESS',effective_fees='UNKNOWN',contingency_usd=1,operator_accepts_uncertainty=True,source='https://www.interactivebrokers.com/en/pricing/commissions-stocks.php'))
        self.assertIn('EFFECTIVE_FEES_UNKNOWN_OR_RESTRICTED',t.blockers(v,self.c,receipt,BASE,True))
    def test_scope_specific_paper_receipts(self):
        p=self.root/'receipts.json';p.write_text(json.dumps(dict(environment='PAPER_TRADING',binding_id='binding',scope=t.SCOPE,capabilities={})))
        with self.assertRaisesRegex(PermissionError,'PAPER_ONLY'):t.evidence(ROOT,p,'binding',expected_scope=t.R3_SCOPE)
    def test_readonly_diagnose_never_creates_orders_journal_or_success(self):
        (t.folder(self.root,TRIAL)).mkdir(parents=True);value=dict(experimental_blockers=[],supervised_consent_present=False,controlled_reference_size=t.size('12.28','11.59','12.96','.01',self.c))
        with patch.object(t,'inspect',return_value=value),patch.object(t,'trial_config',return_value=self.c),patch.object(t,'wire_read',side_effect=AssertionError('mutation wire used')):
            r=t.diagnose(self.root,TRIAL)
        self.assertFalse(r['execution_diagnostic_performed']);self.assertFalse(r['strategy_entry_eligible'])
        self.assertFalse((t.folder(self.root,TRIAL)/'journal.sqlite3').exists());self.assertIn('READ_ONLY',r['diagnostic_kind'])
    def test_diagnostic_files_not_overwritten(self):
        t.folder(self.root,TRIAL).mkdir(parents=True);v=dict(experimental_blockers=[],supervised_consent_present=False)
        with patch.object(t,'inspect',side_effect=lambda *a:copy.deepcopy(v)),patch.object(t,'trial_config',return_value=self.c):
            a=t.diagnose(self.root,TRIAL);b=t.diagnose(self.root,TRIAL)
        self.assertNotEqual(a['diagnostic_evidence_path'],b['diagnostic_evidence_path']);self.assertTrue(Path(a['diagnostic_evidence_path']).exists())
    def guard(self,st,recovery=False):
        binding=AccountBinding.from_attestation(dict(schema_version=1,account='DU123',paper_checked=True,identity_manual_match=True))
        grant=dict(scope=t.R3_SCOPE,trial_id=TRIAL,account=binding.account,binding_id=binding.binding_id,
            environment='PAPER_TRADING',live_enabled=False,supervised_protection_bootstrap=True,
            experiment_profile=t.R3_PROFILE,variant_version=t.variant_version(self.c),
            protocol_sha256='hash',source_hashes={'source':'hash'},read_only_disabled_checked=True,
            tws_pid=1,tws_start_filetime='1',issued_at=BASE.isoformat(),expires_at=(BASE+timedelta(minutes=30)).isoformat(),revoked=False,paper_evidence={})
        st.enter_context(patch.object(t,'config',return_value=self.c));st.enter_context(patch.object(t,'protocol'))
        st.enter_context(patch.object(t,'hashes',return_value={'source':'hash'}));st.enter_context(patch.object(s,'sha',return_value='hash'))
        st.enter_context(patch.object(t,'same_process',return_value=True));st.enter_context(patch.object(t.SessionConfiguration,'load',return_value=SimpleNamespace(matches=lambda g:None)))
        if recovery:
            self.l.reserve(self.p());self.l.fill(fill(10,q=1));self.l.state['intent']['position']='1'
            grant.update(scope=t.recovery_scope(self.c),intent='H40-a',con_id=100,quantity='1',buy_exec_ids=['b'],buy_perm_ids=[110])
            st.enter_context(patch.object(t,'unseal',side_effect=lambda p:binding._record if p.name=='ibkr-account-binding.dpapi' else grant))
            g=t.RecoveryGuard(self.root,TRIAL,self.l,clock=lambda:BASE)
        else:
            st.enter_context(patch.object(t,'unseal',return_value=binding._record));g=t.TrialGuard(self.root,TRIAL,self.l,loader=lambda:grant,clock=lambda:BASE)
        return g,grant
    def test_r2_grant_cannot_authorize_r3(self):
        with ExitStack() as st:
            g,r=self.guard(st);r['scope']=t.SCOPE
            with self.assertRaisesRegex(PermissionError,'INDEPENDENT'):g.grant()
    def test_wrong_variant_identity_blocks(self):
        with ExitStack() as st:
            g,r=self.guard(st);r['variant_version']=s.VERSION
            with self.assertRaisesRegex(PermissionError,'VARIANT_AUTHORIZATION'):g.grant()
    def test_emergency_blocks_even_a_protected_r3_grant(self):
        with ExitStack() as st:
            g,r=self.guard(st);p=self.root/'.local';p.mkdir();(p/'paper-lab.emergency').write_text('active')
            with self.assertRaisesRegex(PermissionError,'EMERGENCY'):g.grant()
            self.assertIsNone(self.l.state['intent']);self.assertEqual(self.l.state['reservation'],'0')
    def test_r3_authorization_has_no_automatic_renewal(self):
        with ExitStack() as st:
            g,r=self.guard(st);r['expires_at']=BASE.isoformat()
            with self.assertRaisesRegex(PermissionError,'EXPIRED'):g.grant()
    def test_recovery_is_separate_from_entry(self):
        with ExitStack() as st:
            g,r=self.guard(st,True);self.assertEqual(g.grant(True)['scope'],t.recovery_scope(self.c))
            with self.assertRaisesRegex(PermissionError,'CANNOT_OPEN'):g.grant()
    def test_recovery_never_exceeds_bound_remaining_long(self):
        with ExitStack() as st:
            g,r=self.guard(st,True);self.l.state['intent']['position']='2'
            with self.assertRaisesRegex(PermissionError,'QUANTITY_CHANGED'):g.grant(True)
    def test_r2_recovery_cannot_close_under_r3_scope(self):
        with ExitStack() as st:
            g,r=self.guard(st,True);r['scope']=t.RECOVERY_SCOPE
            with self.assertRaises(PermissionError):g.grant(True)
    def test_recovery_linked_to_original_buy_exec_and_perm(self):
        with ExitStack() as st:
            g,r=self.guard(st,True);r['buy_perm_ids']=[999]
            with self.assertRaisesRegex(PermissionError,'QUANTITY_CHANGED'):g.grant(True)

if __name__=='__main__':unittest.main()
