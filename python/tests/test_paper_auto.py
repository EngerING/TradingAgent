"""Persistent Paper permits and technical eligibility, never real order authority."""
import copy
from datetime import timedelta
import json
import os
from pathlib import Path
import unittest
import uuid
from unittest.mock import patch
from trading_agent.ibkr_session import AccountBinding
from trading_agent.paper_auto import (PaperAutoAuthorization,permission_status,aggregate,strategy_allowed,
    proposal,save_permission,read_permission,owned_reconciled)
from trading_agent.paper_eligibility import evaluate_registered,validate_structure,StrategyEligibility
from trading_agent.paper_lab import PaperLab,Authorization,stamp,DotnetJournal,EXPERIMENTAL
from trading_agent.paper_lab_runner import strategy_cycle,continuous_strategy
from trading_agent.paper_identity import protect
import test_paper_lab as fixtures
import test_strategy_continuous as continuous

def permit():
    a=fixtures.grant();b=AccountBinding.from_attestation(a);p=continuous.plan(fixtures.NOW)
    eligibility={'state':'PaperEligible','environment':'PAPER_TRADING','live_approved':False,
        'registered':True,'enabled':True,'tests_passed':True,'strategy_version':'synthetic-v1',
        'strategy_id':'trend','name':'Synthetic only'}
    p.update(strategy_id='trend',exit_policy='RESEARCH_D_V1',paper_eligibility=eligibility)
    a.update(scope='PAPER_AUTO_ONLY',execution_mode='PaperAuto',status='Granted',account_binding_id=b.binding_id,
        granted_by='synthetic-operator',mode='StrategyPaper',risk_profile='PAPER_EXPERIMENTAL_10_PERCENT',
        selected_strategy='trend',strategy_version='synthetic-v1',strategy_versions=['synthetic-v1'],
        strategy_requirements_verified=True,strategy_plan=p,execution_requirements=p['execution_requirements'],
        source_hashes={'synthetic':'fixture'},diagnostic_loss_budget=0,continuous=True)
    report={'preferred':'trend','strategies':[eligibility],'source_hashes':a['source_hashes']}
    return a,b,report

