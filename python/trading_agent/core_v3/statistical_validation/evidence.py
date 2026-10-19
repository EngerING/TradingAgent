"""Controlled V3.6 integration and bounded observation archives."""
from dataclasses import replace
from ..contracts import canonical_bytes, content_hash, require
from ..event_backtest import engine, reader
from .contracts import BacktestObservation, ObservationRef


def pin(candidate, dataset, policy, catalog, journal, request_id):
    ref = candidate.catalog_ref
    request = reader.prepare(request_id, catalog, journal, ref.catalog_id, ref.version,
        candidate.validation_operation_id, dataset, policy, research_cutoff=candidate.research_cutoff)
    require(request.catalog_ref == ref, 'STATISTICAL_CANDIDATE_CHANGED')
    return request


def observe(candidate, split, dataset, warmup, policy, manifest_hash, catalog, journal,
            observation_id, scenario_id=None, max_bytes=131072, source_pin=None):
    # A pinned source may bind a new window; V3.6 independently loads/checks it twice.
    request = (pin(candidate, dataset, policy, catalog, journal, observation_id) if source_pin is None else
               replace(source_pin, request_id=observation_id, dataset_sha256=content_hash(dataset),
                       policy_sha256=content_hash(policy)))
    result = engine.run(request, catalog, journal, dataset, policy)
    value = BacktestObservation(observation_id, candidate.candidate_id, split.window_id, split.partition,
        scenario_id, manifest_hash, dataset.bars[warmup].opened_at, dataset.bars[-1].closed_at,
        warmup, dataset, policy, request, result, content_hash(result))
    require(len(canonical_bytes(value)) <= max_bytes, 'OBSERVATION_SIZE_LIMIT')
    return value


def reference(observation):
    return ObservationRef(observation.observation_id, observation.candidate_id, observation.window_id,
        observation.partition, observation.scenario_id, content_hash(observation), observation.result_sha256,
        observation.result.status.value, None if observation.result.metrics is None else len(observation.result.trades))


def recheck(observations, catalog, journal):
    checked = set()
    for observation in observations:
        require(content_hash(observation.result) == observation.result_sha256, 'EVIDENCE_CHANGED')
        request = observation.request
        require(request.dataset_sha256 == content_hash(observation.dataset)
                and request.policy_sha256 == content_hash(observation.policy), 'EVIDENCE_CHANGED')
        source = content_hash(replace(request, request_id='source-check', dataset_sha256='0'*64, policy_sha256='0'*64))
        if source not in checked:
            reader.load(request, catalog, journal, observation.dataset, observation.policy)
            checked.add(source)
