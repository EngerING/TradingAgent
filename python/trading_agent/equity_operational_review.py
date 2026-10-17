"""Fixed three-instrument feasibility review; no strategy search or execution."""
import argparse
from datetime import datetime,timezone
from decimal import Decimal
import json
from pathlib import Path
from .paper_account_capabilities import collect_capabilities, account_facts, observed
from .equity_data_integrity import integrity_report, verified_archive
from .equity_research_data import UNIVERSE
from .equity_evidence_extension import save, SOURCES
from .equity_strategy_research import commission
from .tws import finite

PRIMARY={**SOURCES,
    'fractional_check':'https://www.ibkrguides.com/clientportal/trade-in-fractions.htm',
    'fee_plan_check':'https://www.ibkrguides.com/clientportal/pricingstructure.htm',
    'cash_check':'https://ibkrguides.com/tws/usersguidebook/realtimeactivitymonitoring/balances.htm',
    'portfolio_summary':'https://www.interactivebrokers.com/docs/web-api/api-reference/trading/trading-accounts/get-account-summary',
    'margin_scope':'https://www.interactivebrokers.com/en/trading/margin-requirements.php',
    'schx_split_2022':'https://pressroom.aboutschwab.com/press-releases/press-release/2022/Schwab-Asset-Management-Announces-ETF-Share-Splits/default.aspx',
    'spy_distributions':'https://www.ssga.com/us/en/individual/resources/documents/etf-dividend-distributions',
    'ford_dividends':'https://www.shareholder.ford.com/Information/stock/default.aspx',
    'ford_supplemental':'https://www.miaxglobal.com/sites/default/files/alert-files/F_Dividend__54075.pdf'}


def cash_geometry(bid,ask,q,model):
    bid,ask=finite(bid,True),finite(ask,True)
    if bid>ask or type(q) is not int or not 1<=q<=10000:raise ValueError('QUOTE_OR_QUANTITY_INVALID')
    buy=commission(q,ask,model);sell=commission(q,bid,model)
    # Frozen research stress envelope, with one-cent floor. Never a measured fill cost.
    slip=max(Decimal('.01'),ask*Decimal('.0015'))*2*q
    funds=ask*q+buy+sell+slip
    return dict(quantity=q,notional_usd=float(ask*q),funds_with_exit_reserve_usd=float(funds),
        opening_fee_usd=float(buy),closing_fee_usd=float(sell),roundtrip_fees_usd=float(buy+sell),
        spread_cost_usd=float((ask-bid)*q),slippage_reserve_usd=float(slip),
        roundtrip_cost_usd=float(buy+sell+(ask-bid)*q+slip),
        fits_virtual_usd100=funds<=100 and ask*q<=100,cost_status='ESTIMATED',
        stop_risk_status='UNKNOWN_NO_SIGNAL_OR_STOP_EVALUATED',execution_authorized=False)


def matrix(observation):
    exact=observation.get('identity_verified') is True and observation.get('environment')=='PAPER_TRADING'
    rows=[]
    for symbol in UNIVERSE:
        item=observation.get('symbols',{}).get(symbol,{}) if exact else {}
        contract=item.get('contract',{});quote=item.get('quote',{});base=None;stress=None;maximum=0
        try:
            bid,ask=finite(quote['bid'],True),finite(quote['ask'],True)
            base=cash_geometry(bid,ask,1,'TIERED_BASE');stress=cash_geometry(bid,ask,1,'FIXED_FEE_STRESS')
            for q in range(1,min(int(100/ask),10000)+1):
                if cash_geometry(bid,ask,q,'TIERED_BASE')['fits_virtual_usd100']:maximum=q
        except (ValueError,ArithmeticError,KeyError,TypeError):pass
        rows.append(dict(symbol=symbol,observed_at=quote.get('received_at') or observation.get('completed_at'),
            price_observation=dict(status='VERIFIED' if base else 'UNKNOWN',bid=quote.get('bid') if base else None,
                ask=quote.get('ask') if base else None,source='IBKR_TWS',data_type=quote.get('data_type'),
                source_timestamp=quote.get('source_timestamp'),executable=False),
            minimum_declared=dict(status='VERIFIED' if contract.get('minimum_size') else 'UNKNOWN',
                value=contract.get('minimum_size'),increment=contract.get('size_increment'),
                source='IBKR_contractDetails',scope='DECLARED_METADATA_NOT_ACCOUNT_OR_API_ACCEPTANCE'),
            permission_status='UNKNOWN',fraction_status='UNKNOWN',effective_minimum_status='UNKNOWN',
            whole_share_study_minimum=1,theoretical_max_whole_quantity=maximum,
            tiered_one_share=base,fixed_one_share=stress,fee_plan_status='UNKNOWN',
            effective_fees_status='UNKNOWN',settled_funds_status=(
                'VERIFIED' if observed(observation,'SettledCash','USD') else 'UNKNOWN'),
            intraday_status='UNKNOWN',effective_margin_status='UNKNOWN',
            protection_declared=dict(status='VERIFIED' if contract else 'UNKNOWN',
                types=sorted(set(contract.get('order_types','').split(','))&{'LMT','STP','STPLMT','OCA'}),
                source='IBKR_contractDetails'),protection_effective_status='UNKNOWN',
            status='EXECUTION_CONSTRAINT_BLOCKED',affordability_only=(
                'THEORETICAL_WHOLE_SHARE_FITS' if base and base['fits_virtual_usd100'] else
                'WHOLE_SHARE_EXCEEDS_USD100; FRACTIONS_UNVERIFIED' if base else 'PRICE_UNKNOWN'),
            stock_executor_implemented=False,execution_authorized=False))
    return rows


