"""Evidence contracts. No broker mutations, model calls or authorization writes."""
import hashlib
import json
from pathlib import Path
from .eurusd_exploratory import N,instant,now,PROFILES

def observer_context(root,at):
    from .kronos.persistence import PostgreSQLJournal
    try:
        events=PostgreSQLJournal(root).read().get('events',[])
        candidates=[e['payload'] for e in events if e['kind']=='PREDICTION' and instant(e['payload']['created_at'])<=instant(at)]
        if not candidates:return dict(status='UNKNOWN',reason='NO_FORECAST_AVAILABLE_AT_OPPORTUNITY',calibrated_probability=None)
        p=max(candidates,key=lambda p:instant(p['created_at']))
        return dict(status='OBSERVER_ONLY',prediction_id=p['prediction_id'],model=p['model'],model_version=p.get('model_version'),
            timeframe=p['timeframe'],horizon=p['pred_len'],created_at=p['created_at'],sample_count=p['sample_count'],
            valid_paths=round(p['sample_count']*(1-p['invalid_frequency'])),invalid_paths=round(p['sample_count']*p['invalid_frequency']),
            projected_direction=p.get('consensus',{}).get('kronos_direction'),raw_tp_first=p.get('raw_tp_frequency'),raw_sl_first=p.get('raw_sl_frequency'),
            calibration=p.get('calibration_state'),calibrated_probability=None,regime=p.get('regime'),consensus=p.get('consensus'),
            age_seconds=(instant(at)-instant(p['created_at'])).total_seconds(),not_execution_authority=True)
    except Exception as exc:return dict(status='UNKNOWN',reason=type(exc).__name__,calibrated_probability=None)

def checked_artifact(root,item):
    base=Path(root).resolve();path=(base/item['artifact']).resolve()
    if not path.is_relative_to(base) or not path.is_file():raise PermissionError('PAPER_RECEIPT_ARTIFACT_REQUIRED')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=item.get('artifact_sha256'):raise PermissionError('PAPER_RECEIPT_HASH_MISMATCH')
    return json.loads(raw)

def verify_operator_evidence(root,operator,r,observation,profile,clock=now):
    """Local human receipts are scoped to this Paper session and a bounded quantity.

    A what-if receipt is ESTIMATED, never effective protection/permission evidence.
    """
    if profile not in PROFILES:raise PermissionError('PROFILE_SCOPE_REQUIRED')
    if r.state['protocol'].get('protocol_version')!=2:raise PermissionError('NEW_SUPERVISED_COHORT_REQUIRED')
    e=dict(observation['evidence']);binding=r.state['protocol']['binding_id']
    for k in ('permissions','margin','settled_funds','minimum_size','fees_bounded','protection','api_write_allowed','recovery'):
        item=operator[k]
        trial=k=='protection' and item.get('status')=='SUPERVISED_FIRST_TRIAL'
        if trial and (r.state['protocol']['purpose']!='PAPER_EXECUTION_DIAGNOSTIC' or item.get('explicit_supervision_consent') is not True):raise PermissionError('PROTECTION_UNKNOWN_REQUIRES_DIAGNOSTIC_PROTOCOL')
        if (not trial and item.get('status')!='VERIFIED') or item.get('environment')!='PAPER_TRADING' or item.get('binding_id')!=binding or item.get('profile')!=profile or not item.get('source') or not 0<=(clock()-instant(item['at'])).total_seconds()<=1800:raise PermissionError('OPERATOR_PAPER_EVIDENCE_REQUIRED')
        receipt=checked_artifact(root,item)
        if any(receipt.get(k)!=v for k,v in item.items() if k not in ('artifact','artifact_sha256')):raise PermissionError('RECEIPT_CONTENT_MISMATCH')
        if receipt.get('environment')!='PAPER_TRADING' or receipt.get('binding_id')!=binding or receipt.get('profile')!=profile or receipt.get('status')!=item['status'] or receipt.get('source')!=item['source'] or receipt.get('at')!=item['at']:raise PermissionError('RECEIPT_SCOPE_OR_PROVENANCE_MISMATCH')
        if k=='protection' and not trial:
            if receipt.get('effective_ack') is not True or not receipt.get('stop_ack') or not receipt.get('target_ack') or not receipt.get('perm_ids') or any(not isinstance(i,int) or i<=0 for i in receipt['perm_ids']):raise PermissionError('EFFECTIVE_PROTECTION_ACK_EVIDENCE_REQUIRED')
        if 'WHAT_IF' in item['source'].upper() and k not in ('margin','fees_bounded'):raise PermissionError('WHAT_IF_NOT_EFFECTIVE_ACCEPTANCE')
        if 'WHAT_IF' in item['source'].upper():raise PermissionError('WHAT_IF_ESTIMATE_NOT_VERIFIED_BOUND')
        e[k]=item['status']
    if operator['api_write_allowed'].get('read_only_disabled_checked') is not True:raise PermissionError('PAPER_TWS_API_READ_ONLY_CHECK_REQUIRED')
    e.update(minimum_quantity=operator['minimum_size']['minimum_quantity'],quantity_increment=operator['minimum_size']['quantity_increment'],
        margin_required_usd=operator['margin']['required_usd'],settled_usd=operator['settled_funds']['usd'],
        verified_quantity=operator['margin']['quantity_up_to'],supervised_protection_consent=operator['protection'].get('explicit_supervision_consent',False),
        bounded_unfavorable_experiment_consent=operator.get('bounded_unfavorable_experiment_consent') is True)
    c=r.state['protocol']['costs'];fees=operator['fees_bounded']
    if min(N(e['minimum_quantity']),N(e['quantity_increment']),N(e['verified_quantity']))<=0 or N(e['margin_required_usd'])<0 or N(e['settled_usd'])<0:raise PermissionError('INVALID_NUMERIC_PAPER_EVIDENCE')
    if fees.get('currency')!='USD' or N(fees['opening_bound'])<0 or N(fees['closing_bound'])<0 or N(fees['opening_bound'])>N(c['openingCommission']) or N(fees['closing_bound'])>N(c['closingCommission']):raise PermissionError('FEES_EXCEED_PREREGISTERED_COSTS')
    if not observation['sizes'].get(profile,{}).get('admitted') or N(observation['sizes'][profile]['quantity'])>N(e['verified_quantity']):raise PermissionError('PROPOSED_QUANTITY_NOT_VERIFIED')
    return e
