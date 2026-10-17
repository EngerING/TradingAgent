from datetime import timedelta
from .contracts import instant, validate_ohlc, TIMEFRAMES, digest, finite

def validate_input(request, config):
    if request.get('symbol') != config['symbol'] or request.get('timeframe') != config['timeframe']: raise ValueError('INPUT_SCOPE_MISMATCH')
    at = instant(request['as_of']); step = TIMEFRAMES[config['timeframe']]; bars = request['bars']
    if len(bars) != config['lookback']: raise ValueError('EXACT_LOOKBACK_REQUIRED')
    previous = None; volume_modes = set(); missing = 0
    for bar in bars:
        t = instant(bar['opened_at']); validate_ohlc(bar)
        if t.timestamp() % step != 0: raise ValueError('BAR_ALIGNMENT_REQUIRED')
        if t + timedelta(seconds=step) > at: raise ValueError('FUTURE_OR_INCOMPLETE_BAR')
        if previous is not None:
            delta = (t - previous).total_seconds()
            if delta <= 0: raise ValueError('UNORDERED_OR_DUPLICATE_TIMESTAMP')
            if delta % step != 0 or delta > config['max_gap_seconds']: raise ValueError('MISSING_CANDLES')
            missing += int(delta//step)-1
            if missing > config.get('maximum_missing_candles',0): raise ValueError('EXCESSIVE_MISSING_CANDLES')
        previous = t
        present = bar.get('volume') is not None or bar.get('amount') is not None
        if present:
            if bar.get('volume_evidence') != 'VERIFIED' or bar.get('amount') is None or bar.get('volume') is None:
                raise ValueError('SYNTHETIC_NOT_ALLOWED')
            if finite(bar['volume']) < 0 or finite(bar['amount']) < 0: raise ValueError('INVALID_VOLUME')
        volume_modes.add('WITH_VOLUME' if present else 'WITHOUT_VOLUME')
    if len(volume_modes) != 1: raise ValueError('INCONSISTENT_VOLUME_EVIDENCE')
    closed = previous + timedelta(seconds=step)
    if not 0 <= (at - closed).total_seconds() <= config['max_input_age_seconds']: raise ValueError('STALE_INPUT')
    source = request.get('source', {})
    if source.get('quality') != 'AUTHENTIC' or not source.get('sha256'): raise ValueError('AUTHENTIC_PROVENANCE_REQUIRED')
    # Request hash binds input values as well as the configured model and timeframe.
    return dict(volume_mode=volume_modes.pop(), input_hash=digest(bars), missing_candles=missing, input_window_start=bars[0]['opened_at'],
                input_window_end=closed.isoformat(), candle_timestamp=closed.isoformat(),
                prediction_start=closed.isoformat(), prediction_end=(closed + timedelta(seconds=step*config['pred_len'])).isoformat())

def future_timestamps(request, config):
    step = TIMEFRAMES[config['timeframe']]
    start = instant(request['bars'][-1]['opened_at']) + timedelta(seconds=step)
    # Calendar timestamps only; no future market values are provided to the model.
    return [(start + timedelta(seconds=step*i)).isoformat() for i in range(config['pred_len'])]
