import hashlib
import json
import math
from datetime import datetime, timezone

STATES = ('KRONOS_READY', 'KRONOS_LOADING', 'KRONOS_UNAVAILABLE', 'KRONOS_DEGRADED', 'KRONOS_ERROR')
TIMEFRAMES = {'15m': 900, '1H': 3600, '4H': 14400}

def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')

def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()

def instant(value):
    at = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if at.tzinfo is None: raise ValueError('UTC_TIMESTAMP_REQUIRED')
    return at.astimezone(timezone.utc)

def utcnow(): return datetime.now(timezone.utc)

def finite(value):
    if isinstance(value, bool): raise ValueError('FINITE_NUMBER_REQUIRED')
    n = float(value)
    if not math.isfinite(n): raise ValueError('FINITE_NUMBER_REQUIRED')
    return n

def validate_ohlc(bar):
    o, h, l, c = (finite(bar[k]) for k in ('open', 'high', 'low', 'close'))
    if not 0 < l <= min(o, c) <= max(o, c) <= h: raise ValueError('CORRUPT_OHLC')
    return [o, h, l, c]

def validate_signal(signal):
    if signal is None: return
    entry, stop, target = (finite(signal[k]) for k in ('entry', 'stop_loss', 'take_profit'))
    if signal['direction'] == 'LONG': valid = 0 < stop < entry < target
    elif signal['direction'] == 'SHORT': valid = 0 < target < entry < stop
    else: valid = False
    if not valid: raise ValueError('INVALID_SIGNAL_GEOMETRY')

def classify(path, signal):
    """Adverse open gaps first; stop first on ambiguous OHLC; no favorable gap credit."""
    validate_signal(signal)
    if not path: return 'INVALID'
    # A barrier hit must not hide corrupt later steps of the sampled trajectory.
    try: bars = [validate_ohlc(bar) for bar in path]
    except (ValueError, KeyError, TypeError): return 'INVALID'
    long = signal['direction'] == 'LONG'; stop = signal['stop_loss']; target = signal['take_profit']
    for o, h, l, _ in bars:
        if (o <= stop if long else o >= stop): return 'SL_FIRST'
        sl = l <= stop if long else h >= stop
        tp = h >= target if long else l <= target
        if sl: return 'SL_FIRST'
        if tp: return 'TP_FIRST'
    return 'NEITHER'

def raw_frequencies(paths, signal):
    labels = [classify(p, signal) for p in paths]
    n = len(labels)
    return dict(raw_tp_frequency=labels.count('TP_FIRST') / n if n else None,
                raw_sl_frequency=labels.count('SL_FIRST') / n if n else None,
                neither_frequency=labels.count('NEITHER') / n if n else None,
                invalid_frequency=labels.count('INVALID') / n if n else None,
                frequency_label='RAW_KRONOS_TP_FREQUENCY', sample_count=n)
