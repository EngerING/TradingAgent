"""Explicit binding of a validated preparation to a synthetic lab execution plan.

No activation or permission is performed here. Both are separate owner/operator
actions. The operational store and authentic forward remain unavailable.
"""
from datetime import datetime
from .r20_preparation import PreparationService, validate_values, validate_purpose
from .r20_profiles import canonical, decimal_text, digest, strict_json, utc
from .r20_persistence import sql_text


def bind_preparation(store,context,configuration_hash,at):
    rows=PreparationService(store,context).history()
    if not rows or rows[-1]['lifecycle']!='VALIDO':raise ValueError('VALIDATED_PREPARATION_REQUIRED')
    p=rows[-1]['profile']
    if p['configuration_hash']!=configuration_hash:raise ValueError('PREPARATION_CHANGED')
    if not datetime.fromisoformat(p['effective_from'])<=utc(at)<datetime.fromisoformat(p['effective_until']):
        raise ValueError('PREPARATION_EXPIRED')
    v=validate_values(p['values']);validate_purpose(p['purpose'],v['environment'])
    if v['environment']!='SHADOW':raise ValueError('SHADOW_PLAN_ONLY')
    if context.get('aggregate_leverage_cap') is None:raise ValueError('AGGREGATE_LEVERAGE_CAP_REQUIRED')
    return dict(context,shadow_plan=canonical(dict(preparationHash=configuration_hash,purpose=p['purpose'],
        allocation_usd=v['allocation_usd'],requested_allocation_leverage=v['requested_allocation_leverage'])))


def resolve_plan(store,context,profile,at):
    plan=context.get('shadow_plan')
    if plan is None:return None
    bound=bind_preparation(store,context,plan['preparationHash'],at)
    if bound['shadow_plan']!=plan:raise ValueError('PLAN_BINDING_MISMATCH')
    p=PreparationService(store,context).history()[-1]['profile'];v=validate_values(p['values'])
    expected=(v['logical_capital_usd'],v['risk_per_trade_pct'],v['daily_loss_limit_pct'],v['max_open_positions'])
    actual=(profile.capital_base_usd,profile.risk_per_trade_pct,profile.daily_loss_limit_pct,profile.max_open_positions)
    if actual!=expected or profile.max_leverage!=decimal_text(context['aggregate_leverage_cap']):
        raise ValueError('PROFILE_PLAN_MISMATCH')
    raw=store.execute('SELECT payload FROM r20_v2_shadow.permissions WHERE scope='+sql_text(context['scope'])+';')
    if not any(r.get('plan')==plan and r.get('contextHash')==digest(context)
        and datetime.fromisoformat(r['start'])<=utc(at)<datetime.fromisoformat(r['end'])
        for r in (strict_json(line) for line in raw.splitlines())):
        raise ValueError('BOUND_SHADOW_PERMISSION_REQUIRED')
    return dict(plan,contextHash=digest(context))
