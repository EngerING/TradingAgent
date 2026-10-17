from .contracts import instant, utcnow
from .calibration import metrics

def project(events,now=None):
    now=now or utcnow();preds=[e['payload'] for e in events if e['kind']=='PREDICTION'];preds.sort(key=lambda p:p['candle_timestamp'],reverse=True)
    statuses=[e['payload'] for e in events if e['kind']=='STATUS']
    status=max(statuses,key=lambda s:instant(s['at'])) if statuses else {}
    outcomes={e['payload']['prediction_id']:e['payload'] for e in events if e['kind']=='OUTCOME'}
    latest=preds[0] if preds else None
    records=[dict(p,**{k:v for k,v in outcomes[p['prediction_id']].items() if k not in ('scope','status')}) for p in preds if p['prediction_id'] in outcomes]
    # Aggregate UI only across identical model/config/timeframe. It is not a calibration training pool.
    same=[];seen=set()
    for r in records:
        key=(r['cache_key'],r.get('signal_id'))
        if key not in seen and latest and all(r.get(k)==latest.get(k) for k in ('timeframe','model_version','tokenizer_version','config_hash')):same.append(r);seen.add(key)
    directions=[r['directional_correct'] for r in same if r.get('directional_correct') is not None];errors=[r['mae'] for r in same if r.get('mae') is not None]
    stats=metrics(same); stats.update(predictions=len(preds),evaluated=len(records),directional_accuracy=sum(directions)/len(directions) if directions else None,
        mae=sum(errors)/len(errors) if errors else None,
        net_expectancy_with_kronos=None,net_expectancy_baseline=None,delta_expectancy=None,drawdown_comparison=None)
    totals=next((e['payload'] for e in events if e['kind']=='READ_MODEL_TOTALS'),None)
    if totals:stats.update(predictions=totals['predictions'],evaluated=totals['evaluated'],read_window=totals['window'],metrics_scope='RECENT_MATCHING_MODEL_CONFIG_TIMEFRAME_DEDUPLICATED')
    evaluation=next((e['payload'] for e in events if e['kind']=='EVALUATION'),None)
    stale=not latest or not 0<=(now-instant(latest['candle_timestamp'])).total_seconds()<=latest.get('max_prediction_age_seconds',3900)
    offline=not status or not 0<=(now-instant(status['at'])).total_seconds()<=120
    state='KRONOS_UNAVAILABLE' if offline else status.get('status','KRONOS_UNAVAILABLE')
    if stale and state=='KRONOS_READY':state='KRONOS_DEGRADED'
    reasons=[]
    if offline:reasons.append('OBSERVER_HEARTBEAT_MISSING_OR_STALE')
    if status.get('reason'):reasons.append(status['reason'])
    if stale:reasons.append('PREDICTION_MISSING_OR_STALE')
    diagnostics=dict(latest.get('diagnostics',{})) if latest else {}
    if latest:
        if latest.get('invalid_frequency',0)>0:reasons.append('INVALID_MODEL_OHLC_TRAJECTORIES')
        reasons.extend(diagnostics.get('reasons',[]))
        diagnostics.update(valid_paths=round(latest['sample_count']*(1-latest['invalid_frequency'])),
            invalid_paths=round(latest['sample_count']*latest['invalid_frequency']),total_paths=latest['sample_count'],
            calibration_reason='NO_ELIGIBLE_TECHNICAL_SIGNAL' if not latest.get('signal') else latest['calibration_state'],
            bands_evidence='CONDITIONAL_ON_VALID_MODEL_TRAJECTORIES_NOT_CALIBRATED_CONFIDENCE')
    # Small recent aggregates describe observations, not an approved calibration.
    # Published calibration scores come only from the independently gated pool.
    score_keys=('brier_score','log_loss','calibration_error')
    stats['descriptive_metrics']={k:stats[k] for k in score_keys}
    calibration=latest.get('calibration',{}) if latest else {}
    sufficient=latest and latest['calibration_state']=='CALIBRATED' and not stale and not offline and latest.get('invalid_frequency',0)==0 and calibration.get('comparable_samples',0)>=diagnostics.get('minimum_calibration_samples',100) and calibration.get('sample_size',0)>=diagnostics.get('minimum_bucket_samples',30)
    calibrated=calibration.get('metrics',{}) if sufficient else {}
    for k in score_keys:stats[k]=calibrated.get(k)
    by_regime=[]
    for g in sorted({r['regime'] for r in same}):
        group=metrics([r for r in same if r['regime']==g])
        group['descriptive_metrics']={k:group[k] for k in score_keys}
        for k in score_keys:group[k]=calibrated.get(k) if latest and latest['regime']==g else None
        by_regime.append(dict(regime=g,**group))
    health='UNAVAILABLE' if state in ('KRONOS_UNAVAILABLE','KRONOS_ERROR','KRONOS_LOADING') else 'DEGRADED' if state=='KRONOS_DEGRADED' or reasons else 'HEALTHY'
    diagnostics.update(operational_health=health,reasons=list(dict.fromkeys(reasons)),evaluation=status.get('evaluation'),
        observed_price_samples=len(errors),observed_barrier_samples=stats['sample_size'],
        metrics_evidence='DESCRIPTIVE_OBSERVED_NOT_CALIBRATION_APPROVAL',minimum_calibration_samples=diagnostics.get('minimum_calibration_samples',100),
        minimum_bucket_samples=diagnostics.get('minimum_bucket_samples',30))
    return dict(status=state,operationalHealth=health,diagnostics=diagnostics,heartbeatAt=status.get('at'),reason=status.get('reason') or (reasons[0] if reasons else None),mode='OBSERVATION / SHADOW_FEATURE',paperEligible=False,liveEnabled=False,executionAuthority=False,
        latest=latest,stale=stale,last20=preds[:20],telemetry=status.get('telemetry',{}),evaluation=evaluation,
        calibration=stats,calibrationState=latest['calibration_state'] if latest and not stale else 'CALIBRATION_INSUFFICIENT',
        byRegime=by_regime,
        forecastLabel='KRONOS FORECAST — NOT REALIZED MARKET DATA',realLabel='REAL MARKET DATA — IBKR MIDPOINT',
        finalTest='SEALED',openaiCalls=0)
