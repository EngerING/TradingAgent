"""Pure conditional EUR/USD feasibility. Never an execution permission."""
from datetime import datetime, timezone
from decimal import Decimal, DecimalException, localcontext
import hashlib
import json
import re

CONTEXT_FIELDS = frozenset((
    'schema', 'source', 'evidence_id', 'observed_at', 'valid_until',
    'mid_usd_per_eur', 'equity_usd', 'free_margin_usd', 'remaining_risk_usd',
    'remaining_exposure_usd', 'liquidity_quantity_eur', 'minimum_quantity_eur',
    'quantity_step_eur', 'initial_margin_fraction', 'minimum_net_profit_usd',
    'gap_reserve_usd', 'costs'))
COST_FIELDS = frozenset((
    'status', 'evidence_id', 'valid_until', 'opening_min_usd', 'closing_min_usd',
    'opening_per_eur_usd', 'closing_per_eur_usd', 'spread_usd_per_eur',
    'slippage_per_side_usd_per_eur', 'financing_usd'))
PLAN_FIELDS = frozenset((
    'schema', 'evidence_id', 'direction', 'quantity_eur', 'entry_mid_usd_per_eur',
    'stop_mid_usd_per_eur', 'target_mid_usd_per_eur'))


class EconomicInputError(ValueError):
    """Only fixed local codes, never caller or provider exception text."""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('utf-8')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def require(condition, reason):
    if not condition:
        raise EconomicInputError(reason)


def identifier(value):
    require(type(value) is str and re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}', value),
            'IDENTIFIER_INVALID')
    return value


def number(value, *, positive=False):
    # Bounded plain decimals avoid NaN, binary floats and enormous exponents.
    require(type(value) is str and re.fullmatch(r'(0|[1-9][0-9]{0,17})(\.[0-9]{1,12})?', value),
            'DECIMAL_REQUIRED')
    result = Decimal(value)
    require(not positive or result > 0, 'POSITIVE_VALUE_REQUIRED')
    return result


def instant(value):
    if type(value) is str:
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(isinstance(value, datetime) and value.tzinfo is not None
            and value.utcoffset() is not None, 'AWARE_TIMESTAMP_REQUIRED')
    return value.astimezone(timezone.utc)


def shape(value, fields):
    require(type(value) is dict and set(value) == fields, 'FIELDS_INVALID')


def assess(context, plan, *, now):
    result = dict(schema='FOREX_ECONOMIC_ASSESSMENT_V1', admitted=False,
                  scope='ECONOMIC_SCENARIO_ONLY', reasons=[], metrics={}, input_sha256=None,
                  statistically_validated=False, broker_executability_verified=False,
                  execution_authority=False, paper_execution_eligible=False,
                  live_enabled=False, trading_decision='NO_TRADE')
    try:
        with localcontext() as arithmetic:
            arithmetic.prec = 60
            result.update(_assess(context, plan, now=now))
    except EconomicInputError as exc:
        result['reasons'] = [str(exc)]
    except (ValueError, TypeError, KeyError, OverflowError, DecimalException):
        # No raw input, provider content or exception text is copied to diagnostics.
        result['reasons'] = ['ECONOMIC_INPUT_INVALID']
    return result


