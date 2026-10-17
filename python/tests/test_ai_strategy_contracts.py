import copy
from decimal import Decimal
from datetime import date,timedelta
import json
import unittest
from trading_agent.ai_strategy_researcher.contracts import validate_proposal,strict_json,candidate_version,parse_proposal,ProposalValidationError
from trading_agent.ai_strategy_researcher.configuration import validate_config,estimated_cost
from ai_research_fixtures import proposal,config


class AIStrategyContractsTests(unittest.TestCase):
    def test_parameter_rejections_identify_exact_field_without_values(self):
        cases=[('fast',2,'INTEGER_OUT_OF_RANGE'),('slow',101,'INTEGER_OUT_OF_RANGE'),
            ('lookback',101,'INTEGER_OUT_OF_RANGE'),('atr_period',31,'INTEGER_OUT_OF_RANGE'),
            ('max_hold_bars',41,'INTEGER_OUT_OF_RANGE'),('target_r',6,'RESEARCH_PARAMETER_RANGE'),
            ('stop_atr',.1,'RESEARCH_PARAMETER_RANGE'),('risk_percent',4,'REGISTERED_RISK_GRID_REQUIRED'),
            ('fast',24,'CAUSAL_WINDOWS_REQUIRED'),('risk_percent','2','NUMBER_REQUIRED'),
            ('fast',8.0,'INTEGER_OUT_OF_RANGE')]
        for field,value,code in cases:
            with self.subTest(field=field,value=value):
                p=proposal();p['candidate'][field]=value
                with self.assertRaises(ProposalValidationError) as caught:parse_proposal(json.dumps(p),p['evidence_ids'])
                self.assertEqual(dict(validation_code=code,field='$.candidate.'+field,category='PARAMETER'),caught.exception.diagnostic())

    def test_format_rejections_are_separate_from_parameters_and_evidence(self):
        for raw,code in (('{','JSON_SYNTAX_INVALID'),('{"x":1,"x":2}','DUPLICATE_JSON_KEY'),
                         ('{"x":NaN}','NONFINITE_JSON'),('{}','UNEXPECTED_FIELDS')):
            with self.subTest(code=code):
                with self.assertRaises(ProposalValidationError) as caught:parse_proposal(raw,['authentic_development_prices'])
                self.assertEqual(('FORMAT','$',code),(caught.exception.category,caught.exception.field,caught.exception.code))
        p=proposal();p['evidence_ids']=['invented']
        with self.assertRaises(ProposalValidationError) as caught:parse_proposal(json.dumps(p),['authentic_development_prices'])
        self.assertEqual(('EVIDENCE','$.evidence_ids'),(caught.exception.category,caught.exception.field))

    def test_all_registered_risks_and_boundary_candidates_remain_valid(self):
        for risk in (1,2,3,5,7.5,10,12.5,15):
            p=proposal();p['candidate'].update(fast=3,slow=5,lookback=10,atr_period=5,max_hold_bars=2,stop_atr=.5,target_r=5,risk_percent=risk)
            self.assertEqual(p,parse_proposal(json.dumps(p),p['evidence_ids']))
        p['candidate'].update(fast=40,slow=100,lookback=100,atr_period=30,max_hold_bars=40,stop_atr=4,target_r=.5)
        self.assertEqual(p,parse_proposal(json.dumps(p),p['evidence_ids']))

    def test_sensitive_output_diagnostic_cannot_include_rejected_content(self):
        p=proposal();p['rationale']='Bearer never-store-this-placeholder'
        with self.assertRaises(ProposalValidationError) as caught:parse_proposal(json.dumps(p),p['evidence_ids'])
        self.assertEqual('SENSITIVE_OUTPUT_REJECTED',caught.exception.code)
        self.assertEqual('$.rationale',caught.exception.field)
        self.assertNotIn('placeholder',json.dumps(caught.exception.diagnostic()))

    def test_malformed_unicode_and_missing_response_fail_with_fixed_codes(self):
        for raw in (None,'\ud800'):
            with self.assertRaisesRegex(ProposalValidationError,'PROPOSAL_TEXT_INVALID'):parse_proposal(raw,[])
        p=proposal();p['hypothesis']='\ud800'
        with self.assertRaisesRegex(ProposalValidationError,'TEXT_OUT_OF_RANGE'):parse_proposal(json.dumps(p),p['evidence_ids'])

    def test_valid_declarative_candidate_has_reproducible_version(self):
        p=proposal();self.assertEqual(p,validate_proposal(p,['authentic_development_prices']))
        self.assertEqual(candidate_version(p['candidate']),candidate_version(copy.deepcopy(p['candidate'])))

    def test_rename_cannot_create_another_behavior_or_evade_deduplication(self):
        a=proposal()['candidate'];b={**a,'name':'Another_Name'}
        self.assertEqual(candidate_version(a),candidate_version(b))
        b['stop_atr']=2;self.assertNotEqual(candidate_version(a),candidate_version(b))

    def test_extra_execution_code_authorization_and_risk_fields_are_rejected(self):
        for field in ('code','order','AccountBinding','EmergencyStop','PaperAuto','live_approved','exposure'):
            p=proposal();p['candidate'][field]='execute'
            with self.assertRaises(ValueError):validate_proposal(p,['authentic_development_prices'])

    def test_unregistered_evidence_and_quarantined_or_live_symbols_rejected(self):
        p=proposal();p['evidence_ids']=['invented']
        with self.assertRaises(ValueError):validate_proposal(p,['authentic_development_prices'])
        for symbol in ('SCHX','EURUSD','../../.local'):
            p=proposal();p['candidate']['symbol']=symbol
            with self.assertRaises(ValueError):validate_proposal(p,['authentic_development_prices'])

    def test_fractional_windows_nonfinite_risk_and_outside_grid_rejected(self):
        for field,value in [('fast',True),('fast',8.5),('slow',3),('risk_percent',16),('risk_percent',4),
            ('risk_percent',float('nan')),('stop_atr',0),('max_hold_bars',1000)]:
            p=proposal();p['candidate'][field]=value
            with self.assertRaises(ValueError):validate_proposal(p,['authentic_development_prices'])

    def test_traversal_identifier_and_secret_echo_cannot_be_stored(self):
        for field,value in [('name','../Risk'),('hypothesis',("sk" + "-" + "FAKE_UNIT_TEST_TOKEN_NOT_A_SECRET_1234567890")),('rationale','DU1234567')]:
            p=proposal()
            if field=='name':p['candidate'][field]=value
            else:p[field]=value
            with self.assertRaises(ValueError):validate_proposal(p,['authentic_development_prices'])

    def test_json_duplicate_keys_and_nonfinite_literals_fail_closed(self):
        for raw in ('{"x":1,"x":2}','{"x":NaN}','{"x":Infinity}'):
            with self.assertRaises(ValueError):strict_json(raw)

    def test_configuration_cannot_contain_secret_endpoint_or_broker_fields(self):
        for field in ('api_key','base_url','ibkr_password','capital','risk_policy'):
            c=config();c[field]='untrusted'
            with self.assertRaises(ValueError):validate_config(c)

    def test_resource_budgets_are_finite_bounded_and_strictly_typed(self):
        for field,value in [('max_seconds',100000),('max_provider_calls',0),('max_total_tokens',True),
            ('max_cost_usd','NaN'),('max_cost_usd','0'),('max_candidates',31)]:
            c=config();c[field]=value
            with self.assertRaises(ValueError):validate_config(c)

    def test_online_prices_must_be_reverified_but_offline_mode_needs_no_api(self):
        c=config();c['pricing']['verified_on']=(date.today()-timedelta(days=31)).isoformat()
        self.assertEqual(c,validate_config(c,False))
        with self.assertRaisesRegex(ValueError,'REVERIFY'):validate_config(c,True)
        c['pricing']['verified_on']=date.today().isoformat();validate_config(c,True)
        self.assertEqual(Decimal('.02'),estimated_cost(c,1000,1000))

    def test_changing_model_requires_an_explicit_matching_price_configuration(self):
        c=config();c['model']='different-model'
        with self.assertRaisesRegex(ValueError,'MODEL_PRICE_BINDING'):validate_config(c)
