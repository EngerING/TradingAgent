import json
import re
from pathlib import Path
from .contracts import digest, finite, TIMEFRAMES

def load(root, path=None):
    c = json.loads((Path(path) if path else Path(root)/'config/kronos/observation.json').read_bytes())
    if c['scope'] != 'KRONOS_OBSERVATION_ONLY' or c['live_enabled'] is not False or c['paper_eligible'] is not False:
        raise ValueError('KRONOS_OBSERVATION_SCOPE_REQUIRED')
    if c['symbol'] != 'EUR/USD' or c['timeframe'] not in TIMEFRAMES: raise ValueError('INVALID_INSTRUMENT_TIMEFRAME')
    if c['model'] != 'NeoQuasar/Kronos-base' or c['tokenizer'] != 'NeoQuasar/Kronos-Tokenizer-base': raise ValueError('PINNED_BASE_MODEL_REQUIRED')
    for k in ('upstream_commit', 'model_version', 'tokenizer_version'):
        if not re.fullmatch('[a-f0-9]{40}', c[k]): raise ValueError('PINNED_REVISION_REQUIRED')
    for k, low, high in [('lookback', 16, 512), ('pred_len', 1, 128), ('sample_count', 2, 128), ('batch_size', 1, 16), ('seed', 0, 2**31-1), ('replay_maximum_predictions', 1, 200)]:
        if type(c[k]) is not int or not low <= c[k] <= high: raise ValueError('INVALID_' + k.upper())
    if not 0 < finite(c['temperature']) <= 2 or not 0 < finite(c['top_p']) <= 1: raise ValueError('INVALID_SAMPLING')
    if c['device'] not in ('auto', 'cpu', 'cuda'): raise ValueError('INVALID_DEVICE')
    if c['sealed_final_test'] is not True or c['exposure_cap_usd'] != 100: raise ValueError('RESEARCH_BOUNDARY_REQUIRED')
    for key in ('max_prediction_age_seconds', 'max_input_age_seconds', 'max_gap_seconds', 'poll_seconds', 'minimum_calibration_samples', 'minimum_bucket_samples', 'replay_stride_bars'):
        if finite(c[key]) <= 0: raise ValueError('POSITIVE_LIMIT_REQUIRED')
    if c['replay_stride_bars'] < c['pred_len']: raise ValueError('NON_OVERLAPPING_REPLAY_REQUIRED')
    for key in ('commission_round_trip_usd', 'spread_usd_per_eur', 'slippage_usd_per_eur_per_side', 'gap_usd_per_eur', 'economic_uncertainty_usd'):
        if finite(c[key]) < 0: raise ValueError('NONNEGATIVE_COST_REQUIRED')
    return c

def config_hash(c): return digest(c)
