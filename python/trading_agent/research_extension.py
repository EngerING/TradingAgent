"""Six/twelve-month research protocol; authentic schedule and costs remain separate evidence."""
from collections import Counter
from datetime import datetime,timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo
from .history_extension import digest
from .research_analysis import analyze
from .research_calendar import stamp,ForexCalendar,normalize,aggregate_15m

def regional_windows(at):
    return [name for name,zone,first,last in (('TOKYO','Asia/Tokyo',9,18),('LONDON','Europe/London',8,17),('NEW_YORK','America/New_York',8,17))
            if first<=at.astimezone(ZoneInfo(zone)).hour<last] or ['OTHER']

def prepare(manifest,expected):
    if manifest.get('source')!='IBKR_TWS' or manifest.get('instrument')!='EUR/USD' or manifest.get('account_id')!=expected or manifest.get('orders_supported') is not False or manifest.get('live_enabled') is not False:
        raise ValueError('INVALID_ARCHIVE_IDENTITY_OR_SOURCE')
    start,end=stamp(manifest['requested_start']),stamp(manifest['requested_end'])
    if not timedelta(0)<end-start<=timedelta(days=370) or len(manifest['receipts'])>160 or sum(len(p['rows']) for p in manifest['receipts'])>150000:
        raise ValueError('ARCHIVE_RESOURCE_LIMIT_OR_RANGE')
    originals={str(m):{} for m in (15,60,240)};sessions={};coverage=[];quote_bars={};ticks=[];receipts=[];requests=set()
    for p in manifest['receipts']:
        if p['account_id']!=expected or p['source']!='IBKR_TWS' or digest(p['rows'])!=p['content_hash'] or p.get('orders_supported') is not False or p.get('live_enabled') is not False:
            raise ValueError('ARCHIVE_INTEGRITY_FAILED')
        spec=p['request'];kind=spec['kind'];receipts.append({k:p[k] for k in ('request','received_at','availability','error','content_hash')})
        key=digest(spec)
        if key in requests:raise ValueError('DUPLICATE_ARCHIVE_REQUEST')
        requests.add(key)
        if p['availability']!='AVAILABLE':continue
        if kind=='SCHEDULE':
            for schedule in p['rows']:
                zone=ZoneInfo(schedule['time_zone'])
                parse=lambda t:datetime.strptime(t,'%Y%m%d-%H:%M:%S').replace(tzinfo=zone).astimezone(stamp(manifest['requested_end']).tzinfo)
                coverage.append((parse(schedule['start']),parse(schedule['end'])))
                for s in schedule['sessions']:
                    a,b=parse(s['start']),parse(s['end'])
                    if b<=a:raise ValueError('INVALID_IBKR_SESSION')
                    value={'start':a.isoformat(),'end':b.isoformat()}
                    if a in sessions and sessions[a]!=value:raise ValueError('CONFLICTING_IBKR_SESSION')
                    sessions[a]=value
        elif kind=='TICKS':ticks.extend(p['rows'])
        elif kind in ('MIDPOINT','BID_ASK'):
            page_start,page_end=stamp(spec['start']),stamp(spec['end'])
            for row in p['rows']:
                at=stamp(row['opened_at'])
                if row['minutes']!=spec['minutes'] or not page_start<=at<page_end:raise ValueError('BAR_OUTSIDE_ARCHIVE_PAGE')
                target=originals[str(spec['minutes'])] if kind=='MIDPOINT' else quote_bars
                if at in target and target[at]!=row:raise ValueError('CONFLICTING_ARCHIVE_BAR')
                target[at]=row
        else:raise ValueError('UNSUPPORTED_ARCHIVE_KIND')
    # Require schedule response bounds covering the complete requested interval; no inferred holidays.
    merged=[]
    for a,b in sorted(coverage):
        if merged and a<=merged[-1][1]:merged[-1]=(merged[-1][0],max(b,merged[-1][1]))
        else:merged.append((a,b))
    # Last closed Forex session may precede a Saturday cutoff; permit only the ensuing weekend.
    covered=any(a<=start and (b>=end or (b.astimezone(ZoneInfo('America/New_York')).weekday()==4 and end<=b+timedelta(days=2))) for a,b in merged)
    if not covered or not sessions:raise ValueError('HISTORICAL_SCHEDULE_COVERAGE_INCOMPLETE')
    calendar={'version':'ibkr-historical-schedule-v1','timezone':'America/New_York','grid_timezone':'UTC',
        'coverage_start':min(sessions).date().isoformat(),'coverage_end':max(sessions).date().isoformat(),
        'sessions':[sessions[k] for k in sorted(sessions)],'status':'IBKR_HISTORICAL_SCHEDULE','source':'reqHistoricalData SCHEDULE; exact received sessions',
        'schedule_receipts':[r for r in receipts if r['request']['kind']=='SCHEDULE']}
    for m in originals:
        originals[m]=[originals[m][k] for k in sorted(originals[m]) if start<=k<end]
        if not originals[m]:raise ValueError('MISSING_NATIVE_TIMEFRAME')
    spreads=[]
    for at,r in sorted(quote_bars.items()):
        # BID_ASK bars contain time-average bid in open and time-average ask in close.
        bid,ask=Decimal(r['open']),Decimal(r['close'])
        if ask<bid:raise ValueError('INVALID_AVERAGE_BID_ASK')
        spreads.append({'opened_at':at.isoformat(),'closed_at':(at+timedelta(minutes=r['minutes'])).isoformat(),
            'average_bid':str(bid),'average_ask':str(ask),'raw_average_difference':str(ask-bid),
            'spread':str(ask-bid) if ask>bid else None,
            'status':'OBSERVED_BAR_AVERAGE' if ask>bid else 'UNKNOWN_ZERO_AVERAGE_DIFFERENCE',
            'execution_spread_status':'ESTIMATED_IF_USED_FOR_EXECUTION' if ask>bid else 'UNKNOWN','source':'IBKR_BID_ASK','minutes':r['minutes']})
    for t in ticks:
        if Decimal(t['ask'])<Decimal(t['bid']) or Decimal(t['spread'])!=Decimal(t['ask'])-Decimal(t['bid']):raise ValueError('INVALID_TICK_SPREAD')
    costs={'opening_commission':{'value_usd':'2','status':'MANUAL_ESTIMATE','quantity_eur':'100','source':'user_reported_TWS_preview'},
        'closing_commission':{'value_usd':None,'status':'UNKNOWN'},'slippage':{'value':None,'status':'UNKNOWN'},
        'contract_restrictions':{'status':'UNVERIFIED_FOR_SMALL_ODD_LOTS'},'bid_ask_bar_count':len(spreads),
        'positive_observed_average_spread_count':sum(s['spread'] is not None for s in spreads),
        'unresolved_zero_average_spread_count':sum(s['spread'] is None for s in spreads),
        'observed_tick_count':len(ticks),'tick_spread_status':'OBSERVED_AT_TIMESTAMP' if ticks else 'UNKNOWN',
        'executable':False,'limitations':['Bar averages are not instantaneous entry/exit prices','Ticks cover only the sampled interval',
            'Public tariffs and manual preview do not verify this account round-trip commissions','No order or what-if was sent']}
    costs['limitations'].append('Equal rounded bar averages do not prove a zero executable spread')
    return originals,calendar,spreads,ticks,costs,receipts

