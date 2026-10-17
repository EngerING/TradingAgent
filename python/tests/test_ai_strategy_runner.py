import ast
import copy
import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from trading_agent.ai_strategy_researcher.data import load_dataset,context,write,FOLDER,safe_path
from trading_agent.ai_strategy_researcher.runner import run,ranking,tool_hash
from trading_agent.ai_strategy_researcher.journal import Journal
from trading_agent.ai_strategy_researcher.tools import run_worker
from ai_research_fixtures import fixture,proposal,result,bars,candidate,add_plan


class AIStrategyRunnerTests(unittest.TestCase):
    def test_rejections_link_calls_and_return_safe_field_feedback_without_third_call(self):
        seen=[]
        def invalid(ctx,iteration):
            seen.append(ctx);p=proposal(ctx);p['candidate']['fast']=1
            return dict(usage=dict(input_tokens=0,output_tokens=0),error=None,proposal_text=json.dumps(p),metadata={})
        with tempfile.TemporaryDirectory() as d:
            fixture(d);r=run(d,'s',provider_fn=invalid,tool_fn=lambda *a:self.fail('Invalid proposal reached tool'))
            self.assertEqual(2,len(seen));self.assertEqual('INVALID_PROPOSAL_CIRCUIT_OPEN',r['stop_reason'])
            self.assertEqual('$.candidate.fast',seen[1]['proposal_validation_feedback']['field'])
            j=Journal(d)
            events=[json.loads(x[0]) for x in j.db.execute("SELECT payload FROM events WHERE kind='PROPOSAL_REJECTED'")]
            self.assertEqual([c['id'] for c in j.status('s')['calls']],[e['call_id'] for e in events])
            self.assertTrue(all(e['validation_code']=='INTEGER_OUT_OF_RANGE' and len(e['proposal_sha256'])==64 for e in events))
            rejected=proposal(seen[0]);rejected['candidate']['fast']=1
            self.assertEqual(hashlib.sha256(json.dumps(rejected).encode()).hexdigest(),events[0]['proposal_sha256'])
            j.close()
            replay=run(d,'s',provider_fn=lambda *a:self.fail('Suspended session replayed'),tool_fn=self.tool)
            self.assertEqual(2,replay['consumption']['provider_calls'])

    def test_economic_discard_is_a_valid_proposal_then_two_invalids_open_circuit(self):
        def response(ctx,iteration):
            p=proposal(ctx)
            if iteration:p['candidate']['target_r']=6
            return dict(usage=dict(input_tokens=0,output_tokens=0),error=None,proposal_text=json.dumps(p),metadata={})
        with tempfile.TemporaryDirectory() as d:
            fixture(d);r=run(d,'s',provider_fn=response,tool_fn=self.tool)
            self.assertEqual((3,1,15),(r['consumption']['provider_calls'],r['consumption']['candidates'],r['consumption']['backtests_reserved']))
            self.assertEqual('INVALID_PROPOSAL_CIRCUIT_OPEN',r['stop_reason'])
            self.assertEqual('DISCARDED_RESEARCH_EVIDENCE',r['ranking'][0]['status'])
            j=Journal(d)
            self.assertEqual(1,j.db.execute("SELECT COUNT(*) FROM events WHERE kind='PROPOSAL_ACCEPTED'").fetchone()[0]);j.close()

    def test_valid_proposal_resets_consecutive_failures(self):
        seen=[]
        def response(ctx,iteration):
            seen.append(ctx);p=proposal(ctx)
            if iteration!=1:p['candidate']['risk_percent']=4
            return dict(usage=dict(input_tokens=0,output_tokens=0),error=None,proposal_text=json.dumps(p),metadata={})
        with tempfile.TemporaryDirectory() as d:
            fixture(d);r=run(d,'s',provider_fn=response,tool_fn=self.tool)
            self.assertEqual('BUDGET_STOP',r['session_state']);self.assertEqual(3,r['consumption']['provider_calls'])
            self.assertIn('proposal_validation_feedback',seen[1]);self.assertNotIn('proposal_validation_feedback',seen[2])

    def test_restart_between_rejection_and_stop_cannot_reset_circuit(self):
        with tempfile.TemporaryDirectory() as d:
            _,sha=fixture(d);from ai_research_fixtures import config
            j=Journal(d);j.bind('s',dict(config=config(),dataset_sha256=sha,provider='simulated',tool_sha256=tool_hash(d)))
            for _ in range(2):
                call=j.reserve_call('s','simulated','hash',0,0);j.finish_call(call,dict(input_tokens=0,output_tokens=0),0)
                j.event('s','PROPOSAL_REJECTED',dict(call_id=call,validation_code='INTEGER_OUT_OF_RANGE',field='$.candidate.fast',category='PARAMETER'))
            j.close()
            r=run(d,'s',provider_fn=lambda *a:self.fail('Circuit reset after restart'),tool_fn=self.tool)
            self.assertEqual('INVALID_PROPOSAL_CIRCUIT_OPEN',r['stop_reason']);self.assertEqual(2,r['consumption']['provider_calls'])

    def test_format_and_sensitive_rejections_never_archive_raw_reply(self):
        replies=['{"candidate":}',json.dumps({**proposal(),'rationale':'Bearer never-log-this-placeholder'})]
        def response(ctx,iteration):return dict(usage=dict(input_tokens=0,output_tokens=0),error=None,proposal_text=replies[iteration],metadata={})
        with tempfile.TemporaryDirectory() as d:
            fixture(d);run(d,'s',provider_fn=response,tool_fn=lambda *a:self.fail('Unsafe proposal executed'))
            j=Journal(d);events=[json.loads(x[0]) for x in j.db.execute("SELECT payload FROM events WHERE kind='PROPOSAL_REJECTED'")]
            self.assertEqual(['JSON_SYNTAX_INVALID','SENSITIVE_OUTPUT_REJECTED'],[e['validation_code'] for e in events])
            self.assertNotIn('never-log-this-placeholder',str(events));self.assertNotIn('never-log-this-placeholder',str(j.status('s')));j.close()

    def provider(self,ctx,iteration):
        p=proposal();p['candidate']['stop_atr']=1+.5*iteration;add_plan(p,ctx)
        return dict(usage=dict(input_tokens=0,output_tokens=0),error=None,proposal_text=json.dumps(p),metadata={})

    def tool(self,root,kind,payload,timeout):
        self.assertEqual('simulation',kind)
        self.assertLessEqual(timeout,60);self.assertTrue(all(b['closed_at']<'2024' for b in payload['rows']))
        return result(payload['candidate'])

    def test_autonomous_simulated_cycle_has_three_bounded_experiments_and_no_approval(self):
        with tempfile.TemporaryDirectory() as d:
            fixture(d);r=run(d,'s',provider_fn=self.provider,tool_fn=self.tool)
            self.assertEqual('COMPLETED',r['session_state']);self.assertEqual(3,r['consumption']['candidates'])
            self.assertEqual(45,r['consumption']['backtests_reserved']);self.assertEqual(0,r['orders_sent'])
            self.assertEqual('NO_VIABLE_STRATEGY_FOUND',r['decision']);self.assertTrue(r['final_holdout_sealed'])
            self.assertFalse(r['paper_auto_granted']);self.assertFalse(r['live_approved'])

    def test_completed_session_restart_does_not_call_provider_or_run_tools_again(self):
        with tempfile.TemporaryDirectory() as d:
            fixture(d);run(d,'s',provider_fn=self.provider,tool_fn=self.tool)
            bad=lambda *a: self.fail('Terminal session replayed')
            r=run(d,'s',provider_fn=bad,tool_fn=bad)
            self.assertEqual(3,r['consumption']['provider_calls']);self.assertEqual(45,r['consumption']['backtests_reserved'])

    def test_duplicate_behavior_is_rejected_not_backtested_under_another_name(self):
        def same(ctx,iteration):
            p=proposal(ctx);p['candidate']['name']=f'Renamed_{iteration}'
            return dict(usage=dict(input_tokens=0,output_tokens=0),error=None,proposal_text=json.dumps(p),metadata={})
        with tempfile.TemporaryDirectory() as d:
            fixture(d);r=run(d,'s',provider_fn=same,tool_fn=self.tool)
            self.assertEqual(3,r['consumption']['provider_calls']);self.assertEqual(1,r['consumption']['candidates'])
            self.assertEqual(15,r['consumption']['backtests_reserved']);self.assertEqual('SUSPENDED',r['session_state'])

    def test_invalid_proposal_circuit_consumes_calls_but_no_backtest(self):
        def invalid(ctx,iteration):return dict(usage=dict(input_tokens=0,output_tokens=0),error=None,proposal_text='{"placeOrder":true}')
        with tempfile.TemporaryDirectory() as d:
            fixture(d);r=run(d,'s',provider_fn=invalid,tool_fn=lambda *a:self.fail('Forbidden tool'))
            self.assertEqual(2,r['consumption']['provider_calls']);self.assertEqual(0,r['consumption']['backtests_reserved'])
            self.assertEqual('INVALID_PROPOSAL_CIRCUIT_OPEN',r['stop_reason'])

    def test_unavailable_provider_circuit_retains_unknown_usage_without_execution_fallback(self):
        def bad(ctx,iteration):raise TimeoutError('secret must not appear in log')
        with tempfile.TemporaryDirectory() as d:
            fixture(d);r=run(d,'s',provider_fn=bad,tool_fn=lambda *a:self.fail('Forbidden fallback'))
            self.assertEqual('PROVIDER_CIRCUIT_OPEN',r['stop_reason']);self.assertEqual(0,r['consumption']['candidates'])
            j=Journal(d);s=j.status('s');self.assertTrue(all(c['usage_status']=='UNKNOWN_CHARGED_FULL_RESERVE' for c in s['calls']))
            j.close();self.assertNotIn('secret',str(r))

    def test_simulation_timeout_preserves_pending_evidence_and_cannot_authorize(self):
        with tempfile.TemporaryDirectory() as d:
            fixture(d);r=run(d,'s',provider_fn=self.provider,tool_fn=lambda *a: (_ for _ in ()).throw(TimeoutError()))
            self.assertEqual('SUSPENDED',r['session_state']);self.assertEqual(15,r['consumption']['backtests_reserved'])
            self.assertEqual('PENDING',r['hypotheses'][0]['state']);self.assertEqual([],r['ranking'])

    def test_price_package_and_context_exclude_final_prices_secrets_and_million_balance(self):
        d,sha=load_dataset('.');ctx=context(d,[])
        self.assertTrue(all(b['closed_at']<'2024' for s in d['series'].values() for r in s.values() for b in r))
        text=json.dumps(ctx)
        for forbidden in ('AccountBinding','AvailableFunds','api_key','IBKR_PASSWORD','1000089'):
            self.assertNotIn(forbidden,text)
        self.assertNotRegex(text,r'\b(?:DU|U)\d{5,}')
        self.assertEqual('SEALED_NOT_ACCESSIBLE',ctx['final_holdout']);self.assertNotIn('SCHX',d['series'])

    def test_final_data_quarantine_scope_and_hash_corruption_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            package,_=fixture(d);package['series']['F']['60'][-1]['closed_at']='2025-01-01T00:00:00Z'
            write(d,FOLDER+'/dataset.json',package)
            with self.assertRaisesRegex(ValueError,'FINAL'):load_dataset(d)
        with tempfile.TemporaryDirectory() as d:
            package,_=fixture(d);package['series']['SCHX']=package['series']['F'];write(d,FOLDER+'/dataset.json',package)
            with self.assertRaisesRegex(ValueError,'QUARANTINE'):load_dataset(d)
        with tempfile.TemporaryDirectory() as d:
            fixture(d);Path(d,FOLDER,'dataset.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'HASH'):load_dataset(d)

    def test_source_hash_change_cannot_silently_resume_existing_data(self):
        with tempfile.TemporaryDirectory() as d:
            fixture(d);Path(d,'artifacts/research/equity-evidence/readonly.json').write_text('{"changed":true}')
            with self.assertRaisesRegex(ValueError,'SOURCE_EVIDENCE_CHANGED'):load_dataset(d)

    def test_rank_uses_expectancy_before_win_rate_and_never_marks_live_approved(self):
        a=result();a['results']['TIERED_BASE']['validation']['metrics'].update(net_expectancy=1,win_rate=.99)
        b=result();b['candidate']['name']='Better_EV';b['results']['TIERED_BASE']['validation']['metrics'].update(net_expectancy=2,win_rate=.85)
        s=dict(experiments=[dict(state='COMPLETED',result=a,version='a'),dict(state='COMPLETED',result=b,version='b')])
        rows=ranking(s);self.assertEqual('Better_EV',rows[0]['name']);self.assertFalse(rows[0]['live_approved'])

    def test_controlled_real_child_runs_deterministic_tool_not_generated_code(self):
        p=proposal();payload=dict(proposal=p,candidate=p['candidate'],evidence_ids=p['evidence_ids'],
            rows=bars(100),family_comparisons=200,limitations=['EXPLORATORY'])
        r=run_worker('.','simulation',payload,10)
        self.assertEqual('DISCARDED_RESEARCH_EVIDENCE',r['status']);self.assertFalse(r['execution_authorized'])

    def test_module_does_not_import_broker_dpapi_production_risk_or_evaluate_generated_code(self):
        forbidden={'broker','tws','paper_lab','paper_execution_wire','ibkr_session','ctypes','win32crypt','equity_strategy_research'}
        for path in Path('python/trading_agent/ai_strategy_researcher').glob('*.py'):
            tree=ast.parse(path.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node,ast.ImportFrom):self.assertFalse(set((node.module or '').split('.'))&forbidden,str(path))
                if isinstance(node,ast.Import):self.assertFalse(any(set(x.name.split('.'))&forbidden for x in node.names),str(path))
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Name):self.assertNotIn(node.func.id,('eval','exec','compile'),str(path))

    def test_worker_cannot_substitute_a_candidate_after_proposal_validation(self):
        p=proposal();different=copy.deepcopy(p['candidate']);different['risk_percent']=16
        payload=dict(proposal=p,candidate=different,evidence_ids=p['evidence_ids'],
            rows=bars(100),family_comparisons=200,limitations=[])
        with self.assertRaisesRegex(ValueError,'WORKER_FAILED'):run_worker('.','simulation',payload,10)

    def test_output_path_cannot_escape_workspace(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'WORKSPACE'):safe_path(d,'../../.local')
