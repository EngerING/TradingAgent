"""Synthetic end-to-end experiments reuse actual catalog/research/backtest sources."""
from dataclasses import replace
from decimal import Decimal as D
from unittest.mock import patch
import unittest

from test_core_v36_binding import registered
from test_core_v37_planning import example
from trading_agent.core_v3.contracts import ContractError, content_hash
from trading_agent.core_v3.strategy_v34.contracts import Timeframe
from trading_agent.core_v3.statistical_validation.contracts import Dependence, Status, ValidationResult
from trading_agent.core_v3.statistical_validation.coordinator import Coordinator


class CoordinatorTests(unittest.TestCase):
    def test_three_partitions_exact_net_and_no_mutation_or_authority(self):
        with registered(timeframe=Timeframe.H1) as (_, cmd, catalog, journal):
            plan, rules, chunks = example(cmd, catalog)
            before = catalog.history(), journal.history(), journal.budget_status()
            host = Coordinator()
            request = host.prepare('validation-1', plan, rules, chunks, catalog, journal)
            run = host.run(request, plan, rules, chunks, catalog, journal)
            self.assertEqual(Status.COMPLETE, run.result.status, run.result.reasons)
            self.assertEqual(3, len(run.observations))
            self.assertEqual(D('0.0322'), run.result.windows[0].net.amount)
            self.assertEqual(D('-1.2678'), run.result.windows[1].net.amount)
            self.assertEqual(before, (catalog.history(), journal.history(), journal.budget_status()))
            self.assertEqual('OOS_NOT_ESTABLISHED', run.result.evidence.oos_status)
            self.assertEqual('NO_TRADE', run.result.trading_decision)
            self.assertFalse(run.result.statistically_validated or run.result.live_enabled)
            self.assertEqual(run.result, ValidationResult.from_json(run.result.to_json()))
            self.assertEqual(run, host.run(request, plan, rules, chunks, catalog, journal))
            from trading_agent.core_v3.statistical_validation.aggregation import aggregate
            duplicate = replace(run.observations[0], observation_id='duplicate')
            groups, _, _, _ = aggregate(plan, rules, run.observations+(duplicate,))
            self.assertEqual(1, groups[0].metrics.trades)
            self.assertEqual(1, groups[0].excluded_overlapping_trades)

    def test_three_fold_bootstrap_reproducible_and_insufficient_sample(self):
        with registered(timeframe=Timeframe.H1) as (_, cmd, catalog, journal):
            plan, rules, chunks = example(cmd, catalog, folds=3, modes=('TARGET', 'STOP'))
            rules = replace(rules, dependence=Dependence.IID_WINDOW_BLOCKS_ASSUMED, require_inference=True)
            results = []
            for _ in range(2):
                host = Coordinator()
                request = host.prepare('validation-1', plan, rules, chunks, catalog, journal)
                results.append(host.run(request, plan, rules, chunks, catalog, journal))
            self.assertEqual(results[0].result.to_json(), results[1].result.to_json())
            self.assertIsNotNone(results[0].result.uncertainty[0].estimate.lower)
            self.assertEqual(3, results[0].result.uncertainty[0].estimate.independent_units)
            self.assertLess(results[0].result.uncertainty[0].estimate.lower, D(0))
            self.assertGreater(results[0].result.uncertainty[0].estimate.upper, D(0))
            from trading_agent.core_v3.statistical_validation.aggregation import aggregate
            _, _, estimates, _ = aggregate(plan, replace(rules, selected_after_analysis=True), results[0].observations)
            self.assertEqual('POST_SELECTION_INFERENCE_NOT_ESTABLISHED', estimates[0].estimate.reason)
            host = Coordinator()
            insufficient = replace(rules, min_trades=100)
            req = host.prepare('short-sample', plan, insufficient, chunks, catalog, journal)
            value = host.run(req, plan, insufficient, chunks, catalog, journal).result
            self.assertEqual(Status.INCONCLUSIVE, value.status)
            self.assertIn('INSUFFICIENT_SAMPLE', value.reasons)
            self.assertIsNone(value.uncertainty[0].estimate.lower)

    def test_changed_policy_dataset_source_and_cached_invalidation_fail_closed(self):
        with registered(timeframe=Timeframe.H1) as (original, cmd, catalog, journal):
            plan, rules, chunks = example(cmd, catalog)
            host = Coordinator()
            req = host.prepare('validation-1', plan, rules, chunks, catalog, journal)
            for changed in (replace(rules, seed=8), replace(rules, min_trades=2)):
                self.assertEqual(Status.REJECTED, host.run(req, plan, changed, chunks, catalog, journal).result.status)
            self.assertEqual(Status.REJECTED, host.run(req, plan, rules,
                (replace(chunks[0], dataset_id='changed'),), catalog, journal).result.status)
            result = host.run(req, plan, rules, chunks, catalog, journal)
            self.assertEqual(Status.COMPLETE, result.result.status)
            from trading_agent.core_v3.strategy_catalog.contracts import Action
            catalog.register(replace(cmd, operation_id='invalidate', idempotency_key='invalidate', action=Action.REVALIDATE),
                             journal, replace(original.inputs, context=replace(original.inputs.context, costs=None)),
                             now=plan.candidates[0].research_cutoff)
            self.assertEqual(Status.REJECTED, host.run(req, plan, rules, chunks, catalog, journal).result.status)

    def test_known_holdout_reuse_requires_declaration_and_stale_requests_fail(self):
        with registered(timeframe=Timeframe.H1) as (_, cmd, catalog, journal):
            plan, rules, chunks = example(cmd, catalog)
            host = Coordinator()
            req = host.prepare('first', plan, rules, chunks, catalog, journal)
            stale = host.prepare('stale', plan, rules, chunks, catalog, journal)
            host.run(req, plan, rules, chunks, catalog, journal)
            self.assertEqual(Status.REJECTED, host.run(stale, plan, rules, chunks, catalog, journal).result.status)
            # Earlier test becomes development in a subsequent declared experiment.
            train = replace(plan.splits[0], history_start=24, evaluation_start=27, evaluation_end=30)
            val = replace(plan.splits[1], history_start=30, evaluation_start=33, evaluation_end=36)
            test = replace(plan.splits[2], history_start=36, evaluation_start=39, evaluation_end=42)
            expanded, _, more = example(cmd, catalog, folds=2)
            reused = replace(plan, manifest=expanded.manifest, splits=(train, val, test))
            req = host.prepare('reuse', reused, rules, more, catalog, journal)
            self.assertEqual(Status.REJECTED, host.run(req, reused, rules, more, catalog, journal).result.status)
            reused = replace(reused, splits=(replace(train, reuse_test_declared=True), val, test))
            req = host.prepare('declared', reused, rules, more, catalog, journal)
            value = host.run(req, reused, rules, more, catalog, journal).result
            self.assertTrue(value.evidence.previous_test_reused)
            self.assertEqual('RETROSPECTIVE_SPLIT_ONLY', value.evidence.oos_status)
