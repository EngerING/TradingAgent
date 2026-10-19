"""Predeclared chronology, context-only warmup and horizon separation."""
from dataclasses import replace
from datetime import timedelta
import unittest

from test_core_v36_binding import registered
from test_core_v36_engine import trade_data
from test_core_v36_contracts import policy as backtest_policy
from trading_agent.core_v3.contracts import ContractError
from trading_agent.core_v3.strategy_catalog.contracts import CatalogRef
from trading_agent.core_v3.strategy_v34.contracts import Timeframe
from trading_agent.core_v3.statistical_validation.contracts import (
    CandidateRef, ExperimentPlan, TemporalSplit, Partition, ValidationPolicy)
from trading_agent.core_v3.statistical_validation.planning import manifest, windows


def example(cmd, catalog, *, modes=('TARGET', 'STOP', 'TARGET'), folds=1):
    source = trade_data(cmd)
    bars, splits = [], []
    for index in range(3*folds):
        sample = trade_data(cmd, mode=modes[index % len(modes)])
        start = len(bars)
        # Six-bar blocks separated by six flat bars; required warmup=4.
        for j, bar in enumerate(sample.bars):
            shift = timedelta(seconds=(start+j)*source.timeframe.seconds)- (bar.opened_at-source.bars[0].opened_at)
            bars.append(replace(bar, bar_id='bar-'+str(start+j), opened_at=bar.opened_at+shift,
                                closed_at=bar.closed_at+shift, available_at=bar.available_at+shift))
        splits.append(TemporalSplit('window-'+str(index), index//3+1, tuple(Partition)[index % 3],
                                    start, start+3, start+6))
        for _ in range(6):
            previous = bars[-1]
            bars.append(replace(previous, bar_id='bar-'+str(len(bars)), open=previous.close,
                high=previous.close, low=previous.close, opened_at=previous.closed_at,
                closed_at=previous.closed_at+timedelta(seconds=source.timeframe.seconds),
                available_at=previous.closed_at+timedelta(seconds=source.timeframe.seconds)))
    chunks = tuple(replace(source, dataset_id='chunk-'+str(i//128), bars=tuple(bars[i:i+128]))
                   for i in range(0, len(bars), 128))
    candidate = CandidateRef('candidate-1', CatalogRef.of(catalog.version('catalog-1', 1)),
                             'registration-1', catalog.version('catalog-1', 1).recorded_at)
    plan = ExperimentPlan('experiment-1', manifest('dataset-1', chunks), (candidate,), tuple(splits))
    rules = ValidationPolicy('statistics-1', replace(backtest_policy(), close_at_end=True),
                             min_trades=1, require_inference=False, require_robustness=False)
    return plan, rules, chunks


class PlanningTests(unittest.TestCase):
    def test_windows_only_warm_up_before_first_evaluation_close(self):
        with registered(timeframe=Timeframe.H1) as (_, cmd, catalog, _):
            plan, rules, chunks = example(cmd, catalog)
            version = catalog.version('catalog-1', 1)
            prepared = windows(plan, rules, (version,), chunks)
            self.assertEqual(3, len(prepared))
            self.assertEqual(3, prepared[0][2])
            self.assertEqual(chunks[0].bars[:6], prepared[0][1].bars)

    def test_chronology_overlap_warmup_and_horizon_purge_are_rejected(self):
        with registered(timeframe=Timeframe.H1) as (_, cmd, catalog, _):
            plan, rules, chunks = example(cmd, catalog)
            versions = (catalog.version('catalog-1', 1),)
            variants = [tuple(reversed(plan.splits)),
                        (plan.splits[0], replace(plan.splits[1], history_start=0, evaluation_start=5), plan.splits[2]),
                        (replace(plan.splits[0], history_start=3),)+plan.splits[1:]]
            for splits in variants:
                with self.subTest(splits=splits), self.assertRaises(ContractError):
                    windows(replace(plan, splits=splits), rules, versions, chunks)
            with self.assertRaises(ContractError):
                windows(plan, replace(rules, embargo_bars=10), versions, chunks)

    def test_manifest_detects_content_changes_and_gaps(self):
        with registered(timeframe=Timeframe.H1) as (_, cmd, catalog, _):
            plan, rules, chunks = example(cmd, catalog)
            changed = replace(chunks[0], dataset_id='changed')
            with self.assertRaises(ContractError):
                windows(plan, rules, (catalog.version('catalog-1', 1),), (changed,))

    def test_purge_also_separates_scored_windows_across_folds(self):
        with registered(timeframe=Timeframe.H1) as (_, cmd, catalog, _):
            plan, rules, chunks = example(cmd, catalog, folds=2)
            splits = list(plan.splits)
            splits[3] = replace(splits[3], history_start=12, evaluation_start=15, evaluation_end=18,
                                 reuse_test_declared=True)
            splits[4] = replace(splits[4], history_start=27, evaluation_start=30, evaluation_end=33)
            with self.assertRaises(ContractError):
                windows(replace(plan, splits=tuple(splits)), rules, (catalog.version('catalog-1', 1),), chunks)

    def test_multiple_chunks_retain_v36_window_limits(self):
        with registered(timeframe=Timeframe.H1) as (_, cmd, catalog, _):
            plan, rules, chunks = example(cmd, catalog, folds=4)
            self.assertEqual(2, len(chunks))
            self.assertGreater(plan.manifest.total_bars, 128)
            values = windows(plan, rules, (catalog.version('catalog-1', 1),), chunks)
            self.assertEqual(12, len(values))
            self.assertTrue(all(len(data.bars) <= 128 for _, data, _ in values))

    def test_warmup_available_after_decision_is_temporal_leakage(self):
        with registered(timeframe=Timeframe.H1) as (_, cmd, catalog, _):
            plan, rules, chunks = example(cmd, catalog)
            data = chunks[0]
            bars = list(data.bars)
            bars[2] = replace(bars[2], available_at=bars[3].opened_at+timedelta(seconds=1))
            chunks = (replace(data, bars=tuple(bars)),)
            plan = replace(plan, manifest=manifest('dataset-1', chunks))
            with self.assertRaisesRegex(ContractError, 'TEMPORAL_LEAKAGE'):
                windows(plan, rules, (catalog.version('catalog-1', 1),), chunks)

    def test_incompatible_account_currencies_block_aggregation_before_execution(self):
        from test_core_v35_contracts import request
        with registered(timeframe=Timeframe.H1) as (_, cmd, catalog, _), registered(
                timeframe=Timeframe.H1, req=request(account_currency='EUR')) as (_, _, other, _):
            plan, rules, chunks = example(cmd, catalog)
            versions = catalog.version('catalog-1', 1), other.version('catalog-1', 1)
            second = replace(plan.candidates[0], candidate_id='candidate-2', catalog_ref=CatalogRef.of(versions[1]))
            plan = replace(plan, candidates=plan.candidates+(second,))
            with self.assertRaisesRegex(ContractError, 'INCOMPARABLE_WINDOWS'):
                windows(plan, replace(rules, declared_family_size=2), versions, chunks)
