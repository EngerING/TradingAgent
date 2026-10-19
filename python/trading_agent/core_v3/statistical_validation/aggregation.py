"""No capital chaining. Overlapping development trades belong to the first declared window."""
from dataclasses import replace
from decimal import Decimal

from ..contracts import Money, require
from ..event_backtest.contracts import Status as BacktestStatus
from .contracts import (CandidateUncertainty, MetricGroup, Partition, WindowMetrics)
from .statistics import bootstrap, describe, ratio


def aggregate(plan, policy, observations):
    base = tuple(o for o in observations if o.scenario_id is None)
    groups, windows, estimates, reasons = [], [], [], []
    for observation in base:
        m = observation.result.metrics
        if m is None:
            continue
        windows.append(WindowMetrics(observation.observation_id, m.net, m.initial_capital,
            m.final_realized_capital, m.final_mark_capital, ratio(m.net.amount, m.initial_capital.amount),
            m.max_realized_drawdown, m.max_mark_drawdown, observation.result.status is BacktestStatus.COMPLETE))
    for candidate in plan.candidates:
        selected = tuple(o for o in base if o.candidate_id == candidate.candidate_id)
        currencies = {o.result.metrics.net.currency for o in selected if o.result.metrics is not None}
        require(len(currencies) <= 1, 'INCOMPARABLE_WINDOWS')
        if not currencies:
            reasons.append('BACKTEST_COVERAGE_INCOMPLETE')
            continue  # Rejected backtests have unknown metrics, not invented zeros.
        currency = next(iter(currencies))
        for partition in (*tuple(p.value for p in Partition), 'ALL_UNIQUE'):
            members = tuple(o for o in selected if partition == 'ALL_UNIQUE' or o.partition.value == partition)
            expected = {s.window_id for s in plan.splits if partition == 'ALL_UNIQUE' or s.partition.value == partition}
            complete = {o.window_id for o in members} == expected and all(
                o.result.status is BacktestStatus.COMPLETE for o in members)
            intervals, trades, excluded = [], [], 0
            for observation in members:
                for trade in observation.result.trades:
                    start, end = trade.entry.at, trade.exit.at
                    if any(start < b and a < end or (start == end == a == b) for a, b in intervals):
                        excluded += 1
                        continue
                    intervals.append((start, end))
                    trades.append(trade)
            require(len(trades) <= policy.max_trades, 'ACCUMULATED_TRADE_LIMIT')
            metrics = describe(tuple(t.net.amount for t in trades), tuple(t.gross.amount for t in trades), currency)
            dd = [o.result.metrics for o in members if o.result.metrics is not None]
            groups.append(MetricGroup(candidate.candidate_id, partition, metrics, excluded, complete,
                Money(max((m.max_realized_drawdown.amount for m in dd), default=Decimal(0)), currency),
                Money(max((m.max_mark_drawdown.amount for m in dd), default=Decimal(0)), currency)))
        tests = tuple(o for o in selected if o.partition is Partition.TEST)
        coverage = len(tests) == sum(s.partition is Partition.TEST for s in plan.splits) and all(
            o.result.status is BacktestStatus.COMPLETE for o in tests)
        sufficient = sum(len(o.result.trades) for o in tests) >= policy.min_trades and len(tests) >= policy.min_test_windows
        durations = {o.evaluated_until-o.evaluated_from for o in tests}
        values = tuple(o.result.metrics.net.amount for o in tests if o.result.metrics is not None)
        estimate = bootstrap(values, dependence=policy.dependence, seed=policy.seed,
            replicas=policy.bootstrap_replicas, confidence_bps=policy.confidence_bps,
            family_size=policy.declared_family_size)
        blocked = ('BACKTEST_COVERAGE_INCOMPLETE' if not coverage else 'INSUFFICIENT_SAMPLE' if not sufficient
                   else 'INCOMPARABLE_WINDOW_DURATION' if len(durations) != 1 else
                   'POST_SELECTION_INFERENCE_NOT_ESTABLISHED' if policy.selected_after_analysis else None)
        if blocked is not None:
            estimate = replace(estimate, lower=None, upper=None, independent_units=None, reason=blocked)
        if policy.require_inference and estimate.lower is None:
            reasons.append(estimate.reason)
        estimates.append(CandidateUncertainty(candidate.candidate_id, currency, estimate))
    return tuple(groups), tuple(windows), tuple(estimates), tuple(dict.fromkeys(reasons))
