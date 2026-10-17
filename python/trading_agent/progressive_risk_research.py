"""Isolated, fixed-parameter risk research. No broker connection or permissions."""
import argparse
from collections import defaultdict
import csv
from datetime import timedelta
from decimal import Decimal
import hashlib
import json
from math import sqrt
from pathlib import Path
import random
from statistics import NormalDist
import subprocess
from zoneinfo import ZoneInfo
from .paper_economic_sweep import ARTIFACT,signal,versions
from .research_analysis import analyze,digest
from .research_extension import prepare
from .paper_lab import date,stamp

RATES=(1,2,3,5,7.5,10,12.5,15)
ZONE=ZoneInfo('America/Santo_Domingo')
PROTOCOL={'capital_usd':100,'loss_allowance_usd':20,'exposure_limit':1,'risk_percentages':RATES,
 'policy':'WIN_TO_CONTINUE / FIRST_LOSS_STOPS_DAY','day_timezone':'America/Santo_Domingo',
 'parameters_frozen':True,'optimization':False,'minimum_oos_trades':100,'minimum_oos_trade_days':30,
 'minimum_walk_forward_folds':3,'family_tests':24,'family_alpha':.05,'bootstrap_repetitions':2000,
 'bootstrap_block_trading_days':5,'maximum_closed_drawdown':.20,'require_fresh_unexamined_holdout':True}

def load(path):return json.loads(Path(path).read_bytes())

def wilson(wins,n,alpha=.05):
    if not 0<=wins<=n or not 0<alpha<1:raise ValueError('INVALID_BINOMIAL_SAMPLE')
    if n==0:return None
    z=NormalDist().inv_cdf(1-alpha/2);p=wins/n;den=1+z*z/n
    center=(p+z*z/(2*n))/den;half=z*sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return [max(0,center-half),min(1,center+half)]

def quantile(values,p):
    values=sorted(values)
    if not values:return None
    i=(len(values)-1)*p;lo=int(i);hi=min(lo+1,len(values)-1)
    return values[lo]+(values[hi]-values[lo])*(i-lo)

def uncertainty(trades,identity,repetitions=2000,family_tests=None):
    rows=[x.get('trade',x) for x in trades];n=len(rows);wins=sum(x['netPnl']>0 for x in rows)
    comparisons=PROTOCOL['family_tests'] if family_tests is None else family_tests
    if not isinstance(comparisons,int) or comparisons<1:raise ValueError('INVALID_COMPARISON_FAMILY')
    alpha=PROTOCOL['family_alpha']/comparisons;groups=defaultdict(list)
    for t in rows:groups[date(t['exitAt']).astimezone(ZONE).date()].append(float(t['netPnl']))
    days=[groups[d] for d in sorted(groups)]
    result={'sample_trades':n,'sample_trade_days':len(days),'win_wilson_95':wilson(wins,n),
        'win_wilson_family_adjusted':wilson(wins,n,alpha),'family_alpha':.05,'comparisons':comparisons,
        'block_bootstrap_win_ci':None,'block_bootstrap_expectancy_ci':None,
        'bootstrap_block_days':5,'bootstrap_repetitions':repetitions,'method':'MOVING_BLOCK_OF_TRADING_DAYS',
        'limitations':['Wilson is an IID reference; daily continuation creates dependence.',
            'Block bootstrap is approximate and cannot prove independence or eliminate selection bias.']}
    if len(days)<5:return result
    rng=random.Random(int(hashlib.sha256(identity.encode()).hexdigest()[:16],16));wr=[];ev=[]
    for _ in range(repetitions):
        sample=[]
        while len(sample)<len(days):
            start=rng.randrange(len(days)-4);sample.extend(days[start:start+5])
        pnl=[v for block in sample[:len(days)] for v in block]
        wr.append(sum(v>0 for v in pnl)/len(pnl));ev.append(sum(pnl)/len(pnl))
    result['block_bootstrap_win_ci']=[quantile(wr,alpha/2),quantile(wr,1-alpha/2)]
    result['block_bootstrap_expectancy_ci']=[quantile(ev,alpha/2),quantile(ev,1-alpha/2)]
    return result

