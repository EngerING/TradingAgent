"""Read projection only. No installation, permission, profile or trading writes."""
from decimal import Decimal
from .r20_shadow import ShadowCycle
from .r20_runner import RunnerControl
from .r20_profiles import strict_json, encoded
from .r20_economics import exact
from .r20_configuration import daily_payload


def authentic_cutoff(path):
    """Trusted host artifact, independently hashed; never a continuous feed."""
    if path is None:return None
    from pathlib import Path
    from .r20_profiles import digest
    r=strict_json(Path(path).read_text(encoding='utf-8-sig'));m=r.get('market')
    if r.get('status')!='READ_ONLY_DIAGNOSTIC' or not isinstance(m,dict):return None
    if (m.get('classification')!='AUTHENTIC_IBKR_READ_ONLY_DIAGNOSTIC' or
        m.get('sourceHash')!=digest(r.get('source')) or m.get('readOnly') is not True or
        m.get('exactAccountMatch') is not True or m.get('entryEligible') is not False or
        m.get('brokerOrders')!=0):raise ValueError('AUTHENTIC_ARTIFACT_INTEGRITY')
    return dict(at=m['at'],quoteAt=m['quote']['at'],bid=m['quote']['bid'],ask=m['quote']['ask'],
        sourceHash=m['sourceHash'],timestampBasis=m['timestampBasis'],account=m['account'],
        classification='AUTHENTIC_READ_ONLY_HISTORICAL_CUTOFF',continuousFeed=False)

@exact
def monitor(store,context,*,authentic_evidence=None):
    installed=store.execute("SELECT to_regclass('r20_v2_shadow.events') IS NOT NULL;")=='t'
    empty=dict(classification='SYNTHETIC_VIRTUAL_LAB',cohortStarted=False,brokerOrders=0,liveEnabled=False,
        status='NOT_PREREGISTERED',stopRequested=False,positions=[],trades=[],signals=[],equity=None,
        realizedGross=None,openGross=None,costs=[],exposure=None,margin=None,priceRisk=None,
        daily=None,accountingRevision=None,accountingHash=None,lifecycleRevision=0,
        dataStatus='NO_OBSERVATION',lastObservation=None,integrity='NO_CYCLE_EVIDENCE',
        purpose=None,effectiveProfile=None,netPnl=None,aggregateLeverage=None,
        intrabarProtection='UNVERIFIED_BETWEEN_QUOTES',lastAuthenticRead=authentic_cutoff(authentic_evidence))
    if not installed:return empty
    cycle=ShadowCycle(store,context);rows,head=cycle._state();s=head.snapshot
    control_installed=store.execute("SELECT to_regclass('r20_v2_runner.controls') IS NOT NULL;")=='t'
    controls=RunnerControl(store,context['scope']).state() if control_installed else dict(manifest=None,stopRequested=False)
    last=rows[-1] if rows else None
    positions=last['positions'] if last else []
    view=dict(positions=positions,trades=last['trades'] if last else [],equity=str(s.daily.current_equity),
              accountingRevision=head.revision,accountingHash=head.hash,lifecycleRevision=len(rows))
    def d(x):return Decimal(x)
    # Only quote-valued events are marks. Missing evidence remains null.
    mark=next((r for r in reversed(rows) if r['quote'] and r['kind'] in ('MARK','OPEN','CLOSE')),None)
    price=(d(mark['quote']['bid'])+d(mark['quote']['ask']))/2 if mark else None
    state=('STOPPING_MANAGING_SHADOW' if positions or s.daily.pending_terms else 'STOPPED') if controls['stopRequested'] else (
        'PREPARED_REPLAY' if controls['manifest'] else 'NOT_PREREGISTERED')
    exposure=sum((d(p['quantity'])*price for p in positions),Decimal(0)) if price is not None else None
    # Effective means the profile actually used by the accounting ledger, not a
    # just-saved UI draft. Authentic evidence is never inferred from replay.
    plan=context.get('shadow_plan')
    return strict_json(encoded(dict(empty,**{k:view[k] for k in ('positions','trades','equity','accountingRevision','accountingHash','lifecycleRevision')},
        status=state,stopRequested=controls['stopRequested'],integrity='VERIFIED_AT_READ',
        purpose=plan['purpose'] if plan else 'NORMAL',effectiveProfile=strict_json(s.profile.to_json()),
        netPnl=s.daily.current_equity-s.profile.capital_base_usd,
        aggregateLeverage=exposure/s.daily.current_equity if exposure is not None and s.daily.current_equity>0 else None,
        realizedGross=s.realized_gross,openGross=sum((x[1] for x in s.open_gross),Decimal(0)),
        costs=[dict(costId=c.cost_id,amount=c.amount,status=c.status,provenance=c.provenance) for c in s.costs],
        exposure=exposure,
        margin=sum((d(p['quantity'])*price*d(p['initial_margin_fraction']) for p in positions),Decimal(0)) if price is not None else None,
        priceRisk=sum((d(p['quantity'])*abs(d(p['entry_price'])-d(p['stop'])) for p in positions),Decimal(0)),
        daily=daily_payload(s.daily),lastObservation=last['at'] if last else None,
        dataStatus='DATA_UNAVAILABLE' if last and last['kind']=='DATA_UNAVAILABLE' else 'REPLAY_AT_CUTOFF' if last else 'NO_OBSERVATION',
        signals=[dict(at=r['at'],reason=r['reason'],decision=r['input'].get('decision')) for r in rows if r['kind']=='SIGNAL_DIAGNOSTIC'][-50:])))
