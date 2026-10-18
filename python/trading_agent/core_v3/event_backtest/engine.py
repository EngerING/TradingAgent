"""Controlled reads around a pure mathematical fold. No durable writes or provider calls."""
from decimal import Context, DecimalException, Inexact, localcontext

from ..contracts import ContractError, canonical_bytes, content_hash, require
from .contracts import BacktestPolicy, BacktestRequest, BacktestResult, Status, SyntheticDataset
from .reader import load
from .simulation import Simulation


def _failure(request, status, reason, evidence=None):
    return BacktestResult(content_hash(request), status, reason, evidence, (), (), (), (), (), None, None, ())


def run(request: BacktestRequest, catalog, journal, dataset: SyntheticDataset, policy: BacktestPolicy) -> BacktestResult:
    """Re-running identical pinned inputs yields identical bytes; interruption has no writes to recover."""
    require(type(request) is BacktestRequest and type(dataset) is SyntheticDataset
            and type(policy) is BacktestPolicy, 'BACKTEST_TYPES_REQUIRED')
    evidence = None
    try:
        with localcontext(Context(prec=160)) as arithmetic:
            arithmetic.traps[Inexact] = True
            version, evidence = load(request, catalog, journal, dataset, policy)
            duration = dataset.bars[-1].closed_at-dataset.bars[0].opened_at
            if (len(dataset.bars) > policy.max_bars or duration.days*86400+duration.seconds > policy.max_duration_hours*3600
                    or version.registration.strategy.scenario.horizon_hours > policy.max_duration_hours):
                return _failure(request, Status.REJECTED, 'BACKTEST_INPUT_LIMIT', evidence)
            result = Simulation(request, version, evidence, dataset, policy).execute()
            # These independent reads cannot promise an atomic transaction across files.
            load(request, catalog, journal, dataset, policy)
            if len(canonical_bytes(result)) > policy.max_result_bytes:
                return _failure(request, Status.REJECTED, 'BACKTEST_RESULT_SIZE_LIMIT', evidence)
            return result
    except ContractError as exc:
        reason = 'BACKTEST_RESULT_SIZE_LIMIT' if str(exc) == 'JSON_SIZE_LIMIT' else str(exc)
        return _failure(request, Status.REJECTED, reason, evidence)
    except DecimalException:
        return _failure(request, Status.REJECTED, 'BACKTEST_PRECISION_ERROR', evidence)
