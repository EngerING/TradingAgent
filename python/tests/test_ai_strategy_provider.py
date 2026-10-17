import copy
import json
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from trading_agent.ai_strategy_researcher.providers import request_body,parse_response,openai_response
from trading_agent.ai_strategy_researcher.tools import worker_environment,run_worker
from ai_research_fixtures import config,proposal
from trading_agent.ai_strategy_researcher.contracts import SCHEMA,INTEGER_LIMITS,NUMBER_LIMITS,RATES


class AIStrategyProviderTests(unittest.TestCase):
    def test_schema_and_prompt_expose_constraints_and_dynamic_evidence_without_mutation(self):
        b=request_body({'evidence_ids':['authentic_development_prices']},config())
        schema=b['text']['format']['schema'];c=schema['properties']['candidate']['properties']
        for k,(lo,hi) in {**INTEGER_LIMITS,**NUMBER_LIMITS}.items():
            self.assertEqual((lo,hi),(c[k]['minimum'],c[k]['maximum']))
        self.assertEqual(list(RATES),c['risk_percent']['enum'])
        self.assertEqual('^[A-Za-z][A-Za-z0-9_]{2,48}$',c['name']['pattern'])
        self.assertEqual(['authentic_development_prices'],schema['properties']['evidence_ids']['items']['enum'])
        other=request_body({'evidence_ids':['data_integrity_773']},config())
        self.assertEqual(['data_integrity_773'],other['text']['format']['schema']['properties']['evidence_ids']['items']['enum'])
        self.assertNotIn('enum',SCHEMA['properties']['evidence_ids']['items'])
        for instruction in ('fast must be strictly less than slow','integers','stop_atr','target_r','proposal_validation_feedback'):
            self.assertIn(instruction,b['instructions'])

    def test_missing_evidence_cannot_create_a_provider_request(self):
        for ctx in ({},{'evidence_ids':[]},{'evidence_ids':[None]}):
            with self.assertRaisesRegex(ValueError,'AUTHENTIC_EVIDENCE_REFERENCE_REQUIRED'):request_body(ctx,config())

    def test_cached_and_reasoning_usage_metadata_is_bounded_and_sanitized(self):
        r=self.response();r['usage']['input_tokens_details']={'cached_tokens':5,'secret':'never-log'}
        r['usage']['output_tokens_details']={'reasoning_tokens':3}
        parsed=parse_response(json.dumps(r),config()['model'])
        self.assertEqual((5,3),(parsed['metadata']['cached_input_tokens'],parsed['metadata']['reasoning_output_tokens']))
        self.assertNotIn('never-log',str(parsed))
        for invalid in (21,-1,True,'never-log'):
            r['usage']['input_tokens_details']['cached_tokens']=invalid
            self.assertNotIn('cached_input_tokens',parse_response(json.dumps(r),config()['model'])['metadata'])

    def response(self):
        return dict(id='resp_test',model=config()['model'],status='completed',usage=dict(input_tokens=20,output_tokens=10),
            output=[dict(type='message',content=[dict(type='output_text',text=json.dumps(proposal()))])])

    def test_request_uses_responses_strict_schema_no_tools_no_store_no_truncation(self):
        b=request_body({'evidence_ids':['authentic_development_prices']},config())
        self.assertFalse(b['store']);self.assertEqual('disabled',b['truncation']);self.assertNotIn('tools',b)
        self.assertTrue(b['text']['format']['strict']);self.assertEqual('json_schema',b['text']['format']['type'])

    def test_completed_structured_response_preserves_both_token_counts(self):
        r=parse_response(json.dumps(self.response()),config()['model'])
        self.assertEqual(dict(input_tokens=20,output_tokens=10),r['usage']);self.assertIsNone(r['error'])

    def test_incomplete_refusal_and_tool_requests_never_create_candidates(self):
        r=self.response();r['status']='incomplete'
        self.assertTrue(parse_response(json.dumps(r),config()['model'])['error'])
        for content in ([dict(type='refusal',refusal='No')],[dict(type='function_call',name='placeOrder')]):
            r=self.response();r['output'][0]['content']=content
            self.assertTrue(parse_response(json.dumps(r),config()['model'])['error'])
        r=self.response();r['output']=[dict(type='function_call',name='placeOrder')]
        self.assertTrue(parse_response(json.dumps(r),config()['model'])['error'])

    def test_unknown_usage_or_different_model_cannot_be_success(self):
        r=self.response();r['usage']=None
        self.assertEqual('PROVIDER_USAGE_UNKNOWN',parse_response(json.dumps(r),config()['model'])['error'])
        r=self.response();r['model']='unconfigured-model'
        self.assertEqual('UNEXPECTED_PROVIDER_MODEL',parse_response(json.dumps(r),config()['model'])['error'])

    def test_duplicate_json_is_rejected_not_silently_last_write_wins(self):
        with self.assertRaises(ValueError):parse_response('{"status":"completed","status":"incomplete"}',config()['model'])

    def test_https_host_path_and_credentials_are_fixed_no_redirect_or_raw_error_logging(self):
        requests=[]
        class Connection:
            def __init__(self,host,**kwargs):requests.append(host)
            def request(self,method,path,body,headers):requests.append((method,path));self.headers=headers
            def getresponse(self):return type('Response',(),{'status':302})()
            def close(self):requests.append('closed')
        with patch.dict(os.environ,{'OPENAI_API_KEY':'not-a-secret-test-placeholder'}):
            r=openai_response(request_body({'evidence_ids':['authentic_development_prices']},config()),1,Connection)
        self.assertEqual('OPENAI_HTTP_302',r['error']);self.assertIsNone(r['usage'])
        self.assertEqual(['api.openai.com',('POST','/v1/responses'),'closed'],requests)
        self.assertNotIn('placeholder',str(r))

    def test_network_failure_does_not_echo_key_exception_or_provider_body(self):
        class Connection:
            def __init__(self,*a,**kw):pass
            def request(self,*a,**kw):raise OSError('test-secret-should-not-leak')
            def close(self):pass
        with patch.dict(os.environ,{'OPENAI_API_KEY':'test-secret-should-not-leak'}):
            r=openai_response(request_body({'evidence_ids':['authentic_development_prices']},config()),1,Connection)
        self.assertNotIn('test-secret',str(r));self.assertIsNone(r['usage'])

    def test_worker_credentials_are_stripped_in_simulation_and_only_openai_reaches_provider(self):
        with patch.dict(os.environ,{'IBKR_PASSWORD':'test-only','OPENAI_API_KEY':'test-only','PGPASSWORD':'test-only'}):
            sim=worker_environment('.',False);api=worker_environment('.',True)
        self.assertNotIn('OPENAI_API_KEY',sim);self.assertIn('OPENAI_API_KEY',api)
        for env in (sim,api):self.assertNotIn('IBKR_PASSWORD',env);self.assertNotIn('PGPASSWORD',env)

    def test_child_timeout_is_bounded_and_does_not_retry(self):
        with patch('subprocess.run',side_effect=subprocess.TimeoutExpired('fixed-worker',1)) as child:
            with self.assertRaisesRegex(TimeoutError,'WORKER_TIMEOUT'):run_worker('.','simulation',{},.01)
            self.assertEqual(1,child.call_count)
        with self.assertRaises(ValueError):run_worker('.','placeOrder',{},1)

    def test_missing_api_key_cannot_start_a_request(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaisesRegex(ValueError,'API_KEY_REQUIRED'):openai_response(request_body({'evidence_ids':['authentic_development_prices']},config()),1)