class PersistentPermissionTests(unittest.TestCase):
    def setUp(self):
        self.a,self.b,self.report=permit();self.process_calls=[]
        self.auth=self.new()
    def new(self):
        def process():
            self.process_calls.append(1)
            return {'tws_pid':2,'tws_start_filetime':'2','calendar':self.a['strategy_plan']['calendar']}
        return PaperAutoAuthorization(lambda:copy.deepcopy(self.a),lambda:self.b,lambda:self.report,process,
            clock=lambda:fixtures.NOW,session_alive=lambda *a:True)
    def test_valid_permission_allows_multiple_reads_without_confirmation(self):
        for _ in range(4):self.assertEqual('PaperAuto',self.auth.read()['execution_mode'])
        self.assertEqual(1,len(self.process_calls))
    def test_permission_survives_agent_restart_without_extension(self):
        first=self.auth.read();second=self.new().read()
        self.assertEqual(first['expires_at'],second['expires_at']);self.assertEqual(first['session_id'],second['session_id'])
    def test_expired_permission_blocks_new_entries(self):
        self.a['confirmed_at']=stamp(fixtures.NOW-timedelta(hours=2));self.a['expires_at']=stamp(fixtures.NOW-timedelta(hours=1))
        with self.assertRaisesRegex(PermissionError,'EXPIRED'):self.auth.read()
    def test_revocation_immediate_on_next_gate(self):
        self.auth.read();self.a.update(status='Revoked',revoked=True)
        with self.assertRaisesRegex(PermissionError,'REVOKED'):self.auth.read()
    def test_revoked_permission_can_only_manage_existing_owned_positions(self):
        self.a.update(status='Revoked',revoked=True)
        self.assertTrue(self.auth.read(management=True)['revoked'])
    def test_changed_full_identity_and_binding_invalidate(self):
        for changes in ({'account':'DU00005678'},{'account_binding_id':'0'*64}):
            self.assertEqual('INVALID',permission_status({**self.a,**changes},self.b,fixtures.NOW))
    def test_paper_permission_never_valid_in_live(self):
        for changes in ({'environment':'LIVE_TRADING'},{'live_enabled':True},{'execution_mode':'LiveApproval'}):
            self.assertEqual('INVALID',permission_status({**self.a,**changes},self.b,fixtures.NOW))
        with patch.dict(os.environ,{'LIVE_TRADING':'true'}):
            with self.assertRaisesRegex(PermissionError,'LIVE_DISABLED'):self.auth.read()
    def test_expiry_is_bounded_and_cannot_be_missing(self):
        for change in ({'expires_at':stamp(fixtures.NOW+timedelta(days=2))},{'expires_at':'invalid'}):
            self.assertEqual('INVALID',permission_status({**self.a,**change},self.b,fixtures.NOW))
    def test_reconnection_preserves_explicit_permission_and_account(self):
        first=self.auth.read();self.auth.process=None;second=self.auth.read()
        self.assertEqual(first['account_binding_id'],second['account_binding_id'])
        self.assertEqual(first['expires_at'],second['expires_at'])
    def test_strategy_or_components_change_invalidates_permission(self):
        self.report['source_hashes']={'changed':'fixture'}
        with self.assertRaisesRegex(PermissionError,'ELIGIBILITY_CHANGED'):self.auth.read()
    def test_dpapi_permission_roundtrip_in_isolated_fixture_root(self):
        root=Path(__file__).resolve().parents[2]/'.local/paper-auto-tests'/uuid.uuid4().hex
        (root/'.local').mkdir(parents=True)
        try:
            save_permission(root,self.a);saved=read_permission(root)
            self.assertEqual(self.a,saved);self.assertEqual('VALID',permission_status(saved,self.b,fixtures.NOW))
            self.assertNotIn(self.a['account'].encode(),(root/'.local/paper-auto-authorization.dpapi').read_bytes())
        finally:
            (root/'.local/paper-auto-authorization.dpapi').unlink(missing_ok=True);(root/'.local').rmdir();root.rmdir()