def analyze(root):
    root=Path(root);folder=root/'artifacts/research/equity-operational'
    observation=verified_archive(folder/'capabilities-readonly.json')
    if observation.get('identity_verified') is not True or observation.get('environment')!='PAPER_TRADING':
        # Failed observation can be reported, but never used to prove account capabilities.
        observation={**observation,'identity_verified':False,'symbols':{},'queries':{}}
    integrity=integrity_report(root)
    report=dict(status='EXECUTION_CONSTRAINT_BLOCKED',observed_at=datetime.now(timezone.utc).isoformat(),
        facts=account_facts(observation),matrix=matrix(observation),integrity=integrity,
        account=observation.get('account'),source_capabilities_sha256=(folder/'capabilities-readonly.sha256').read_text().strip(),
        complete_queries={k:v['complete'] for k,v in observation['queries'].items()},
        portal_status=json.loads((folder/'portal-status.json').read_bytes()),sources=PRIMARY,
        current_allocation_usd=100,exposure_limit=1,strategies_recomputed=0,
        final_holdout_sealed=True,orders_sent=0,live_enabled=False,execution_authorized=False,
        known_public_tariff=dict(status='VERIFIED',observed_at=datetime.now(timezone.utc).isoformat(),
            source=PRIMARY['commissions'],tiered_minimum_usd='.35',fixed_minimum_usd='1.00',
            maximum_base_trade_value_percent='1',
            scope='PUBLIC_SCHEDULE_NOT_EFFECTIVE_ACCOUNT_FEE',additional_fees=True),
        estimated_envelope=dict(status='ESTIMATED',extra_per_order_usd='.02',extra_per_share_usd='.01',
            slippage_per_share_per_side='max(USD0.01, ask * 0.15%)',source='FROZEN_RESEARCH_COST_MODEL; NOT_BROKER_QUOTE'),
        reviewed_only_existing_candidates=True)
    save(folder/'report.json',report);render(root,report);return report


