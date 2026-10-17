"""Seeded EMA and Wilder RSI/ATR, with explicit null warmup and causal rolling metrics."""
from math import log
from statistics import pstdev
from .market import ema,rsi,atr


DEFAULTS=dict(rsi=14,ema_fast=20,ema_slow=50,macd_fast=12,macd_slow=26,macd_signal=9,
              atr=14,volatility=20,slope=1,trend_gap_atr=.25,trend_slope_atr=.03,
              high_volatility_atr_ratio=.002,low_volatility_atr_ratio=.0004,stop_atr=2.,take_atr=3.)


def settings(overrides=None):
    config={**DEFAULTS,**(overrides or {})}
    if set(config)!=set(DEFAULTS):raise ValueError('UNKNOWN_INDICATOR_PARAMETER')
    for key in ('rsi','ema_fast','ema_slow','macd_fast','macd_slow','macd_signal','atr','volatility','slope'):
        if type(config[key]) is not int or not 1<=config[key]<=1000:raise ValueError('INVALID_INDICATOR_PERIOD')
    if config['ema_fast']>=config['ema_slow'] or config['macd_fast']>=config['macd_slow']:raise ValueError('INVALID_PERIOD_ORDER')
    for key in set(DEFAULTS)-{'rsi','ema_fast','ema_slow','macd_fast','macd_slow','macd_signal','atr','volatility','slope'}:
        if not 0<config[key]<100:raise ValueError('INVALID_THRESHOLD')
    if config['low_volatility_atr_ratio']>=config['high_volatility_atr_ratio']:raise ValueError('INVALID_VOLATILITY_THRESHOLDS')
    return config


def calculate(candles, config):
    closes=[c.close for c in candles];n=len(candles)
    fast,slow=ema(closes,config['ema_fast']),ema(closes,config['ema_slow'])
    mfast,mslow=ema(closes,config['macd_fast']),ema(closes,config['macd_slow'])
    line=[None if a is None or b is None else a-b for a,b in zip(mfast,mslow)]
    start=config['macd_slow']-1
    signal=[None]*min(start,n)+ema(line[start:],config['macd_signal'])
    strength=rsi(closes,config['rsi']);ranges=atr(candles,config['atr']);points=[]
    for i,c in enumerate(candles):
        def slope(values):
            k=config['slope']
            return None if i<k or values[i] is None or values[i-k] is None else (values[i]-values[i-k])/k
        returns=[log(closes[j]/closes[j-1]) for j in range(i-config['volatility']+1,i+1)] if i>=config['volatility'] else None
        p={'closed_at':c.closed_at.isoformat(),'rsi':strength[i],'ema_fast':fast[i],'ema_slow':slow[i],
           'macd':line[i],'macd_signal':signal[i],'macd_histogram':None if signal[i] is None else line[i]-signal[i],
           'atr':ranges[i],'ema_fast_slope':slope(fast),'ema_slow_slope':slope(slow),
           'log_return_std':None if returns is None else pstdev(returns),'range':c.high-c.low,
           'atr_ratio':None if ranges[i] is None else ranges[i]/c.close}
        ready=all(p[k] is not None for k in ('rsi','ema_fast','ema_slow','macd_signal','atr','ema_slow_slope','log_return_std'))
        trend='INDETERMINATE';volatility='INDETERMINATE'
        if ready:
            a=p['atr'];gap=fast[i]-slow[i];s=p['ema_slow_slope'];f=p['ema_fast_slope']
            trend='UPTREND' if gap>config['trend_gap_atr']*a and s>config['trend_slope_atr']*a and f>0 else \
                  'DOWNTREND' if gap<-config['trend_gap_atr']*a and s<-config['trend_slope_atr']*a and f<0 else 'SIDEWAYS'
            volatility='HIGH' if p['atr_ratio']>=config['high_volatility_atr_ratio'] else 'LOW' if p['atr_ratio']<=config['low_volatility_atr_ratio'] else 'NORMAL'
        points.append({**p,'status':'READY' if ready else 'INSUFFICIENT_DATA','trend':trend,'volatility':volatility})
    return points
