from copy import deepcopy
from datetime import timedelta
import unittest
from unittest.mock import Mock,patch
import test_eurusd_exploratory as fixtures
AT=fixtures.AT
from trading_agent.eurusd_exploratory import Rotator,PROFILES,sha,encoded

class SupervisedTests(unittest.TestCase):
    def setUp(self):
        fixtures.ExploratoryTests.setUp(self)
        self.r.state['protocol'].update(protocol_version=2,rotation_policy='SKIP_WITH_REASON')
        self.r.state['protocol']['costs'].update(openingCommission='2',closingCommission='2')
        self.e.update(verified_quantity='100',bounded_unfavorable_experiment_consent=True)
        self.r.append('V2_TEST_PROTOCOL')
        self.grant=dict(session_id='fresh',profile=PROFILES[1],single_use=True,max_openings=1,purpose='PAPER_EXPLORATORY_RESEARCH')
    def begin(self):
        send=Mock();d=self.r.begin(self.signal,self.quote,self.e,self.grant,False,10,send)
        return d,send
    def test_skip_r1_with_reason_not_silent(self):
        d,s=self.begin();self.assertEqual(PROFILES[1],d['profile']);self.assertTrue(d['admitted']);s.assert_called_once()
        self.assertEqual('COMMISSION_EXCEEDS_RISK_BUDGET',self.r.state['skips'][0]['reason'])
        self.assertEqual('BROKER_INELIGIBLE',self.r.state['profiles'][PROFILES[0]]['eligibility'])
    def test_all_profiles_receive_sizing_same_signal(self):
        self.begin();o=self.r.state['last_opportunity'];self.assertEqual(set(PROFILES),set(o['decisions']));self.assertEqual('s1',o['signal']['opportunity_id']);self.assertIn('NOT_A_FILL',o['shadow_mode'])
    def test_unknown_margin_does_not_skip_r5(self):
        self.e['margin']='UNKNOWN';d,s=self.begin();self.assertEqual(PROFILES[1],d['profile']);s.assert_not_called();self.assertEqual(1,self.r.state['rotation'])
    def test_emergency_zero_intents_and_reservations(self):
        s=Mock();d=self.r.begin(self.signal,self.quote,self.e,self.grant,True,1,s);s.assert_not_called();self.assertIsNone(self.r.state['active']);self.assertEqual('0',self.r.state['profiles'][PROFILES[1]]['reserved'])
    def test_profile_specific_grant_cannot_rotate_authority(self):
        self.grant['profile']=PROFILES[2];d,s=self.begin();s.assert_not_called();self.assertIn('PROFILE_SCOPED_SINGLE_USE_AUTHORIZATION_REQUIRED',d['reasons'])
    def test_grant_not_single_use_rejected(self):
        self.grant['single_use']=False;d,s=self.begin();s.assert_not_called();self.assertFalse(d['admitted'])
    def test_consumed_after_send_timeout_and_restart(self):
        s=Mock(side_effect=TimeoutError())
        with self.assertRaises(TimeoutError):self.r.begin(self.signal,self.quote,self.e,self.grant,False,1,s)
        restored=Rotator(self.j,lambda:self.at);self.assertEqual(1,restored.state['opening_attempts']);self.assertIsNotNone(restored.state['active']);self.assertGreater(float(restored.state['profiles'][PROFILES[1]]['reserved']),0)
        retry=Mock();restored.begin(self.signal,self.quote,self.e,self.grant,False,100,retry);retry.assert_not_called()
    def test_cli_transport_failure_does_not_claim_zero_transmissions(self):
        from trading_agent.eurusd_exploratory_runner import failure_summary
        for action in ('Run','Once','Recovery'):
            result=failure_summary(action,TimeoutError());self.assertIsNone(result['orders_sent']);self.assertTrue(result['reconciliation_required'])
    def test_cli_read_only_failure_has_zero_transmissions(self):
        from trading_agent.eurusd_exploratory_runner import failure_summary
        result=failure_summary('Inspect',TimeoutError());self.assertEqual(0,result['orders_sent']);self.assertFalse(result['reconciliation_required'])
    def test_closed_trial_requires_new_approval(self):
        self.r.state['opening_attempts']=1;self.r.append('TRIAL_ALREADY_CONSUMED');d,s=self.begin();s.assert_not_called();self.assertIn('SUPERVISED_TRIAL_CONSUMED_NEW_APPROVAL_REQUIRED',d['reasons'])
    def test_negative_target_requires_bounded_cost_consent(self):
        self.e['bounded_unfavorable_experiment_consent']=False;d,s=self.begin();s.assert_not_called();self.assertIn('NET_TARGET_NEGATIVE_EXPERIMENT_CONSENT_REQUIRED',d['reasons'])
    def test_margin_quantity_scope(self):
        self.e['verified_quantity']='1';d,s=self.begin();s.assert_not_called();self.assertIn('QUANTITY_EXCEEDS_VERIFIED_SCOPE',d['reasons'])
    def test_diagnostic_protection_trial_is_not_general_exception(self):
        self.e.update(protection='SUPERVISED_FIRST_TRIAL',recovery='VERIFIED',supervised_protection_consent=True);d,s=self.begin();s.assert_not_called();self.assertIn('PROTECTION_UNVERIFIED',d['reasons'])
    def test_diagnostic_specific_protection_trial(self):
        self.r.state['protocol']['purpose']='PAPER_EXECUTION_DIAGNOSTIC';self.r.append('DIAGNOSTIC_FIXTURE')
        self.signal.update(execution_purpose='PAPER_EXECUTION_DIAGNOSTIC',predictive_validation=False);self.grant['purpose']='PAPER_EXECUTION_DIAGNOSTIC'
        self.e.update(protection='SUPERVISED_FIRST_TRIAL',recovery='VERIFIED',supervised_protection_consent=True)
        d,s=self.begin();self.assertTrue(d['admitted'],d);self.assertFalse(self.r.state['active']['predictive_validation'])
    def test_diagnostic_recovery_unknown_blocks(self):
        self.r.state['protocol']['purpose']='PAPER_EXECUTION_DIAGNOSTIC';self.r.append('DIAGNOSTIC_FIXTURE');self.grant['purpose']='PAPER_EXECUTION_DIAGNOSTIC'
        self.signal.update(execution_purpose='PAPER_EXECUTION_DIAGNOSTIC',predictive_validation=False);self.e.update(protection='SUPERVISED_FIRST_TRIAL',recovery='UNKNOWN',supervised_protection_consent=True)
        d,s=self.begin();s.assert_not_called()
    def test_daily_stop_persisted_across_restart_and_santo_domingo_midnight(self):
        self.r.settle_profile(PROFILES[1],__import__('decimal').Decimal('-1'),AT.isoformat(),{},False);self.r.append('LOSS')
        self.r=Rotator(self.j,lambda:self.at);self.assertEqual('STOPPED_FOR_DAY',self.r.size(PROFILES[1],self.signal,self.quote)['reason'])
        self.at=AT+timedelta(days=1);self.assertNotEqual('STOPPED_FOR_DAY',self.r.size(PROFILES[1],self.signal,self.quote)['reason']);self.assertEqual('1',self.r.state['profiles'][PROFILES[1]]['consumed_loss'])
    def test_gain_does_not_restore_consumed_loss(self):
        from decimal import Decimal
        self.r.settle_profile(PROFILES[1],Decimal('-1'),AT.isoformat(),{},False);self.r.settle_profile(PROFILES[1],Decimal('2'),AT.isoformat(),{},False)
        self.assertEqual('1',self.r.state['profiles'][PROFILES[1]]['consumed_loss'])
    def test_updated_equity_risk_without_changing_fraction(self):
        self.r.state['profiles'][PROFILES[1]]['equity']='110';d=self.r.size(PROFILES[1],self.signal,self.quote);self.assertEqual('5.50',d['budget']);self.assertLessEqual(float(d['reservation']),100)
    def test_feed_does_not_label_intent_as_ack(self):
        self.begin();k=[r['kind'] for r in self.r.state['paper_feed']];self.assertIn('PAPER_INTENT_PERSISTED',k);self.assertNotIn('PAPER_ORDER_ACK',k)
    def test_broker_and_shadow_read_model_separate(self):
        from trading_agent.eurusd_exploratory_projection import overlay
        self.r.select_profile(self.signal,self.quote)
        result=dict(market=dict(quality='MISSING'),trades=[],experiments=[],openPositions=[],notifications=[])
        v=overlay(result,dict(scope='EURUSD_PAPER_EXPLORATORY',classification='EXPLORATORY_NOT_VALIDATED',live_enabled=False,state=self.r.state,cohort_id=self.j.cohort))
        self.assertEqual(0,v['rotation']['completedPaper']);self.assertEqual('NOT_AUTHORIZED',v['rotation']['authorizationStatus']);self.assertEqual('BROKER_INELIGIBLE',v['rotation']['eligibility'][PROFILES[0]]['status'])
    def test_completed_diagnostic_is_not_predictive_strategy_performance(self):
        from trading_agent.eurusd_exploratory_projection import overlay
        fixture=fixtures.ExploratoryTests();fixture.setUp()
        trial=fixture.begin();trial['purpose']='PAPER_EXECUTION_DIAGNOSTIC'
        self.assertTrue(fixture.close(trial))
        result=dict(market=dict(quality='MISSING'),trades=[],experiments=[dict(id=PROFILES[0])],openPositions=[],notifications=[])
        view=overlay(result,dict(scope='EURUSD_PAPER_EXPLORATORY',classification='EXPLORATORY_NOT_VALIDATED',live_enabled=False,state=fixture.r.state,cohort_id=fixture.j.cohort))
        metrics=view['experiments'][0]['brokerMetrics']
        self.assertEqual('SUPERVISED_INFRASTRUCTURE_DIAGNOSTIC_NOT_STRATEGY_SIGNAL',view['trades'][0]['entryReason'])
        self.assertEqual(1,metrics['diagnosticTrades']);self.assertEqual(0,metrics['researchTrades'])
        self.assertGreater(metrics['netPnl'],0)
        for key in ('winRate','expectancy','profitFactor'):self.assertIsNone(metrics[key])
    def test_forged_receipt_hash_rejected(self):
        from trading_agent.eurusd_exploratory_evidence import checked_artifact
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory(dir='artifacts') as d:
            Path(d,'receipt.json').write_text('{}')
            with self.assertRaisesRegex(PermissionError,'HASH_MISMATCH'):checked_artifact(d,dict(artifact='receipt.json',artifact_sha256='a'*64))
    def test_receipt_cannot_escape_workspace(self):
        from trading_agent.eurusd_exploratory_evidence import checked_artifact
        with self.assertRaisesRegex(PermissionError,'ARTIFACT_REQUIRED'):checked_artifact('.',dict(artifact='../outside.json',artifact_sha256='a'*64))
    def test_kronos_context_does_not_use_future_prediction(self):
        from trading_agent.eurusd_exploratory_evidence import observer_context
        with patch('trading_agent.kronos.persistence.PostgreSQLJournal') as store:
            store.return_value.read.return_value=dict(events=[dict(kind='PREDICTION',payload=dict(created_at=(AT+timedelta(seconds=1)).isoformat()))])
            value=observer_context('.',AT.isoformat());self.assertIsNone(value['calibrated_probability']);self.assertEqual('UNKNOWN',value['status'])
    def test_kronos_unavailable_does_not_fabricate_confidence(self):
        from trading_agent.eurusd_exploratory_evidence import observer_context
        with patch('trading_agent.kronos.persistence.PostgreSQLJournal',side_effect=RuntimeError()):
            self.assertIsNone(observer_context('.',AT.isoformat())['calibrated_probability'])

    def test_additional_funds_query_captures_tag_before_legacy_filter(self):
        from trading_agent.eurusd_exploratory_wire import capability_summary
        w=Mock();w.request.return_value=900;w.expected='DU_TEST';w.account_errors=[];w.request_errors={};w.connected=True
        original=w.accountSummary
        w.client.reqAccountSummary.side_effect=lambda *args:w.accountSummary(900,'DU_TEST','SettledCash','100','USD')
        result=capability_summary(w)
        self.assertEqual('COMPLETE',result['status']);self.assertEqual('SettledCash',result['rows'][0]['tag']);self.assertIs(original,w.accountSummary);w.client.cancelAccountSummary.assert_called_once_with(900)
    def test_additional_query_missing_tag_remains_empty(self):
        from trading_agent.eurusd_exploratory_wire import capability_summary
        w=Mock();w.request.return_value=900;w.expected='DU_TEST';w.account_errors=[];w.request_errors={};w.connected=True
        result=capability_summary(w);self.assertEqual([],result['rows'])

    def test_local_api_cancelled_does_not_release_reservation(self):
        self.begin();t=self.r.state['active'];t['statuses']={str(i):'ApiCancelled' for i in t['order_ids']}
        self.r.append('LOCAL_CALLBACK_FIXTURE');s,a=fixtures.ExploratoryTests.snapshot(self)
        self.r.reconcile(s,a);self.assertIsNotNone(self.r.state['active']);self.assertGreater(float(self.r.state['profiles'][PROFILES[1]]['reserved']),0)
    def test_cancel_requires_positive_broker_perm_id(self):
        from trading_agent.eurusd_exploratory_runner import Service
        self.begin();t=self.r.state['active'];oid=t['order_ids'][0];t['cancellations'].append(oid);self.r.append('CANCEL_TEST')
        svc=Service.__new__(Service);svc.r=self.r;svc.gate=Mock(return_value={});svc.wire=Mock();svc.wire.assert_mutation_allowed=Mock();svc.attempted=set();svc.certificate={'orders':[dict(order_id=oid,perm_id=0,reference=t['intent'],client_id=82,contract_id=12087792)]}
        with self.assertRaisesRegex(PermissionError,'CANCEL_BROKER_ACK'):svc.cancel_guard(oid)
        self.assertEqual(set(),svc.attempted)