def render(root,r):
    lines=['# IBKR Paper: capacidades y datos bursátiles','',f"**{r['status']}**. Observación UTC: {r['observed_at']}. Cuenta Paper {r.get('account')}; cero órdenes.",'',
        'No hay aprobación operativa. SCHX/F caben nominalmente como acciones enteras bajo costos estimados; SPY entero excede US$100. Fracciones no verificadas y ningún tamaño recomendado. El executor productivo sigue siendo EUR/USD. Capital de dimensionamiento aislado US$100, exposición 1×; el millón Paper nunca determina cantidades.',
        '', '## Matriz final','',
        '| Instrumento | BID/ASK observado USD | Mínimo / incremento declarados | Permisos / fracciones | Fondos estimados para 1 entera | Comisión roundtrip estimada | Intradía / margen efectivo | Protección | Estado |',
        '|---|---|---|---|---:|---:|---|---|---|']
    for x in r['matrix']:
        p=x['price_observation'];c=x['minimum_declared'];g=x['tiered_one_share']
        lines.append(f"| {x['symbol']} | {p['bid']}/{p['ask']} ({p['data_type']}, no ejecutable) | {c['value']} / {c['increment']} (metadata) | UNKNOWN / UNKNOWN | {format(g['funds_with_exit_reserve_usd'],'.4f') if g else 'UNKNOWN'} | {format(g['roundtrip_fees_usd'],'.4f') if g else 'UNKNOWN'} | UNKNOWN / UNKNOWN | {','.join(x['protection_declared']['types'])} declaradas; aceptación UNKNOWN | {x['status']} |")
    lines+=['','Las fechas de recepción específicas, tamaño efectivo UNKNOWN, escenario Fixed, máximo entero teórico y costos de spread/slippage figuran en el JSON. Cantidad entera mínima 1 es una restricción del estudio, no una aceptación broker demostrada. Metadata mínima 0.0001 no acredita permisos de fracciones. No se calcula margen a partir de InitMarginReq=0 ni se confunde AvailableFunds con SettledCash.',
        '', '## Valores de cuenta','', '| Dato | Estado | Valor | Fuente | Fecha UTC |','|---|---|---|---|---|']
    for f in r['facts']:
        lines.append(f"| {f['name']} | {f['status']} | {f['value'] if f['value'] is not None else 'null'} | {f['source']} | {f['observed_at']} |")
    lines+=['','Consulta summary/ledger/updates/multi: '+json.dumps(r['complete_queries'])+'. El prefijo $LEDGER- se normaliza sin descartar moneda ni validar fondos desde metadata de contrato. AccountOrGroup exige identidad exacta y se elimina del archivo. Caché incompleta/conflictiva/BASE no se convierte a USD; ausencia conserva null.',
        'Tarifas: tabla pública Tiered/Fixed verificada; aplicación a esta cuenta UNKNOWN. El modelo mantiene el máximo de comisión base de 1% del valor negociado, más la reserva de cargos adicionales; por eso una orden pequeña puede resultar inferior al mínimo publicado. Los números de la matriz son ESTIMATED y reservan ambos lados y slippage de max(US$0.01, 0.15% del ASK) por acción/lado. Precio BID/ASK retrasado observado es VERIFIED como dato recibido, nunca cotización ejecutable actual. Todas las capacidades UNKNOWN conservan fuente y fecha de observación fallida/incompleta.',
        'Reg T es ESTIMATED desde STKNOPT. Las restricciones dependen de entidad/régimen y transición PDT/Intraday Margin; no se presume límite universal de US$25.000 ni margen del 50%. El mínimo público Reg T de US$2.000 afecta uso de margen/short, no demuestra rechazo de una compra totalmente financiada con US$100. Aplicación Paper concreta UNKNOWN. T+1 no habilita reutilizar automáticamente proceeds intradía.',
        '', '## Integridad de datos','',
        f"Revisadas {r['integrity']['reviewed_bar_count']} velas. Final sellado; estrategias recalculadas 0. Corpus y resultados 739 preservados con hashes. Sidecars de precios separados, sin modificar fuentes originales.",
        '| Instrumento | Dividendos verificados reportados | Cobertura corporativa | Velas inválidas | Flags 1h/diario |','|---|---:|---|---:|---|']
    for s in UNIVERSE:
        i=r['integrity']['instruments'][s];n=sum(e['symbol']==s for e in r['integrity']['events'])
        lines.append(f"| {s} | {n} | {r['integrity']['corporate_source_coverage'][s]['status']} | {i['60']['invalid_bars']+i['1440']['invalid_bars']} | {len(i['60']['flags'])}/{len(i['1440']['flags'])} |")
    lines+=['','SCHX: split 3:1 del 2024-10-11 y split 2:1 del 2022-03-11 documentados por el emisor. El archivo muestra un salto de ~−50% el 2022-02-11. Esa fecha no coincide con el anuncio: SCHX queda en cuarentena y la evidencia de entrenamiento previo no se considera fiable. No desplazar el split ni escalar velas para encubrir el salto. Las observaciones ajustadas y no ajustadas comparten la anomalía; ADJUSTED_LAST no puede reparar automáticamente TRADES.',
        'Precios derivados SCHX anteriores a 2024-10-11 ×3, volumen sin cambio y unidades de volumen UNKNOWN; el sidecar no es una serie limpia aprobada. Sin estrategias que atraviesen un split hasta contar con inventario/features causales consistentes. Flags incluyen el gap F 2024-07-25; no se elimina una pérdida auténtica por parecer anómala. Los detalles de calidad final se almacenan aparte de resultados de estrategias; no se abren señales ni P&L finales.',
        'Dividendos: SCHX 22 eventos del emisor (extracción de tabla vía web; descarga directa HTTP403), SPY 21 del XLSX oficial, F solamente el suplementario US$0.18 documentado por OCC/MIAX. Feed Ford vacío y lookup HTTP403 no significan cero dividendos: ordinarios/calendario completo UNKNOWN. El navegador público no pudo inicializar su runtime; no se automatizó TWS/Portal.',
        'Registro de receivables bruto para ocho resultados de selección ya examinados, sin modificar P&L, gates diarios, equity ni presupuestos. Ser LONG antes de apertura ex-date exige posesión previa; compra en ex-date no adquiere derecho. Pago publicado no prueba abono broker/retención ni fondos liquidados. Neto y retenciones UNKNOWN. ADJUSTED_LAST/total-return rechazan créditos de dividendos para impedir doble conteo. Componentes de capital gains ausentes no se imputan como cero.',
        'Reconsulta acotada SCHX: '+json.dumps(r['integrity']['split_followup'])+'. Independiente completitud de todos los eventos, ajuste de volumen, sesgo de supervivencia y conciliación fiscal siguen pendientes. No se promueve ningún candidato.',
        '', '## Intervención humana exacta — solo Paper','',
        '1. TWS: confirmar banner Paper Trading y la identidad completa local de la cuenta vinculada terminada en 3784. Account → Account Window; expandir Balances con +, personalizar filas para Settled Cash. Registrar columna USD/moneda y fecha; expandir Available for Trading y Margin Requirements. Mostrar Day Trades Left/restricciones si existen. Campo ausente sigue UNKNOWN; no convertir Cash/AvailableFunds a Settled Cash.',
        '2. Client Portal: iniciar sesión con el usuario Paper; comprobar que la cuenta seleccionada es exactamente la Paper vinculada antes de consultar ajustes. User menu → Settings → Trading → Trading Permissions → Stocks: leer permisos US y Global (Trade in Fractions), sin marcar casillas ni guardar cambios. Si Paper no expone ese panel, no entrar a Live como sustituto: solicitar confirmación escrita a soporte IBKR para ese usuario/cuenta Paper y canal TWS API.',
        '3. En la misma sesión Paper: User menu → Settings → Account Configuration → IBKR Pricing Plan; registrar plan Pro y estructura Fixed/Tiered si están visibles, entidad y tipo Cash/Reg T/PM. No cambiar el plan. Si el panel exige cuenta Live, mantener UNKNOWN y pedir a soporte confirmación del plan efectivo Paper, cargos por ruta/odd lot/fracción y restricciones intradía/PDT/IMD aplicables. Una tabla pública no reemplaza esa respuesta.',
        '4. TWS Paper durante RTH: observar cotización SCHX/SPY/F y su indicación de retraso/entitlement. Financial Instrument Info → Description para contrato; los controles Attach/Bracket/OCA solamente prueban disponibilidad UI. No pulsar Transmit ni Preview/what-if para demostrar margen/comisión/aceptación: what-if también usa placeOrder y está fuera de esta fase. Aceptación efectiva necesita prueba posterior expresamente autorizada o evidencia histórica Paper existente, no un ciclo nuevo.',
        '5. Datos: exportar Dividend History de Ford por 2021–2026 desde su página oficial, con ex-date, payment date, monto y suplemento separado; conservar el archivo original. Para SCHX, pedir a IBKR revisión del salto 2022-02-11 versus split oficial 2022-03-11, adjuntando las fechas/consultas/hashes del artefacto split-verification. Contrastar exportación de gráfico TWS Paper y fuente oficial; no editar el corpus hasta tener evidencia de corrección. Completar dividendos, retenciones y unidades de volumen antes de nueva validación.',
        '', '## Archivos y reproducción offline','',
        '`python/trading_agent/paper_account_capabilities.py`: lector aislado. `equity_data_integrity.py`: integridad/receivables. `equity_operational_review.py`: matriz e informe. Tres archivos de pruebas correspondientes. Artefactos en `artifacts/research/equity-operational/`; no cambios en RiskEngine, estrategias, AccountBinding ni límites.',
        'Recrear el informe sin red ni órdenes: `.venv/Scripts/python.exe -m trading_agent.equity_operational_review --root .` con `PYTHONPATH=python`. `--collect` hace exclusivamente una nueva observación Paper de lectura. No es Run ni concede autorización.',
        '', '## Fuentes primarias','']
    lines.extend(f'- [{name}]({url}).' for name,url in r['sources'].items())
    verification=Path(root)/'artifacts/test-results/equity-operational/verification.json'
    if verification.exists():
        v=json.loads(verification.read_bytes());lines+=['','## Verificación','',
            f"{v['python_passed']} Python + {v['csharp_passed']} C# = {v['total_passed']} aprobadas; fallos/omitidas {v['failed']}/{v['skipped']}. Build: {v['build_errors']} errores, {v['build_warnings']} advertencias.",
            f"{v['protected_files_unchanged']} archivos/estados protegidos idénticos por SHA256. Emergencia activa, PaperAuto ausente, Live bloqueado; cero órdenes. PostgreSQL desechable detenido."]
    (Path(root)/'docs/architecture/equity-account-data-integrity.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',default='.');p.add_argument('--collect',action='store_true')
    args=p.parse_args()
    if args.collect:
        r=collect_capabilities(args.root);print(json.dumps(dict(identity_verified=r['identity_verified'],orders_sent=0)))
    else:
        r=analyze(args.root);print(json.dumps(dict(status=r['status'],bars=r['integrity']['reviewed_bar_count'],orders_sent=0)))
