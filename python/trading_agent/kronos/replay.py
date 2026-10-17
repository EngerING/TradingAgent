"""Bounded, preregistered chronological replay. Final holdout remains sealed."""
from datetime import timedelta
import json
from pathlib import Path
from .contracts import digest, instant, utcnow, classify
from .config import load
from .adapter import LocalKronosAdapter
from .predictor import KronosPredictionService
from .persistence import PostgreSQLJournal
from .evaluation import paired_benchmark
from .calibration import metrics

def run_replay(root,config_path=None):
    # This existing loader verifies archive receipts, hashes and the frozen six-month split.
    from trading_agent.progressive_risk_research import authentic_inputs
    from trading_agent.eurusd_cost_aware_search import catalogue, signals
    root=Path(root);c=load(root,config_path)
    if c['timeframe']!='1H':raise ValueError('INITIAL_BENCHMARK_1H_ONLY')
    analysis,versions,provenance=authentic_inputs(root)
    candidate=next(x for x in catalogue() if x['family']=='trend' and x['minutes']==60 and x['horizon']=='swing')
    bars=analysis['normalized']['60'];by_at={b['opened_at']:i for i,b in enumerate(bars)}
    split=analysis['extension']['split'];boundary=instant(split['validation_start'])
    opportunities=[r for r in signals(analysis,candidate) if r.get('side') and not r['reasons']]
    # Freeze the comparator and bounded opportunity set before loading any model or inspecting results.
    selected=[];previous=None
    for role in ('CALIBRATION','VALIDATION'):
        n=0;previous=None
        for row in opportunities:
            at=instant(row['entry_at'])
            if (at<boundary)!= (role=='CALIBRATION'):continue
            if previous and at<previous+timedelta(hours=c['replay_stride_bars']):continue
            i=by_at.get(row['entry_at'])
            if i is None or i<c['lookback'] or i+c['pred_len']>len(bars):continue
            future=bars[i:i+c['pred_len']]
            if any(instant(b['opened_at'])!=at+timedelta(hours=j) for j,b in enumerate(future)):continue
            selected.append(dict(row=row,index=i,partition=role));previous=at;n+=1
            if n>=c['replay_maximum_predictions']//2:break
    protocol=dict(scope='KRONOS_OBSERVATION_ONLY',execution_authority=False,live_enabled=False,kind='BENCHMARK_PREREGISTRATION',
        at=utcnow().isoformat(),candidate=candidate,model=c['model_version'],config_hash=digest(c),provenance=provenance,
        split=split,selected=[dict(at=s['row']['entry_at'],partition=s['partition']) for s in selected],
        final_test='SEALED',baseline_parameters_unchanged=True,changes='KRONOS_FILTER_ONLY',maximum_predictions=c['replay_maximum_predictions'])
    protocol_id='kronos-'+digest(protocol);directory=root/'artifacts/research/kronos/benchmark'/protocol_id;directory.mkdir(parents=True,exist_ok=False)
    (directory/'protocol.json').write_bytes(__import__('trading_agent.kronos.contracts',fromlist=['encoded']).encoded(protocol))
    journal=PostgreSQLJournal(root);journal.append('EVALUATION',protocol,protocol_id)
    saved={e['payload']['prediction_id']:e['payload'] for e in journal.read()['events'] if e['kind']=='PREDICTION'}
    service=KronosPredictionService(root,c,LocalKronosAdapter(root,c));records=[];failures=[]
    try:
        for s in selected:
            row=s['row'];i=s['index'];at=row['entry_at'];entry=float(row['entry_midpoint']);side=1 if row['side']=='BUY' else -1
            signal=dict(signal_id=row['opportunity_id'],strategy_id=candidate['id'],direction='LONG' if side==1 else 'SHORT',entry=entry,
                hold_until=(instant(at)+timedelta(days=candidate['hold_calendar_days'])).isoformat(),
                stop_loss=entry-side*float(row['stop_distance']),take_profit=entry+side*float(row['take_profit_distance']),geometry_bucket='FROZEN_2_ATR_STRUCTURE_12_ATR_TARGET')
            request=dict(symbol='EUR/USD',timeframe='1H',as_of=at,bars=[{k:b[k] for k in ('opened_at','open','high','low','close')} for b in bars[i-c['lookback']:i]],
                signal=signal,regime=row.get('regime','UNKNOWN'),partition=s['partition'],source=dict(quality='AUTHENTIC',sha256=provenance['dataset_hash'],provider='VERIFIED_SIX_MONTH_IBKR_ARCHIVE'))
            try:
                from .features import validate_input
                meta=validate_input(request,c)
                cache=digest([request['symbol'],request['timeframe'],meta['candle_timestamp'],c['model_version'],c['tokenizer_version'],digest(c),meta['input_hash']])
                pid='kronos-'+digest([cache,signal])
                p=saved.get(pid) or service.submit(request,records).result(timeout=600)
            except Exception as exc:failures.append(dict(at=at,reason=str(exc) if isinstance(exc,ValueError) else type(exc).__name__));continue
            journal.append('PREDICTION',p,p['prediction_id'])
            future=[{k:b[k] for k in ('opened_at','open','high','low','close')} for b in bars[i:i+c['pred_len']]]
            actual=classify(future,signal)
            outcome=dict(scope='KRONOS_OBSERVATION_ONLY',execution_authority=False,live_enabled=False,status='OBSERVED_REPLAY',
                prediction_id=p['prediction_id'],prediction_start=p['prediction_start'],prediction_end=p['prediction_end'],observed_at=p['prediction_end'],
                actual=actual,tp_first_actual=actual=='TP_FIRST',sl_first_actual=actual=='SL_FIRST',brier_component=(p['raw_tp_frequency']-(actual=='TP_FIRST'))**2,
                directional_correct=(float(future[-1]['close'])-entry)*p['predicted_return_median']>0,
                mae=sum(abs(float(b['close'])-q['median']) for b,q in zip(future,p['quantiles']))/len(future),partition=s['partition'],future_bars=future,
                strategy_future_bars=[{k:b[k] for k in ('opened_at','open','high','low','close')} for b in bars[i:] if instant(b['opened_at'])<=instant(at)+timedelta(days=candidate['hold_calendar_days'],hours=72)])
            oid='kronos-'+digest(['OUTCOME',p['prediction_id']])
            old=next((e['payload'] for e in journal.read()['events'] if e['id']==oid),None)
            if old:
                if old!=outcome:raise ValueError('REPLAY_OUTCOME_CONFLICT')
            else:journal.append('OUTCOME',outcome,oid)
            records.append(dict(p,**{k:v for k,v in outcome.items() if k not in ('scope','status')}))
            (directory/(p['prediction_id']+'.json')).write_text(json.dumps(records[-1],allow_nan=False),encoding='utf-8')
            print(json.dumps(dict(completed=len(records),maximum=len(selected),partition=s['partition'],at=at)),flush=True)
    finally:service.close()
    validation=[r for r in records if r['partition']=='VALIDATION'];wf=[]
    for start in range(0,len(validation),10):
        block=validation[start:start+10];wf.append(dict(start=block[0]['prediction_start'],end=block[-1]['prediction_end'],metrics=metrics(block),benchmark=paired_benchmark(block,c)))
    report=dict(scope='KRONOS_OBSERVATION_ONLY',execution_authority=False,live_enabled=False,at=utcnow().isoformat(),protocol_id=protocol_id,
        state='INSUFFICIENT_EVIDENCE',prediction_count=len(records),failed=failures,calibration_samples=sum(r['partition']=='CALIBRATION' for r in records),
        validation=metrics(validation),walk_forward=wf,benchmark=paired_benchmark(records,c),final_test='SEALED',
        limitations=['BOUNDED_REPLAY_NOT_ECONOMIC_VALIDATION','PRETRAINING_DATA_OVERLAP_UNKNOWN','MIDPOINT_NOT_EXECUTABLE_QUOTES','CALIBRATION_SAMPLE_REQUIREMENTS_NOT_RELAXED',
            'FEES_OBSERVED_ONE_PRIOR_CYCLE_GENERALIZATION_UNKNOWN','NO_IBKR_ORDERS','NO_AUTOMATIC_PROMOTION'],provenance=provenance)
    (directory/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8');journal.append('EVALUATION',report)
    print(json.dumps(dict(report=str(directory/'report.json'),predictions=len(records),state=report['state'])))
