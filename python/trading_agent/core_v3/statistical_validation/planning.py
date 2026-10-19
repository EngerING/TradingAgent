"""Deterministic partitions over contiguous bounded synthetic chunks."""
from ..contracts import content_hash, require
from ..event_backtest.contracts import SyntheticDataset
from .contracts import (ChunkRef, DatasetManifest, ExperimentPlan, Partition, ValidationPolicy)


def manifest(dataset_id, chunks):
    require(type(chunks) is tuple and 1 <= len(chunks) <= 4
            and all(type(c) is SyntheticDataset for c in chunks), 'DATASET_CHUNKS_REQUIRED')
    first = chunks[0]
    require(all(c.instrument == first.instrument and c.timeframe is first.timeframe for c in chunks),
            'INCOMPARABLE_WINDOWS')
    bars = tuple(b for c in chunks for b in c.bars)
    require(len({b.bar_id for b in bars}) == len(bars)
            and all(a.closed_at == b.opened_at and a.available_at <= b.available_at
                    for a, b in zip(bars, bars[1:])), 'DATASET_SEQUENCE_INVALID')
    return DatasetManifest(dataset_id, first.instrument, first.timeframe,
        tuple(ChunkRef(c.dataset_id, content_hash(c), len(c.bars), c.bars[0].opened_at, c.bars[-1].closed_at)
              for c in chunks), len(bars))


def windows(plan, policy, versions, chunks):
    """Return (split, V3.6 dataset, warmup). No fitting or data repair occurs here."""
    require(type(plan) is ExperimentPlan and type(policy) is ValidationPolicy
            and type(versions) is tuple and len(versions) == len(plan.candidates), 'EXPERIMENT_TYPES_REQUIRED')
    require(manifest(plan.manifest.dataset_id, chunks) == plan.manifest, 'DATASET_MANIFEST_CHANGED')
    require(len(chunks) <= policy.max_datasets and len(plan.candidates) <= policy.max_candidates
            and len(plan.splits) <= policy.max_windows and len(plan.scenarios) <= policy.max_scenarios,
            'STATISTICAL_RESOURCE_LIMIT')
    require(sum(len(c.to_json().encode('utf-8')) for c in chunks)+len(plan.to_json().encode('utf-8'))
            +len(policy.to_json().encode('utf-8')) <= policy.max_input_bytes, 'STATISTICAL_INPUT_BYTES')
    runs = len(plan.candidates)*len(plan.splits)*(1+sum(s.close_at_end is not None for s in plan.scenarios))
    require(runs <= policy.max_backtests and runs*128+policy.bootstrap_replicas*len(plan.splits)
            *len(plan.candidates) <= policy.max_work_units, 'STATISTICAL_WORK_LIMIT')
    require(policy.declared_family_size >= len(plan.candidates)*policy.parameter_variants*(1+len(plan.scenarios)),
            'DECLARED_FAMILY_TOO_SMALL')
    strategies = tuple(v.registration.strategy for v in versions)
    contexts = tuple(v.source.request.inputs.context for v in versions)
    require(all(s.instrument == plan.manifest.instrument and s.timeframe is plan.manifest.timeframe for s in strategies),
            'INCOMPARABLE_WINDOWS')
    require(len({content_hash(c) for c in contexts}) == 1
            and len({content_hash(v.source.request.inputs.policy) for v in versions}) == 1, 'INCOMPARABLE_WINDOWS')
    warmups = tuple(max(r.required_bars for r in s.entry_rules+s.exit_rules)-1 for s in strategies)
    # All candidates must see exactly the same amount of context for aggregate comparability.
    require(len(set(warmups)) == 1, 'INCOMPARABLE_WARMUP')
    warmup = warmups[0]
    horizon = max(s.max_holding_bars for s in strategies)
    require(tuple(sorted(plan.splits, key=lambda s: (s.fold, tuple(Partition).index(s.partition)))) == plan.splits,
            'TEMPORAL_CHRONOLOGY_INVALID')
    folds = sorted({s.fold for s in plan.splits})
    require(folds == list(range(1, len(folds)+1)), 'TEMPORAL_FOLD_INVALID')
    for fold in folds:
        members = tuple(s for s in plan.splits if s.fold == fold)
        require(tuple(s.partition for s in members) == tuple(Partition), 'THREE_PARTITIONS_REQUIRED')
        require(all(b.evaluation_start-a.evaluation_end >= horizon+policy.embargo_bars
                    for a, b in zip(members, members[1:])), 'TEMPORAL_PURGE_REQUIRED')
    scored = tuple(s for s in plan.splits if s.partition is not Partition.TRAIN)
    for index, left in enumerate(scored):
        for right in scored[index+1:]:
            require(left.evaluation_end <= right.evaluation_start or right.evaluation_end <= left.evaluation_start,
                    'SCORED_WINDOWS_OVERLAP')
    # Fold progression must advance reserved windows, even for expanding development windows.
    tests = tuple(s for s in plan.splits if s.partition is Partition.TEST)
    require(all(a.evaluation_end <= b.evaluation_start for a, b in zip(tests, tests[1:])),
            'TEMPORAL_CHRONOLOGY_INVALID')
    bars = tuple(b for c in chunks for b in c.bars)
    output = []
    for split in plan.splits:
        start, end = split.evaluation_start-warmup, split.evaluation_end
        require(split.history_start <= start and 0 <= start < end <= len(bars), 'WARMUP_COVERAGE_REQUIRED')
        require(end-start <= min(128, policy.backtest.max_bars), 'BACKTEST_WINDOW_LIMIT')
        require(all(b.available_at <= bars[split.evaluation_start].opened_at
                    for b in bars[start:split.evaluation_start]), 'TEMPORAL_LEAKAGE')
        output.append((split, SyntheticDataset(split.window_id, plan.manifest.instrument, plan.manifest.timeframe,
                                               bars[start:end]), warmup))
    return tuple(output)
