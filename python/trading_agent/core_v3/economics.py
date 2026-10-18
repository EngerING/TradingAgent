"""V3.2 preflight/postflight. Pure research decisions, no execution authority."""
from datetime import datetime, timedelta
from decimal import Context, DecimalException, localcontext
import hashlib

from .contracts import (
    ContractError, Environment, SourceKind, canonical_bytes, content_hash, utc,
)
from .economic_contracts import (
    EconomicContext, EconomicResult, EconomicStatus, ReasonCount, ResearchPolicy, Scenario,
)
from .economic_scenarios import prepare_domain, scenarios
from .economic_calculation import calculate


def _input_issue(context, policy, now):
    if not policy.effective_from <= now < policy.valid_until:
        return 'POLICY_NOT_CURRENT'
    if not context.hypotheses:
        return 'TECHNICAL_DOMAIN_UNKNOWN'
    if context.costs is None or any(getattr(context.costs, name) is None for name in (
        'opening_minimum', 'opening_per_unit', 'closing_minimum', 'closing_per_unit',
        'financing_fixed', 'financing_per_unit_per_hour', 'slippage_per_side')):
        return 'COSTS_UNKNOWN'
    if context.margin is None or context.margin.initial_fraction is None or context.margin.maintenance_fraction is None:
        return 'MARGIN_UNKNOWN'
    portfolio, market = context.portfolio, context.market
    amounts = (portfolio.equity, portfolio.allocation_available, portfolio.free_margin,
               portfolio.remaining_exposure, portfolio.remaining_risk, policy.max_loss, policy.minimum_net_target)
    if any(v is None for v in amounts):
        return 'PORTFOLIO_UNKNOWN'
    if any(v.currency != portfolio.account_currency for v in amounts):
        return 'ACCOUNT_CURRENCY_MISMATCH'
    if portfolio.allocation_available.amount > portfolio.equity.amount:
        return 'ALLOCATION_EQUITY_INCONSISTENT'
    instrument = market.instrument
    if policy.max_quantity.unit != instrument.quantity_unit:
        return 'QUANTITY_UNIT_MISMATCH'
    prices = [market.bid, market.ask, policy.max_stop_distance, policy.max_target_distance]
    for h in context.hypotheses:
        if h.instrument_sha256 != content_hash(instrument):
            return 'HYPOTHESIS_INSTRUMENT_MISMATCH'
        prices.extend((h.entry, h.stop_distance, h.target_distance, h.plausible_move))
    if any(p.currency != instrument.quote_currency or p.per_unit != instrument.quantity_unit for p in prices):
        return 'PRICE_UNIT_OR_CURRENCY_MISMATCH'
    costs = context.costs
    if any(h.direction not in costs.directions for h in context.hypotheses):
        return 'DIRECTION_COSTS_UNKNOWN'
    if any(v.currency != instrument.quote_currency for v in
           (costs.opening_minimum, costs.closing_minimum, costs.financing_fixed)):
        return 'COST_CURRENCY_MISMATCH'
    rates = [costs.opening_per_unit, costs.closing_per_unit, costs.financing_per_unit_per_hour,
             costs.slippage_per_side, policy.max_entry_deviation, policy.maximum_spread]
    for s in policy.stresses:
        rates.extend((s.adverse_gap, s.extra_slippage_per_side))
    if any(v.money.currency != instrument.quote_currency or v.per_unit != instrument.quantity_unit for v in rates):
        return 'COST_UNIT_OR_CURRENCY_MISMATCH'
    if market.bid.amount > market.ask.amount:
        return 'QUOTE_INVALID'
    try:
        for price in (market.bid, market.ask):
            instrument.check_terms(instrument.minimum_quantity, price)
    except ContractError:
        return 'QUOTE_OFF_GRID'
    records = [market, portfolio, costs, context.margin, *context.hypotheses]
    if portfolio.account_currency != instrument.quote_currency:
        if context.fx is None:
            return 'FX_UNKNOWN'
        if (context.fx.from_currency, context.fx.to_currency) != (instrument.quote_currency, portfolio.account_currency):
            return 'FX_PAIR_MISMATCH'
        records.append(context.fx)
    elif context.fx is not None:
        return 'UNEXPECTED_FX_CONVERSION'
    for record in records:
        ref = record.evidence
        try:
            ref.require_current(now)
        except ContractError as exc:
            return str(exc)
        if now - ref.observed_at > timedelta(seconds=policy.max_evidence_age_seconds):
            return 'EVIDENCE_TOO_OLD'
        if ref.content_sha256 != record.material_hash():
            return 'EVIDENCE_HASH_MISMATCH'
        if ref.environment not in (Environment.RESEARCH, Environment.SIMULATION):
            return 'OFFLINE_ENVIRONMENT_REQUIRED'
        if ref.environment != market.evidence.environment:
            return 'EVIDENCE_ENVIRONMENT_MISMATCH'
        if ref.source_kind is not SourceKind.SYNTHETIC or not policy.allow_synthetic:
            return 'EVIDENCE_NOT_AUTHENTICATED'
    return None


