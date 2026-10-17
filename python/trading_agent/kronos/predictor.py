from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import json
from pathlib import Path
import statistics
import threading
from .contracts import digest, encoded, utcnow, validate_ohlc, raw_frequencies, validate_signal
from .features import validate_input, future_timestamps
from .config import config_hash
from .calibration import KronosCalibrationEngine
from .evaluation import consensus

def percentile(values, p):
    values=sorted(values); pos=(len(values)-1)*p; a=int(pos); b=min(a+1,len(values)-1)
    return values[a]+(values[b]-values[a])*(pos-a)

class KronosPredictionService:
    def __init__(self, root, config, adapter, clock=utcnow):
        self.root,self.config,self.adapter,self.clock=Path(root),config,adapter,clock
        self.state='KRONOS_UNAVAILABLE'; self.cache={}; self.lock=threading.Lock()
        self.queue=ThreadPoolExecutor(max_workers=1,thread_name_prefix='kronos-local');self.pending={}

    def close(self): self.queue.shutdown(wait=True)

    def restore_forecast(self, prediction):
        """Reuse immutable trajectories after restart; reassess costs without reinference."""
        path=(self.root/prediction['samples_artifact']).resolve()
        if path.parent != (self.root/'artifacts/research/kronos/samples').resolve():raise ValueError('SAMPLE_ARTIFACT_SCOPE_INVALID')
        packed=path.read_bytes()
        if hashlib.sha256(packed).hexdigest()!=prediction['samples_sha256']:raise ValueError('SAMPLE_ARTIFACT_HASH_INVALID')
        paths=json.loads(gzip.decompress(packed))
        if len(paths)!=self.config['sample_count'] or any(len(p)!=self.config['pred_len'] for p in paths):raise ValueError('INVALID_SAMPLES_SHAPE')
        if len(self.cache)>=128:del self.cache[next(iter(self.cache))]
        self.cache[prediction['cache_key']]=paths
        self.adapter.telemetry=dict(prediction.get('telemetry',{}),inference_seconds=0.,forecast_reused_from_verified_artifact=True)
        self.adapter.degraded=prediction.get('diagnostics',{}).get('provider_degraded',False) or prediction.get('telemetry',{}).get('cpu_oom_fallback',False)

    def submit(self, request, records=()):
        key=digest([request,self.config])
        with self.lock:
            prior=self.pending.get(key)
            if prior is not None and prior.done() and (prior.cancelled() or prior.exception() is not None):
                del self.pending[key] # Retry a failed inference on the next bounded observer poll.
            if key not in self.pending:
                if sum(not f.done() for f in self.pending.values())>=2:raise RuntimeError('KRONOS_INFERENCE_QUEUE_FULL')
                if len(self.pending)>=128:
                    old=next((k for k,f in self.pending.items() if f.done()),None)
                    if old is not None:del self.pending[old]
                self.pending[key]=self.queue.submit(self.predict,request,records)
            return self.pending[key]

    def predict(self, request, records=()):
        meta=validate_input(request,self.config);validate_signal(request.get('signal'));c=self.config
        from .contracts import instant
        if request.get('partition','FORWARD')=='FORWARD' and not 0 <= (self.clock()-instant(request['as_of'])).total_seconds() <= c['max_input_age_seconds']:
            raise ValueError('FUTURE_OR_STALE_REQUEST')
        cache_key=digest([request['symbol'],request['timeframe'],meta['candle_timestamp'],c['model_version'],c['tokenizer_version'],config_hash(c),meta['input_hash']])
        if cache_key not in self.cache:
            self.state='KRONOS_LOADING'
            try:
                paths=self.adapter.samples(request)
                if len(paths)!=c['sample_count'] or any(len(p)!=c['pred_len'] for p in paths): raise ValueError('INVALID_SAMPLES_SHAPE')
                if len(self.cache)>=128:del self.cache[next(iter(self.cache))]
                self.cache[cache_key]=paths
            except Exception:
                self.state='KRONOS_ERROR'; raise
        paths=self.cache[cache_key]; valid=[]
        for path in paths:
            try:
                for bar in path: validate_ohlc(bar)
                valid.append(path)
            except ValueError:pass
        if not valid:self.state='KRONOS_DEGRADED';raise ValueError('ALL_MODEL_TRAJECTORIES_INVALID')
        self.state='KRONOS_DEGRADED' if len(valid)!=len(paths) or getattr(self.adapter,'degraded',False) else 'KRONOS_READY'
        base=float(request['bars'][-1]['close']); returns=[p[-1]['close']/base-1 for p in valid]
        projected=[]
        for i, at in enumerate(future_timestamps(request,c)):
            closes=[p[i]['close'] for p in valid]; high=[p[i]['high'] for p in valid]; low=[p[i]['low'] for p in valid]
            projected.append(dict(at=at, mean=statistics.mean(closes), median=statistics.median(closes),
                p05=percentile(closes,.05),p25=percentile(closes,.25),p75=percentile(closes,.75),p95=percentile(closes,.95),
                high_median=statistics.median(high),low_median=statistics.median(low)))
        artifact=encoded(paths); packed=gzip.compress(artifact,mtime=0); h=hashlib.sha256(packed).hexdigest()
        relative=Path('artifacts/research/kronos/samples')/(h+'.json.gz');p=self.root/relative;p.parent.mkdir(parents=True,exist_ok=True)
        if not p.exists():
            with p.open('xb') as f:f.write(packed)
        elif p.read_bytes()!=packed:raise ValueError('SAMPLE_ARTIFACT_CONFLICT')
        signal=request.get('signal'); frequency=raw_frequencies(paths,signal) if signal else dict(raw_tp_frequency=None,raw_sl_frequency=None,neither_frequency=None,invalid_frequency=(len(paths)-len(valid))/len(paths),sample_count=len(paths),frequency_label='RAW_KRONOS_TP_FREQUENCY')
        identity=[cache_key,signal]
        if 'profile_state' in request:identity.append(request['profile_state'])
        result=dict(prediction_id='kronos-'+digest(identity),cache_key=cache_key,scope='KRONOS_OBSERVATION_ONLY',execution_authority=False,live_enabled=False,
            symbol=request['symbol'],timeframe=request['timeframe'],created_at=self.clock().isoformat(),model=c['model'],model_version=c['model_version'],tokenizer=c['tokenizer'],tokenizer_version=c['tokenizer_version'],
            config_hash=config_hash(c),max_prediction_age_seconds=c['max_prediction_age_seconds'],lookback=c['lookback'],pred_len=c['pred_len'],temperature=c['temperature'],top_p=c['top_p'],**meta,**frequency,
            profile_state=request.get('profile_state'),signal=signal,signal_id=signal.get('signal_id') if signal else None,strategy_id=signal.get('strategy_id') if signal else None,
            geometry_bucket=signal.get('geometry_bucket') if signal else None,regime=request.get('regime','UNKNOWN'),partition=request.get('partition','FORWARD'),
            predicted_return_mean=statistics.mean(returns),predicted_return_median=statistics.median(returns),predicted_volatility=statistics.pstdev(returns),
            quantiles=projected,return_distribution=returns,samples_artifact=str(relative).replace('\\','/'),samples_sha256=h,
            historical=[dict(at=b['opened_at'],open=float(b['open']),high=float(b['high']),low=float(b['low']),close=float(b['close'])) for b in request['bars'][-50:]],
            telemetry=dict(getattr(self.adapter,'telemetry',{})),status=self.state,source=request['source'],execution_profile='COMMON_R1_R5_R10_SHADOW_FEATURE')
        calibration=KronosCalibrationEngine(c).probability(result,list(records)) if signal else dict(state='RAW_ONLY',calibrated_probability=None,lower95=None,upper95=None,bucket=None,sample_size=0,comparable_samples=0,metrics={})
        result['calibration']=calibration;result['calibrated_probability']=calibration['calibrated_probability'];result['calibration_state']=calibration['state']
        result['consensus']=consensus(signal,result,calibration,c,request.get('features'),request.get('profile_state'))
        reasons=[]
        if len(valid)!=len(paths):reasons.append('INVALID_MODEL_OHLC_TRAJECTORIES')
        if getattr(self.adapter,'degraded',False):reasons.append('PROVIDER_CPU_OOM_FALLBACK')
        result['diagnostics']=dict(inference_health='DEGRADED' if reasons else 'HEALTHY',reasons=reasons,
            valid_paths=len(valid),invalid_paths=len(paths)-len(valid),total_paths=len(paths),
            bands_evidence='CONDITIONAL_ON_VALID_MODEL_TRAJECTORIES_NOT_CALIBRATED_CONFIDENCE',
            provider_degraded=getattr(self.adapter,'degraded',False),
            calibration_reason='NO_ELIGIBLE_TECHNICAL_SIGNAL' if not signal else calibration['state'],
            minimum_calibration_samples=c['minimum_calibration_samples'],minimum_bucket_samples=c['minimum_bucket_samples'])
        return result