class EligibilityTests(unittest.TestCase):
    def setUp(self):
        self.a,self.b,self.report=permit();self.plan=self.a['strategy_plan']
        self.spec={'id':'trend','parameters_hash':'synthetic'}
        self.rows=[{'hash':'synthetic-v1','strategy':{'name':'Synthetic','parametersJson':json.dumps(self.spec),
            'instrument':'EUR/USD','version':1},'registration':{'state':'CANDIDATE_RESEARCH_ONLY'}}]
        self.analysis={'strategies':[self.spec],'parameters':self.plan['indicators']}
    def evaluate(self,proof=True,probe=None):
        return evaluate_registered(self.rows,self.analysis,['trend'],{'passed':proof},probe or (lambda:{'allowed':False,'reason':'RISK_VETO'}))[0]
    def test_registered_candidate_can_be_paper_eligible_without_live_approval(self):
        result=self.evaluate();self.assertEqual('PaperEligible',result['state']);self.assertFalse(result['live_approved'])
        self.assertTrue(strategy_allowed(result,'PAPER_TRADING'));self.assertFalse(strategy_allowed(result,'LIVE_TRADING'))
    def test_candidate_cannot_operate_live_or_paper_before_eligibility(self):
        result={**self.evaluate(),'state':'Candidate'}
        for env in ('PAPER_TRADING','LIVE_TRADING'):self.assertFalse(strategy_allowed(result,env))
    def test_paper_eligible_does_not_imply_live_approved(self):
        self.assertNotEqual(StrategyEligibility.PaperEligible,StrategyEligibility.LiveApproved)
        self.assertFalse(strategy_allowed({**self.evaluate(),'state':'LiveApproved'},'LIVE_TRADING'))
    def test_risk_veto_is_not_a_health_exception_and_is_not_bypassed(self):
        result=self.evaluate();self.assertEqual('PaperEligible',result['state']);self.assertFalse(result['risk_probe']['allowed'])
    def test_missing_required_parameters_make_ineligible(self):
        del self.analysis['parameters']['rsi']
        self.assertIn('REQUIRED_PARAMETERS_MISSING',self.evaluate()['reasons'])
    def test_failed_associated_tests_make_ineligible(self):
        self.assertEqual('Candidate',self.evaluate(False)['state'])
    def test_missing_risk_component_or_exception_make_ineligible(self):
        def failure():raise RuntimeError('risk unavailable')
        self.assertIn('RISK_ENGINE_UNHEALTHY',self.evaluate(probe=failure)['reasons'])
    def test_disabled_registration_make_ineligible(self):
        self.rows[0]['registration']['enabled']=False
        self.assertIn('STRATEGY_DISABLED',self.evaluate()['reasons'])
    def test_parameters_cannot_be_changed_for_eligibility(self):
        self.analysis['strategies'][0]={'id':'trend','parameters_hash':'different'}
        self.assertIn('REGISTERED_PARAMETERS_NOT_EQUIVALENT',self.evaluate()['reasons'])
    def test_missing_evidence_metadata_cannot_claim_paper_eligibility(self):
        self.plan['paper_eligibility']['tests_passed']=False
        with self.assertRaises(PermissionError):validate_structure(self.plan)
    def test_receipt_of_another_strategy_cannot_authorize_plan(self):
        self.plan['paper_eligibility']['strategy_id']='pullback'
        with self.assertRaises(PermissionError):validate_structure(self.plan)
    def test_known_evidence_prerequisite_is_veto_not_engine_failure(self):
        core=DotnetJournal(Path(__file__).resolve().parents[2],EXPERIMENTAL)
        with patch.object(core,'command',side_effect=RuntimeError('STRATEGY_PAPER_EVIDENCE_REQUIRED')):
            result=core.strategy_risk({},{});self.assertFalse(result['allowed']);self.assertEqual(0,result['quantity'])
        eligible=self.evaluate(probe=lambda:result)
        self.assertEqual('PaperEligible',eligible['state']);self.assertFalse(eligible['risk_probe']['allowed'])
    def test_unknown_engine_errors_remain_blocking(self):
        core=DotnetJournal(Path('.'),EXPERIMENTAL)
        with patch.object(core,'command',side_effect=RuntimeError('LAB_JOURNAL_FAILED')):
            with self.assertRaisesRegex(RuntimeError,'LAB_JOURNAL_FAILED'):core.strategy_risk({},{})
    def test_existing_paper_profile_with_unknown_real_constraints_has_zero_quantity(self):
        core=DotnetJournal(Path(__file__).resolve().parents[2],EXPERIMENTAL)
        request=copy.deepcopy(self.plan['execution_requirements'])
        request.update(instrument='EUR/USD',side='BUY',bid=1,ask='1.0001',stop='.99',marketAt=stamp())
        request['execution'].update(at=stamp(),quoteStatus='LIVE',takeProfit='1.5',equivalentRealAccount={})
        result=core.strategy_risk(core.strategy_initial(),request)
        self.assertFalse(result['allowed']);self.assertEqual('STRATEGY_PAPER_EVIDENCE_REQUIRED',result['reason'])
        self.assertEqual(0,result['quantity'])