def _counts(reasons):
    return tuple(ReasonCount(key, reasons[key]) for key in sorted(reasons))


def _result(status, now, ch, ph, limit, *, size=0, evaluated=0, complete=False,
            reasons=(), trace=None, witness=None, evaluation=None, stage='PREFLIGHT'):
    if trace is None:
        trace = content_hash(dict(engine='CORE_V3_2_V1', context=ch, policy=ph, as_of=now, stage=stage,
                                  reasons=list(reasons)))
    return EconomicResult(status, now, ch, ph, size, evaluated, limit, complete,
                          tuple(ReasonCount(reason, 1) for reason in reasons), trace, witness, evaluation, stage)


def _prepare(context, policy, now, stage):
    if type(context) is not EconomicContext or type(policy) is not ResearchPolicy:
        return None, None, _result(EconomicStatus.UNKNOWN, now, None, None, 0,
                                  reasons=('ECONOMIC_CONTRACT_REQUIRED',), stage=stage)
    ch, ph = content_hash(context), content_hash(policy)
    issue = _input_issue(context, policy, now)
    if issue:
        return ch, ph, _result(EconomicStatus.UNKNOWN, now, ch, ph, policy.max_evaluations,
                              reasons=(issue,), stage=stage)
    return ch, ph, None


def preflight(context: EconomicContext, policy: ResearchPolicy, *, now: datetime) -> EconomicResult:
    """Existential proof within this finite, explicit technical/policy domain only."""
    now = utc(now)
    with localcontext(Context(prec=160)):
        ch, ph, blocked = _prepare(context, policy, now, 'PREFLIGHT')
        if blocked is not None:
            return blocked
        if context.market.ask.amount - context.market.bid.amount > policy.maximum_spread.money.amount:
            return _result(EconomicStatus.INFEASIBLE, now, ch, ph, policy.max_evaluations,
                           complete=True, reasons=('SPREAD_POLICY_EXCEEDED',))
        domain = prepare_domain(context, policy)
        reasons = {}
        for reason in domain.geometry_rejections:
            reasons[reason] = reasons.get(reason, 0) + 1
        if domain.quantity_points == 0:
            reasons['EMPTY_QUANTITY_DOMAIN'] = 1
        trace = content_hash(dict(engine='CORE_V3_2_V1', context=ch, policy=ph, as_of=now))
        evaluated, unresolved = 0, domain.quantity_points > 0 and 'NUMERIC_RANGE_UNRESOLVED' in reasons
        for trial in scenarios(domain, context, policy, ch, ph):
            evaluated += 1
            scenario = trial.scenario
            try:
                if trial.reason:
                    raise ContractError(trial.reason)
                evaluation = calculate(context, policy, scenario)
                trial_reasons = evaluation.reasons
                material = evaluation.to_dict()
            except (ContractError, DecimalException):
                trial_reasons, material, evaluation = ('NUMERIC_RANGE_UNRESOLVED',), None, None
                unresolved = True
            trace = hashlib.sha256(trace.encode('ascii') + canonical_bytes(
                dict(hypothesis_id=trial.hypothesis_id, quantity_index=trial.quantity_index,
                     scenario=scenario.to_dict() if scenario is not None else None,
                     evaluation=material, reasons=list(trial_reasons)))).hexdigest()
            for reason in trial_reasons:
                reasons[reason] = reasons.get(reason, 0) + 1
            if not trial_reasons:
                return EconomicResult(EconomicStatus.FEASIBLE, now, ch, ph, domain.size, evaluated,
                    policy.max_evaluations, evaluated == domain.size and not unresolved,
                    _counts(reasons), trace, scenario, evaluation)
        complete = evaluated == domain.size and not unresolved
        if evaluated < domain.size and evaluated >= policy.max_evaluations:
            reasons['SEARCH_LIMIT_REACHED'] = 1
        status = EconomicStatus.INFEASIBLE if complete and not unresolved else EconomicStatus.UNRESOLVED
        return EconomicResult(status, now, ch, ph, domain.size, evaluated, policy.max_evaluations,
                              complete, _counts(reasons), trace, None, None)


