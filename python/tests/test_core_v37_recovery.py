"""Partial coverage and terminal retries must remain honest after reservation."""
from dataclasses import replace
from unittest.mock import patch
import unittest

from test_core_v36_binding import registered
from test_core_v37_planning import example
from trading_agent.core_v3.strategy_v34.contracts import Timeframe
from trading_agent.core_v3.statistical_validation.contracts import Status
from trading_agent.core_v3.statistical_validation.coordinator import Coordinator
from trading_agent.core_v3.statistical_validation.evidence import observe


class RecoveryTests(unittest.TestCase):
    def test_empty_failure_accounting_stops_further_entry_budget_consumption(self):
        from trading_agent.core_v3.event_backtest.simulation import Simulation
        original = Simulation.enter
        entered = []
        def counted(simulation, *args):
            original(simulation, *args)
            if simulation.position is not None:
                entered.append(1)
        with registered(timeframe=Timeframe.H1) as (_, cmd, catalog, journal):
            plan, rules, chunks = example(cmd, catalog)
            rules = replace(rules, max_trades=1, backtest=replace(rules.backtest, max_result_bytes=4096))
            host = Coordinator()
            req = host.prepare('empty-accounting', plan, rules, chunks, catalog, journal)
            with patch.object(Simulation, 'enter', counted):
                artifact = host.run(req, plan, rules, chunks, catalog, journal)
            self.assertEqual(1, len(entered))
            self.assertEqual(1, len(artifact.observations))
            self.assertEqual('BACKTEST_RESULT_SIZE_LIMIT', artifact.observations[0].result.reason)
            self.assertEqual(Status.INCONCLUSIVE, artifact.result.status)

    def test_partial_fold_never_marks_partition_coverage_complete(self):
        with registered(timeframe=Timeframe.H1) as (_, cmd, catalog, journal):
            plan, rules, chunks = example(cmd, catalog, folds=2)
            host = Coordinator()
            req = host.prepare('partial', plan, rules, chunks, catalog, journal)
            from trading_agent.core_v3.statistical_validation.coordinator import observe as actual
            calls = 0
            def first_only(*args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise KeyboardInterrupt
                return actual(*args, **kwargs)
            with patch('trading_agent.core_v3.statistical_validation.coordinator.observe', side_effect=first_only):
                artifact = host.run(req, plan, rules, chunks, catalog, journal)
            self.assertEqual(Status.INCONCLUSIVE, artifact.result.status)
            self.assertFalse(artifact.result.groups[0].coverage_complete)
            self.assertFalse(artifact.result.groups[-1].coverage_complete)

    def test_interrupt_during_postprocessing_has_cached_inconclusive_result(self):
        with registered(timeframe=Timeframe.H1) as (_, cmd, catalog, journal):
            plan, rules, chunks = example(cmd, catalog)
            host = Coordinator()
            req = host.prepare('interrupted', plan, rules, chunks, catalog, journal)
            with patch('trading_agent.core_v3.statistical_validation.coordinator.observe', side_effect=KeyboardInterrupt), \
                 patch('trading_agent.core_v3.statistical_validation.coordinator.aggregate', side_effect=KeyboardInterrupt):
                try:
                    artifact = host.run(req, plan, rules, chunks, catalog, journal)
                except KeyboardInterrupt:
                    self.fail('Postprocessing interruption escaped after exposure reservation')
            self.assertEqual(Status.INCONCLUSIVE, artifact.result.status)
            self.assertEqual(artifact, host.run(req, plan, rules, chunks, catalog, journal))

    def test_limit_rejection_preserves_completed_observations_and_terminal_retry(self):
        with registered(timeframe=Timeframe.H1) as (_, cmd, catalog, journal):
            plan, rules, chunks = example(cmd, catalog)
            rules = replace(rules, max_trades=1)
            host = Coordinator()
            req = host.prepare('limited', plan, rules, chunks, catalog, journal)
            artifact = host.run(req, plan, rules, chunks, catalog, journal)
            self.assertEqual(('ACCUMULATED_TRADE_LIMIT',), artifact.result.reasons)
            self.assertEqual(1, len(artifact.observations))
            self.assertEqual(artifact, host.run(req, plan, rules, chunks, catalog, journal))
