"""Offline orchestration with existing Forex V2 contracts and real temp persistence."""
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from test_forex_research_economics import AT, context, plan
from trading_agent.forex_research.journal import Journal, FOLDER
from trading_agent.forex_research.runner import SimulatedDesigner, run, source_manifest


def proposal(direction='LONG'):
    return json.dumps(dict(candidate=dict(
        schema='FOREX_STRATEGY_CANDIDATE_V2', strategy_id='synthetic-eurusd-test',
        version=1, instrument='EUR/USD', timeframe='1H', direction=direction,
        risk_profile='MODERATE', hypothesis='Synthetic hypothesis for deterministic isolated tests.',
        entry_spec=dict(description='EMA20 above EMA50 on closed candles.'),
        exit_spec=dict(description='EMA20 below EMA50 on closed candles.'),
        research_capital_usd=100, execution_authority=False,
        paper_execution_eligible=False, live_enabled=False),
        rules=dict(schema='FOREX_STRATEGY_RULES_V2', direction=direction,
                   entry=dict(all=[dict(left='ema20', operator='>', right='ema50')]),
                   exit=dict(all=[dict(left='ema20', operator='<', right='ema50')]))))


class RunnerTests(unittest.TestCase):
    def run_case(self, root, *, c=None, p=None, raw=None, request_id='first', clock=lambda: AT):
        return run(root, request_id=request_id, context=context() if c is None else c,
                   plan=plan() if p is None else p, risk_profile='MODERATE',
                   designer=SimulatedDesigner(proposal() if raw is None else raw), clock=clock)

    def test_accepted_candidate_survives_restart_without_repeating_designer(self):
        with tempfile.TemporaryDirectory() as root:
            with patch.object(socket.socket, 'connect', side_effect=AssertionError('NETWORK_FORBIDDEN')):
                result = self.run_case(root)
                self.assertEqual('ACCEPTED_FOR_RESEARCH', result['state'])
                record = result['candidate']
                self.assertEqual('ECONOMIC_SCENARIO_ONLY', record['scope'])
                self.assertEqual('0', result['api_cost_usd'])
                self.assertFalse(record['execution_authority'])
                self.assertFalse(record['statistically_validated'])
                with patch.object(SimulatedDesigner, 'propose', side_effect=AssertionError('REPEATED')):
                    self.assertEqual(result, self.run_case(root))
            with Journal(root) as journal:
                self.assertEqual(2, len(journal.history()))
            self.assertEqual(['artifacts'], [p.name for p in Path(root).iterdir()])
            self.assertTrue((Path(root) / FOLDER / 'journal.sqlite3').is_file())

    def test_preflight_failure_never_reaches_designer_and_records_no_candidate(self):
        with tempfile.TemporaryDirectory() as root:
            c = context()
            c['costs']['closing_min_usd'] = None
            with patch.object(SimulatedDesigner, 'propose', side_effect=AssertionError('MUST_NOT_DESIGN')):
                result = self.run_case(root, c=c)
            self.assertEqual('PREFLIGHT_BLOCKED', result['reason'])
            self.assertIsNone(result['candidate'])
            with Journal(root) as journal:
                self.assertIsNone(journal.history()[-1]['value']['candidate'])

    def test_expiry_during_design_blocks_registration(self):
        with tempfile.TemporaryDirectory() as root:
            ticks = iter((AT, AT + timedelta(seconds=31)))
            result = self.run_case(root, clock=lambda: next(ticks))
            self.assertEqual('POSTFLIGHT_BLOCKED', result['reason'])
            self.assertIsNone(result['candidate'])

    def test_invalid_or_mismatched_output_is_a_diagnostic_only(self):
        cases = ['{"candidate":}', proposal('SHORT')]
        unsafe = json.loads(proposal())
        unsafe['candidate']['execution_authority'] = True
        cases.append(json.dumps(unsafe))
        unsafe = json.loads(proposal())
        unsafe['candidate']['hypothesis'] = 'Bearer\nnever-archive-this-placeholder-value'
        cases.append(json.dumps(unsafe))
        duplicate = proposal().replace('"version": 1', '"version": 2, "version": 1')
        cases.append(duplicate)
        for raw in cases:
            with self.subTest(raw=raw[:30]), tempfile.TemporaryDirectory() as root:
                result = self.run_case(root, raw=raw)
                self.assertEqual('PROPOSAL_INVALID', result['reason'])
                self.assertIsNone(result['candidate'])
                data = (Path(root) / FOLDER / 'journal.sqlite3').read_bytes()
                self.assertNotIn(b'never-archive-this', data)

    def test_short_scenario_and_current_equity_are_bound_to_saved_record(self):
        with tempfile.TemporaryDirectory() as root:
            c, p = context(), plan('SHORT')
            c['equity_usd'] = '120'
            before = deepcopy((c, p))
            result = self.run_case(root, c=c, p=p, raw=proposal('SHORT'))
            self.assertEqual('ACCEPTED_FOR_RESEARCH', result['state'])
            self.assertEqual('120', result['candidate']['economic_context']['equity_usd'])
            self.assertEqual(before, (c, p))
            c['equity_usd'] = '121'
            with self.assertRaisesRegex(ValueError, 'IDEMPOTENCY_CONFLICT'):
                self.run_case(root, c=c, p=p, raw=proposal('SHORT'))

    def test_proposal_cannot_change_approved_economic_scenario(self):
        with tempfile.TemporaryDirectory() as root:
            extra = json.loads(proposal())
            extra['economic_plan'] = dict(plan(), quantity_eur='100000')
            result = self.run_case(root, raw=json.dumps(extra))
            self.assertEqual('PROPOSAL_INVALID', result['reason'])

    def test_request_includes_economic_limits_and_explicit_research_exit_scope(self):
        requests = []

        def capture(designer, request):
            requests.append(request)
            return proposal()

        with tempfile.TemporaryDirectory() as root:
            with patch.object(SimulatedDesigner, 'propose', capture):
                self.run_case(root)
        economic = json.loads(requests[0]['input'][-1]['content'])
        self.assertEqual(context(), economic['economic_context'])
        self.assertEqual(plan(), economic['economic_plan'])
        self.assertIn('ECONOMIC_SCENARIO_ONLY', economic['scope'])
        self.assertFalse(requests[0]['store'])

    def test_direct_persistence_rechecks_gate_and_bundle_hash(self):
        from trading_agent.ai_strategy_researcher.strategy_designer_v2 import validate_design_proposal
        bundle = validate_design_proposal(proposal(), direction='LONG', risk_profile='MODERATE')
        inputs = dict(context=context(), plan=plan(), risk_profile='MODERATE',
                      source_manifest=source_manifest())
        with tempfile.TemporaryDirectory() as root, Journal(root) as journal:
            journal.reserve('one', inputs)
            with self.assertRaises(ValueError):
                journal.finish('one', inputs, bundle=bundle, now=AT + timedelta(seconds=31))
            broken = deepcopy(bundle)
            broken['rules']['entry']['all'][0]['operator'] = '<'
            with self.assertRaises(ValueError):
                journal.finish('one', inputs, bundle=broken, now=AT)
            self.assertEqual(1, len(journal.history()))

    def test_source_change_during_design_prevents_candidate_registration(self):
        with tempfile.TemporaryDirectory() as root:
            with patch('trading_agent.forex_research.runner.source_manifest',
                       side_effect=[{'code': 'before'}, {'code': 'after'}]):
                result = self.run_case(root)
            self.assertEqual('SOURCE_CHANGED', result['reason'])
            self.assertIsNone(result['candidate'])

    def test_saved_candidate_identifies_sources_and_rejects_changed_source_on_replay(self):
        with tempfile.TemporaryDirectory() as root:
            result = self.run_case(root)
            self.assertIn('forex_research/economics.py', result['candidate']['source_manifest'])
            with patch('trading_agent.forex_research.runner.source_manifest', return_value={}):
                with self.assertRaisesRegex(ValueError, 'IDEMPOTENCY_CONFLICT'):
                    self.run_case(root)

    def test_real_transports_are_not_an_accepted_adapter(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ValueError, 'OFFLINE_DESIGNER_REQUIRED'):
                run(root, request_id='no-network', context=context(), plan=plan(),
                    risk_profile='MODERATE', designer=lambda _: self.fail('NETWORK_ADAPTER_CALLED'))
            self.assertEqual([], list(Path(root).iterdir()))

    def test_provider_failure_is_a_safe_terminal_diagnostic_without_retry(self):
        with tempfile.TemporaryDirectory() as root:
            with patch.object(SimulatedDesigner, 'propose', side_effect=RuntimeError('never-log-provider-detail')):
                result = self.run_case(root)
            self.assertEqual('SIMULATED_PROVIDER_FAILED', result['reason'])
            self.assertNotIn('never-log-provider-detail', str(result))
            self.assertEqual(result, self.run_case(root))

    def test_designer_cannot_mutate_snapshot_through_request_reference(self):
        def mutate(designer, request):
            request['input'][-1]['content'] = '{}'
            return proposal()

        with tempfile.TemporaryDirectory() as root:
            with patch.object(SimulatedDesigner, 'propose', mutate):
                result = self.run_case(root)
            self.assertEqual(context(), result['candidate']['economic_context'])


if __name__ == '__main__':
    unittest.main()