class ReadyTests(unittest.TestCase):
    def setUp(self):
        self.conditions={k:'PASS' for k in ('IBKR_CONNECTED','ACCOUNT_VERIFIED','ENVIRONMENT_PAPER','RECONCILIATION',
            'EMERGENCY_STOP','PAPER_AUTHORIZATION','STRATEGY_PAPER_ELIGIBLE','RISK_ENGINE','EXECUTION_GUARD')}
    def test_only_all_conditions_pass_can_be_ready(self):
        self.assertTrue(aggregate(self.conditions)['paper_auto_ready'])
        for key in self.conditions:
            self.assertFalse(aggregate({**self.conditions,key:'BLOCKED'})['paper_auto_ready'])
    def test_missing_condition_cannot_default_to_ready(self):
        del self.conditions['EXECUTION_GUARD']
        with self.assertRaises(PermissionError):aggregate(self.conditions)
    def test_expired_or_revoked_permission_blocks_readiness(self):
        for status in ('EXPIRED','REVOKED','NOT_GRANTED','INVALID'):
            self.assertFalse(aggregate({**self.conditions,'PAPER_AUTHORIZATION':status})['paper_auto_ready'])
    def test_ready_never_enables_live(self):self.assertFalse(aggregate(self.conditions)['live_enabled'])
    def test_restart_reconciliation_only_accepts_own_session_exact_inventory(self):
        record={'session_id':'synthetic'}
        observation={'owned_reconciliation':{'status':'RECONCILED_WITH_EMERGENCY_RETAINED'},
            'snapshot':{'cash_reconciliation':{'query_status':'COMPLETE','account_ready':True},'eur_cash':'25',
                'exposure_reads_complete':True,'orders':[{'order_id':3}],
                'positions':[{'contract_id':12087792,'quantity':'25'}]},
            'additional_exposure':{'status':'COMPLETE','errors':[],'positions':[{'contract_id':12087792,'quantity':'25'}]},
            'owned_orders':{'synthetic':{'state':'PARTIALLY_FILLED','session_id':'synthetic',
                'payload':{'mode':'StrategyPaper'},'order_ids':[1,2,3],
                'fills':{'exec':{'quantity':'25','side':'BUY'}}}}}
        self.assertTrue(owned_reconciled(observation,record))
        self.assertFalse(owned_reconciled(observation,{'session_id':'different'}))
        for changed in ('quantity','contract_id'):
            other=copy.deepcopy(observation);other['additional_exposure']['positions'][0][changed]='26'
            self.assertFalse(owned_reconciled(other,record))
        other=copy.deepcopy(observation);other['snapshot']['orders'].append({'order_id':999})
        self.assertFalse(owned_reconciled(other,record))
    def test_restart_reconciliation_blocks_incomplete_sources(self):
        self.assertFalse(owned_reconciled({'owned_reconciliation':{'status':'RECONCILED_WITH_EMERGENCY_RETAINED'}},{'session_id':'synthetic'}))

