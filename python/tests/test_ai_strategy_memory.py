import copy
import json
from pathlib import Path
import tempfile
import unittest
from trading_agent.ai_strategy_researcher.memory import (load_readonly,persist,compact,validate_plan,record,build)
from trading_agent.ai_strategy_researcher.contracts import candidate_version,digest,parse_proposal,encoded
from trading_agent.ai_strategy_researcher.data import FOLDER,context
from trading_agent.ai_strategy_researcher.journal import Journal
from trading_agent.ai_strategy_researcher.providers import request_body
from trading_agent.ai_strategy_researcher.runner import run
from ai_research_fixtures import fixture,proposal,result,config,add_plan


class AIStrategyMemoryTests(unittest.TestCase):
    def setup_history(self,root):
        package,sha=fixture(root);j=Journal(root)
        j.bind('prior',dict(config=config(),dataset_sha256=sha,provider='openai',tool_sha256='old'))
        p=proposal();key=digest(p['candidate']);j.reserve_experiment('prior',key,candidate_version(p['candidate']),p)
        r=result();r['results']['TIERED_BASE']['validation']['metrics'].update(net_expectancy=-1,net_pnl=-10)
        r['rejection_reasons']=['NET_ECONOMICS_INSUFFICIENT','INSUFFICIENT_SAMPLE']
        j.finish_experiment(key,r);j.close()
        return package,load_readonly(Path(root).resolve(),package)

    def test_readonly_memory_preserves_journal_and_links_hypothesis_results(self):
        with tempfile.TemporaryDirectory() as d:
            package,s=self.setup_history(d);p=Path(d,FOLDER,'journal.sqlite3');before=p.read_bytes()
            again=load_readonly(Path(d),package);self.assertEqual(before,p.read_bytes());self.assertEqual(s,again)
            e=s['entries'][0];self.assertEqual(proposal()['hypothesis'],e['hypothesis'])
            self.assertEqual(-10,e['metrics']['net_pnl']);self.assertIn('INSUFFICIENT_SAMPLE',e['reasons'])
            self.assertEqual('OBSERVED_NET_OBJECTIVE_FAILED',e['conclusion'])
            self.assertEqual('SIMULATED',e['evidence_status']['performance']);self.assertEqual('ESTIMATED',e['evidence_status']['costs'])
            self.assertEqual('UNKNOWN',e['evidence_status']['execution']);self.assertFalse(e['fresh_out_of_sample'])

    def test_snapshot_is_append_only_idempotent_and_tamper_fails(self):
        with tempfile.TemporaryDirectory() as d:
            _,s=self.setup_history(d);sha=persist(d,s);self.assertEqual(sha,persist(d,s))
            path=Path(d,FOLDER,'memory',sha+'.json');path.write_text('{}')
            with self.assertRaisesRegex(ValueError,'TAMPERED'):persist(d,s)

    def test_modified_result_without_matching_event_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            package,_=self.setup_history(d);j=Journal(d)
            j.db.execute("UPDATE experiments SET result='{}'");j.close()
            with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'):load_readonly(Path(d),package)

    def test_modified_event_chain_cannot_be_used_as_memory(self):
        with tempfile.TemporaryDirectory() as d:
            package,_=self.setup_history(d);j=Journal(d);j.db.execute("UPDATE events SET hash='bad' WHERE sequence=1");j.close()
            with self.assertRaisesRegex(ValueError,'TAMPERED'):load_readonly(Path(d),package)

    def test_proposal_specification_cannot_change_behind_its_result_and_version(self):
        with tempfile.TemporaryDirectory() as d:
            package,_=self.setup_history(d);j=Journal(d);p=proposal();p['candidate']['target_r']=2
            j.db.execute('UPDATE experiments SET proposal=?',(json.dumps(p),));j.close()
            with self.assertRaisesRegex(ValueError,'SPECIFICATION_MISMATCH'):load_readonly(Path(d),package)

    def test_unknown_legacy_proposal_rejection_does_not_invent_failed_field(self):
        with tempfile.TemporaryDirectory() as d:
            package,_=self.setup_history(d);j=Journal(d)
            j.event('prior','PROPOSAL_REJECTED',dict(reason='UNTRUSTED_PROPOSAL_INVALID'));j.close()
            s=load_readonly(Path(d),package);r=s['proposal_rejections'][0]
            self.assertEqual('UNKNOWN_LEGACY_GENERIC_REJECTION',r['code']);self.assertIsNone(r['field'])
            self.assertEqual(1,compact(s)['contract_rejection_counts']['UNKNOWN_LEGACY_GENERIC_REJECTION'])

    def test_pending_record_keeps_unknown_cost_and_blocks_same_family(self):
        with tempfile.TemporaryDirectory() as d:
            package,sha=fixture(d);j=Journal(d);j.bind('prior',dict(config=config(),dataset_sha256=sha,provider='simulated',tool_sha256='old'))
            p=proposal();j.reserve_experiment('prior','p',candidate_version(p['candidate']),p);j.close()
            s=load_readonly(Path(d),package);ctx=context(package,[],compact(s));p=proposal(ctx)
            with self.assertRaisesRegex(ValueError,'NOT_DEFINITIVE'):validate_plan(p,s)
            self.assertEqual('UNKNOWN',s['entries'][0]['cost_version'])

    def test_exact_behavior_rejected_across_sessions_tools_and_renames(self):
        with tempfile.TemporaryDirectory() as d:
            package,s=self.setup_history(d);ctx=context(package,[],compact(s));p=proposal(ctx)
            p['candidate']['name']='Another_Name'
            with self.assertRaisesRegex(ValueError,'ALREADY_RESEARCHED'):validate_plan(p,s)

    def test_risk_only_change_is_materially_equivalent(self):
        with tempfile.TemporaryDirectory() as d:
            package,s=self.setup_history(d);p=proposal();p['candidate']['risk_percent']=10;add_plan(p,context(package,[],compact(s)))
            with self.assertRaisesRegex(ValueError,'MATERIALLY_EQUIVALENT'):validate_plan(p,s)

    def test_small_parameter_nudge_is_rejected_even_with_new_hypothesis_text(self):
        with tempfile.TemporaryDirectory() as d:
            package,s=self.setup_history(d);p=proposal();p['candidate']['lookback']=49;add_plan(p,context(package,[],compact(s)))
            p['research_plan']['novelty']='A wholly different descriptive narrative cannot change fixed behavior.'
            with self.assertRaisesRegex(ValueError,'PARAMETER_NUDGE'):validate_plan(p,s)

    def test_material_change_requires_exact_fields_and_nearest_reference(self):
        with tempfile.TemporaryDirectory() as d:
            package,s=self.setup_history(d);p=proposal();p['candidate']['target_r']=1.5;add_plan(p,context(package,[],compact(s)))
            self.assertEqual(['target_r'],validate_plan(p,s)['changed_fields'])
            p['research_plan']['changed_fields']=[]
            with self.assertRaisesRegex(ValueError,'MATERIAL_CHANGE_REFERENCE'):validate_plan(p,s)

    def test_new_supported_family_requires_history_reference_but_no_fabricated_changes(self):
        with tempfile.TemporaryDirectory() as d:
            package,s=self.setup_history(d);p=proposal();p['candidate']['symbol']='SPY';add_plan(p,context(package,[],compact(s)))
            self.assertEqual('NEW_EXECUTABLE_FAMILY',validate_plan(p,s)['classification'])
            p['research_plan']['prior_evidence_ids']=[]
            with self.assertRaisesRegex(ValueError,'PRIOR_RESEARCH_REFERENCE'):validate_plan(p,s)

    def test_schema_requires_plan_and_nullable_candidate_with_defer(self):
        with tempfile.TemporaryDirectory() as d:
            package,s=self.setup_history(d);ctx=context(package,[],compact(s));b=request_body(ctx,config());schema=b['text']['format']['schema']
            self.assertIn('research_plan',schema['required']);self.assertIn('anyOf',schema['properties']['candidate'])
            self.assertEqual(ctx['evidence_ids'],schema['properties']['research_plan']['properties']['prior_evidence_ids']['items']['enum'])
            self.assertIn('UNKNOWN',b['instructions']);self.assertIn('DEFER_RESEARCH',b['instructions'])

    def test_missing_plan_is_rejected_after_legacy_contract_remains_readable(self):
        p=proposal();parse_proposal(json.dumps(p),p['evidence_ids'])
        with self.assertRaisesRegex(ValueError,'RESEARCH_PLAN_REQUIRED'):validate_plan(p,dict(entries=[]))

    def test_plan_secret_or_invented_reference_is_rejected_without_logging_value(self):
        p=proposal(dict(research_memory=dict(records=[])));p['research_plan']['novelty']='Bearer do-not-log-this'
        with self.assertRaisesRegex(ValueError,'SENSITIVE_OUTPUT'):parse_proposal(json.dumps(p),p['evidence_ids'])
        p=proposal(dict(research_memory=dict(records=[])));p['research_plan']['prior_evidence_ids']=['invented']
        with self.assertRaisesRegex(ValueError,'REFERENCES'):parse_proposal(json.dumps(p),p['evidence_ids'])

    def test_defer_stops_after_one_simulated_reply_without_any_backtest(self):
        def defer(ctx,iteration):
            p=proposal(ctx);p['candidate']=None;p['research_plan'].update(action='DEFER_RESEARCH',changed_fields=[])
            return dict(usage=dict(input_tokens=0,output_tokens=0),proposal_text=json.dumps(p),error=None,metadata={})
        with tempfile.TemporaryDirectory() as d:
            fixture(d);r=run(d,'next',provider_fn=defer,tool_fn=lambda *a:self.fail('Deferred research ran tools'))
            self.assertEqual('RESEARCH_DEFERRED_INSUFFICIENT_EVIDENCE',r['stop_reason'])
            self.assertEqual(1,r['consumption']['provider_calls']);self.assertEqual(0,r['consumption']['backtests_reserved'])
            self.assertEqual(0,r['orders_sent']);self.assertFalse(r['paper_auto_granted'])
            package,_=fixture_read(d)
            s=load_readonly(Path(d),package);self.assertEqual(1,len(s['deferred_decisions']))
            self.assertEqual('next',compact(s)['deferred_decisions'][0]['session'])

    def test_each_new_iteration_receives_persisted_previous_conclusion(self):
        seen=[]
        def response(ctx,iteration):
            seen.append(ctx);p=proposal();p['candidate']['stop_atr']=1+.5*iteration;add_plan(p,ctx)
            return dict(usage=dict(input_tokens=0,output_tokens=0),proposal_text=json.dumps(p),error=None,metadata={})
        with tempfile.TemporaryDirectory() as d:
            fixture(d);r=run(d,'next',provider_fn=response,tool_fn=lambda root,kind,payload,timeout:result(payload['candidate']))
            self.assertEqual([0,1,2],[c['research_memory']['total_records'] for c in seen])
            self.assertIn('prior_refutation_test',seen[1]['research_memory']['records'][0])
            j=Journal(d)
            self.assertEqual(3,j.db.execute("SELECT COUNT(*) FROM events WHERE kind='RESEARCH_CONCLUSION_RECORDED'").fetchone()[0])
            self.assertEqual(3,j.db.execute("SELECT COUNT(*) FROM events WHERE kind='RESEARCH_MEMORY_CONSULTED'").fetchone()[0]);j.close()
            self.assertEqual(45,r['consumption']['backtests_reserved']);self.assertEqual('0.00',r['consumption']['estimated_or_reserved_cost_usd'])

    def test_current_sources_include_both_real_sessions_and_corrected_h40(self):
        from trading_agent.ai_strategy_researcher.data import load_dataset
        p,_=load_dataset('.');s=load_readonly(Path('.').resolve(),p);m=compact(s)
        self.assertTrue({'research-openai-001','research-openai-002'}<={e['session'] for e in m['specifications']})
        audited=[e for e in s['entries'] if 'supersedes_evidence_id' in e][0]
        self.assertAlmostEqual(-2.44,audited['metrics']['net_pnl'])
        self.assertTrue(audited['pending_inventory']['TIERED_BASE']['wf1'])
        self.assertTrue(audited['pending_inventory']['TIERED_BASE']['wf2'])
        self.assertEqual('UNKNOWN',s['broker_constraints']['effective_fees'])
        self.assertLess(len(encoded(request_body(context(p,[],m),config()))),24000)

    def test_prompt_compaction_is_bounded_and_not_sorted_by_profitable_results(self):
        with tempfile.TemporaryDirectory() as d:
            _,s=self.setup_history(d);older=copy.deepcopy(s['entries'][0]);older['evidence_id']='older';older['metrics']['net_pnl']=999
            s['entries'].insert(0,older);m=compact(s)
            self.assertLessEqual(len(encoded(m)),7500);self.assertNotEqual('older',m['records'][0]['evidence_id'])

    def test_audit_without_verification_cannot_silently_fall_back_to_old_h40(self):
        from trading_agent.ai_strategy_researcher.memory import AUDIT
        with tempfile.TemporaryDirectory() as d:
            package,_=self.setup_history(d);p=Path(d,AUDIT);p.mkdir(parents=True);(p/'revalidation-final.json').write_text('{}')
            with self.assertRaises(OSError):load_readonly(Path(d),package)

    def test_legacy_pending_true_survives_without_invented_inventory_details(self):
        r=result();r['results']['TIERED_BASE']['wf1']['metrics']['pending_position']=True
        e=record('id','s',proposal(),r,'COMPLETED','openai')
        self.assertEqual([],e['pending_inventory']['TIERED_BASE']['wf1'])
        self.assertEqual('LEGACY_NOT_RECORDED',e['pending_detail_status'])

    def test_memory_cannot_describe_small_order_minimum_as_guaranteed_effective_fee(self):
        from trading_agent.ai_strategy_researcher.costs import commission_details
        c=commission_details(1,10,'TIERED_BASE','BUY')
        self.assertEqual(.1,float(c['components']['base_commission']))
        self.assertEqual('UNKNOWN',c['effective_account_fees'])

    def test_original_003_defer_plan_is_hash_linked_and_present_in_next_context(self):
        from trading_agent.ai_strategy_researcher.data import load_dataset
        package,_=load_dataset('.');s=load_readonly(Path('.').resolve(),package);m=compact(s)
        defer=next(d for d in s['deferred_decisions'] if d['session']=='research-openai-003')
        self.assertEqual('DEFER_RESEARCH',defer['research_plan']['action'])
        self.assertIn(defer['evidence_id'],context(package,[],m)['evidence_ids'])
        self.assertIn('research-openai-003',{d['session'] for d in m['deferred_decisions']})
        self.assertEqual(7,len(m['specifications']));self.assertEqual(7,len({e['spec'].__repr__() for e in m['specifications']}))

    def test_defer_snapshot_tamper_is_not_silently_ignored(self):
        def defer(ctx,iteration):
            p=proposal(ctx);p['candidate']=None;p['research_plan'].update(action='DEFER_RESEARCH',changed_fields=[])
            return dict(usage=dict(input_tokens=0,output_tokens=0),proposal_text=json.dumps(p),error=None,metadata={})
        with tempfile.TemporaryDirectory() as d:
            package,_=fixture(d);run(d,'next',provider_fn=defer)
            s=load_readonly(Path(d),package);path=Path(d,FOLDER,'memory',s['deferred_decisions'][0]['memory_sha256']+'.json');path.write_text('{}')
            with self.assertRaisesRegex(ValueError,'DEFER_MEMORY_INTEGRITY'):load_readonly(Path(d),package)

    def test_readonly_study_evidence_is_citable_and_preserved_in_defer_snapshot(self):
        from unittest.mock import patch
        study=dict(study='s',spec_sha256='b'*64,chain_head='c'*64,decision='EVIDENCE_READY_FOR_RESEARCH',research_summary=dict(slippage='UNKNOWN'))
        def worker(root,kind,payload,timeout):
            self.assertEqual('provider',kind);ctx=json.loads(payload['body']['input']);p=proposal(ctx)
            proof=ctx['new_readonly_evidence'][0]['evidence_id'];self.assertIn(proof,ctx['evidence_ids'])
            p['candidate']=None;p['research_plan'].update(action='DEFER_RESEARCH',changed_fields=[],prior_evidence_ids=[proof])
            return dict(usage=dict(input_tokens=0,output_tokens=0),proposal_text=json.dumps(p),error=None,metadata={})
        with tempfile.TemporaryDirectory() as d:
            package,_=fixture(d)
            with patch('trading_agent.paper_evidence_observer.research_preflight',return_value=dict(decision='EVIDENCE_READY_FOR_RESEARCH',ready_studies=[study])),patch('trading_agent.ai_strategy_researcher.runner.worker_environment'):
                run(d,'next',provider='openai',tool_fn=worker)
            s=load_readonly(Path(d),package);self.assertEqual(['paper_observation_'+'c'*20],s['deferred_decisions'][0]['research_plan']['prior_evidence_ids'])


def fixture_read(root):
    from trading_agent.ai_strategy_researcher.data import load_dataset
    return load_dataset(root)
