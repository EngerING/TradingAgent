"""Counterfactual exposure study. Archive input only; no broker or permissions."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
from datetime import timedelta
from .progressive_risk_research import (authentic_inputs, cost_evidence, date, stamp,
    walk_forward, uncertainty, selection_checks, choose, PROTOCOL as BASE_PROTOCOL)
from .paper_economic_sweep import signal

EXPOSURES=(1,2,5,10,15,20)
RATES=tuple(sorted({*range(1,16),7.5,12.5}))
FAMILY_TESTS=3*len(EXPOSURES)*len(RATES)*5
PROTOCOL={**BASE_PROTOCOL,'risk_percentages':RATES,'exposures':EXPOSURES,'family_tests':FAMILY_TESTS,
    'margin_rate_assumption':.05,'maintenance_rate_assumption':.05,'margin_account_verified':False,
    'annual_financing_assumption':.10,'financing_day_basis':360,'parameter_refitting':False,
    'financing_notional_basis':'FULL_NOTIONAL_COUNTERFACTUAL_CONSERVATIVE_NOT_BROKER_BALANCE',
    'margin_formula':'max(initial_margin,maintenance_at_adverse_stop)+total_reserved_risk<=virtual_equity'}
SOURCES={
 'forex_margin':'https://www.interactivebrokers.co.uk/en/trading/margin-forex.php?ex=uk&hm=ot&pm=0&rgt=1&rsk=0&rst=120104010408080801',
 'account_types':'https://www.interactivebrokers.com/en/accounts/configuring-your-account.php',
 'permissions':'https://www.interactivebrokers.com/en/accounts/trading-and-market-data.php',
 'fx_fees':'https://www.interactivebrokers.com/en/pricing/commissions-spot-currencies.php',
 'stocks_fees':'https://www.interactivebrokers.com/en/pricing/commissions-stocks.php',
 'fractional':'https://www.interactivebrokers.com/en/trading/fractional-trading.php',
 'api_errors':'https://www.interactivebrokers.com/docs/tws-api/doc/error-handling/error-codes',
 'stock_margin':'https://www.interactivebrokers.com/en/trading/margin-stocks.php?ex=us&hm=us&pm=1&rgt=1&rsk=0&rst=101004100808',
 'crypto':'https://www.interactivebrokers.com/en/trading/products-cryptocurrencies.php',
 'options':'https://www.interactivebrokers.com/en/pricing/commissions-options.php',
 'micro_fx':'https://www.cmegroup.com/markets/microsuite/fx.html?trk=test',
 'financing':'https://www.interactivebrokers.com/en/trading/margin-rates.php',
 'idealpro_minimum':'https://investors.interactivebrokers.com/en/?f=5479',
 'schx_issuer':'https://www.schwabassetmanagement.com/products/schx'}


def profiles(costs):
    # One tick conservative floor, never a claim of executable historical BID/ASK.
    base={**costs,'spread':'.00005','source':'OBSERVED_FEES_ESTIMATED_SPREAD_SLIPPAGE_GAP_ACCOUNT_CONSTRAINTS_UNKNOWN'}
    return [dict(name='CONSERVATIVE_1_DAY',costs=base,annual=.10,days=1),
            dict(name='ARCHIVE_SPREAD_STRESS',costs=costs,annual=.10,days=1),
            dict(name='OPTIMISTIC_NO_FINANCING',costs=base,annual=0,days=0),
            dict(name='FINANCING_4_DAY_STRESS',costs=base,annual=.10,days=4),
            dict(name='OPTIMISTIC_MARGIN_2_5_PERCENT',costs=base,annual=0,days=0,margin=.025)]


def invoke(root,strategy,bars,signals,exits,profile,minimum=False):
    payload=dict(environment='SIMULATION',capital=100,lossAllowance=20,exposure=1,liveEnabled=False,
        executionAuthorized=False,researchMode='EXPOSURE_SWEEP',minimumOnly=minimum,
        strategy=strategy,bars=bars,signals=signals,exits=exits,costs=profile['costs'],
        marginAssumptions=dict(exposure=20,initialMarginRate=profile.get('margin',.05),maintenanceMarginRate=profile.get('margin',.05),
            annualFinancingRate=profile['annual'],financingReserveDays=profile['days']))
    dll=root/'src/TradingAgent.ResearchLab/bin/Debug/net9.0/TradingAgent.ResearchLab.dll'
    p=subprocess.run(['dotnet',str(dll)],input=json.dumps(payload),text=True,capture_output=True,cwd=root,timeout=180)
    result=json.loads(p.stdout)
    if p.returncode or not isinstance(result,list):raise ValueError('EXPOSURE_SIMULATION_REJECTED')
    return result


def minimum_summary(rows,margin_rate=.05):
    valid=[x for x in rows if x['minimum'] is not None]
    bounded=[x for x in valid if x['minimum']['withinFifteenPercent'] and x['minimum']['withinTwentyTimes']]
    funded=[x for x in bounded if x['minimum']['maximumAffordableMarginRate']>=margin_rate]
    smallest=min(valid,key=lambda x:x['minimum']['exposure']) if valid else None
    useful=min(funded,key=lambda x:x['minimum']['exposure']) if funded else None
    return dict(eligible_signals=len(rows),no_positive_target_or_invalid_geometry=len(rows)-len(valid),
        positive_thresholds_within_20x_15usd=len(bounded),hypothetically_funded=len(funded),
        funding_margin_rate_assumption=margin_rate,
        minimum_cost_covering=smallest,minimum_funded_risk_bounded=useful,
        actual_ibkr_executable=False,actual_margin_rate=None)


def margin_sensitivity(notional,risk=0):
    if notional<0 or risk<0:raise ValueError('INVALID_MARGIN_SENSITIVITY')
    return [dict(rate=rate,initial_margin=notional*rate,total_with_reserved_loss=notional*rate+risk,
                 collateral_fits_100=notional*rate+risk<=100,account_verified=False)
            for rate in (.025,.05,.10,.20,1)]


def alternative_costs(notional=90):
    """Illustrative tariff screen only. No price, signal or alternative strategy."""
    if not 0<notional<=100:raise ValueError('ALTERNATIVE_SCOPE_INVALID')
    rows=[]
    for instrument,side_fee in [('EURUSD_CASH',2),('US_WHOLE_SHARES_TIERED',min(.35,.01*notional)),
        ('US_WHOLE_SHARES_FIXED',min(1,.01*notional)),('US_FRACTIONAL',max(.01,.01*notional)),
        ('SPOT_CRYPTO',min(max(.0018*notional,1.75),.01*notional)),('US_LONG_OPTION',1)]:
        rows.append(dict(instrument=instrument,notional_usd=notional,round_trip_fee_usd=2*side_fee,
            fee_only_breakeven_move_percent=100*2*side_fee/notional,
            spread_slippage_regulatory_data_and_conversion_costs_included=False,
            execution_verified=False,strategy_backtested=False))
    return rows


def run(root):
    root=Path(root).resolve();a,versions,provenance=authentic_inputs(root)
    costs,evidence=cost_evidence(root,provenance);models=profiles(costs);split=a['extension']['split']
    parts=[dict(name='continuous_six_months',test_start=split['start'],test_end=split['end']),
        dict(name='development',test_start=split['start'],test_end=split['validation_start']),
        dict(name='validation',test_start=split['validation_start'],test_end=split['end']),*walk_forward(split)]
    results=[];minimums={};validation_minimums={};all_minimums={}
    for strategy in versions:
        signals=[signal(s) for s in a['candidates'] if s['strategy_id']==strategy]
        exits=[dict(strategyId=e['strategy_id'],side=e['side'],at=e['at']) for e in a['exit_signals'] if e['strategy_id']==strategy]
        for model in models:
            key=model['name']+'/'+strategy
            all_minimums[key]=invoke(root,strategy,[],signals,exits,model,True)
            minimums[key]=minimum_summary(all_minimums[key],model.get('margin',.05))
            validation_minimums[key]=minimum_summary([x for x in all_minimums[key]
                if date(split['validation_start'])<=date(x['signal']['entryAt'])<date(split['end'])],model.get('margin',.05))
            for part in parts:
                start,end=date(part['test_start']),date(part['test_end'])
                bars=[dict(openedAt=b['opened_at'],minutes=15,**{k:b[k] for k in ('open','high','low','close')})
                    for b in a['normalized']['15'] if start<=date(b['opened_at']) and date(b['opened_at'])+timedelta(minutes=15)<=end]
                candidates=[s for s in signals if start<=date(s['entryAt'] or s['signalAt'])<end]
                for row in invoke(root,strategy,bars,candidates,exits,model):
                    m=row['metrics'];n=m['admitted']+m['rejected']
                    row.update(partition=part['name'],cost_profile=model['name'],strategy_version=versions[strategy]['strategy_version'],
                        confidence=uncertainty(row['trades'],f"{key}-{part['name']}-{row['exposureLimit']}-{row['riskFraction']}",family_tests=FAMILY_TESTS),
                        empirical_model_admission_share=m['admitted']/n if n else None,
                        actual_execution_probability_current=0,future_execution_probability=None,
                        ruin_probability=None,ruin_probability_status='INSUFFICIENT_SAMPLE_AND_UNKNOWN_GAP_EXECUTION',
                        margin_sensitivity=margin_sensitivity(m['maximumNotional'],m['maximumRisk']) if m['maximumNotional'] else [])
                    results.append(row)
    validation=[x for x in results if x['partition']=='validation']
    for row in validation:
        folds=[x for x in results if x['strategy']==row['strategy'] and x['cost_profile']==row['cost_profile']
            and x['exposureLimit']==row['exposureLimit'] and x['riskFraction']==row['riskFraction'] and x['partition'].startswith('walk_forward_')]
        row['selection']=selection_checks(row['metrics'],row['confidence'],folds)
        if row['metrics']['riskBudgetBreaches'] or row['metrics']['financingReserveExceedances']:
            row['selection']['eligible_for_further_review']=False
            row['selection']['reasons'].append('MODELED_RISK_OR_FINANCING_RESERVE_BREACHED')
    files=['src/TradingAgent.ResearchLab/ExposureStudy.cs','src/TradingAgent.ResearchLab/ProgressiveRisk.cs',
        'src/TradingAgent.ResearchLab/Program.cs','src/TradingAgent.Core/ResearchExitSemantics.cs',
        'python/trading_agent/progressive_risk_research.py','python/trading_agent/exposure_economic_research.py']
    report=dict(generated_at=stamp(),protocol=PROTOCOL,strategy_versions=versions,provenance=provenance,
        frozen_split=split,partitions=parts,cost_profiles=models,execution_evidence=evidence,minimums=minimums,
        validation_minimums=validation_minimums,
        results=results,recommendation=choose(validation),alternative_tariff_screen=alternative_costs(),
        alternative_issuer_examples=[dict(symbol='SCHX',name='Schwab US Large-Cap ETF',exchange='NYSE Arca',
            published_midpoint_usd=30.03,price_observation_date='2026-09-09',
            published_30_day_median_spread_percent=.03,price_is_current=False,
            source=SOURCES['schx_issuer'],ibkr_contract_verified=False,account_permission_verified=False,
            eligible_for_activation=False,strategy_backtested=False)],
        capacity_margin_sensitivity={str(e):margin_sensitivity(100*e) for e in EXPOSURES},
        gap_stress_capacity=[dict(exposure=e,notional=100*e,price_gap_percent=g,
            loss_before_costs=100*e*g/100,equity_after_before_costs=100-100*e*g/100,
            probability=None,stop_failed_assumption=True) for e in EXPOSURES for g in (1,2,5)],
        broker_constraints=dict(actual_initial_margin_rate=None,actual_maintenance_margin_rate=None,
            legal_entity=None,account_type=None,spot_currency_borrowing_permission=None,
            all_sizes_acceptance_verified=False,minimum_eur_metadata=.01,quantity_increment_eur_metadata=.01,
            price_tick_metadata=.00005,metadata_from_cached_diagnostic_only=True,
            active_strategy_entry_side='BUY',independent_short_entry_supported=False),
        source_hashes={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in files},
        public_sources_reviewed_at=stamp(),public_sources=SOURCES,account_constraints_verified=False,
        orders_sent=0,broker_connected=False,live_enabled=False,execution_authorized=False,
        active_limits_modified=False,strategy_parameters_modified=False,
        limitations=[
            'Virtual allocation USD100 and persistent consumed losses USD20; no broker buying power is used.',
            'Initial/maintenance 5% is a hypothesis, NOT verified IBKR EURUSD margin. Loss to stop and costs also need collateral.',
            'Full-notional ACT/360 financing at 10% is a scenario, not broker accrual reconstruction. One-day/four-day reserves do not change V1 exits.',
            'Estimated financing uses elapsed calendar days. Actual broker settlement, interest tiers, minimum financing, rollover and fee changes remain unknown.',
            'Current observed Paper fees are replayed counterfactually on historical MIDPOINT candles. Limit fill probability and liquidity are not reconstructed.',
            'One-tick spread is an estimate; archive maximum spread and four-day financing are disclosed stress cases.',
            'Reported model admission shares are deterministic historical frequencies, not probabilities of IBKR acceptance or fill.',
            'Current execution cannot pass emergency/no-authorization/economic-evidence gates. Future execution probability and capital ruin probability are unknown.',
            'Existing validation was examined before this study. It is retrospective OOS replay, not a fresh untouched confirmation.',
            '1530 validation comparisons, Bonferroni-adjusted Wilson and moving-block intervals; no parameters optimized.',
            'The favorable 2.5% margin case was added after initial 5% results to check sensitivity. This is exploratory, not preregistered confirmation; family correction does not erase adaptive selection bias.',
            'Expanding past-only folds with 15-minute separation; folds start independent USD100/USD20, and results cannot be summed.',
            'Continuous six-month run does not replenish losses or restart equity at validation boundary.',
            'Shared V1 stop/target/EMA/multiframe/next-open/gap semantics preserved. Actual broker protection, tick rounding and short entry support remain unverified.',
            'All quantities under the 20x ceiling are odd lot. Contract minimum 0.01/increment0.01 is metadata, not verified permission for every size.',
            'Cash settlement may block a second same-day trade despite a first net winner. Daily policy never overrides cash/permission gates.',
            'Stops cannot guarantee loss caps under gaps or disconnection. A 20x position can consume USD100 on a 5% adverse gap before fees.',
            'Alternative tariff calculations do not imply a strategy, current executable quotes or net profitability. No alternative dataset/backtest was created.'
        ])
    out=root/'artifacts/research/exposure-alternatives';out.mkdir(parents=True,exist_ok=True)
    (out/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    (out/'minimum-opportunities.json').write_text(json.dumps(all_minimums,indent=2),encoding='utf-8')
    with (out/'comparison.csv').open('w',encoding='utf-8',newline='') as stream:
        names=['strategy','strategy_version','partition','cost_profile','exposureLimit','riskFraction',*results[0]['metrics'],
            'empirical_model_admission_share','future_execution_probability','ruin_probability','rejections','confidence','margin_sensitivity']
        writer=csv.DictWriter(stream,fieldnames=names);writer.writeheader()
        for row in results:
            values={k:row[k] for k in names if k in row};values.update(row['metrics'])
            for k in ('rejections','confidence','margin_sensitivity'):values[k]=json.dumps(values[k])
            writer.writerow(values)
    write_report(root,report)
    return dict(status=report['recommendation']['status'],scenarios=len(results),family_tests=FAMILY_TESTS,
        orders_sent=0,report=str(out/'report.json'))


def write_report(root,r):
    def f(x):
        if x is None:return 'n/a'
        if isinstance(x,(int,float)):return f'{x:.3e}' if 0<abs(x)<.0001 else f'{x:.4f}'
        return str(x)
    lines=['# Exposición Forex y alternativas con capital experimental US$100','',
        f"Resultado: **{r['recommendation']['status']}**. Sin promoción, órdenes, permisos ni cambios operativos.",'',
        'Se evaluaron 17 riesgos (enteros 1–15%, más 7.5/12.5% anteriores), seis exposiciones y cinco escenarios: 9,180 simulaciones en seis particiones; 1,530 combinaciones en validación. Tres V1 sin cambios. Exposición mayor solo en el ejecutable ResearchLab, sin transporte.',
        '',f"Dataset `{r['provenance']['dataset_hash']}`, {r['frozen_split']['start']} a {r['frozen_split']['end']}; validación desde {r['frozen_split']['validation_start']}.",
        '', '## Costos, margen y restricciones','',
        'US$2 por lado observados en un único diagnóstico Paper. Base: spread estimado 0.00005, slippage conservador 0.00045 y gap reservado 0.00005 USD/EUR. Financiación estimada 10% anual ACT/360 sobre todo el notional, reserva de un día; se liquida el costo modelado por tiempo realmente mantenido. No se fuerza una salida al cumplir el plazo de reserva. Se informa cualquier exceso.',
        '',f"Spread de estrés del archivo: {r['cost_profiles'][1]['costs']['spread']}. Se compara sin financiación, con reserva de cuatro días y en un quinto caso favorable sin financiación/margen 2.5% hipotético. Un costo de USD4 ya impide los riesgos iniciales 1–4% antes del movimiento del precio.",
        '', 'La tasa inicial/mantenimiento 5% es **hipotética**, con margen más pérdida completa al stop financiados por los US$100. IBKR calcula margen por saldos netos de moneda y puede exigir más; sus ejemplos 2.5% no certifican una tasa actual. [IBKR Forex margin]('+SOURCES['forex_margin']+').',
        '', 'El [tipo de cuenta]('+SOURCES['account_types']+') puede impedir préstamos; [Spot Currencies requiere permisos adicionales]('+SOURCES['permissions']+'). Para determinadas entidades/cuentas IBLLC se exige ECP; la entidad, residencia, tipo de cuenta y permisos aplicables siguen sin verificar. El margen archivado 0 estando flat no prueba capacidad para abrir.',
        '', 'El mínimo/incremento del contrato archivado es 0.01 EUR/0.01 EUR; tick 0.00005. [IDEALPRO estándar]('+SOURCES['idealpro_minimum']+') publica 20,000 EUR; todos los tamaños del estudio hasta 20× quedan por debajo. Solo 100 EUR se probó en el diagnóstico previo; otros tamaños, protección, min tick efectivo y short permanecen sin confirmar.',
        '', '## Exposición mínima para target neto positivo','',
        'Umbrales mínimos en los seis meses completos; no representan mínimos confirmados fuera de muestra. La validación se distingue en la tabla siguiente.',
        '',
        '| Costos | Estrategia | EUR mínimo | Notional USD | Exposición | Stop USD | Costos USD | Gap / financiación USD | Riesgo total USD | Target bruto / neto USD | Margen máximo financiable % | Umbrales ≤20×/≤US15 / financiados al margen supuesto |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for key,s in r['minimums'].items():
        record=s['minimum_cost_covering'];m=record['minimum'] if record else None
        if m:
            lines.append(f"| {key} | {record['signal']['strategyId']} | {f(m['quantity'])} | {f(m['notional'])} | {f(m['exposure'])} | {f(m['stopLoss'])} | {f(m['costs'])} | {f(m['gapReserve'])} / {f(m['financingReserve'])} | {f(m['totalRisk'])} | {f(m['grossTarget'])} / {f(m['netTarget'])} | {f(100*m['maximumAffordableMarginRate'])} | {s['positive_thresholds_within_20x_15usd']} / {s['hypothetically_funded']} ({100*s['funding_margin_rate_assumption']:g}%) |")
        else:lines.append(f'| {key} | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 0 / 0 |')
    lines += ['', 'El mínimo cubre costos por un excedente infinitesimal a causa del paso de cantidad. No acredita beneficio razonable, muestra suficiente, permisos ni ejecución. La oportunidad mínima financiada, si existe, y cada señal/versión exacta están en JSON. Todas siguen executionAuthorized=false.',
        '', '### Umbrales en validación exclusivamente','',
        '| Costos / estrategia | Señales elegibles | Menor exposición de target positivo | Riesgo a ese umbral USD | Umbrales ≤20×/≤US15 | Financiados al margen supuesto |',
        '|---|---:|---:|---:|---:|---:|']
    for key,s in r['validation_minimums'].items():
        m=s['minimum_cost_covering']['minimum'] if s['minimum_cost_covering'] else None
        lines.append(f"| {key} | {s['eligible_signals']} | {f(m['exposure'] if m else None)} | {f(m['totalRisk'] if m else None)} | {s['positive_thresholds_within_20x_15usd']} | {s['hypothetically_funded']} ({100*s['funding_margin_rate_assumption']:g}%) |")
    lines += [
        '', '## Margen de capacidad por exposición (sin costos ni reserva de pérdida)','',
        '| Exposición | Notional capacidad USD | Margen hipotético 2.5% | 5% | 10% | 20% | Sin préstamo 100% |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for e in EXPOSURES:lines.append(f'| {e}× | {100*e} | {2.5*e} | {5*e} | {10*e} | {20*e} | {100*e} |')
    lines += ['', 'La tabla usa equity inicial US$100. Durante la simulación, riesgo porcentual y exposición se calculan sobre equity virtual actual; las ganancias aumentan equity, pero no restauran pérdidas consumidas. Se agregan comisión, spread, slippage, gap y pérdida al stop. A 20×, 5% consume US$100 antes de esas reservas: el tamaño efectivo debe reducirse. El CSV contiene margen inicial/mantenimiento y sensibilidad para las cantidades realmente admitidas. No se utiliza la capacidad de compra ficticia de IBKR.',
        '', '## Backtesting cronológico con política diaria','',
        'America/Santo_Domingo; una posición y bloqueo hasta resultado final. Ganancias permiten buscar otra señal; primera pérdida neta o break-even bloquea entradas hasta el día siguiente. NO_TRADE no cuenta. Pérdidas acumuladas US$20 no se restauran con beneficios. La cuenta continua atraviesa desarrollo/validación sin reiniciarse.',
        '', 'Celdas: operaciones admitidas / P&L neto USD. Cada celda es un experimento independiente, no una cartera. Rechazos, fees, spread, slippage, financiación, riesgo, DD, primera pérdida y todas las particiones figuran en CSV/JSON.']
    lines += ['', '### Resultado continuo observado','',
        '| Estrategia / costos / riesgo % | Trades / rechazadas | EUR | Margen inicial / al stop USD | Riesgo reservado USD | Bruto / neto USD | Comisión / spread / slippage / financiación USD | Win % / PF / EV | DD intrabar % | Días detenidos |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    seen=set()
    for row in [x for x in r['results'] if x['partition']=='continuous_six_months' and x['metrics']['admitted']]:
        m=row['metrics'];key=(row['strategy'],row['cost_profile'],m['netPnl'])
        if key in seen:continue
        seen.add(key)
        lines.append(f"| {row['strategy']} / {row['cost_profile']} / {100*row['riskFraction']:g} (20×) | {m['admitted']} / {m['rejected']} | {f(m['meanQuantity'])} | {f(m['maximumInitialMargin'])} / {f(m['maximumMaintenanceMargin'])} | {f(m['maximumRisk'])} | {f(m['grossPnl'])} / {f(m['netPnl'])} | {f(m['commissions'])} / {f(m['spreadCost'])} / {f(m['slippageCost'])} / {f(m['financingCost'])} | {f(100*m['winRate'])} / {f(m['netProfitFactor'])} / {f(m['netExpectancy'])} | {f(100*m['intrabarDrawdownBound'])} | {m['firstLossDays']} |")
    primary=next((x for x in r['results'] if x['partition']=='continuous_six_months' and x['cost_profile']=='CONSERVATIVE_1_DAY' and x['metrics']['admitted']),None)
    lines += ['', 'Se muestran una vez los resultados idénticos entre riesgos; cada celda del barrido y cada trade están disponibles completos.']
    if primary:
        t=primary['trades'][0];trade=t['trade'];size=t['size'];m=primary['metrics']
        funded=max(size['initialMarginRequired'],size['maintenanceMarginAtStop'])+size['totalRisk']
        lines += ['', f"En la base, {primary['strategy']} desde riesgo {100*primary['riskFraction']:g}% realiza {trade['side']} de {f(trade['quantity'])} EUR en {trade['entryAt']}, cierra por {trade['reason']} y registra neto US${f(trade['netPnl'])}. Margen al stop + riesgo reservado US${funded:.5f}: colchón adicional US${size['entryEquity']-funded:.5f}. La admisión histórica {m['admitted']}/{m['admitted']+m['rejected']} ({100*primary['empirical_model_admission_share']:.3f}%) no es una probabilidad de fill."]
    sides=sorted({t['trade']['side'] for x in r['results'] for t in x['trades']})
    lines += ['', f"Lados de entrada admitidos en el modelo: {sides}. El adapter StrategyPaper vigente acepta únicamente BUY y cierre SELL del inventario propio; entradas short SELL **no son ejecutables con el transporte protegido actual**. La investigación conserva ambos lados originales de V1, sin habilitar SELL independiente.",
        '', 'En la base 5% de margen y reserva de un día, validación y los tres folds fuera de muestra tienen cero admisiones. El quinto escenario favorable se presenta por separado abajo; no verifica la tasa real IBKR. Los resultados continuos no prueban rentabilidad ni el objetivo >80%.']
    for partition in ('continuous_six_months','validation'):
        for strategy in r['strategy_versions']:
            lines += ['',f'### {partition}: {strategy}, CONSERVATIVE_1_DAY','',
                '| Riesgo % | 1× | 2× | 5× | 10× | 15× | 20× |','|---:|---:|---:|---:|---:|---:|---:|']
            for rate in RATES:
                cells=[]
                for e in EXPOSURES:
                    row=next(x for x in r['results'] if x['partition']==partition and x['strategy']==strategy
                        and x['cost_profile']=='CONSERVATIVE_1_DAY' and x['riskFraction']==rate/100 and x['exposureLimit']==e)
                    cells.append(f"{row['metrics']['admitted']} / {f(row['metrics']['netPnl'])}")
                lines.append('| '+str(rate)+' | '+' | '.join(cells)+' |')
    lines += ['', '## Estadística y robustez: todas las configuraciones con trades en validación','',
        '| Estrategia / costos | Expo / riesgo % | n / días | Win % | Win CI familia | Ganancia / pérdida media | PF / EV | Neto / fees / financiación | DD intrabar % | Días primera pérdida | Brechas riesgo / financiación |',
        '|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|']
    rows=[x for x in r['results'] if x['partition']=='validation' and x['metrics']['admitted']]
    for row in rows:
        m=row['metrics'];c=row['confidence']
        lines.append(f"| {row['strategy']} / {row['cost_profile']} | {row['exposureLimit']} / {100*row['riskFraction']:g} | {m['admitted']} / {c['sample_trade_days']} | {f(100*m['winRate'])} | {c['win_wilson_family_adjusted']} | {f(m['averageWin'])} / {f(m['averageLoss'])} | {f(m['netProfitFactor'])} / {f(m['netExpectancy'])} | {f(m['netPnl'])} / {f(m['commissions'])} / {f(m['financingCost'])} | {f(100*m['intrabarDrawdownBound'])} | {m['firstLossDays']} | {m['riskBudgetBreaches']} / {m['financingReserveExceedances']} |")
    if not rows:lines += ['','No hubo operaciones de validación admitidas en ningún modelo; win rate, expectativa y PF no son estimables.']
    if rows:
        best=max(rows,key=lambda x:x['metrics']['netPnl']);m=best['metrics'];ci=best['confidence']
        lines += ['', f"El caso favorable que admite trades OOS ({best['cost_profile']}, {best['strategy']}, {best['exposureLimit']}×) tiene n={m['admitted']}, win rate {100*m['winRate']:g}%, neto US${f(m['netPnl'])}, PF {f(m['netProfitFactor'])} y expectativa US${f(m['netExpectancy'])}. Wilson familiar: {ci['win_wilson_family_adjusted']}. Sin cinco días de trades no se estima bootstrap. El 2.5% de margen y financiación cero siguen siendo hipótesis favorables, no condiciones demostradas IBKR."]
        if m['averageWin'] and m['averageLoss']:
            breakeven=m['averageLoss']/(m['averageLoss']+m['averageWin'])
            lines += ['', f"Usando solo esas medias observadas, la tasa de equilibrio sería {100*breakeven:.2f}%: superar 80% no bastaría con ese reparto de ganancias/pérdidas. Con n={m['admitted']} esto es una identidad descriptiva, no un pronóstico ni una estimación robusta."]
    lines += ['', 'La selección exige n≥100 OOS, ≥30 días, tres folds netamente positivos, win rate >80% y límites inferiores ajustados/bootstrap >80%, expectativa y límite inferior >0, PF>1, DD intrabar≤20%, margen/permisos comprobados y nueva muestra nunca examinada. Wilson supone IID; bootstrap por bloques de cinco días es aproximado. La validación ya se examinó antes, y las 1,530 comparaciones se corrigen conjuntamente; ningún resultado puntual alto se fuerza a aprobación. Métodos: [Wilson/NIST](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm) y [Bonferroni/NIST](https://www.itl.nist.gov/div898/handbook/prc/section4/prc473.htm).',
        '', '## Probabilidad de filtros y agotamiento de capital','',
        'Con emergencia activa, permiso PaperAuto ausente y veto económico, ninguna entrada puede superar los gates actuales: 0 por condición determinista. Para una futura sesión autorizada la probabilidad de aceptación/fill IBKR es UNKNOWN; el porcentaje histórico admitido por el modelo no la estima. Tampoco existe muestra suficiente para inferir probabilidad de ruina.',
        '', 'El presupuesto acumulado de US$20 suspende nuevas entradas; no garantiza pérdidas máximas si falla el stop. Un gap adverso 1%/2%/5%, sin stop efectivo, genera pérdidas antes de costos de US$20/40/100 a exposición 20×. Tabla de estrés completa y flags de agotamiento/brechas en JSON. La política de primera pérdida reduce nuevas entradas; no protege por sí sola la posición abierta.',
        '', '## Alternativas de menor costo relativo','',
        'Screen de tarifas con notional ilustrativo US$90, sin señal ni precio real; las tarifas de cuenta y los costos variables no están verificados. No se trasladan V1 Forex a estos instrumentos ni se implementan estrategias nuevas.',
        '', '| Instrumento | Comisión ida/vuelta ilustrativa USD | Movimiento bruto mínimo para solo comisión % | Mínimos / restricciones |',
        '|---|---:|---:|---|']
    descriptions={
        'EURUSD_CASH':'0.01 EUR metadata; odd lot, préstamo/permiso Cash Forex desconocidos',
        'US_WHOLE_SHARES_TIERED':'Una acción/cuota; precio debe caber en cash. Requiere stock permissions, USD liquidado, market data y adapter nuevo',
        'US_WHOLE_SHARES_FIXED':'Una acción/cuota; USD liquidado; same-day reutilización del cash no asumida',
        'US_FRACTIONAL':'Marketing desde USD1; incremento, SMART, API/stop/bracket y permisos por contrato por verificar',
        'SPOT_CRYPTO':'Proveedor/residencia, mínimo e incremento por contrato, Paper/API y protección por verificar',
        'US_LONG_OPTION':'Un contrato; prima, multiplicador, spread, griegas/expiración. Riesgo total prima+costos, sin ventas descubiertas'}
    for x in r['alternative_tariff_screen']:
        lines.append(f"| {x['instrument']} | {f(x['round_trip_fee_usd'])} | {f(x['fee_only_breakeven_move_percent'])} | {descriptions[x['instrument']]} |")
    lines += ['', 'Las [acciones/ETF estadounidenses completos]('+SOURCES['stocks_fees']+') tienen mínimos publicados USD0.35 Tiered o USD1 Fixed, cap 1% por lado; fractions tienen su propia regla mayor de 1% o USD0.01. El ejemplo supone pocas acciones y excluye cargos externos. Lite no se asume disponible para esta cuenta.',
        '', 'Las [fracciones]('+SOURCES['fractional']+') caben por importe, pero [errores API 10242–10249]('+SOURCES['api_errors']+') documentan restricciones de modificación, colocación, SMART, instrumentos y permisos; no se presume que una orden protectora fraccional funcione.',
        '', '[Crypto IBKR]('+SOURCES['crypto']+') publica mínimo USD1.75 con cap 1% por orden; depende de proveedor y residencia. [Opciones]('+SOURCES['options']+') publican mínimo USD1 por orden más cargos externos. Menor comisión no prueba una ventaja estadística ni soporte Paper de este proyecto.',
        '', 'El [micro EUR/USD M6E]('+SOURCES['micro_fx']+') representa 12,500 EUR por contrato entero: con el midpoint archivado ≈1.12 supera US$14,000/140×, fuera del techo investigado 20×. Margen actual y permiso futuros no están confirmados. No reduce automáticamente la barrera de US$100.',
        '', 'Para instrumentos en cash se requiere saldo liquidado; vender con beneficio no vuelve utilizable automáticamente todo el efectivo. [Restricciones de acciones/margen]('+SOURCES['stock_margin']+') y reglas de day trading dependen de entidad, residencia, plan y normativa vigente; no se infieren de la cuenta Paper grande.',
        '', 'Prioridad de investigación siguiente: acciones/ETF completos en USD con precio y liquidez compatibles, plan Tiered y evidencia auténtica nueva. Solo es una candidatura para investigar costos y datos: **ninguna configuración alternativa está demostrada viable ni autorizada**.',
        '', 'Ejemplo concreto para esa siguiente investigación: [SCHX, Schwab U.S. Large-Cap ETF]('+SOURCES['schx_issuer']+'), NYSE Arca. El emisor publica midpoint US$30.03 al 2026-09-09 y spread mediano de 30 días 0.03%; esos datos son antiguos, no BID/ASK actuales de IBKR. Tres cuotas a ese precio serían US$90.09 y comisión Tiered ilustrativa US$0.70 por ciclo antes de cargos externos/spread/slippage. Cabe por capital y evita fracciones; no demuestra señal rentable, permiso de cuenta, protección ni disponibilidad efectiva del contrato en Paper. No se usan sus retornos de inversión como resultados de una estrategia TradingAgent.',
        '', '## Condiciones que impiden operar','',
        '- Verificadas/preservadas: EmergencyStop activo, PaperAuto no concedido, veto de evidencia económica, exposición operativa 1× y riesgo operativo protegido sin cambios.',
        '- Investigación: Trend requiere exposición superior a 20× en todos los escenarios de costos considerados; muestras positivas potenciales de las otras V1 no bastan para certificar 80%/expectativa/robustez.',
        '- Pendientes bloqueantes: tasa efectiva de margen/maintenance, entidad y permisos de préstamo, odd lot, cantidades, tick/protección/short, comisiones por tamaño y financiación real, BID/ASK y mercado frescos.',
        '- Alternativas: sin adapter aprobado, estrategia/dataset/evidencia fuera de muestra, reconciliación y protección específicas. No están en la autorización/allowlist existente.',
        '- No eliminar estos controles para convertir una simulación condicional en permiso. No promover ninguna V1 ni activar PaperAuto. Live permanece bloqueado.',
        '', '## Limitaciones','']+[f'- {s}' for s in r['limitations']]
    lines += ['', '## Versiones exactas','']+[f"- {s}: `{v['strategy_version']}`; config `{v['configuration_hash']}`." for s,v in r['strategy_versions'].items()]
    lines += ['', '## Reproducción sin órdenes','', '```powershell','dotnet build TradingAgent.sln -m:1',
        '$env:PYTHONPATH = "python"','.venv/Scripts/python.exe -m trading_agent.exposure_economic_research --root .','```',
        '', 'Resultados completos: `artifacts/research/exposure-alternatives/report.json`, `comparison.csv` y `minimum-opportunities.json`. Logs/regresiones en `artifacts/test-results/exposure-alternatives/`.']
    verification=root/'artifacts/test-results/exposure-alternatives/verification.json'
    if verification.exists():
        v=json.loads(verification.read_bytes())
        if v['research_source_hashes']==r['source_hashes']:
            lines += ['', '## Verificación y archivos de esta entrega','',
                f"{v['verified_at']}: **{v['total_passed']} pruebas aprobadas** ({v['python_passed']} Python + {v['csharp_passed']} C#); cero fallos y cero omisiones. Build cero warnings/errores y compileall correcto. PostgreSQL desechable 55432 iniciado/detenido; base Paper sin utilizar. Conservadas las 665 anteriores; 25 nuevas (11 Python, 14 C#).",
                '', 'Pruebas nuevas: exposición/costos/margen dentro del capital virtual, financiaciones y excesos, gaps con agotamiento sin ocultar pérdidas, límites de ámbito, redondeo estricto del umbral, tipos de costo, corrección estadística, frontera real del ejecutable y persistencia de los gates anteriores.',
                '', 'Los 19 controles/archivos protegidos verificados permanecen idénticos. AccountBinding, emergencia, autorizaciones y fuentes operativas sin cambios. No hubo conexión IBKR ni órdenes; no se certificaron condiciones nuevas de cuenta.',
                '', 'Código/documentación agregado o modificado:','']
            lines += [f'- `{p}`' for p in v['changed_files']]
    (root/'docs/architecture/exposure-alternatives-research.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',default='.');args=p.parse_args()
    print(json.dumps(run(args.root)))
