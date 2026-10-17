import argparse
from contextlib import contextmanager
from datetime import timedelta
import json
import os
from pathlib import Path
import time
from .contracts import digest, instant, utcnow, classify, TIMEFRAMES, validate_ohlc
from .config import load
from .adapter import LocalKronosAdapter
from .persistence import PostgreSQLJournal, source_request
from .predictor import KronosPredictionService

def status_payload(state,**details):
    return dict(scope='KRONOS_OBSERVATION_ONLY',execution_authority=False,live_enabled=False,at=utcnow().isoformat(),status=state,**details)

def finalize_predictions(journal,events,request,observations=None):
    outcomes={e['payload']['prediction_id'] for e in events if e['kind']=='OUTCOME'}
    bars=request['bars'] if observations is None else observations
    available={};duplicates=set();step=TIMEFRAMES[request['timeframe']];pending=[];observed=0
    for b in bars:
        at=instant(b['opened_at'])
        if at in available:duplicates.add(at)
        available[at]=b
    for e in events:
        if e['kind']!='PREDICTION':continue
        p=e['payload']
        if p['prediction_id'] in outcomes or p['timeframe']!=request['timeframe'] or p['symbol']!=request['symbol']:continue
        if instant(p['prediction_end'])>instant(request['as_of']):continue
        future=[];reason=None
        for i in range(p['pred_len']):
            t=instant(p['prediction_start'])+timedelta(seconds=step*i)
            b=available.get(t)
            if b is None:reason='MISSING_OUTCOME_CANDLES';break
            if t in duplicates:reason='DUPLICATE_OUTCOME_CANDLES';break
            if t+timedelta(seconds=step)>instant(request['as_of']):reason='OUTCOME_CANDLE_NOT_CLOSED';break
            try:validate_ohlc(b)
            except (ValueError,KeyError,TypeError):reason='CORRUPT_OUTCOME_OHLC';break
            future.append(b)
        if reason:
            # Absence is not a realized outcome. Retry from a later authentic archive;
            # observed_at records when evidence actually arrived, preserving the embargo.
            pending.append(dict(prediction_id=p['prediction_id'],reason=reason));continue
        label=classify(future,p['signal']) if p['signal'] else None
        last=float(future[-1]['close']);base=p['historical'][-1]['close'];pred=p['quantiles'][-1]['median']
        out=status_payload('OBSERVED',prediction_id=p['prediction_id'],prediction_start=p['prediction_start'],prediction_end=p['prediction_end'],
            observed_at=request['as_of'],actual=label,tp_first_actual=label=='TP_FIRST' if label else None,
            sl_first_actual=label=='SL_FIRST' if label else None,brier_component=(p['raw_tp_frequency']-(label=='TP_FIRST'))**2 if label in ('TP_FIRST','SL_FIRST','NEITHER') else None,
            directional_correct=(last-base)*(pred-base)>0,mae=sum(abs(b['close']-q['median']) for b,q in zip(future,p['quantiles']))/len(future),
            market_source=request['source'],partition=p['partition'])
        journal.append('OUTCOME',out,'kronos-'+digest(['OUTCOME',p['prediction_id']]))
        outcomes.add(p['prediction_id']);observed+=1
    return dict(newly_observed=observed,pending_count=len(pending),pending=pending[:20],scope='MATURE_FORECASTS_IN_JOURNAL_READ_WINDOW')

def report_failure(journal,exc):
    reason=str(exc) if isinstance(exc,(ValueError,RuntimeError)) and str(exc).isupper() else type(exc).__name__
    payload=status_payload('KRONOS_UNAVAILABLE',reason=reason,pid=os.getpid())
    try:journal.append('STATUS',payload)
    except Exception:payload['journal_status']='UNAVAILABLE_NOT_PERSISTED'
    print(json.dumps(dict(payload,broker_orders=0)),flush=True)

@contextmanager
def instance_lock(root):
    # File byte lock releases automatically on crash. Does not lock or stop Shadow.
    import msvcrt
    path=Path(root)/'.local/kronos/observer.lock';path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as f:
        f.seek(0);f.write(b'0');f.flush();f.seek(0)
        try:msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:raise RuntimeError('KRONOS_OBSERVER_ALREADY_RUNNING') from None
        try:yield
        finally:f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)

