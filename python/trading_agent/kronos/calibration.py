import math
from .contracts import instant

def bucket(p):
    if p < .5: return 'below50'
    if p >= .8: return '80%+'
    lo = int((p*100 + 1e-8)//5)*5
    return f'{lo}-{lo+5}%'

def wilson(success, n):
    if not n: return [None, None]
    z = 1.95996398454; p = success/n; denominator = 1+z*z/n
    mid = (p+z*z/(2*n))/denominator
    width = z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/denominator
    return [max(0, mid-width), min(1, mid+width)]

def metrics(records):
    # NEITHER is a non-TP outcome, never silently removed to inflate TP probability.
    rows = [r for r in records if r.get('actual') in ('TP_FIRST','SL_FIRST','NEITHER') and r.get('raw_tp_frequency') is not None]
    n = len(rows); buckets = []
    for label in ['below50','50-55%','55-60%','60-65%','65-70%','70-75%','75-80%','80%+']:
        group = [r for r in rows if bucket(r['raw_tp_frequency']) == label]; count = len(group)
        observed = sum(r['actual']=='TP_FIRST' for r in group)/count if count else None
        mean = sum(r['raw_tp_frequency'] for r in group)/count if count else None
        buckets.append(dict(bucket=label, samples=count, observed_tp_rate=observed, average_probability=mean,
                            confidence_interval=wilson(sum(r['actual']=='TP_FIRST' for r in group), count)))
    return dict(sample_size=n, brier_score=sum((r['raw_tp_frequency']-(r['actual']=='TP_FIRST'))**2 for r in rows)/n if n else None,
        log_loss=-sum(math.log(max(1e-8,min(1-1e-8,r['raw_tp_frequency'] if r['actual']=='TP_FIRST' else 1-r['raw_tp_frequency']))) for r in rows)/n if n else None,
        calibration_error=sum(b['samples']*abs(b['average_probability']-b['observed_tp_rate']) for b in buckets if b['samples'])/n if n else None,
        observed_tp_rate=sum(r['actual']=='TP_FIRST' for r in rows)/n if n else None,
        tp_first_accuracy=sum((r['raw_tp_frequency']>=.5)==(r['actual']=='TP_FIRST') for r in rows)/n if n else None, buckets=buckets)

class KronosCalibrationEngine:
    def __init__(self, config): self.config = config

    def probability(self, prediction, records):
        keys = ('symbol','timeframe','model_version','tokenizer_version','config_hash','regime','strategy_id','geometry_bucket')
        start = instant(prediction['prediction_start']); selected = []; prior_end = None
        for r in sorted(records, key=lambda x: x['prediction_start']):
            if any(r.get(k) != prediction.get(k) for k in keys): continue
            if r.get('partition') != 'CALIBRATION' or r.get('actual') not in ('TP_FIRST','SL_FIRST','NEITHER'): continue
            if r.get('invalid_frequency',0)>0 or r.get('raw_tp_frequency') is None: continue
            # Embargo: outcome known before the new inference; no overlapping calibration observations.
            if instant(r['prediction_end']) > start or instant(r['observed_at']) > start: continue
            if prior_end and instant(r['prediction_start']) < prior_end: continue
            selected.append(r); prior_end = instant(r['prediction_end'])
        stats = metrics(selected); label = bucket(prediction['raw_tp_frequency']) if prediction.get('raw_tp_frequency') is not None else None
        group = [r for r in selected if bucket(r['raw_tp_frequency']) == label]
        result = dict(state='CALIBRATION_INSUFFICIENT', calibrated_probability=None, lower95=None, upper95=None,
                      bucket=label, sample_size=len(group), comparable_samples=len(selected), metrics=stats,
                      evidence='HISTORICAL_OBSERVED_NOT_MODEL_CONFIDENCE')
        if prediction.get('invalid_frequency', 0) > 0: result['state']='CALIBRATION_DEGRADED'; return result
        if len(selected) < self.config['minimum_calibration_samples'] or len(group) < self.config['minimum_bucket_samples']: return result
        if stats['calibration_error'] > self.config['maximum_calibration_error']: result['state']='CALIBRATION_DEGRADED'; return result
        wins = sum(r['actual']=='TP_FIRST' for r in group); low, high = wilson(wins,len(group))
        result.update(state='CALIBRATED', calibrated_probability=wins/len(group), lower95=low, upper95=high)
        return result
