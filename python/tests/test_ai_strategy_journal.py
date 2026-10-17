import json
import tempfile
import unittest
from trading_agent.ai_strategy_researcher.journal import Journal,exclusive,session_name
from ai_research_fixtures import binding,proposal,result


class AIStrategyJournalTests(unittest.TestCase):
    def test_confirmed_usage_releases_reservations_without_claiming_invoice_cost(self):
        from decimal import Decimal
        with tempfile.TemporaryDirectory() as d:
            j=Journal(d);j.bind('s',binding());reserved=Decimal(0)
            for i,o,bound in ((4927,934,18480),(4950,1013,18540),(4950,1049,18540)):
                call=j.reserve_call('s','openai','hash',bound,2048)
                reserved+=Decimal(json.loads(j.status('s')['calls'][-1]['reservation'])['estimated_cost'])
                j.finish_call(call,dict(input_tokens=i,output_tokens=o),0)
            s=j.status('s');self.assertEqual('0.119075',s['estimated_or_reserved_cost_usd'])
            self.assertEqual(Decimal('.369960'),reserved);self.assertEqual((14827,2996),(s['input_tokens'],s['output_tokens']))
            self.assertTrue(all(c['usage_status']=='API_USAGE_CONFIGURED_PRICE_CEILINGS' for c in s['calls']));j.close()

    def test_failure_streak_survives_reopen_and_accepted_proposal_resets_it(self):
        with tempfile.TemporaryDirectory() as d:
            j=Journal(d);j.bind('s',binding())
            j.event('s','PROVIDER_FINALIZED',{'error':'OPENAI_HTTP_429'})
            j.event('s','PROPOSAL_REJECTED',dict(validation_code='CAUSAL_WINDOWS_REQUIRED',field='$.candidate.fast',category='PARAMETER'));j.close()
            j=Journal(d);state=j.failure_state('s');self.assertEqual(2,state['count']);self.assertEqual('$.candidate.fast',state['feedback']['field'])
            j.event('s','PROPOSAL_ACCEPTED',{});self.assertEqual(0,j.failure_state('s')['count']);self.assertIsNone(j.failure_state('s')['feedback']);j.close()

    def test_budget_reservations_survive_unknown_call_and_restart_without_replay(self):
        with tempfile.TemporaryDirectory() as d:
            j=Journal(d);j.bind('session',binding());j.reserve_call('session','openai','hash',1000,1000);j.close()
            j=Journal(d);s=j.bind('session',binding());self.assertEqual('SUSPENDED',s['state'])
            self.assertEqual('0.02',s['estimated_or_reserved_cost_usd']);self.assertEqual(1,s['provider_calls'])
            self.assertEqual('RECOVERED_UNKNOWN_USAGE',s['calls'][0]['state'])
            with self.assertRaises(ValueError):j.reserve_call('session','openai','hash',1000,1000)
            j.close()

    def test_token_cost_and_request_count_are_checked_before_external_call(self):
        with tempfile.TemporaryDirectory() as d:
            j=Journal(d);j.bind('s',binding())
            with self.assertRaisesRegex(ValueError,'TOKEN'):j.reserve_call('s','openai','a',120000,2048)
            with self.assertRaisesRegex(ValueError,'COST'):j.reserve_call('s','openai','a',0,100000)
            self.assertEqual(0,j.status('s')['provider_calls'])
            for _ in range(3):
                call=j.reserve_call('s','openai','a',100,100);j.finish_call(call,dict(input_tokens=10,output_tokens=10),.1)
            with self.assertRaisesRegex(ValueError,'CALL_BUDGET'):j.reserve_call('s','openai','a',100,100)
            j.close()

    def test_usage_is_finalized_once_and_actual_usage_excess_suspends(self):
        with tempfile.TemporaryDirectory() as d:
            j=Journal(d);j.bind('s',binding());call=j.reserve_call('s','openai','a',100,100)
            self.assertTrue(j.finish_call(call,dict(input_tokens=101,output_tokens=20),.1))
            self.assertEqual('SUSPENDED',j.status('s')['state'])
            with self.assertRaisesRegex(ValueError,'ALREADY_FINALIZED'):j.finish_call(call,dict(input_tokens=1,output_tokens=1),.1)
            j.close()

    def test_resume_cannot_change_provider_price_time_budget_or_dataset(self):
        with tempfile.TemporaryDirectory() as d:
            j=Journal(d);j.bind('s',binding());changed=binding();changed['config']['max_cost_usd']='2'
            with self.assertRaisesRegex(ValueError,'CHANGED'):j.bind('s',changed)
            changed=binding();changed['dataset_sha256']='other'
            with self.assertRaises(ValueError):j.bind('s',changed)
            j.close()

    def test_elapsed_time_does_not_restart_with_the_service(self):
        with tempfile.TemporaryDirectory() as d:
            j=Journal(d);j.bind('s',binding());j.db.execute("UPDATE sessions SET started_at='2020-01-01T00:00:00+00:00'")
            self.assertEqual(0,j.remaining_seconds('s'))
            with self.assertRaisesRegex(ValueError,'EXPIRED'):j.reserve_call('s','openai','a',100,100)
            j.close()

    def test_backtests_and_candidates_reserved_before_run_and_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            j=Journal(d);j.bind('s',binding());j.reserve_experiment('s','key','version',proposal())
            self.assertEqual(15,j.status('s')['backtests_reserved']);j.finish_experiment('key',result())
            with self.assertRaisesRegex(ValueError,'ALREADY'):j.finish_experiment('key',result())
            with self.assertRaisesRegex(ValueError,'ALREADY'):j.reserve_experiment('s','key','version',proposal())
            j.close()

    def test_crash_during_simulation_preserves_uncertain_experiment_and_suspends(self):
        with tempfile.TemporaryDirectory() as d:
            j=Journal(d);j.bind('s',binding());j.reserve_experiment('s','key','version',proposal());j.close()
            j=Journal(d);s=j.bind('s',binding());self.assertEqual('SUSPENDED',s['state'])
            self.assertEqual(15,s['backtests_reserved']);self.assertIsNone(s['experiments'][0]['result']);j.close()

    def test_global_experiment_family_counts_prior_sessions(self):
        with tempfile.TemporaryDirectory() as d:
            j=Journal(d);j.bind('s',binding());before=j.family_size();j.reserve_experiment('s','key','version',proposal())
            self.assertGreater(j.family_size(),before);j.close()
            j=Journal(d);self.assertGreater(j.family_size(),192);j.close()

    def test_full_backtest_budget_blocks_next_experiment_before_computation(self):
        with tempfile.TemporaryDirectory() as d:
            b=binding();b['config']['max_backtests']=15
            j=Journal(d);j.bind('s',b);j.reserve_experiment('s','one','v',proposal());j.finish_experiment('one',result())
            with self.assertRaisesRegex(ValueError,'EXPERIMENT_BUDGET'):j.reserve_experiment('s','two','v2',proposal())
            self.assertEqual(15,j.status('s')['backtests_reserved']);j.close()

    def test_event_chain_detects_mutation_without_logging_secrets(self):
        with tempfile.TemporaryDirectory() as d:
            j=Journal(d);j.bind('s',binding());j.db.execute("UPDATE events SET payload='{}'");j.close()
            with self.assertRaisesRegex(ValueError,'TAMPERED'):Journal(d)

    def test_second_process_lock_and_path_traversal_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with exclusive(d):
                with self.assertRaisesRegex(RuntimeError,'ALREADY_RUNNING'):
                    with exclusive(d):pass
        for name in ('../.local','a/b','a b',''):
            with self.assertRaises(ValueError):session_name(name)
