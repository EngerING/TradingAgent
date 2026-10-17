"""Offline analysis protocol. No broker, database credentials or AI client imports."""
from bisect import bisect_right
from dataclasses import asdict
from datetime import datetime,timezone
import hashlib
import json
from .research_calendar import ForexCalendar,normalize,stamp
from .research_indicators import settings,calculate


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


STRATEGIES=[
    {'id':'trend','name':'Trend following','entry_rule':'15m EMA fast/slow cross; 1h same trend; 4h ready and not opposite',
     'exit_rule':'ATR stop or ATR target, stop first on ambiguity, opposite 15m EMA cross, or higher timeframe invalidation',
     'invalidation_rule':'Higher timeframe missing/opposite, incomplete entry bar, gap or unknown costs'},
    {'id':'pullback','name':'Trend pullback','entry_rule':'15m trend; candle touches EMA fast and closes back beyond it; 1h confirms; 4h ready and not opposite',
     'exit_rule':'ATR stop or ATR target, stop first on ambiguity, opposite 15m EMA cross, or higher timeframe invalidation',
     'invalidation_rule':'Higher timeframe missing/opposite, incomplete entry bar, gap or unknown costs'},
    {'id':'mean_reversion','name':'Mean reversion','entry_rule':'15m SIDEWAYS and RSI crosses back above 30 or below 70; no mandatory three-way alignment',
     'exit_rule':'ATR stop or ATR target, stop first on ambiguity, or RSI reaches 50',
     'invalidation_rule':'15m no longer sideways, incomplete entry bar, gap or unknown costs'}
]


