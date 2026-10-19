"""In-memory experiment coordinator. No model calls, writes or authority mutations."""
from dataclasses import replace
from decimal import DecimalException
from sqlite3 import Error as PersistenceError
from threading import Lock

from ..contracts import ContractError, canonical_bytes, content_hash, require
from ..event_backtest import reader
from ..event_backtest.contracts import Status as BacktestStatus
from ..research_journal import ResearchJournal
from ..strategy_catalog.service import Catalog
from .aggregation import aggregate
from .contracts import (ExperimentPlan, ExperimentRun, ExposureRecord, Partition, Status,
    ValidationEvidence, ValidationPolicy, ValidationRequest, ValidationResult)
from .evidence import observe, pin, recheck, reference
from .planning import windows


def _started(observations):
    return sum(sum(fill.role.value == 'ENTRY' for fill in o.result.fills) for o in observations)


class Coordinator:
    """Two cached experiments/128 accesses per instance. Host-wide past access is unknown."""
    def __init__(self):
        self._exposures = ()
        self._cache = {}
        self._lock = Lock()

    @property
    def exposures(self):
        return self._exposures

    def _inputs(self, plan, policy, chunks, catalog, journal):
        require(type(plan) is ExperimentPlan and type(policy) is ValidationPolicy
                and type(catalog) is Catalog and type(journal) is ResearchJournal, 'VERIFIED_SOURCES_REQUIRED')
        versions = tuple(catalog.version(c.catalog_ref.catalog_id, c.catalog_ref.version) for c in plan.candidates)
        return windows(plan, policy, versions, chunks)

    def prepare(self, request_id, plan, policy, chunks, catalog, journal):
        require(self._lock.acquire(blocking=False), 'COORDINATOR_BUSY')
        try:
            prepared = self._inputs(plan, policy, chunks, catalog, journal)
            first = prepared[0][1]
            pins = tuple(pin(c, first, policy.backtest, catalog, journal, 'pin-'+str(index))
                         for index, c in enumerate(plan.candidates))
            return ValidationRequest(request_id, content_hash(plan), content_hash(policy), len(self._exposures),
                                     content_hash(self._exposures), pins)
        finally:
            self._lock.release()

    def _check_pins(self, request, plan, policy, prepared, catalog, journal):
        require(request.plan_sha256 == content_hash(plan) and request.policy_sha256 == content_hash(policy),
                'STATISTICAL_INPUT_CHANGED')
        require(len(request.source_pins) == len(plan.candidates), 'STATISTICAL_SOURCE_PINS_REQUIRED')
        for candidate, pinned in zip(plan.candidates, request.source_pins):
            require(pinned.catalog_ref == candidate.catalog_ref
                    and pinned.validation_operation_id == candidate.validation_operation_id
                    and pinned.research_cutoff == candidate.research_cutoff, 'STATISTICAL_CANDIDATE_CHANGED')
            reader.load(pinned, catalog, journal, prepared[0][1], policy.backtest)

    def run(self, request, plan, policy, chunks, catalog, journal):
        require(type(request) is ValidationRequest, 'VALIDATION_REQUEST_REQUIRED')
        if not self._lock.acquire(blocking=False):
            return self._finish_failure(request, Status.REJECTED, 'COORDINATOR_BUSY')
        try:
            return self._run(request, plan, policy, chunks, catalog, journal)
        finally:
            self._lock.release()

    def _run(self, request, plan, policy, chunks, catalog, journal):
        observations, proofs, robustness, accesses = [], [], [], []
        reused, interrupted, reserved = False, False, False
        def terminal(status, reason):
            artifact = self._finish_failure(request, status, reason)
            if reserved:
                # A rejected archive is forensic input, never an aggregate claim.
                artifact = ExperimentRun(artifact.result, tuple(observations), tuple(proofs))
                self._cache[request.request_id] = artifact
            return artifact
        try:
            prepared = self._inputs(plan, policy, chunks, catalog, journal)
            self._check_pins(request, plan, policy, prepared, catalog, journal)
            cached = self._cache.get(request.request_id)
            if cached is not None:
                require(cached.result.request_sha256 == content_hash(request), 'VALIDATION_REQUEST_CONFLICT')
                recheck(cached.observations, catalog, journal)
                return cached
            require(len(self._cache) < 2, 'COORDINATOR_CACHE_LIMIT')
            require(request.exposure_count == len(self._exposures)
                    and request.exposure_sha256 == content_hash(self._exposures), 'EXPOSURE_PREFIX_CHANGED')
            require(len(self._exposures)+len(prepared) <= 128, 'EXPOSURE_LIMIT')
            # Reserve all accesses before any result is computed; interruption cannot erase a holdout read.
            history = list(self._exposures)
            for split, data, warmup in prepared:
                exposure = ExposureRecord(content_hash(plan), content_hash(plan.manifest.instrument),
                    plan.manifest.timeframe, split.window_id, split.partition, data.bars[0].opened_at,
                    data.bars[-1].closed_at, split.reuse_test_declared)
                known_test = any(e.partition is Partition.TEST and e.instrument_sha256 == exposure.instrument_sha256
                    and e.timeframe is exposure.timeframe and e.read_from < exposure.read_until
                    and exposure.read_from < e.read_until for e in history)
                if known_test:
                    reused = True
                    if split.partition is Partition.TRAIN:
                        require(split.reuse_test_declared, 'TEST_REUSE_UNDECLARED')
                history.append(exposure)
                accesses.append(exposure)
            self._exposures = tuple(history)
            reserved = True
            try:
                for candidate, source_pin in zip(plan.candidates, request.source_pins):
                    for split, data, warmup in prepared:
                        remaining = policy.max_trades-_started(observations)
                        require(remaining > 0, 'ACCUMULATED_TRADE_LIMIT')
                        # Resource allocation is predefined: reduce only the engine's hard trade cap.
                        bounded = replace(policy.backtest, max_trades=min(policy.backtest.max_trades, remaining))
                        observation = observe(candidate, split, data, warmup, bounded,
                            content_hash(plan.manifest), catalog, journal, 'observation-'+str(len(observations)+1),
                            max_bytes=policy.max_observation_bytes, source_pin=source_pin)
                        observations.append(observation)
                        require(observation.result.metrics is not None, 'BACKTEST_ACCOUNTING_UNAVAILABLE')
                        if _started(observations) > policy.max_trades:
                            require(False, 'ACCUMULATED_TRADE_LIMIT')
                        for scenario in plan.scenarios:
                            from .robustness import evaluate
                            remaining = policy.max_trades-_started(observations)
                            require(scenario.close_at_end is None or remaining > 0, 'ACCUMULATED_TRADE_LIMIT')
                            value, extra, proof = evaluate(observation, scenario, candidate, split, warmup,
                                catalog, journal, policy, content_hash(plan.manifest), len(observations)+1,
                                remaining_trades=remaining)
                            robustness.append(value)
                            if extra is not None:
                                observations.append(extra)
                                require(extra.result.metrics is not None, 'BACKTEST_ACCOUNTING_UNAVAILABLE')
                            if proof is not None:
                                proofs.append(proof)
                            require(_started(observations) <= policy.max_trades,
                                    'ACCUMULATED_TRADE_LIMIT')
            except KeyboardInterrupt:
                interrupted = True
            # Integrity change discards all aggregate claims, including after bootstrap.
            recheck(observations, catalog, journal)
            groups, metrics, estimates, reasons = aggregate(plan, policy, tuple(observations))
            reasons = list(reasons)
            base = tuple(o for o in observations if o.scenario_id is None)
            if interrupted:
                reasons.append('EXPERIMENT_INTERRUPTED')
            if len(base) != len(plan.candidates)*len(plan.splits) or any(o.result.status is not BacktestStatus.COMPLETE
                                                                      for o in observations):
                reasons.append('BACKTEST_COVERAGE_INCOMPLETE')
            if policy.require_robustness and (not plan.scenarios or any(r.method == 'NOT_ESTABLISHED' for r in robustness)):
                reasons.append('ROBUSTNESS_NOT_ESTABLISHED')
            if policy.require_oos:
                reasons.append('OOS_NOT_ESTABLISHED')
            evidence = ValidationEvidence(request, plan, policy, tuple(reference(o) for o in observations),
                tuple(accesses), reused, 'RETROSPECTIVE_SPLIT_ONLY' if reused else 'OOS_NOT_ESTABLISHED',
                len(observations))
            result = ValidationResult(content_hash(request), Status.INCONCLUSIVE if reasons else Status.COMPLETE,
                tuple(dict.fromkeys(reasons)) or ('EXPLORATORY_CALCULATION_COMPLETE',), evidence,
                groups, metrics, estimates, tuple(robustness))
            recheck(observations, catalog, journal)
            self._check_pins(request, plan, policy, prepared, catalog, journal)
            require(len(canonical_bytes(result)) <= policy.max_result_bytes, 'STATISTICAL_RESULT_BYTES')
            artifact = ExperimentRun(result, tuple(observations), tuple(proofs))
            self._cache[request.request_id] = artifact
            return artifact
        except ContractError as exc:
            # Fixed codes only; never echo arbitrary source content into public errors.
            code = str(exc)
            known = {'STATISTICAL_INPUT_CHANGED', 'DATASET_MANIFEST_CHANGED', 'TEST_REUSE_UNDECLARED',
                'EXPOSURE_PREFIX_CHANGED', 'VALIDATION_REQUEST_CONFLICT', 'COORDINATOR_CACHE_LIMIT',
                'ACCUMULATED_TRADE_LIMIT', 'OBSERVATION_SIZE_LIMIT', 'STATISTICAL_RESULT_BYTES',
                'STATISTICAL_RESOURCE_LIMIT', 'STATISTICAL_WORK_LIMIT', 'STATISTICAL_INPUT_BYTES',
                'INCOMPARABLE_WINDOWS', 'STATISTICAL_CANDIDATE_CHANGED'}
            if code == 'BACKTEST_ACCOUNTING_UNAVAILABLE':
                return terminal(Status.INCONCLUSIVE, code)
            return terminal(Status.REJECTED, code if code in known else 'EVIDENCE_CHANGED')
        except DecimalException:
            return terminal(Status.REJECTED, 'STATISTICAL_PRECISION_ERROR')
        except (PersistenceError, OSError):
            return terminal(Status.REJECTED, 'SOURCE_UNAVAILABLE')
        except KeyboardInterrupt:
            if not reserved:
                raise
            # Interruption during aggregation/bootstrap/postchecks cannot erase prior access.
            return terminal(Status.INCONCLUSIVE, 'EXPERIMENT_INTERRUPTED')

    @staticmethod
    def _finish_failure(request, status, reason):
        return ExperimentRun(ValidationResult(content_hash(request), status, (reason,), None), ())
