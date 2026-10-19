"""Failure paths preserve uncertainty, source ownership and finite resources."""
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D
from unittest.mock import patch
import unittest

from test_core_v36_binding import registered
from test_core_v37_planning import example
from trading_agent.core_v3.contracts import ContractError, Money, content_hash
from trading_agent.core_v3.strategy_v34.contracts import Timeframe
from trading_agent.core_v3.statistical_validation.contracts import Dependence, RobustnessScenario, Status
from trading_agent.core_v3.statistical_validation.coordinator import Coordinator
from trading_agent.core_v3.statistical_validation.aggregation import aggregate
from trading_agent.core_v3.statistical_validation.planning import windows


def execute(plan, rules, chunks, catalog, journal, name='validation'):
    host = Coordinator()
    req = host.prepare(name, plan, rules, chunks, catalog, journal)
    return host, req, host.run(req, plan, rules, chunks, catalog, journal)


class AdversarialValidationTests(unittest.TestCase):
    def test_closed_source_and_concurrent_entry_return_controlled_rejections(self):
        with registered(timeframe=Timeframe.H1) as (_, cmd, catalog, journal):
            plan, rules, chunks = example(cmd, catalog)
            host = Coordinator()
            req = host.prepare('closed', plan, rules, chunks, catalog, journal)
            host._lock.acquire()
            try:
                self.assertEqual(('COORDINATOR_BUSY',), host.run(req, plan, rules, chunks, catalog, journal).result.reasons)
            finally:
                host._lock.release()
            journal.db.close()
            self.assertEqual(('SOURCE_UNAVAILABLE',), host.run(req, plan, rules, chunks, catalog, journal).result.reasons)

    def test_v36_rejection_is_archived_with_unknown_metrics(self):
        with registered(timeframe=Timeframe.H1) as (_, cmd, catalog, journal):
            plan, rules, chunks = example(cmd, catalog)
            rules = replace(rules, backtest=replace(rules.backtest, max_duration_hours=1))
            _, _, artifact = execute(plan, rules, chunks, catalog, journal)
            self.assertEqual(Status.INCONCLUSIVE, artifact.result.status)
            self.assertEqual(1, len(artifact.observations))
            self.assertTrue(all(o.result.status.value == 'REJECTED' for o in artifact.observations))
            self.assertEqual((), artifact.result.groups)

    def test_delayed_evaluation_bar_remains_inconclusive_no_silent_repair(self):
        with registered(timeframe=Timeframe.H1) as (_, cmd, catalog, journal):
            plan, rules, chunks = example(cmd, catalog)
            source = chunks[0]
            bars = list(source.bars)
            bars[4] = replace(bars[4], available_at=bars[4].closed_at+timedelta(seconds=1))
            changed = replace(source, bars=tuple(bars))
            from trading_agent.core_v3.statistical_validation.planning import manifest
            chunks = (changed,)
            plan = replace(plan, manifest=manifest('dataset-1', chunks))
            _, _, artifact = execute(plan, rules, chunks, catalog, journal)
            self.assertEqual(Status.INCONCLUSIVE, artifact.result.status)
            self.assertEqual('DELAYED_BAR_UNRESOLVED', artifact.observations[0].result.reason)
            self.assertFalse(artifact.result.groups[0].coverage_complete)

    def test_interruption_records_test_access_and_retry_is_same_incomplete_result(self):
        with registered(timeframe=Timeframe.H1) as (_, cmd, catalog, journal):
            plan, rules, chunks = example(cmd, catalog)
            host = Coordinator()
            req = host.prepare('interrupted', plan, rules, chunks, catalog, journal)
            with patch('trading_agent.core_v3.statistical_validation.coordinator.observe', side_effect=KeyboardInterrupt):
                artifact = host.run(req, plan, rules, chunks, catalog, journal)
            self.assertEqual(Status.INCONCLUSIVE, artifact.result.status)
            self.assertIn('EXPERIMENT_INTERRUPTED', artifact.result.reasons)
            self.assertEqual(3, len(host.exposures))
            self.assertEqual(artifact, host.run(req, plan, rules, chunks, catalog, journal))

    def test_after_fold_source_change_discards_all_claims(self):
        with registered(timeframe=Timeframe.H1) as (_, cmd, catalog, journal):
            plan, rules, chunks = example(cmd, catalog)
            host = Coordinator()
            req = host.prepare('changed', plan, rules, chunks, catalog, journal)
            from trading_agent.core_v3.statistical_validation.evidence import recheck
            calls = 0
            def fail_after_results(observations, *args):
                nonlocal calls
                calls += 1
                if calls >= 2:
                    raise ContractError('TEST_CORRUPTION')
                return recheck(observations, *args)
            with patch('trading_agent.core_v3.statistical_validation.coordinator.recheck', side_effect=fail_after_results):
                result = host.run(req, plan, rules, chunks, catalog, journal).result
            self.assertEqual(Status.REJECTED, result.status)
            self.assertEqual((), result.groups)
            self.assertIn('EVIDENCE_CHANGED', result.reasons)

    def test_input_work_result_and_trade_caps_fail_closed(self):
        with registered(timeframe=Timeframe.H1) as (_, cmd, catalog, journal):
            plan, rules, chunks = example(cmd, catalog)
            for restricted in (replace(rules, max_input_bytes=1), replace(rules, max_work_units=1),
                               replace(rules, max_windows=2)):
                with self.assertRaises(ContractError):
                    Coordinator().prepare('limited', plan, restricted, chunks, catalog, journal)
            for restricted in (replace(rules, max_result_bytes=4096), replace(rules, max_trades=1),
                               replace(rules, max_observation_bytes=4096)):
                _, _, artifact = execute(plan, restricted, chunks, catalog, journal)
                self.assertEqual(Status.REJECTED, artifact.result.status)
                self.assertFalse(artifact.result.groups)

    def test_post_selection_and_required_oos_cannot_be_certified(self):
        with registered(timeframe=Timeframe.H1) as (_, cmd, catalog, journal):
            plan, rules, chunks = example(cmd, catalog)
            rules = replace(rules, selected_after_analysis=True, require_oos=True, require_inference=True,
                            min_test_windows=2, dependence=Dependence.IID_WINDOW_BLOCKS_ASSUMED)
            _, _, artifact = execute(plan, rules, chunks, catalog, journal)
            self.assertEqual(Status.INCONCLUSIVE, artifact.result.status)
            self.assertIn('OOS_NOT_ESTABLISHED', artifact.result.reasons)
            self.assertFalse(artifact.result.statistically_validated)

    def test_robustness_coordinator_archives_hashes_and_fragility(self):
        with registered(timeframe=Timeframe.H1) as (_, cmd, catalog, journal):
            plan, rules, chunks = example(cmd, catalog)
            scenario = RobustnessScenario('commission', extra_opening_fee=Money(D('.1'), 'USD'))
            plan = replace(plan, scenarios=(scenario,))
            rules = replace(rules, declared_family_size=2, require_robustness=True)
            _, _, artifact = execute(plan, rules, chunks, catalog, journal)
            self.assertEqual(Status.COMPLETE, artifact.result.status)
            self.assertTrue(artifact.result.robustness[0].fragile)
            self.assertEqual(3, len(artifact.proofs))
            self.assertEqual(content_hash(scenario), artifact.result.robustness[0].scenario_sha256)
