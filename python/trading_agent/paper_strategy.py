"""Owner-approved declarative Paper plans and causal signals. No authorization or orders."""
import argparse
import copy
from datetime import timedelta
from decimal import Decimal,ROUND_CEILING,ROUND_FLOOR
import json
from pathlib import Path
from .paper_lab import date,num,stamp,utc,EXPERIMENTAL
from .research_analysis import analyze,digest
from .research_calendar import ForexCalendar
from .research_indicators import settings

ENGINE='research-d-v1-long-paper-v1'
EXIT_ENGINE='research-d-exits-v1'

def validate_plan(p,now,versions,*,allow_expired=False):
    if isinstance(p,dict) and 'paper_eligibility' in p:
        from .paper_eligibility import validate_runtime_plan
        return validate_runtime_plan(p,now,versions,allow_expired)
    required={'schema_version','engine','strategy_version','strategy_id','name','instrument','side','exit_policy',
              'indicators','calendar','evidence_at','evidence_expires_at','execution_requirements'}
    if not isinstance(p,dict) or set(p)-{'promotion_evidence'}!=required or p['schema_version']!=1 or p['engine']!=ENGINE:
        raise PermissionError('STRATEGY_PLAN_INVALID')
    evidence=p.get('promotion_evidence')
    if evidence is not None:
        if evidence.get('promotion_target')!='PAPER_EXPERIMENTAL' or evidence.get('risk_profile')!=EXPERIMENTAL or evidence.get('strategy_version')!=p['strategy_version'] or evidence.get('live_validated') is not False or evidence.get('profitable') is not False:
            raise PermissionError('STRATEGY_PROMOTION_SCOPE_INVALID')
        if evidence.get('entry_exit_equivalence_verified') is not True:
            raise PermissionError('STRATEGY_EXIT_SEMANTICS_NOT_EQUIVALENT')
    if p['strategy_version'] not in versions or p['strategy_id'] not in ('trend','pullback','mean_reversion') or not p['name']:
        raise PermissionError('STRATEGY_VERSION_NOT_AUTHORIZED')
    if p['instrument']!='EUR/USD' or p['side']!='BUY' or p['exit_policy'] not in ('BRACKET_OR_TIME_LIMIT','RESEARCH_D_V1'):
        raise PermissionError('STRATEGY_PLAN_UNSUPPORTED_SCOPE')
    if p['exit_policy']=='RESEARCH_D_V1':
        from .paper_exit_evidence import verified_equivalence
        if not verified_equivalence():raise PermissionError('STRATEGY_EXIT_SEMANTICS_NOT_EQUIVALENT')
    start,end=date(p['evidence_at']),date(p['evidence_expires_at'])
    if not start<=now or end<=start or (end-start).total_seconds()>86400 or not allow_expired and now>=end:
        raise PermissionError('STRATEGY_EVIDENCE_EXPIRED')
    settings(p['indicators']);calendar=ForexCalendar(p['calendar'])
    if p['calendar'].get('status') not in ('VERIFIED_EXPLICIT_SESSIONS','VERIFIED_REGULAR_SESSIONS','IBKR_HISTORICAL_SCHEDULE','IBKR_AUTHENTIC_SESSIONS') or not p['calendar'].get('source'):
        raise PermissionError('STRATEGY_CALENDAR_UNVERIFIED')
    if not allow_expired and not calendar.start<=now.date()<=calendar.end:raise PermissionError('STRATEGY_CALENDAR_EXPIRED')
    r=p['execution_requirements']
    expected={'quoteToAccountFx','multiplier','minQuantity','quantityStep','marginRate','availableMargin',
              'commissionFixedRoundTrip','commissionPerUnitRoundTrip','slippagePerUnit','adverseGapPerUnit','execution'}
    if not isinstance(r,dict) or set(r)!=expected:raise PermissionError('EXECUTION_EVIDENCE_INCOMPLETE')
    for k in expected-{'execution'}:num(r[k])
    if num(r['quoteToAccountFx'])!=1 or num(r['multiplier'])!=1 or min(num(r[k]) for k in ('minQuantity','quantityStep','marginRate','availableMargin'))<=0 or num(r['marginRate'])>1:
        raise PermissionError('EXECUTION_EVIDENCE_INVALID')
    if any(num(r[k])<0 for k in ('commissionFixedRoundTrip','commissionPerUnitRoundTrip','slippagePerUnit','adverseGapPerUnit')):
        raise PermissionError('EXECUTION_EVIDENCE_INVALID')
    f=r['execution'];real=f.get('equivalentRealAccount',{})
    if not f.get('source') or f.get('environment')!='PAPER_TRADING' or f.get('mode') not in ('STANDARD','ODD_LOT') or any(f.get(k) is not True for k in ('costsReliable','marginReliable','contractReliable','brokerPermitsEntry')):
        raise PermissionError('EXECUTION_EVIDENCE_INCOMPLETE')
    if num(f.get('openingCommission',-1))<0 or num(f.get('closingCommission',-1))<0 or num(f['openingCommission'])+num(f['closingCommission'])!=num(r['commissionFixedRoundTrip']):
        raise PermissionError('EXECUTION_COST_EVIDENCE_INVALID')
    if any(real.get(k) is not True for k in ('instrumentPermitted','executionModePermitted','accountEligible')) or any(num(real.get(k,0))<=0 for k in ('minimumQuantity','quantityStep','marginRate','maximumLeverage')) or num(real['marginRate'])>1 or num(real['maximumLeverage'])>1:
        raise PermissionError('REAL_ACCOUNT_EVIDENCE_INCOMPLETE')
    return p