def extended(payload):
    manifest=payload['archive'];originals,calendar,spreads,ticks,costs,receipts=prepare(manifest,payload['expected_account'])
    start,end=stamp(manifest['requested_start']),stamp(manifest['requested_end']);split=stamp(payload['validation_start'])
    if not start<split<end:raise ValueError('INVALID_CHRONOLOGICAL_SPLIT')
    analysis=analyze({**payload,'originals':originals,'calendar':calendar})
    analysis['engine_version']='research-extension-v2'
    bins=Counter();annotations=[]
    for index,c in enumerate(analysis['candidates']):
        at=stamp(c['signal_at']);role='development' if at<split else 'validation';windows=regional_windows(at)
        annotations.append({'candidate_index':index,'dataset_role':role,'regional_windows':windows})
        p=c['context']['15']['indicators']
        for session in windows:bins[(role,c['strategy_id'],p['trend'],p['volatility'],session)]+=1
    cal=ForexCalendar(calendar);bars,_=normalize(originals['15'],15,stamp(payload['as_of']),cal)
    for minutes in (15,60,240):
        present={stamp(r['opened_at']) for r in analysis['normalized'][str(minutes)]}
        missing=[t.isoformat() for t in cal.expected(minutes,start,end-timedelta(minutes=minutes)) if t not in present]
        analysis['quality'][str(minutes)]['missing_expected_in_requested_range']=missing
        analysis['quality'][str(minutes)]['requested_range_complete']=not missing
    derived={str(m):[{'opened_at':c.opened_at.isoformat(),'minutes':m,'open':c.open,'high':c.high,'low':c.low,'close':c.close,
        'volume':None,'spread':None,'source':'DERIVED_IBKR_MIDPOINT_15M','aggregation_version':'full-utc-grid-v1'} for c in aggregate_15m(bars,m,cal)] for m in (60,240)}
    analysis['extension']={'requested_start':start.isoformat(),'requested_end':end.isoformat(),'originals':originals,
        'receipts':receipts,'derived_series':derived,'spread_series':spreads,'observed_ticks':ticks,'cost_evidence':costs,
        'split':{'start':start.isoformat(),'validation_start':split.isoformat(),'end':end.isoformat(),
            'parameters_frozen':True,'optimization_performed':False,'warmup_may_use_prior_development_bars':True,
            'independent_virtual_allocation_per_strategy_and_partition':True},
        'signal_annotations':annotations,
        'conditions':[{'dataset_role':k[0],'strategy':k[1],'trend':k[2],'volatility':k[3],'regional_window':k[4],'signals':v} for k,v in sorted(bins.items())],
        'statistical_comparison_status':'INSUFFICIENT_EXECUTION_AND_COST_EVIDENCE_NO_SIGNIFICANCE_CLAIM',
        'execution_comparison':{'schema_version':1,'theoretical_source':'BACKTEST','paper_execution_observations':[],
            'execution_delta':None,'cost_delta':None,'status':'NO_AGENT_EXECUTION_OBSERVED',
            'required_keys':['strategy_version','signal_timestamp','market_condition','theoretical_entry_exit_cost_net',
                'paper_observation_id','observed_entry_exit_cost_net','execution_difference','cost_difference']}}
    # The calendar and params are frozen inputs; the version distinguishes changed research semantics.
    analysis['config_hash']=digest({'base':analysis['config_hash'],'engine':'research-extension-v2','split':analysis['extension']['split']})
    return analysis

if __name__=='__main__':
    import sys,json
    try:print(json.dumps(extended(json.load(sys.stdin)),allow_nan=False),flush=True)
    except Exception:
        print('RESEARCH_EXTENSION_FAILED',file=sys.stderr);raise SystemExit(1)