def analyze(payload):
    if payload.get('instrument')!='EUR/USD' or payload.get('source')!='IBKR_TWS' or payload.get('what_to_show')!='MIDPOINT':
        raise ValueError('UNSUPPORTED_RESEARCH_SOURCE')
    cutoff=stamp(payload['as_of']);config=settings(payload.get('indicators'));calendar=ForexCalendar(payload['calendar'])
    config_hash=digest({'indicators':config,'calendar':payload['calendar'],'engine':'research-d-v1'})
    series={};points={};quality={}
    for minutes in (15,60,240):
        rows=payload['originals'][str(minutes)]
        bars,q=normalize(rows,minutes,cutoff,calendar);series[minutes]=bars;quality[str(minutes)]=q
        # Unknown missing expected bars reset warmup. Scheduled breaks never fabricate observations.
        missing=[stamp(x) for x in q['missing_expected_openings']];parts=[];segment=[]
        for bar in bars:
            if segment and any(segment[-1].closed_at<=t<bar.opened_at for t in missing):
                parts.extend(calculate(segment,config));segment=[]
            segment.append(bar)
        parts.extend(calculate(segment,config));points[minutes]=parts
    times={m:[stamp(p['closed_at']) for p in points[m]] for m in points}
    def snapshot(at):
        result={}
        for minutes,role in ((240,'context'),(60,'confirmation'),(15,'entries')):
            index=bisect_right(times[minutes],at)-1
            result[str(minutes)]={'role':role,'as_of':at.isoformat(),'indicators':points[minutes][index] if index>=0 else None,
                                  'status':points[minutes][index]['status'] if index>=0 else 'INSUFFICIENT_DATA'}
        return result
    candidates=[];exit_signals=[];signals={s['id']:0 for s in STRATEGIES};counts={}
    bars=series[15]
    for i,p in enumerate(points[15]):
        if i==0 or p['status']!='READY':continue
        prev=points[15][i-1];bar=bars[i];at=bar.closed_at;multi=snapshot(at)
        direction='BUY' if p['trend']=='UPTREND' else 'SELL' if p['trend']=='DOWNTREND' else None
        cross_up=prev['ema_fast'] is not None and prev['ema_slow'] is not None and prev['ema_fast']<=prev['ema_slow'] and p['ema_fast']>p['ema_slow']
        cross_down=prev['ema_fast'] is not None and prev['ema_slow'] is not None and prev['ema_fast']>=prev['ema_slow'] and p['ema_fast']<p['ema_slow']
        for strategy in ('trend','pullback'):
            higher_ready=all(multi[str(m)]['status']=='READY' for m in (60,240))
            invalidate_buy=not higher_ready or multi['60']['indicators']['trend']!='UPTREND' or multi['240']['indicators']['trend']=='DOWNTREND'
            invalidate_sell=not higher_ready or multi['60']['indicators']['trend']!='DOWNTREND' or multi['240']['indicators']['trend']=='UPTREND'
            if cross_up or invalidate_sell:exit_signals.append({'strategy_id':strategy,'side':'SELL','at':at.isoformat()})
            if cross_down or invalidate_buy:exit_signals.append({'strategy_id':strategy,'side':'BUY','at':at.isoformat()})
        if p['trend']!='SIDEWAYS' or p['rsi']>=50:exit_signals.append({'strategy_id':'mean_reversion','side':'BUY','at':at.isoformat()})
        if p['trend']!='SIDEWAYS' or p['rsi']<=50:exit_signals.append({'strategy_id':'mean_reversion','side':'SELL','at':at.isoformat()})
        hypotheses=[]
        if cross_up or cross_down:hypotheses.append(('trend','BUY' if cross_up else 'SELL'))
        if direction and ((direction=='BUY' and bar.low<=p['ema_fast']<bar.close) or (direction=='SELL' and bar.high>=p['ema_fast']>bar.close)):
            hypotheses.append(('pullback',direction))
        if p['trend']=='SIDEWAYS' and prev['rsi'] is not None:
            if prev['rsi']<=30<p['rsi']:hypotheses.append(('mean_reversion','BUY'))
            elif prev['rsi']>=70>p['rsi']:hypotheses.append(('mean_reversion','SELL'))
        for strategy,side in hypotheses:
            signals[strategy]+=1;reasons=[];higher='UPTREND' if side=='BUY' else 'DOWNTREND';opposite='DOWNTREND' if side=='BUY' else 'UPTREND'
            if strategy!='mean_reversion':
                if any(multi[str(m)]['status']!='READY' for m in (60,240)):reasons.append('MULTITIMEFRAME_INSUFFICIENT_DATA')
                else:
                    if multi['60']['indicators']['trend']!=higher or multi['240']['indicators']['trend']==opposite:
                        reasons.append('MULTITIMEFRAME_CONTRADICTION')
            entry=bars[i+1] if i+1<len(bars) else None
            if entry is None:reasons.append('NO_NEXT_CLOSED_BAR')
            elif entry.opened_at!=at:reasons.append('ENTRY_GAP')
            stop=max(.00005,p['atr']*config['stop_atr']);take=max(.00005,p['atr']*config['take_atr'])
            candidates.append({'strategy_id':strategy,'side':side,'signal_at':at.isoformat(),
                               'entry_at':None if entry is None else entry.opened_at.isoformat(),
                               'entry_midpoint':None if entry is None else entry.open,
                               'stop_distance':stop,'take_profit_distance':take,'reasons':reasons,
                               'context':multi})
    for minutes in (15,60,240):
        names=('rsi','ema_fast','ema_slow','macd','macd_signal','macd_histogram','atr','ema_fast_slope','ema_slow_slope','log_return_std','range','atr_ratio')
        counts[str(minutes)]={k:sum(p[k] is not None for p in points[minutes]) for k in names}
    strategies=[{**s,'version':1,'parameters_hash':config_hash,'stop_rule':f"max(0.00005, ATR * {config['stop_atr']})",
                 'take_profit_rule':f"max(0.00005, ATR * {config['take_atr']})",'risk_rule':'Existing C# RiskEngine, allocation USD100, accumulated losses USD20; no execution'} for s in STRATEGIES]
    normalized={str(m):[{**asdict(c),'opened_at':c.opened_at.isoformat()} for c in series[m]] for m in series}
    # All features use closes <= cutoff. Dataset identity includes the original evidence separately.
    return {'schema_version':1,'engine_version':'research-d-v1','instrument':'EUR/USD','source':'IBKR_TWS','what_to_show':'MIDPOINT',
            'as_of':cutoff.isoformat(),'dataset_hash':digest(payload['originals']),'config_hash':config_hash,
            'parameters':config,'calendar':payload['calendar'],'quality':quality,'normalized':normalized,
            'indicator_points':{str(m):points[m] for m in points},'usable_counts':counts,'latest':snapshot(cutoff),
            'strategies':strategies,'signal_counts':signals,'candidates':candidates,'exit_signals':exit_signals,
            'evaluation_status':'INCOMPLETE','net_profit':None,'costs_status':'UNKNOWN_HISTORICAL_SPREAD_COMMISSIONS_SLIPPAGE_AND_CONTRACT_RESTRICTIONS',
            'sample_status':'TECHNICAL_DEMONSTRATION_ONLY_NO_PROFITABILITY_CONCLUSION',
            'live_enabled':False,'orders_supported':False,'openai_enabled':False}


if __name__=='__main__':
    import sys
    try:
        payload=json.load(sys.stdin)
        print(json.dumps(analyze(payload),allow_nan=False),flush=True)
    except Exception:
        print('RESEARCH_ANALYSIS_FAILED',file=sys.stderr);raise SystemExit(1)
