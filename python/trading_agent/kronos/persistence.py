import hashlib
import json
import os
from pathlib import Path
import subprocess
from .contracts import encoded, digest

def profile_state_from_source(event):
    """Only authenticated Shadow inventory/equity, never an IBKR account balance."""
    from .contracts import finite, instant
    from zoneinfo import ZoneInfo
    day=instant(event['at']).astimezone(ZoneInfo('America/Santo_Domingo')).date().isoformat()
    metrics=event.get('state',{}).get('portfolio_metrics',{})
    out={}
    for name in ('R1','R5','R10'):
        m=metrics.get('EURUSD_'+name,{})
        try:
            equity=finite(m['equity_realized']);consumed=finite(m['consumed_loss']);pending=m['pending_position']
            if min(equity,consumed)<0 or not isinstance(m['daily_stops'],dict):raise ValueError('INVALID_PROFILE_STATE')
            # The source simulator has a single position/reservation; none when flat.
            reserved=0. if pending is None else finite(pending['decision']['quantity'])*finite(pending['entry_midpoint'])+finite(pending['decision']['costs'])
            out[name]=dict(equity=equity,consumed_loss=consumed,reserved_usd=reserved,pending=pending is not None,
                stopped_day=day in m['daily_stops'],quality='VERIFIED_SHADOW_JOURNAL')
        except (KeyError,TypeError,ValueError):out[name]=dict(quality='UNKNOWN')
    return out

class PostgreSQLJournal:
    def __init__(self,root):self.root=Path(root)
    def call(self,data):
        allowed=('PATH','SystemRoot','TEMP','TMP','TRADING_LAB_DB')
        env={k:v for k,v in os.environ.items() if k.upper() in (x.upper() for x in allowed)}
        p=subprocess.run(['dotnet',str(self.root/'src/TradingAgent.Api/bin/Release/net9.0/TradingAgent.Api.dll'),'--kronos-journal'],
            input=encoded(data).decode(),text=True,capture_output=True,env=env,cwd=self.root,timeout=20)
        try:out=json.loads(p.stdout)
        except ValueError:raise RuntimeError('KRONOS_POSTGRES_UNAVAILABLE') from None
        if p.returncode or out.get('error'):raise RuntimeError('KRONOS_POSTGRES_UNAVAILABLE_OR_CONFLICT')
        return out
    def read(self,study=None):return self.call(dict(action='read',study=study))
    def append(self,kind,payload,id=None):
        text=encoded(payload).decode();id=id or 'kronos-'+digest([kind,payload])
        return self.call(dict(action='append',id=id,kind=kind,payload=text,hash=hashlib.sha256(text.encode()).hexdigest()))

def source_request(root,source,config,with_observations=False):
    """Verify the existing immutable Shadow event and content-addressed IBKR archive."""
    from .contracts import instant, TIMEFRAMES
    from datetime import timedelta
    if not source:raise ValueError('SHADOW_MARKET_SOURCE_MISSING')
    event=source['payload'];r=event['revision'] if 'revision' in event else None
    # Shadow revision is represented in the stored hash material; obtain it below in the source wrapper.
    revision=source.get('revision',r)
    if revision is None or digest([revision,event,source['previous']])!=source['hash']:raise ValueError('SHADOW_SOURCE_HASH_INVALID')
    if event.get('classification')!='SIMULATED_SHADOW' or event.get('broker_orders')!=0 or event.get('live_enabled') is not False:raise ValueError('SHADOW_READ_ONLY_REQUIRED')
    details=event['details'];archive=details['history_source'];path=(Path(root)/archive['path']).resolve()
    base=(Path(root)/'artifacts/research/eurusd-shadow/market-data').resolve()
    if path.parent!=base or path.stem!=archive['sha256']:raise ValueError('SOURCE_ARTIFACT_SCOPE_INVALID')
    raw=json.loads(path.read_bytes())
    if digest(raw)!=archive['sha256'] or raw['source']!='AUTHENTIC_IBKR_PAPER_READ_ONLY':raise ValueError('SOURCE_ARCHIVE_INTEGRITY_FAILURE')
    at=event['at'];step=TIMEFRAMES[config['timeframe']];key=str(step//60);original=raw['originals'][key]
    # IBKR wire history is a list of parsed opened_at OHLC values, not synthesized volume.
    bars=[{k:b[k] for k in ('opened_at','open','high','low','close')} for b in original
          if instant(b['opened_at'])+timedelta(seconds=step)<=instant(at) and instant(b['opened_at']).timestamp()%step==0]
    observations=bars
    bars=bars[-config['lookback']:]
    signal=None
    if config['timeframe']=='1H' and bars:
        from trading_agent.research_analysis import analyze
        from trading_agent.eurusd_cost_aware_search import catalogue,signals
        analysis=analyze(dict(instrument='EUR/USD',source='IBKR_TWS',what_to_show='MIDPOINT',as_of=at,
            indicators=json.loads((Path(root)/'config/research-indicators.json').read_bytes()),calendar=raw['calendar'],originals=raw['originals']))
        candidate=next(x for x in catalogue() if x['family']=='trend' and x['minutes']==60 and x['horizon']=='swing')
        closed=instant(bars[-1]['opened_at'])+timedelta(seconds=step)
        row=next((r for r in reversed(signals(analysis,candidate)) if instant(r['entry_at'])==closed and r['side'] and not r['reasons']),None)
        if row:
            entry=float(row['entry_midpoint']);side=1 if row['side']=='BUY' else -1
            signal=dict(signal_id=row['opportunity_id'],strategy_id=candidate['id'],direction='LONG' if side==1 else 'SHORT',entry=entry,
                stop_loss=entry-side*float(row['stop_distance']),take_profit=entry+side*float(row['take_profit_distance']),geometry_bucket='FROZEN_2_ATR_STRUCTURE_12_ATR_TARGET')
    request=dict(symbol='EUR/USD',timeframe=config['timeframe'],as_of=at,bars=bars,signal=signal,
        regime=details.get('features',{}).get('regime','UNKNOWN'),features=details.get('features',{}),partition='FORWARD',profile_state=profile_state_from_source(event),
        source=dict(quality='AUTHENTIC',sha256=archive['sha256'],event_hash=source['hash'],study=event['study_id'],path=archive['path'],provider='IBKR_PAPER_MIDPOINT',
            partial_session_bars_excluded=sum(instant(b['opened_at']).timestamp()%step!=0 for b in original),missing_bars_not_filled=True))
    # Full authenticated archive is used only to score past forecasts. Model context stays unchanged.
    return (request,observations) if with_observations else request
