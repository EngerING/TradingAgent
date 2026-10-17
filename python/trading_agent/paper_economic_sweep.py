"""Frozen six-month archive, offline C# RiskEngine scenarios. No broker or grants."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
from .paper_lab import DotnetJournal,date,stamp,utc
from .research_analysis import analyze,digest
from .research_extension import prepare

ARTIFACT='artifacts/research/6dd3f0c7e256f1c86fdb397133513a2896ab57822250b0e2748ca1acd6e6ab40.extended.json'
COSTS={'spread':'.00005','openingCommission':'2','closingCommission':'2','commissionPerUnitRoundTrip':'0',
       'slippage':'.00045','adverseGap':'.00005','minimumQuantity':'.01','quantityStep':'.01','marginRate':'1',
       'source':'ESTIMATED_CONSERVATIVE_2026_10_05_NOT_ACCOUNT_VERIFIED'}

def versions(root,analysis):
    rows={}
    for line in (root/'artifacts/paper-lab/strategy-versions-postgres.txt').read_text(encoding='utf-8-sig').splitlines():
        if not line.strip():continue
        identity,raw=line.split('|',1);p=json.loads(raw);spec=json.loads(p['parametersJson']);strategy=spec['id']
        if p['version']!=1 or p['strategyId']!=f"research-d-{strategy}-{analysis['config_hash'][:12]}" or spec!=next(s for s in analysis['strategies'] if s['id']==strategy):
            raise ValueError('STRATEGY_VERSION_CONFIG_MISMATCH')
        if strategy in rows:raise ValueError('AMBIGUOUS_STRATEGY_VERSION')
        rows[strategy]={'strategy_version':identity,'strategy_id':p['strategyId'],'version':1,
                        'parameters_hash':spec['parameters_hash'],'configuration_hash':analysis['config_hash']}
    if set(rows)!={'trend','pullback','mean_reversion'}:raise ValueError('EXISTING_STRATEGY_VERSIONS_REQUIRED')
    return rows

def signal(s):
    # Check causal feature timestamps before removing bulky feature data from the stdin protocol.
    for frame in s['context'].values():
        for t in (frame.get('as_of'),frame.get('indicators',{}).get('closed_at')):
            if t and date(t)>date(s['signal_at']):raise ValueError('LOOK_AHEAD_CONTEXT')
    return {'strategyId':s['strategy_id'],'side':s['side'],'signalAt':s['signal_at'],'entryAt':s['entry_at'],
            'entryMidpoint':s['entry_midpoint'],'stopDistance':s['stop_distance'],'takeProfitDistance':s['take_profit_distance'],
            'reasons':s['reasons'],'context':{}}

def run(root):
    root=Path(root);raw=(root/ARTIFACT).read_bytes();research=json.loads(raw)['research'];a=research['analysis']
    manifest=json.loads((root/'.local/research-history/manifest.json').read_text(encoding='utf-8-sig'))
    originals,calendar,_,_,archive_costs,_=prepare(manifest,manifest['account_id'])
    rebuilt=analyze({'instrument':'EUR/USD','source':'IBKR_TWS','what_to_show':'MIDPOINT','as_of':a['as_of'],
                     'indicators':a['parameters'],'calendar':calendar,'originals':originals})
    for key in ('dataset_hash','parameters','normalized','candidates','exit_signals'):
        if digest(rebuilt[key])!=digest(a[key]):raise ValueError('AUTHENTIC_ARCHIVE_REPLAY_MISMATCH_'+key.upper())
    if digest({'base':rebuilt['config_hash'],'engine':'research-extension-v2','split':a['extension']['split']})!=a['config_hash']:
        raise ValueError('FROZEN_CONFIG_HASH_MISMATCH')
    identities=versions(root,a);split=a['extension']['split'];core=DotnetJournal(root)
    partitions={'continuous_six_months':(split['start'],split['end']),
                'development':(split['start'],split['validation_start']),
                'validation':(split['validation_start'],split['end'])}
    results=[];minimum={}
    for strategy in identities:
        all_signals=[signal(s) for s in a['candidates'] if s['strategy_id']==strategy]
        exits=[{'strategyId':e['strategy_id'],'side':e['side'],'at':e['at']} for e in a['exit_signals'] if e['strategy_id']==strategy]
        minimum[strategy]=core.command({'operation':'paper-minimum-sizes','signals':all_signals,'costs':COSTS})
        for partition,(start,end) in partitions.items():
            bars=[{'openedAt':b['opened_at'],'minutes':b['minutes'],**{k:b[k] for k in ('open','high','low','close')}}
                  for b in a['normalized']['15'] if date(start)<=date(b['opened_at'])<date(end)]
            candidates=[s for s in all_signals if date(start)<=date(s['signalAt'])<date(end)]
            output=core.command({'operation':'paper-economic-sweep','strategy':strategy,'bars':bars,
                                 'signals':candidates,'exits':exits,'costs':COSTS})
            for row in output:row.update(partition=partition,strategy_version=identities[strategy]['strategy_version'])
            results.extend(output)
    # A positive hypothetical target alone is insufficient promotion evidence.
    promotion={}
    for strategy in identities:
        validation=[r for r in results if r['strategy']==strategy and r['partition']=='validation']
        promotion[strategy]={'target':'PAPER_EXPERIMENTAL','status':'NOT_ELIGIBLE','plan_issued':False,
            'positive_risk_bounded_opportunities':sum(x['size']['withinTenDollarRisk'] for x in minimum[strategy]),
            'validation_trades_by_exposure':{str(r['exposureLimit']):r['metrics']['trades'] for r in validation},
            'blockers':['STRATEGY_EXIT_SEMANTICS_NOT_EQUIVALENT','MARGIN_AND_BROKER_CONDITIONS_UNKNOWN',
                        'VALIDATION_INSUFFICIENT_FOR_PROMOTION','ACTIVE_EXPOSURE_1X_UNCHANGED'],
            'profitable':False,'live_validated':False,'economically_viable_with_100_real_usd':False}
    report={'generated_at':stamp(utc()),'source_artifact':ARTIFACT,'source_sha256':hashlib.sha256(raw).hexdigest(),
        'dataset_hash':a['dataset_hash'],'frozen_split':split,'strategy_versions':identities,'cost_scenario':COSTS,
        'archived_cost_evidence':archive_costs,'semantics':'research-d-exits-v1','policy':'WIN_TO_CONTINUE / FIRST_LOSS_STOPS_DAY',
        'capital':100,'cumulative_loss_allowance':20,'maximum_trade_risk':10,'active_exposure_unchanged':1,
        'day_clock':'UTC, matching the existing persistent PaperContinuation policy',
        'allocation':'Independent USD100/USD20 per strategy/scenario. Continuous six-month results NEVER reset at validation boundary; development/validation are separate protocol samples.',
        'results':results,'minimum_sizes':minimum,'promotion':promotion,'recommended_strategy':None,
        'recommended_quantity':0,'live_enabled':False,'execution_authorized':False,
        'limitations':['Hypothetical BUY and SELL research; current protected Paper transport supports BUY entries only.',
            'Constant conservative spread/slippage estimates, not historical executable quote reconstruction.',
            'Gap reserve is included in sizing and potential target screening; actual model stop gaps change gross P&L.',
            'Gaps can exceed the reserved amount; USD10/USD20 are entry budgets, not guarantees on fills.',
            'Costs assume USD2 each side and no percentage surcharge in this size range; this account tariff remains unverified.',
            'Potential net >0 is a strict mathematical threshold, not a reasonable profit or positive expectancy.',
            'Positions one at a time; fees finalized synchronously only in offline replay; runtime remains pending until actual fees reconcile.',
            'MarginRate=1 is an unused serialization placeholder, not evidence of actual margin; no candidate called viable.',
            'No parameter optimization, no active leverage or authorization changes, no broker order or what-if request.']}
    out=root/'artifacts/paper-lab';out.mkdir(exist_ok=True)
    (out/'economic-sweep.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    with (out/'economic-sweep.csv').open('w',encoding='utf-8',newline='') as f:
        names=['strategy','partition','exposureLimit']+list(results[0]['metrics'])
        writer=csv.DictWriter(f,fieldnames=names);writer.writeheader()
        for r in results:writer.writerow({**{k:r[k] for k in names[:3]},**{k:json.dumps(v) if isinstance(v,list) else v for k,v in r['metrics'].items()}})
    lines=['# Frozen Paper economic sweep','',f"Dataset `{a['dataset_hash']}`; six months {split['start']} to {split['end']}; validation starts {split['validation_start']}.",
        '', 'All sizes are conditional estimates. Actual margin, odd-lot execution and account commissions remain UNKNOWN. Active exposure stays 1x. No promotion is issued.',
        '', 'USD100 equity; risk min(10% equity, USD10, remaining cumulative loss allowance); cumulative losses USD20, profits never replenish consumed losses.',
        '', 'Costs: USD2 opening + USD2 closing; spread 0.00005; round-trip slippage 0.00045; adverse gap reserve 0.00005 USD/EUR. Original ATR stop/target and exits unchanged.',
        '', 'No-trade P&L/statistics are n/a. PF is n/a when there is no losing trade. Drawdown is a fraction of peak equity. Target-fail percentage screens structurally eligible signals at initial capital and includes sizes of zero.',
        '', 'Continuous samples stop permanently at the cumulative budget; partitions each start their own independent allocation, as in the original research protocol. Do not add their trade counts or P&L.',
        '', '## Exact existing strategy versions','']
    for key,value in identities.items():lines.append(f"- {key}: `{value['strategy_version']}` (V1).")
    def fmt(x):return 'n/a' if x is None else f'{x:.4f}' if isinstance(x,(float,int)) else str(x)
    for partition in partitions:
        lines.extend(['',f'## {partition}','', '| Strategy | Cap x | Trades | Qty mean / median EUR | Risk mean / max USD | Costs USD | Gross USD | Net USD | Target <= costs % | Win % | Net PF | Expectancy USD | DD closed / intrabar bound % | First-loss days / zero days | Days entries / potential | Odd lots |',
            '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|'])
        for r in [r for r in results if r['partition']==partition]:
            m=r['metrics'];loss=sum(s['net']<0 for s in m['dailyStops']);zero=sum(s['net']==0 for s in m['dailyStops'])
            pct=lambda x:fmt(None if x is None else 100*x)
            lines.append(f"| {r['strategy']} | {r['exposureLimit']} | {m['trades']} | {fmt(m['meanQuantity'])} / {fmt(m['medianQuantity'])} | {fmt(m['meanRisk'])} / {fmt(m['maximumRisk'])} | {fmt(m['costs'])} | {fmt(m['grossPnl'])} | {fmt(m['netPnl'])} | {fmt(m['targetNotCoveringCostPercent'])} | {pct(m['winRate'])} | {fmt(m['netProfitFactor'])} | {fmt(m['netExpectancy'])} | {pct(m['maximumClosedDrawdown'])} / {pct(m['maximumIntrabarDrawdownBound'])} | {loss} / {zero} | {m['daysWithEntries']} / {m['potentialOperableDays']} | {m['oddLotTrades']} |")
    lines.extend(['','## Minimum sizes with strictly positive conservative target','',
        'This selects the smallest historical eligible opportunity satisfying the USD10 risk cap, not a size for today. Net at this boundary is almost zero. Every signal minimum and exact daily first-loss timestamp is in economic-sweep.json.',
        '', '| Strategy | Signal UTC / side | EUR | USD notional | Exposure x | Stop USD | Costs USD | Gap reserve USD | Total risk USD | Gross target USD | Net target USD |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|'])
    for strategy,items in minimum.items():
        acceptable=[x for x in items if x['size']['withinTenDollarRisk']]
        if not acceptable:lines.append(f'| {strategy} | no risk-compatible size | | | | | | | | | |');continue
        best=min(acceptable,key=lambda x:x['size']['exposure']);s=best['size']
        lines.append(f"| {strategy} | {best['signalAt']} / {best['side']} | {fmt(s['quantity'])} | {fmt(s['notional'])} | {fmt(s['exposure'])} | {fmt(s['stopLoss'])} | {fmt(s['costs'])} | {fmt(s['gapReserve'])} | {fmt(s['totalRisk'])} | {fmt(s['grossTarget'])} | {s['conservativeNetTarget']:.8f} |")
    lines.extend(['','## Limitations','']+[f'- {s}' for s in report['limitations']])
    (root/'docs/architecture/paper-strategy-economic-sweep.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return {'scenarios':len(results),'dataset_hash':a['dataset_hash'],'strategy_versions':identities,
            'recommended_strategy':None,'orders_sent':0}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',default='.');args=parser.parse_args()
    print(json.dumps(run(args.root)))