def run(root,once=False,study=None,config_path=None):
    root=Path(root);config=load(root,config_path);journal=PostgreSQLJournal(root);service=KronosPredictionService(root,config,LocalKronosAdapter(root,config))
    stop=root/'.local/kronos/observer.stop'
    with instance_lock(root):
        try:
            while not stop.exists():
                try:
                    snapshot=journal.read(study);request,observations=source_request(root,snapshot['source'],config,with_observations=True)
                    if not 0<=(utcnow()-instant(request['as_of'])).total_seconds()<=config['max_input_age_seconds']:raise ValueError('STALE_SHADOW_SOURCE')
                    existing=[e['payload'] for e in snapshot['events'] if e['kind']=='PREDICTION']
                    # Persistent cache: don't infer again after a restart when an identical closed window exists.
                    from .features import validate_input
                    from .config import config_hash
                    meta=validate_input(request,config)
                    evaluation=finalize_predictions(journal,snapshot['events'],request,observations)
                    key=digest([request['symbol'],request['timeframe'],meta['candle_timestamp'],config['model_version'],config['tokenizer_version'],config_hash(config),meta['input_hash']])
                    found=next((p for p in existing if p['cache_key']==key and p.get('signal')==request.get('signal') and p.get('profile_state')==request.get('profile_state')),None)
                    if found:result=found
                    else:
                        reusable=next((p for p in existing if p['cache_key']==key),None)
                        if reusable and key not in service.cache:service.restore_forecast(reusable)
                        outcomes={e['payload']['prediction_id']:e['payload'] for e in snapshot['events'] if e['kind']=='OUTCOME'}
                        records=[dict(p,**{k:v for k,v in outcomes[p['prediction_id']].items() if k not in ('scope','status')}) for p in existing if p['prediction_id'] in outcomes]
                        result=service.submit(request,records).result(timeout=600)
                        journal.append('PREDICTION',result,result['prediction_id'])
                    journal.append('STATUS',status_payload(result['status'],last_prediction=result['prediction_id'],telemetry=result['telemetry'],diagnostics=result.get('diagnostics'),evaluation=evaluation,pid=os.getpid(),cached=found is not None))
                    print(json.dumps(dict(status=result['status'],prediction_id=result['prediction_id'],cached=found is not None,broker_orders=0)),flush=True)
                except Exception as exc:
                    report_failure(journal,exc)
                    if once:raise
                if once:break
                for _ in range(int(config['poll_seconds'])):
                    if stop.exists():break
                    time.sleep(1)
        finally:
            service.close()
            if not once:report_failure(journal,RuntimeError('OBSERVER_STOPPED'))

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['Observe','Once','Status','Stop','Resume','Replay']);p.add_argument('--root',default='.');p.add_argument('--study');p.add_argument('--config');a=p.parse_args();root=Path(a.root).resolve()
    if a.action=='Stop':(root/'.local/kronos/observer.stop').write_text('OPERATOR_STOP',encoding='utf-8');print('KRONOS_STOP_REQUESTED');return
    if a.action=='Resume':(root/'.local/kronos/observer.stop').unlink(missing_ok=True);print('KRONOS_OBSERVATION_RESUMABLE');return
    if a.action=='Status':
        from .projection import project
        print(json.dumps(project(PostgreSQLJournal(root).read(a.study)['events']),allow_nan=False));return
    if a.action=='Replay':
        from .replay import run_replay
        run_replay(root,a.config);return
    if (root/'.local/kronos/observer.stop').exists():raise RuntimeError('OBSERVER_STOP_LATCH_ACTIVE_USE_RESUME')
    run(root,a.action=='Once',a.study,a.config)

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(json.dumps(dict(status='KRONOS_UNAVAILABLE',reason=str(exc) if isinstance(exc,(ValueError,RuntimeError)) and str(exc).isupper() else type(exc).__name__)),flush=True)
        raise SystemExit(1)