def _assess(context, plan, *, now):
    shape(context, CONTEXT_FIELDS)
    shape(plan, PLAN_FIELDS)
    require(context['schema'] == 'FOREX_ECONOMIC_CONTEXT_V1'
            and plan['schema'] == 'FOREX_ECONOMIC_PLAN_V1', 'SCHEMA_INVALID')
    require(context['source'] in ('SYNTHETIC_TEST_ONLY', 'CALLER_SUPPLIED_UNVERIFIED'),
            'RESEARCH_SOURCE_REQUIRED')
    identifier(context['evidence_id'])
    require(plan['evidence_id'] == context['evidence_id'], 'EVIDENCE_MISMATCH')
    now = instant(now)
    observed, expires = instant(context['observed_at']), instant(context['valid_until'])
    require(observed <= now < expires and (expires - observed).total_seconds() <= 30,
            'SNAPSHOT_EXPIRED_OR_INVALID')
    costs = context['costs']
    shape(costs, COST_FIELDS)
    identifier(costs['evidence_id'])
    if costs['status'] != 'ESTIMATED_RESEARCH_ONLY':
        return dict(admitted=False, reasons=['COSTS_UNKNOWN'])
    require(now < instant(costs['valid_until']), 'COST_POLICY_EXPIRED')
    c = {key: number(context[key], positive=key in (
        'equity_usd', 'mid_usd_per_eur', 'minimum_quantity_eur',
        'quantity_step_eur', 'initial_margin_fraction'))
         for key in CONTEXT_FIELDS - {'schema', 'source', 'evidence_id', 'observed_at', 'valid_until', 'costs'}}
    fees = {key: number(costs[key]) for key in COST_FIELDS - {'status', 'evidence_id', 'valid_until'}}
    p = {key: number(plan[key], positive=True) for key in PLAN_FIELDS - {'schema', 'evidence_id', 'direction'}}
    require(plan['direction'] in ('LONG', 'SHORT'), 'DIRECTION_INVALID')
    quantity, entry, stop, target = (p[k] for k in (
        'quantity_eur', 'entry_mid_usd_per_eur', 'stop_mid_usd_per_eur', 'target_mid_usd_per_eur'))
    sign = 1 if plan['direction'] == 'LONG' else -1
    require(sign * (entry - stop) > 0 and sign * (target - entry) > 0, 'GEOMETRY_INVALID')
    require(entry == c['mid_usd_per_eur'], 'ENTRY_SNAPSHOT_MISMATCH')
    require(c['initial_margin_fraction'] <= 1 and c['remaining_risk_usd'] <= c['equity_usd'],
            'LIMITS_INVALID')
    opening = max(fees['opening_min_usd'], quantity * fees['opening_per_eur_usd'])
    closing = max(fees['closing_min_usd'], quantity * fees['closing_per_eur_usd'])
    cost = (opening + closing + fees['financing_usd'] + quantity *
            (fees['spread_usd_per_eur'] + 2 * fees['slippage_per_side_usd_per_eur']))
    notional = quantity * entry
    gross_target = quantity * sign * (target - entry)
    net = gross_target - cost
    loss = quantity * sign * (entry - stop) + cost + c['gap_reserve_usd']
    margin = notional * c['initial_margin_fraction'] + cost + c['gap_reserve_usd']
    checks = [
        (quantity < c['minimum_quantity_eur'], 'MINIMUM_QUANTITY'),
        ((quantity - c['minimum_quantity_eur']) % c['quantity_step_eur'] != 0, 'QUANTITY_STEP'),
        (quantity > c['liquidity_quantity_eur'], 'LIQUIDITY_EXCEEDED'),
        (notional > c['remaining_exposure_usd'], 'EXPOSURE_EXCEEDED'),
        (margin > min(c['free_margin_usd'], c['equity_usd']), 'MARGIN_INSUFFICIENT'),
        (loss > c['remaining_risk_usd'], 'RISK_BUDGET_EXCEEDED'),
        (net <= 0, 'NONPOSITIVE_NET_TARGET'),
        (net < c['minimum_net_profit_usd'], 'NET_PROFIT_BELOW_MINIMUM')]
    reasons = [reason for failed, reason in checks if failed]
    return dict(admitted=not reasons, reasons=reasons,
                input_sha256=digest(dict(context=context, plan=plan)),
                metrics={key: str(value) for key, value in dict(
                    opening_commission_usd=opening, closing_commission_usd=closing,
                    round_trip_cost_usd=cost, gross_target_usd=gross_target, net_target_usd=net,
                    stop_loss_with_costs_usd=loss, required_margin_usd=margin,
                    notional_usd=notional, break_even_move_usd_per_eur=cost / quantity).items()})