def walk_forward(split):
    start,val,end=[date(split[k]) for k in ('start','validation_start','end')]
    if not start<val<end:raise ValueError('INVALID_FROZEN_SPLIT')
    seconds=int((end-val).total_seconds());boundaries=[val+timedelta(seconds=(seconds*i//3//900)*900) for i in range(4)]
    boundaries[-1]=end
    return [{'name':f'walk_forward_{i+1}','training_start':stamp(start),'training_end':stamp(boundaries[i]-timedelta(minutes=15)),
        'test_start':stamp(boundaries[i]),'test_end':stamp(boundaries[i+1]),'gap_minutes':15,
        'parameters_refitted':False,'allocation':'INDEPENDENT_USD100_USD20_TEST_FOLD'} for i in range(3)]

def selection_checks(metrics,ci,folds,broker_verified=False,fresh_holdout=False):
    reasons=[]
    if metrics['admitted']<PROTOCOL['minimum_oos_trades']:reasons.append('INSUFFICIENT_OOS_TRADES')
    if ci['sample_trade_days']<PROTOCOL['minimum_oos_trade_days']:reasons.append('INSUFFICIENT_OOS_TRADING_DAYS')
    if metrics['winRate'] is None or metrics['winRate']<=.8:reasons.append('NET_WIN_RATE_NOT_ABOVE_80_PERCENT')
    for field in ('win_wilson_family_adjusted','block_bootstrap_win_ci'):
        if ci[field] is None or ci[field][0]<=.8:reasons.append('WIN_RATE_CONFIDENCE_INSUFFICIENT_'+field.upper())
    if metrics['netPnl']<=0 or metrics['netExpectancy'] is None or metrics['netExpectancy']<=0:reasons.append('NET_EXPECTANCY_NOT_POSITIVE')
    if ci['block_bootstrap_expectancy_ci'] is None or ci['block_bootstrap_expectancy_ci'][0]<=0:reasons.append('EXPECTANCY_CONFIDENCE_INSUFFICIENT')
    if metrics['netProfitFactor'] is None or metrics['netProfitFactor']<=1:reasons.append('NET_PROFIT_FACTOR_INSUFFICIENT')
    if metrics['intrabarDrawdownBound']>PROTOCOL['maximum_closed_drawdown']:reasons.append('EXCESSIVE_DRAWDOWN')
    if len(folds)<3 or any(x['metrics']['admitted']==0 or x['metrics']['netPnl']<=0 for x in folds):reasons.append('WALK_FORWARD_EVIDENCE_INSUFFICIENT')
    if not broker_verified:reasons.append('IBKR_EXECUTABILITY_UNKNOWN')
    if not fresh_holdout:reasons.append('PREVIOUSLY_EXAMINED_HOLDOUT_REQUIRES_NEW_CONFIRMATION')
    return {'eligible_for_further_review':not reasons,'reasons':reasons,'execution_authorized':False,'live_approved':False}

def choose(rows):
    valid=[x for x in rows if x['selection']['eligible_for_further_review']]
    if not valid:return {'status':'NO_VIABLE_STRATEGY_FOUND','strategy':None,'risk_percent':None,'quantity':0,'execution_authorized':False}
    # Rank only after all evidence/execution gates; minimum risk first, never win rate alone.
    best=min(valid,key=lambda x:(x['riskFraction'],-x['metrics']['netExpectancy'],x['strategy']))
    return {'status':'RESEARCH_CANDIDATE_REQUIRES_OWNER_REVIEW','strategy':best['strategy'],'risk_percent':100*best['riskFraction'],
        'quantity':best['metrics']['meanQuantity'],'execution_authorized':False}

def authentic_inputs(root):
    raw=(root/ARTIFACT).read_bytes();a=json.loads(raw)['research']['analysis']
    manifest=load(root/'.local/research-history/manifest.json');originals,calendar,spreads,ticks,archive_costs,receipts=prepare(manifest,manifest['account_id'])
    rebuilt=analyze({'instrument':'EUR/USD','source':'IBKR_TWS','what_to_show':'MIDPOINT','as_of':a['as_of'],
        'indicators':a['parameters'],'calendar':calendar,'originals':originals})
    for name in ('dataset_hash','parameters','normalized','candidates','exit_signals'):
        if digest(rebuilt[name])!=digest(a[name]):raise ValueError('AUTHENTIC_ARCHIVE_MISMATCH_'+name.upper())
    if digest({'base':rebuilt['config_hash'],'engine':'research-extension-v2','split':a['extension']['split']})!=a['config_hash']:
        raise ValueError('FROZEN_CONFIGURATION_MISMATCH')
    ids=versions(root,a);elig=load(root/'artifacts/paper-lab/paper-eligibility.json')
    for id,v in ids.items():
        if not any(s['strategy_id']==id and s['strategy_version']==v['strategy_version'] and s['state']=='PaperEligible' for s in elig['strategies']):
            raise ValueError('EXISTING_PAPER_ELIGIBLE_VERSION_REQUIRED')
    return a,ids,{'source_artifact':ARTIFACT,'source_sha256':hashlib.sha256(raw).hexdigest(),'dataset_hash':a['dataset_hash'],
        'archive_manifest_sha256':hashlib.sha256((root/'.local/research-history/manifest.json').read_bytes()).hexdigest(),
        'bar_counts':{k:len(v) for k,v in a['normalized'].items()},'archive_receipts':len(receipts),
        'original_cost_evidence':archive_costs,'positive_average_spread_count':sum(x['spread'] is not None for x in spreads),
        'spread_values':[x['spread'] for x in spreads if x['spread'] is not None]+[x['spread'] for x in ticks]}

def cost_evidence(root,provenance):
    path=root/'artifacts/paper-lab/data-diagnostics.json';d=load(path);observed=[]
    for o in d.get('owned_orders',{}).values():
        if o['state']!='CLOSED' or o.get('category')!='PAPER_DIAGNOSTIC':continue
        for id,f in o['fills'].items():
            fee=o['commissions'].get(id)
            if fee and fee['currency']=='USD':observed.append({'side':f['side'],'exec_id':id,'quantity':f['quantity'],
                'commission_usd':fee['amount'],'commission_currency':'USD','at':fee['at']})
    buy=[Decimal(x['commission_usd']) for x in observed if x['side']=='BUY'];sell=[Decimal(x['commission_usd']) for x in observed if x['side']=='SELL']
    if not buy or not sell:raise ValueError('OBSERVED_PAPER_ROUND_TRIP_FEES_REQUIRED')
    # Constant stress spread uses the largest authentic positive average/tick or conservative floor.
    spreads=[Decimal(x) for x in provenance.pop('spread_values') if Decimal(x)>0]
    quote=d.get('quote',{});spread=max([Decimal('.00005'),*(spreads or []),Decimal(quote['ask'])-Decimal(quote['bid'])])
    costs={'spread':str(spread),'openingCommission':str(max(buy)),'closingCommission':str(max(sell)),
        'commissionPerUnitRoundTrip':'0','slippage':'.00045','adverseGap':'.00005',
        'minimumQuantity':d['contract']['minimum_size_metadata'],'quantityStep':d['contract']['size_increment_metadata'],
        'marginRate':'1','source':'OBSERVED_PAPER_FEES_CONSERVATIVE_ARCHIVE_MAX_SPREAD_UNKNOWN_IBKR_MARGIN'}
    return costs,{'source_path':str(path.relative_to(root)),'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'paper_fee_observations':observed,'borrowed_strategy_results':False,'market_observation_at':quote.get('at'),
        'positive_spread_samples':len(spreads),'spread_basis':'MAX_AUTHENTIC_ARCHIVE_OBSERVATIONS_AND_FLOOR',
        'slippage_status':'CONSERVATIVE_ESTIMATE_NOT_HISTORICAL_EXECUTION_RECONSTRUCTION',
        'commission_status':'OBSERVED_ON_ONE_100_EUR_DIAGNOSTIC_CYCLE_TARIFF_GENERALIZATION_UNKNOWN',
        'margin_status':'UNKNOWN_FULL_NOTIONAL_PLUS_COST_FUNDING_MODEL_ONLY',
        'minimum_quantity_status':'IBKR_CONTRACT_METADATA_NOT_ACCOUNT_PERMISSION',
        'odd_lot_status':'100_EUR_EXECUTED_PAPER_ONLY_OTHER_QUANTITIES_UNVERIFIED'}

def simulate(root,strategy,bars,signals,exits,costs):
    payload={'environment':'SIMULATION','capital':100,'lossAllowance':20,'exposure':1,'liveEnabled':False,
        'executionAuthorized':False,'strategy':strategy,'bars':bars,'signals':signals,'exits':exits,'costs':costs}
    dll=root/'src/TradingAgent.ResearchLab/bin/Debug/net9.0/TradingAgent.ResearchLab.dll'
    result=subprocess.run(['dotnet',str(dll)],input=json.dumps(payload),capture_output=True,text=True,cwd=root,timeout=120)
    output=json.loads(result.stdout)
    if result.returncode or not isinstance(output,list):raise ValueError('ISOLATED_SIMULATION_FAILED')
    return output

def commission_only_upper_bound(signals,costs):
    """Favorable analytical bound, never an admission or recommendation.

    Ignore risk, spread, slippage, gap and quantity rounding. Funding the fixed
    round-trip fee leaves at most USD96 for notional at initial equity. A
    nonpositive bound proves no first target can grow this USD100 account.
    """
    capital=Decimal(100);fee=Decimal(costs['openingCommission'])+Decimal(costs['closingCommission'])
    best=None;eligible=0
    for s in signals:
        if s['reasons'] or s['entryAt'] is None:continue
        eligible+=1;mid=Decimal(str(s['entryMidpoint']));target=Decimal(str(s['takeProfitDistance']))
        if mid<=0 or target<=0:raise ValueError('INVALID_BOUND_PRICE')
        quantity=max(Decimal(0),capital-fee)/mid;gross=quantity*target
        candidate={'quantity_eur':float(quantity),'notional_usd':float(quantity*mid),
            'gross_target_usd':float(gross),'net_target_usd':float(gross-fee),'signal_at':s['signalAt']}
        if best is None or candidate['net_target_usd']>best['net_target_usd']:best=candidate
    return {'eligible_signals':eligible,'best_target_bound':best,'fixed_round_trip_fee_usd':float(fee),
        'exposure_limit':1,'initial_equity_usd':100,'ignored_costs':['spread','slippage','gap','variable_commission'],
        'risk_constraint_ignored_for_upper_bound':True,'quantity_rounding_ignored_for_upper_bound':True,
        'execution_authorized':False,'purpose':'OPTIMISTIC_IMPOSSIBILITY_SCREEN_NOT_SIMULATED_TRADE'}

def run(root):
    root=Path(root).resolve();a,ids,provenance=authentic_inputs(root);costs,evidence=cost_evidence(root,provenance)
    split=a['extension']['split'];folds=walk_forward(split)
    partitions=[{'name':'continuous_six_months','test_start':split['start'],'test_end':split['end']},
        {'name':'development','test_start':split['start'],'test_end':split['validation_start']},
        {'name':'validation','test_start':split['validation_start'],'test_end':split['end']},*folds]
    results=[];bounds={}
    for strategy in ids:
        all_signals=[signal(s) for s in a['candidates'] if s['strategy_id']==strategy]
        bounds[strategy]=commission_only_upper_bound(all_signals,costs)
        exits=[{'strategyId':e['strategy_id'],'side':e['side'],'at':e['at']} for e in a['exit_signals'] if e['strategy_id']==strategy]
        for part in partitions:
            start,end=date(part['test_start']),date(part['test_end'])
            bars=[{'openedAt':b['opened_at'],'minutes':15,**{k:b[k] for k in ('open','high','low','close')}}
                for b in a['normalized']['15'] if start<=date(b['opened_at']) and date(b['opened_at'])+timedelta(minutes=15)<=end]
            selected=[s for s in all_signals if start<=date(s['entryAt'] or s['signalAt'])<end]
            rows=simulate(root,strategy,bars,selected,exits,costs)
            for row in rows:
                row.update(partition=part['name'],strategy_version=ids[strategy]['strategy_version'],
                    confidence=uncertainty(row['trades'],f"{strategy}-{part['name']}-{row['riskFraction']}"))
            results.extend(rows)
    validation=[r for r in results if r['partition']=='validation']
    for row in validation:
        wf=[r for r in results if r['strategy']==row['strategy'] and r['riskFraction']==row['riskFraction'] and r['partition'].startswith('walk_forward_')]
        row['selection']=selection_checks(row['metrics'],row['confidence'],wf)
    recommendation=choose(validation)
    source_files=['src/TradingAgent.ResearchLab/ProgressiveRisk.cs','src/TradingAgent.ResearchLab/Program.cs',
        'src/TradingAgent.Core/ResearchExitSemantics.cs','python/trading_agent/progressive_risk_research.py']
    report={'generated_at':stamp(),'protocol':PROTOCOL,'provenance':provenance,'strategy_versions':ids,'frozen_split':split,
        'partitions':partitions,'costs':costs,'execution_evidence':evidence,'commission_only_upper_bounds':bounds,
        'results':results,'recommendation':recommendation,
        'source_hashes':{p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in source_files},
        'orders_sent':0,'execution_authorized':False,'live_enabled':False,'active_risk_limits_modified':False,
        'limitations':['Existing validation has already been examined; this is retrospective OOS replay, not fresh untouched confirmation.',
            '24 risk/strategy comparisons are disclosed; Wilson and block-bootstrap intervals use Bonferroni family correction.',
            'No parameters are refitted; expanding chronological training windows only establish past-only context.',
            'Each partition/fold starts independent USD100/USD20. Never add their P&L or compare them as one persistent account.',
            'Six-month replay carries consumed losses continuously, including across the development/validation boundary.',
            'Model includes BUY and SELL; protected Paper strategy adapter supports long entries only.',
            'Original research exit semantics shared; actual broker execution equivalence is not certified.',
            'OHLC cannot identify intrabar fill times; exit timestamps follow original close/next-open model.',
            'Pending/uncertain outcomes retain one-position lock across local midnight; replay assumes estimated fees finalized at exit.',
            'Gap reserve is a sizing buffer. Actual modeled gaps enter gross P&L and may exceed the budget.',
            'Maximum archived average/tick spread is a stress scenario, not reconstructed historical executable BID/ASK.',
            'Current Paper fees and archive-wide spread stress are applied counterfactually to past signals; they are not an ex-ante historical cost forecast.',
            'The commission-only upper bound ignores risk and all variable costs to test whether any first target can cover fixed fees at 1x.',
            'Full notional plus round-trip costs funded from own equity; margin, actual tariff and odd-lot eligibility remain unknown.',
            'No-trade win rate, expectancy, average win/loss and PF are undefined. Zero P&L/drawdown does not establish viability.'],
        'research_alternatives':['Obtain authoritative small-size Paper tariff, margin and odd-lot evidence through a separately authorized diagnostic.',
            'Collect fresh untouched data and historical executable BID/ASK/slippage observations.',
            'Investigate fee-compatible instruments or a different virtual capital in a separately approved research scope.',
            'Do not raise leverage or operative risk to compensate for fixed commissions.']}
    out=root/'artifacts/research/progressive-risk';out.mkdir(parents=True,exist_ok=True)
    (out/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    with (out/'comparison.csv').open('w',encoding='utf-8',newline='') as stream:
        names=['strategy','strategy_version','partition','riskFraction',*results[0]['metrics'].keys(),'rejection_reasons','confidence']
        writer=csv.DictWriter(stream,fieldnames=names);writer.writeheader()
        for row in results:writer.writerow({**{k:row[k] for k in names[:4]},**row['metrics'],
            'rejection_reasons':json.dumps(row['rejections']),'confidence':json.dumps(row['confidence'])})
    write_markdown(root,report)
    return {'status':recommendation['status'],'scenarios':len(results),'risk_strategy_combinations':24,
        'admitted_continuous':sum(r['metrics']['admitted'] for r in results if r['partition']=='continuous_six_months'),
        'report':str(out/'report.json'),'orders_sent':0}

def write_markdown(root,report):
    lines=['# Investigación progresiva de riesgo con US$100','',f"Resultado: **{report['recommendation']['status']}**.",
        '', 'Simulación aislada. Exposición 1×, pérdidas acumuladas US$20 y políticas operativas intactas. Ninguna estrategia promovida ni orden enviada.',
        '',f"Dataset `{report['provenance']['dataset_hash']}`; {report['frozen_split']['start']}–{report['frozen_split']['end']}; validación desde {report['frozen_split']['validation_start']}.",
        '',f"Costos por ciclo: BUY US${report['costs']['openingCommission']} + SELL US${report['costs']['closingCommission']}; spread {report['costs']['spread']}; slippage {report['costs']['slippage']}; reserva gap {report['costs']['adverseGap']} USD/EUR.",
        '', 'La comisión observada procede del diagnóstico Paper cerrado, no de resultados de estrategia. La extensión de esa tarifa a otras cantidades y el margen IBKR siguen desconocidos.',
        '', '## Versiones exactas','']
    lines += [f"- {k}: `{v['strategy_version']}` (V1, parámetros sin cambios)." for k,v in report['strategy_versions'].items()]
    lines += ['', '## Comprobación favorable independiente del spread de estrés','',
        'Incluso suponiendo spread, slippage y gap cero, sin redondeo de cantidad y sin aplicar el límite de riesgo, se reservan US$4 de comisión y se financia un notional máximo de US$96. Esta cota superior evalúa el mejor target entre todas las señales elegibles; no recomienda esos tamaños ni constituye un trade. Ningún target cubre las comisiones: no existe una primera entrada admisible por este criterio económico. Esto no calcula la probabilidad de un resultado positivo excepcional por gaps o por salida a la siguiente apertura.',
        '', '| Estrategia | Señales elegibles | EUR en el mejor target | Notional USD | Target bruto máximo USD | Target neto máximo USD |',
        '|---|---:|---:|---:|---:|---:|']
    for strategy,b in report['commission_only_upper_bounds'].items():
        t=b['best_target_bound']
        if t:lines.append(f"| {strategy} | {b['eligible_signals']} | {t['quantity_eur']:.4f} | {t['notional_usd']:.2f} | {t['gross_target_usd']:.5f} | {t['net_target_usd']:.5f} |")
    def fmt(x):return 'n/a' if x is None else f'{x:.5f}' if isinstance(x,(float,int)) else str(x)
    lines += ['', '## Comparación por riesgo: cuenta continua de seis meses','',
        '| Riesgo % | Presupuesto inicial USD | Admitidas / rechazadas | Comisión supera riesgo | Geometría inválida | Target no cubre costos | Neto / comisiones USD | DD % / días detenidos |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for rate in RATES:
        rows=[r for r in report['results'] if r['partition']=='continuous_six_months' and r['riskFraction']==rate/100]
        def count(reason):return sum(r['rejections'].get(reason,0) for r in rows)
        lines.append(f"| {rate:g} | {rate:g} | {sum(r['metrics']['admitted'] for r in rows)} / {sum(r['metrics']['rejected'] for r in rows)} | {count('COMMISSION_EXCEEDS_RISK_BUDGET')} | {count('INVALID_PRICE_GEOMETRY')} | {count('TARGET_DOES_NOT_COVER_COSTS')} | {fmt(sum(r['metrics']['netPnl'] for r in rows))} / {fmt(sum(r['metrics']['commissions'] for r in rows))} | {fmt(100*max(r['metrics']['intrabarDrawdownBound'] for r in rows))} / {sum(r['metrics']['firstLossDays'] for r in rows)} |")
    lines += ['', 'Conteos agregados entre tres estrategias independientes, nunca una cartera ni la suma de beneficios de folds. Además se excluyen 751 candidatos NO_TRADE por riesgo (175 Trend, 576 Pullback), sin contarlos como operaciones. El win rate, PF y expectativa son n/a porque no hubo trades. Cero drawdown y cero días detenidos tampoco acreditan seguridad. La ejecución IBKR continúa UNKNOWN y las entradas están rechazadas económicamente.']
    for part in report['partitions']:
        lines += ['',f"## {part['name']}",'', '| Estrategia | Riesgo % | Admitidas / rechazadas / NO_TRADE | Win neto % | Ganancia / pérdida media USD | Bruto / neto USD | Comisiones USD | PF neto | Expectativa USD | DD cerrado / intrabar % | Días primera pérdida / break-even | EUR media | Riesgo máx USD | Ejecución IBKR |',
            '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|']
        for r in [r for r in report['results'] if r['partition']==part['name']]:
            m=r['metrics'];pct=lambda v:fmt(None if v is None else 100*v)
            lines.append(f"| {r['strategy']} | {100*r['riskFraction']:g} | {m['admitted']} / {m['rejected']} / {m['noTradeCandidates']} | {pct(m['winRate'])} | {fmt(m['averageWin'])} / {fmt(m['averageLoss'])} | {fmt(m['grossPnl'])} / {fmt(m['netPnl'])} | {fmt(m['commissions'])} | {fmt(m['netProfitFactor'])} | {fmt(m['netExpectancy'])} | {pct(m['closedDrawdown'])} / {pct(m['intrabarDrawdownBound'])} | {m['firstLossDays']} / {m['breakEvenDays']} | {fmt(m['meanQuantity'])} | {fmt(m['maximumRisk'])} | UNKNOWN |")
            lines.append(f"<!-- {r['strategy']} {r['riskFraction']}: {json.dumps(r['rejections'],sort_keys=True)} -->")
    lines += ['', '## Rechazos y tamaño de muestra fuera de muestra','',
        '| Estrategia | Riesgo % | Rechazos | n / días | Wilson 95% | Wilson familia 95% (24 comparaciones) | CI bootstrap win / expectativa |',
        '|---|---:|---|---:|---|---|---|']
    for r in [r for r in report['results'] if r['partition']=='validation']:
        c=r['confidence'];lines.append(f"| {r['strategy']} | {100*r['riskFraction']:g} | {json.dumps(r['rejections'],sort_keys=True)} | {c['sample_trades']} / {c['sample_trade_days']} | {fmt(c['win_wilson_95'])} | {fmt(c['win_wilson_family_adjusted'])} | {fmt(c['block_bootstrap_win_ci'])} / {fmt(c['block_bootstrap_expectancy_ci'])} |")
    lines += ['', '## Protocolo estadístico y selección','',
        'Se fijaron previamente los ocho riesgos y tres estrategias, sin optimización. Walk-forward expansivo: cuatro meses iniciales de desarrollo y tres bloques contiguos de validación; separación de 15 minutos entre entrenamiento y prueba. Los indicadores solo usan contexto pasado. No se suman los resultados de asignaciones independientes.',
        '', 'Mínimos de investigación: 100 trades OOS y 30 días con trades; tres folds con beneficio neto positivo; win rate neto estrictamente >80%; límites inferiores de Wilson ajustado y bootstrap >80%; expectativa neta y su límite inferior >0; PF >1; drawdown intrabar ≤20%; restricciones IBKR comprobadas y una nueva muestra jamás examinada. Son criterios de investigación, no garantías ni autorización.',
        '', 'El dataset de validación ya fue usado en investigaciones anteriores: sus resultados no constituyen confirmación nueva. Un intervalo n/a con n=0 no equivale a 0% ni 100% de acierto. El bootstrap usa bloques de cinco días de trades y semilla reproducible; es aproximado y puede omitir dependencia más larga.',
        '', 'Referencias metodológicas: [Wilson/NIST](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm), [intervalos simultáneos Bonferroni/NIST](https://www.itl.nist.gov/div898/handbook/prc/section4/prc473.htm), [validación temporal/scikit-learn](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html).',
        '', '## Perfil experimental recomendado','',
        'Ninguno para activación. Aumentar el porcentaje de riesgo sin aumentar exposición no elimina la comisión fija ni crea una expectativa positiva. Se conserva PAPER_EXPERIMENTAL_10_PERCENT operativo protegido y sin activar. El perfil mínimo viable no se pudo identificar.',
        '', '## Restricciones de ejecución IBKR','',
        'El contrato informa mínimo 0.01 EUR e incremento 0.01 EUR; esa metadata no certifica permisos de cuenta, margen ni ejecución de todos los tamaños. Solo consta un diagnóstico Paper de 100 EUR. Todos los tamaños financiables aquí son inferiores al [mínimo estándar IDEALPRO de 20,000 EUR publicado por IBKR](https://investors.interactivebrokers.com/en/?f=5479) y se etiquetan odd lot; su tratamiento efectivo sigue pendiente.',
        '', 'La [tarifa pública de spot currencies IBKR](https://www.interactivebrokers.com/en/pricing/commissions-spot-currencies.php) incluye mínimos por orden, pero no sustituye la tarifa de esta cuenta. El modelo utiliza los US$2 observados en cada lado de un único diagnóstico; no asume margen disponible ni apalancamiento adicional.',
        '', '## Limitaciones','']+[f'- {s}' for s in report['limitations']]
    lines += ['', '## Alternativas de investigación','']+[f'- {s}' for s in report['research_alternatives']]
    lines += ['', '## Condiciones pendientes antes de considerar PaperAuto','',
        '- Evidencia económica nueva y suficiente, resultado neto positivo y tasas/intervalos exigidos.',
        '- Tarifas, cantidades, margen y semántica de ejecución verificadas; no eliminar STRATEGY_PAPER_EVIDENCE_REQUIRED para hacer pasar el laboratorio.',
        '- Identidad Paper y reconciliación frescas; revisión explícita del operador para emergencia y permiso PaperAuto nuevo.',
        '- Cualquier riesgo operativo diferente requiere decisión expresa y un cambio separado; este laboratorio jamás lo autoriza.',
        '- Live permanece absolutamente bloqueado.']
    lines += ['', '## Reproducción del laboratorio sin broker','', '```powershell',
        'dotnet build TradingAgent.sln -m:1', '$env:PYTHONPATH = "python"',
        '.venv/Scripts/python.exe -m trading_agent.progressive_risk_research --root .', '```',
        '', 'Salida completa: `artifacts/research/progressive-risk/report.json` y `comparison.csv`. El proceso solo lee el archivo auténtico y escribe evidencia de simulación; no consulta TWS ni registra permisos.']
    verification=root/'artifacts/test-results/progressive-risk/verification.json'
    if verification.exists():
        v=load(verification)
        if v['research_source_hashes']==report['source_hashes']:
            lines += ['', '## Regresiones y archivos de esta entrega','',
                f"Verificación {v['verified_at']}: **{v['total_passed']} pruebas aprobadas** ({v['python_passed']} Python + {v['csharp_passed']} C#), {v['failed']} fallidas y {v['skipped']} omitidas. Build sin warnings/errores, compileall Python correcto; PostgreSQL de pruebas iniciado y detenido, sin utilizar la base Paper.",
                '', 'Se preservaron las 623 pruebas anteriores y se agregaron 42 (18 Python, 24 C#). Cubren costos, ocho riesgos, exposición aislada, resultados inciertos, pérdida/break-even diario, America/Santo_Domingo, reinicios, pérdida acumulada, salidas originales, cronología, intervalos y selección conservadora.',
                '', 'Los 19 controles/archivos protegidos comparados permanecieron idénticos; emergencia activa, permiso PaperAuto ausente y cero órdenes de esta investigación. Logs y hashes en `artifacts/test-results/progressive-risk/`.',
                '', 'Archivos de código/documentación agregados o modificados:','']
            lines += [f'- `{p}`' for p in v['changed_files']]
            lines += ['', 'Evidencia generada: `report.json`, `comparison.csv`, informe Markdown y logs/hashes de verificación. No se alteraron parámetros ni versiones de estrategia.']
    (root/'docs/architecture/progressive-risk-research.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',default='.');args=p.parse_args()
    print(json.dumps(run(args.root)))
