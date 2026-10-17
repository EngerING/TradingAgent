"""Build a reviewable Paper-only evidence plan. Pure calculations, no order or grant writes."""
import argparse
import copy
import json
from datetime import timedelta
from decimal import Decimal,ROUND_CEILING,ROUND_FLOOR
from pathlib import Path
from .paper_lab import DotnetJournal,EXPERIMENTAL,num,stamp,date,utc
from .paper_strategy import ENGINE
from .research_analysis import digest
from .research_extension import prepare

RUN='6dd3f0c7e256f1c86fdb397133513a2896ab57822250b0e2748ca1acd6e6ab40'

def build(root):
    root=Path(root);out=root/'artifacts/paper-lab'
    read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
    source=root/f'artifacts/research/{RUN}.extended.json';research=read(source);a=research['research']['analysis']
    manifest=read(root/'.local/research-history/manifest.json')
    originals,calendar,_,_,_,receipts=prepare(manifest,manifest['account_id'])
    if digest(originals)!=a['dataset_hash']:raise ValueError('DATASET_IDENTITY_MISMATCH')
    selected=[]
    for line in (out/'trend-versions-postgres.txt').read_text(encoding='utf-8-sig').splitlines():
        identity,raw=line.split('|',1);version=json.loads(raw)
        if version['strategyId']=='research-d-trend-'+a['config_hash'][:12]:selected.append((identity,version))
    if len(selected)!=1:raise ValueError('EXACT_STRATEGY_VERSION_NOT_RESOLVED')
    identity,version=selected[0]
    if version['version']!=1 or json.loads(version['parametersJson'])['parameters_hash']!=a['strategies'][0]['parameters_hash']:
        raise ValueError('STRATEGY_PARAMETERS_MISMATCH')
    market=read(out/'market-evidence.json');inspection=read(out/'data-diagnostics.json');q=inspection['quote']
    if q['type']!='LIVE' or q['market_status']!='OPEN' or not q['available_for_execution']:
        raise ValueError('AUTHENTIC_OPEN_MARKET_QUOTE_REQUIRED')
    # Explicit estimates. Public tariff does not verify this account's realized commission/restrictions.
    requirements={'quoteToAccountFx':1,'multiplier':1,'minQuantity':inspection['contract']['minimum_size_metadata'],
        'quantityStep':inspection['contract']['size_increment_metadata'],'marginRate':1,'availableMargin':100,
        'commissionFixedRoundTrip':4,'commissionPerUnitRoundTrip':0,'slippagePerUnit':'.00045','adverseGapPerUnit':'.00005',
        'execution':{'source':'IBKR_PUBLIC_TIER_I_AND_CONSERVATIVE_ESTIMATES_NOT_ACCOUNT_VERIFIED',
            'environment':'PAPER_TRADING','mode':'ODD_LOT','openingCommission':2,'closingCommission':2,
            'costsReliable':False,'marginReliable':False,'contractReliable':True,'brokerPermitsEntry':False,
            'equivalentRealAccount':{'minimumQuantity':None,'quantityStep':None,'marginRate':None,'maximumLeverage':1,
                'instrumentPermitted':None,'executionModePermitted':None,'accountEligible':None}}}
    now=utc();plan={'schema_version':1,'engine':ENGINE,'strategy_version':identity,'strategy_id':'trend',
        'name':version['name'],'instrument':'EUR/USD','side':'BUY','exit_policy':'BRACKET_OR_TIME_LIMIT',
        'indicators':a['parameters'],'calendar':market['calendar'],'evidence_at':stamp(now),
        'evidence_expires_at':stamp(now+timedelta(hours=24)),'execution_requirements':requirements,
        'promotion_evidence':{'promotion_target':'PAPER_EXPERIMENTAL','risk_profile':EXPERIMENTAL,
            'strategy_version':identity,'strategy_id':version['strategyId'],'version_number':version['version'],
            'configuration_hash':a['config_hash'],'parameters_hash':a['strategies'][0]['parameters_hash'],
            'dataset_hash':a['dataset_hash'],'research_run':RUN,'research_path':str(source.resolve()),
            'archive_path':str((root/'.local/research-history/manifest.json').resolve()),
            'partitions':a['extension']['split'],'signals':{'development':140,'validation':78,'total':218,'admitted':0},
            'status':'EVIDENCE_PLAN_PENDING_OWNER_APPROVAL','profitable':False,'live_validated':False,
            'economically_viable_with_real_usd100':False,'entry_exit_equivalence_verified':False,
            'limitations':['No admitted historical trades or profitability metrics',
                'Long-only Paper adapter omits opposite EMA / higher-frame exit: promotion blocked',
                'Protected holding-time limit changes realized outcomes versus historical research',
                'Account round-trip commissions, odd-lot execution and margin permissions unverified',
                'No new authorization, no emergency release, no orders; exposure remains 1x']}}
    core=DotnetJournal(root,EXPERIMENTAL);account=core.strategy_initial();tick=Decimal('.00005')
    # The latest eligible signal is historical: reprice its distances for a diagnostic, never revive it.
    historical=[s for s in a['candidates'] if s['strategy_id']=='trend' and s['side']=='BUY' and not s['reasons']][-1]
    atr=market['analysis']['latest']['15']['indicators']['atr']
    samples=[('LAST_ELIGIBLE_HISTORICAL_BUY',historical['signal_at'],num(historical['stop_distance']),num(historical['take_profit_distance'])),
             ('LATEST_ATR_GEOMETRY_NO_ENTRY_SIGNAL',market['analysis']['latest']['15']['indicators']['closed_at'],num(atr)*2,num(atr)*3)]
    economics=[]
    for label,at,stop_distance,target_distance in samples:
        r=copy.deepcopy(requirements);bid=num(q['bid']);ask=(num(q['ask'])/tick).to_integral_value(rounding=ROUND_CEILING)*tick
        stop=((bid-stop_distance)/tick).to_integral_value(rounding=ROUND_FLOOR)*tick
        target=((ask+target_distance)/tick).to_integral_value(rounding=ROUND_CEILING)*tick
        r.update(instrument='EUR/USD',side='BUY',bid=str(bid),ask=str(ask),stop=str(stop),marketAt=q['at'])
        r['execution'].update(at=q['at'],takeProfit=str(target),quoteStatus='LIVE')
        study=core.command({'operation':'experimental-economics','account':account,'request':r})
        economics.append({'basis':label,'signal_or_bar_at':at,'entry_eligible_now':False,
            'bid':str(bid),'rounded_entry_ask':str(ask),'stop':str(stop),'target':str(target),'request':r,'study':study})
    # Verify counters against actual candidates, rather than relying on copied prose.
    trend=[s for s in a['candidates'] if s['strategy_id']=='trend'];split=date(a['extension']['split']['validation_start'])
    counts={'development':sum(date(s['signal_at'])<split for s in trend),'validation':sum(date(s['signal_at'])>=split for s in trend),'total':len(trend),'admitted':0}
    if counts!=plan['promotion_evidence']['signals']:raise ValueError('SIGNAL_EVIDENCE_MISMATCH')
    report={'observed_at':inspection['observed_at'],'quote':q,'strategy_version':identity,'strategy':version,
        'strategy_evidence_path':str((out/'trend-v1-evidence.json').resolve()),'promotion_evidence':plan['promotion_evidence'],
        'native_original_counts':{k:len(v) for k,v in originals.items()},'verified_archive_receipts':len(receipts),
        'eur_exception':inspection['strategy_initial_absence_route'],'calendar':market['calendar'],
        'economics':economics,'commission_estimate_status':'USD2_OPEN_USD2_CLOSE_PUBLIC_TIER_I_NOT_ACCOUNT_VERIFIED',
        'slippage_estimate_status':'USD_PER_EUR_0.00045_ROUND_TRIP_CONSERVATIVE_ODD_LOT_ASSUMPTION_NOT_MEASURED',
        'margin_and_account_restrictions':{'verified':False,'virtual_equity':100,'maximum_exposure':1,
            'broker_snapshot_initial_margin':inspection['snapshot'].get('initial_margin'),
            'paper_million_dollar_balance_used_for_sizing':False},
        'entry_recommendation_quantity':0,'entry_recommendation_reason':'NO_FRESH_VALID_SIGNAL_AND_CURRENT_1X_LIMIT_NOT_ECONOMIC',
        'blockers':['NO_FRESH_VALID_APPROVED_SIGNAL','NO_ECONOMIC_ENTRY_WITHIN_CURRENT_LIMITS',
            'STRATEGY_EXIT_SEMANTICS_NOT_EQUIVALENT','EXECUTION_EVIDENCE_INCOMPLETE','EUR_EXCEPTION_NOT_REGISTERED',
            'AUTHORIZATION_EXPIRED','EMERGENCY_STOP'],
        'preserved_additional_limits':{'authorization_max_quantity':100,'authorization_max_notional_usd':250,'maximum_hold_seconds':300},
        'orders_sent':0,'authorization_renewed':False,'emergency_cleared':False,'live_enabled':False}
    (out/'trend-v1-evidence.json').write_text(json.dumps(plan,indent=2),encoding='utf-8')
    (out/'trend-v1-readiness.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'strategy_version':identity,'strategy_evidence_path':report['strategy_evidence_path'],
        'economics':[{'basis':x['basis'],'sizes':x['study']['sizes']} for x in economics],'recommendation':0,'orders_sent':0}))
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',required=True);args=parser.parse_args();build(args.root)