def signal(plan,originals,quote,now):
    validate_plan(plan,now,[plan['strategy_version']])
    result=analyze({'instrument':'EUR/USD','source':'IBKR_TWS','what_to_show':'MIDPOINT','as_of':stamp(now),
                    'indicators':plan['indicators'],'calendar':plan['calendar'],'originals':originals})
    points=result['indicator_points']['15']
    if not points or not 0<=(now-date(points[-1]['closed_at'])).total_seconds()<=30:return None
    candidates=[s for s in result['candidates'] if s['strategy_id']==plan['strategy_id'] and s['side']=='BUY' and
                s['signal_at']==points[-1]['closed_at'] and all(r=='NO_NEXT_CLOSED_BAR' for r in s['reasons'])]
    if not candidates:return None
    s=candidates[-1];tick=Decimal('0.00005')
    midpoint=(num(quote['bid'])+num(quote['ask']))/2
    if plan['exit_policy']=='RESEARCH_D_V1':
        stop=midpoint-num(s['stop_distance']);target=midpoint+num(s['take_profit_distance'])
        if stop%tick or target%tick:raise PermissionError('STRATEGY_PRICE_GRID_NOT_EQUIVALENT')
    else:
        stop=((num(quote['bid'])-num(s['stop_distance']))/tick).to_integral_value(rounding=ROUND_FLOOR)*tick
        target=((num(quote['ask'])+num(s['take_profit_distance']))/tick).to_integral_value(rounding=ROUND_CEILING)*tick
    if stop<=0:return None
    return {'strategy_version':plan['strategy_version'],'signal_at':s['signal_at'],'stop':str(stop),'target':str(target),
            'market_context':{'strategy_name':plan['name'],'strategy_id':plan['strategy_id'],'signal_at':s['signal_at'],
                'signal_reason':next(x['entry_rule'] for x in result['strategies'] if x['id']==plan['strategy_id']),
                'indicators':copy.deepcopy(s['context']),'timeframe':'15m','engine':ENGINE,'plan_hash':digest(plan),
                'exit_semantics':EXIT_ENGINE if plan['exit_policy']=='RESEARCH_D_V1' else 'LEGACY_TIME_LIMIT',
                'research_position':{'strategyId':plan['strategy_id'],'side':'BUY','entry':str(midpoint),
                    'stop':str(stop),'target':str(target),'entryAt':s['signal_at']}}}

def exit_decision(plan,originals,quote,now,position,core):
    """Original closed-bar rule signals; a broker fill is never rewritten as a model fill."""
    if plan['exit_policy']!='RESEARCH_D_V1':raise PermissionError('RESEARCH_EXIT_PLAN_REQUIRED')
    result=analyze({'instrument':'EUR/USD','source':'IBKR_TWS','what_to_show':'MIDPOINT','as_of':stamp(now),
        'indicators':plan['indicators'],'calendar':plan['calendar'],'originals':originals})
    opening=now.replace(minute=now.minute//15*15,second=0,microsecond=0)
    if opening<date(position['entryAt']):return None
    # Catch a rule exit missed by a delayed poll/restart. Never consume a pre-entry exit.
    relevant=[e for e in result['exit_signals'] if e['strategy_id']==position['strategyId'] and
        e['side']==position['side'] and date(position['entryAt'])<date(e['at'])<=opening]
    midpoint=(num(quote['bid'])+num(quote['ask']))/2
    bar={'openedAt':stamp(opening),'minutes':15,**{k:str(midpoint) for k in ('open','high','low','close')}}
    previous=opening-timedelta(minutes=15)
    if relevant:previous=min(previous,min(date(e['at']) for e in relevant)-timedelta(microseconds=1))
    request={'operation':'research-exit','position':position,'bar':bar,'previousOpenedAt':stamp(previous),
        'exits':[{'strategyId':e['strategy_id'],'side':e['side'],'at':e['at']} for e in relevant],'opening':True}
    decision=core.command(request)
    if decision['exit']:
        decision.update(observed_at=stamp(now),fill_timing='FIRST_AVAILABLE_QUOTE_AFTER_RULE_NEXT_OPEN',
                        lateness_seconds=(now-opening).total_seconds())
        return decision
    request['opening']=False;decision=core.command(request)
    if decision['exit']:
        decision.update(observed_at=stamp(now),fill_timing='OBSERVED_MIDPOINT_THRESHOLD')
        return decision
    return None

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--validate-file',required=True);p.add_argument('--version',required=True);a=p.parse_args()
    try:
        plan=json.loads(Path(a.validate_file).read_text(encoding='utf-8-sig'))
        validate_plan(plan,utc(),[a.version]);print(json.dumps({'plan':plan,'plan_hash':digest(plan)}))
    except Exception as e:
        reason=str(e);print(json.dumps({'error':reason if reason.replace('_','').isalnum() and reason.isupper() else 'STRATEGY_PLAN_INVALID'}));raise SystemExit(1)