def postflight(context: EconomicContext, policy: ResearchPolicy, candidate: Scenario,
               previous: EconomicResult, *, now: datetime) -> EconomicResult:
    """Revalidate one exact witnessed scenario; no approval is inherited from previous."""
    now = utc(now)
    with localcontext(Context(prec=160)):
        ch, ph, blocked = _prepare(context, policy, now, 'POSTFLIGHT')
        if blocked is not None:
            return blocked
        def reject(reason, status=EconomicStatus.UNKNOWN):
            return _result(status, now, ch, ph, policy.max_evaluations, reasons=(reason,), stage='POSTFLIGHT')
        if type(candidate) is not Scenario or type(previous) is not EconomicResult:
            return reject('V32_SCENARIO_AND_RESULT_REQUIRED')
        if previous.stage != 'PREFLIGHT' or previous.status is not EconomicStatus.FEASIBLE:
            return reject('FEASIBLE_PREFLIGHT_REQUIRED')
        if previous.as_of > now:
            return reject('PREFLIGHT_FROM_FUTURE')
        if (candidate.context_sha256, previous.context_sha256) != (ch, ch):
            return reject('CONTEXT_CHANGED')
        if (candidate.policy_sha256, previous.policy_sha256) != (ph, ph):
            return reject('POLICY_CHANGED')
        if candidate != previous.witness:
            return reject('CANDIDATE_CHANGED')
        if context.market.ask.amount - context.market.bid.amount > policy.maximum_spread.money.amount:
            return reject('SPREAD_POLICY_EXCEEDED', EconomicStatus.INFEASIBLE)
        # Match against generated geometry/grid even if a caller constructed previous by hand.
        domain = prepare_domain(context, policy)
        if not any(candidate == trial.scenario for trial in scenarios(domain, context, policy, ch, ph)):
            if 'NUMERIC_RANGE_UNRESOLVED' in domain.geometry_rejections:
                return reject('NUMERIC_RANGE_UNRESOLVED', EconomicStatus.UNRESOLVED)
            if domain.size > policy.max_evaluations:
                return reject('CANDIDATE_NOT_REACHED_WITHIN_SEARCH_LIMIT', EconomicStatus.UNRESOLVED)
            return reject('CANDIDATE_OUTSIDE_SEARCH_DOMAIN', EconomicStatus.INFEASIBLE)
        try:
            evaluation = calculate(context, policy, candidate)
        except (ContractError, DecimalException):
            return reject('NUMERIC_RANGE_UNRESOLVED', EconomicStatus.UNRESOLVED)
        status = EconomicStatus.INFEASIBLE if evaluation.reasons else EconomicStatus.FEASIBLE
        trace = content_hash(dict(engine='CORE_V3_2_V1', context=ch, policy=ph,
                                  candidate=candidate, evaluation=evaluation, as_of=now))
        return _result(status, now, ch, ph, policy.max_evaluations, size=1, evaluated=1,
            complete=True, reasons=evaluation.reasons, trace=trace,
            witness=candidate if not evaluation.reasons else None, evaluation=evaluation, stage='POSTFLIGHT')