class RuntimeTests(unittest.TestCase):
    def setUp(self):
        continuous.ContinuousPaperTests.setUp(self)
    def test_no_trade_is_journaled_and_never_creates_order(self):
        with patch('trading_agent.paper_strategy.signal',return_value=None):
            result=strategy_cycle(self.lab,self.plan,{},self.w.quote())
        self.assertEqual('NO_TRADE',result['decision']);self.assertEqual([],self.w.calls)
        self.assertEqual('NO_TRADE',self.j.events[-1]['event'])
    def test_emergency_survives_restart_and_blocks_paper(self):
        self.lab.stop('EXPLICIT_OPERATOR_STOP')
        restarted=PaperLab(self.auth,self.j,self.w,clock=lambda:self.now);restarted.connect_and_reconcile()
        self.assertTrue(restarted.state['emergency'])
        with self.assertRaisesRegex(PermissionError,'EMERGENCY_STOP'):restarted.check()
    def test_readonly_reconciliation_does_not_relatch_an_explicitly_cleared_emergency(self):
        from trading_agent.paper_lab_diagnostics import record_owned_reconciliation
        record_owned_reconciliation(self.lab,{'status':'RECONCILED_WITH_EMERGENCY_RETAINED'})
        self.assertFalse(self.lab.state['emergency'])
        self.lab.stop('OWNER_STOP');record_owned_reconciliation(self.lab,{'status':'RECONCILED_WITH_EMERGENCY_RETAINED'})
        self.assertTrue(self.lab.state['emergency'])
    def test_failed_readonly_reconciliation_latches_emergency(self):
        from trading_agent.paper_lab_diagnostics import record_owned_reconciliation
        record_owned_reconciliation(self.lab,{'status':'BLOCKED','reason':'UNRECOGNIZED_ORDER'})
        self.assertTrue(self.lab.state['emergency'])
        with self.assertRaisesRegex(PermissionError,'EMERGENCY_STOP'):self.lab.check()
    def test_paper_eligible_valid_permission_still_obeys_actual_risk_veto(self):
        self.plan.update(exit_policy='RESEARCH_D_V1',paper_eligibility={'state':'PaperEligible','environment':'PAPER_TRADING',
            'live_approved':False,'registered':True,'enabled':True,'tests_passed':True,'strategy_version':'synthetic-v1',
            'strategy_id':self.plan['strategy_id']})
        self.plan['execution_requirements']['execution']['costsReliable']=False
        result=self.lab.strategy_proposal(continuous.ContinuousPaperTests.proposal(self),self.w.quote())
        self.assertEqual('STRATEGY_REJECTED',result['state']);self.assertEqual([],self.w.calls)
        self.assertEqual(100,self.lab.state['strategy_account']['equity'])
    def test_one_persistent_permission_runs_multiple_simulated_trades_and_retains_loss_stop(self):
        self.plan.update(exit_policy='RESEARCH_D_V1',paper_eligibility={'state':'PaperEligible','environment':'PAPER_TRADING',
            'live_approved':False,'registered':True,'enabled':True,'tests_passed':True,'strategy_version':'synthetic-v1',
            'strategy_id':self.plan['strategy_id'],'name':'Synthetic only'})
        b=AccountBinding.from_attestation(self.a)
        self.a.update(scope='PAPER_AUTO_ONLY',execution_mode='PaperAuto',status='Granted',account_binding_id=b.binding_id,
            granted_by='synthetic',selected_strategy=self.plan['strategy_id'],strategy_version='synthetic-v1',source_hashes={'fixture':'synthetic'})
        report={'preferred':self.plan['strategy_id'],'strategies':[self.plan['paper_eligibility']],'source_hashes':self.a['source_hashes']}
        self.auth=PaperAutoAuthorization(lambda:copy.deepcopy(self.a),lambda:b,lambda:report,
            lambda:{'tws_pid':2,'tws_start_filetime':'2','calendar':self.plan['calendar']},
            clock=lambda:self.now,session_alive=lambda *args:True)
        self.lab=PaperLab(self.auth,self.j,self.w,clock=lambda:self.now);self.lab.connect_and_reconcile()
        for net in (2,1,-1):
            o=self.lab.strategy_proposal(continuous.ContinuousPaperTests.proposal(self),self.w.quote())
            self.assertNotEqual('STRATEGY_REJECTED',o['state']);continuous.ContinuousPaperTests.close(self,o,net)
        self.assertEqual(3,len(self.w.calls));self.assertEqual(1,len(self.lab.state['sessions']))
        self.assertEqual('DAILY_FIRST_LOSS_STOP',strategy_cycle(self.lab,self.plan,{},self.w.quote())['reason'])
        self.assertEqual('VALID',permission_status(self.a,b,self.now))
    def test_explicit_stop_exits_flat_runner_without_order_or_emergency_clear(self):
        root=Path(__file__).resolve().parents[2]/'.local/paper-auto-tests'/uuid.uuid4().hex;root.mkdir(parents=True)
        try:
            stop=root/'paper-lab.emergency';stop.write_text('synthetic');(root/'paper-auto.stop').write_text('synthetic')
            self.lab.stop_file=stop;self.lab.auth.paper_auto=True
            continuous_strategy(self.lab,self.a,max_cycles=1,sleep=lambda _:None)
            self.assertEqual([],self.w.calls);self.assertTrue(stop.exists());self.assertTrue(self.lab.state['emergency'])
            self.assertEqual('PAPER_AUTO_OPERATOR_STOPPED',self.j.events[-1]['event'])
        finally:
            stop.unlink(missing_ok=True);(root/'paper-auto.stop').unlink(missing_ok=True);root.rmdir()

if __name__=='__main__':unittest.main()
