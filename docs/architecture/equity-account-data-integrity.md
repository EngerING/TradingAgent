# IBKR Paper: capacidades y datos bursátiles

**EXECUTION_CONSTRAINT_BLOCKED**. Observación UTC: 2026-10-06T09:43:32.996873+00:00. Cuenta Paper ***3784; cero órdenes.

No hay aprobación operativa. SCHX/F caben nominalmente como acciones enteras bajo costos estimados; SPY entero excede US$100. Fracciones no verificadas y ningún tamaño recomendado. El executor productivo sigue siendo EUR/USD. Capital de dimensionamiento aislado US$100, exposición 1×; el millón Paper nunca determina cantidades.

## Matriz final

| Instrumento | BID/ASK observado USD | Mínimo / incremento declarados | Permisos / fracciones | Fondos estimados para 1 entera | Comisión roundtrip estimada | Intradía / margen efectivo | Protección | Estado |
|---|---|---|---|---:|---:|---|---|---|
| SCHX | 30.5/30.65 (DELAYED, no ejecutable) | 0.0001 / 0.0001 (metadata) | UNKNOWN / UNKNOWN | 31.4135 | 0.6715 | UNKNOWN / UNKNOWN | LMT,OCA,STP,STPLMT declaradas; aceptación UNKNOWN | EXECUTION_CONSTRAINT_BLOCKED |
| SPY | 776.39/776.44 (DELAYED, no ejecutable) | 0.0001 / 0.0001 (metadata) | UNKNOWN / UNKNOWN | 779.5293 | 0.7600 | UNKNOWN / UNKNOWN | LMT,OCA,STP,STPLMT declaradas; aceptación UNKNOWN | EXECUTION_CONSTRAINT_BLOCKED |
| F | 12.18/12.19 (DELAYED, no ejecutable) | 0.0001 / 0.0001 (metadata) | UNKNOWN / UNKNOWN | 12.5303 | 0.3037 | UNKNOWN / UNKNOWN | LMT,OCA,STP,STPLMT declaradas; aceptación UNKNOWN | EXECUTION_CONSTRAINT_BLOCKED |

Las fechas de recepción específicas, tamaño efectivo UNKNOWN, escenario Fixed, máximo entero teórico y costos de spread/slippage figuran en el JSON. Cantidad entera mínima 1 es una restricción del estudio, no una aceptación broker demostrada. Metadata mínima 0.0001 no acredita permisos de fracciones. No se calcula margen a partir de InitMarginReq=0 ni se confunde AvailableFunds con SettledCash.

## Valores de cuenta

| Dato | Estado | Valor | Fuente | Fecha UTC |
|---|---|---|---|---|
| AccountType | VERIFIED | INDIVIDUAL | IBKR_TWS | 2026-10-06T09:20:45.886662+00:00 |
| SettledCash_USD | UNKNOWN | null | IBKR_TWS | 2026-10-06T09:20:50.460875+00:00 |
| AvailableFunds_USD | VERIFIED | 1000089.01 | IBKR_TWS | 2026-10-06T09:20:45.887728+00:00 |
| BuyingPower_USD | VERIFIED | 4000356.03 | IBKR_TWS | 2026-10-06T09:20:45.890881+00:00 |
| DayTradesRemaining | UNKNOWN | null | IBKR_TWS | 2026-10-06T09:20:50.460875+00:00 |
| DayTradesRemainingT+1 | UNKNOWN | null | IBKR_TWS | 2026-10-06T09:20:50.460875+00:00 |
| DayTradesRemainingT+2 | UNKNOWN | null | IBKR_TWS | 2026-10-06T09:20:50.460875+00:00 |
| DayTradesRemainingT+3 | UNKNOWN | null | IBKR_TWS | 2026-10-06T09:20:50.460875+00:00 |
| DayTradesRemainingT+4 | UNKNOWN | null | IBKR_TWS | 2026-10-06T09:20:50.460875+00:00 |
| InitMarginReq_USD | VERIFIED | 0.00 | IBKR_TWS | 2026-10-06T09:20:45.939793+00:00 |
| MaintMarginReq_USD | VERIFIED | 0.00 | IBKR_TWS | 2026-10-06T09:20:45.943617+00:00 |
| RegTEquity_USD | VERIFIED | 1000460.81 | IBKR_TWS | 2026-10-06T09:20:45.952416+00:00 |
| RegTMargin_USD | VERIFIED | 0.00 | IBKR_TWS | 2026-10-06T09:20:45.952438+00:00 |
| SMA_USD | VERIFIED | 1000460.81 | IBKR_TWS | 2026-10-06T09:20:45.952451+00:00 |
| ExcessLiquidity_USD | VERIFIED | 1000089.01 | IBKR_TWS | 2026-10-06T09:20:45.893796+00:00 |
| LookAheadAvailableFunds_USD | VERIFIED | 1000089.01 | IBKR_TWS | 2026-10-06T09:20:45.940389+00:00 |
| LookAheadInitMarginReq_USD | VERIFIED | 0.00 | IBKR_TWS | 2026-10-06T09:20:45.943562+00:00 |
| LookAheadMaintMarginReq_USD | VERIFIED | 0.00 | IBKR_TWS | 2026-10-06T09:20:45.943588+00:00 |
| Cushion | VERIFIED | 1 | IBKR_TWS | 2026-10-06T09:20:45.892576+00:00 |
| TotalCashValue_USD | VERIFIED | 1000089.01 | IBKR_TWS | 2026-10-06T09:20:45.956311+00:00 |
| CashBalance_USD | VERIFIED | 1000089.007 | IBKR_TWS | 2026-10-06T09:20:45.976608+00:00 |
| TotalCashBalance_USD | VERIFIED | 1000089.007 | IBKR_TWS | 2026-10-06T09:20:45.976618+00:00 |
| NetLiquidation_USD | VERIFIED | 1000460.81 | IBKR_TWS | 2026-10-06T09:20:45.943655+00:00 |
| TradingType-S | VERIFIED | STKNOPT | IBKR_TWS | 2026-10-06T09:20:45.975471+00:00 |
| AccountReady | VERIFIED | true | IBKR_TWS | 2026-10-06T09:20:45.886291+00:00 |
| Leverage-S | VERIFIED | 0.00 | IBKR_TWS | 2026-10-06T09:20:45.940339+00:00 |
| stock_etf_permissions | UNKNOWN | null | IBKR_TWS_READ_ONLY | 2026-10-06T09:20:50.460875+00:00 |
| fractional_permissions | UNKNOWN | null | IBKR_TWS_READ_ONLY | 2026-10-06T09:20:50.460875+00:00 |
| effective_fee_plan | UNKNOWN | null | IBKR_TWS_READ_ONLY | 2026-10-06T09:20:50.460875+00:00 |
| effective_per_order_fees | UNKNOWN | null | IBKR_TWS_READ_ONLY | 2026-10-06T09:20:50.460875+00:00 |
| account_entity | UNKNOWN | null | IBKR_TWS_READ_ONLY | 2026-10-06T09:20:50.460875+00:00 |
| effective_intraday_restrictions | UNKNOWN | null | IBKR_TWS_READ_ONLY | 2026-10-06T09:20:50.460875+00:00 |
| contract_specific_margin | UNKNOWN | null | IBKR_TWS_READ_ONLY | 2026-10-06T09:20:50.460875+00:00 |
| effective_bracket_acceptance | UNKNOWN | null | IBKR_TWS_READ_ONLY | 2026-10-06T09:20:50.460875+00:00 |

Consulta summary/ledger/updates/multi: {"summary": true, "ledger": true, "updates": true, "multi": true}. El prefijo $LEDGER- se normaliza sin descartar moneda ni validar fondos desde metadata de contrato. AccountOrGroup exige identidad exacta y se elimina del archivo. Caché incompleta/conflictiva/BASE no se convierte a USD; ausencia conserva null.
Tarifas: tabla pública Tiered/Fixed verificada; aplicación a esta cuenta UNKNOWN. El modelo mantiene el máximo de comisión base de 1% del valor negociado, más la reserva de cargos adicionales; por eso una orden pequeña puede resultar inferior al mínimo publicado. Los números de la matriz son ESTIMATED y reservan ambos lados y slippage de max(US$0.01, 0.15% del ASK) por acción/lado. Precio BID/ASK retrasado observado es VERIFIED como dato recibido, nunca cotización ejecutable actual. Todas las capacidades UNKNOWN conservan fuente y fecha de observación fallida/incompleta.
Reg T es ESTIMATED desde STKNOPT. Las restricciones dependen de entidad/régimen y transición PDT/Intraday Margin; no se presume límite universal de US$25.000 ni margen del 50%. El mínimo público Reg T de US$2.000 afecta uso de margen/short, no demuestra rechazo de una compra totalmente financiada con US$100. Aplicación Paper concreta UNKNOWN. T+1 no habilita reutilizar automáticamente proceeds intradía.

## Integridad de datos

Revisadas 31542 velas. Final sellado; estrategias recalculadas 0. Corpus y resultados 739 preservados con hashes. Sidecars de precios separados, sin modificar fuentes originales.
| Instrumento | Dividendos verificados reportados | Cobertura corporativa | Velas inválidas | Flags 1h/diario |
|---|---:|---|---:|---|
| SCHX | 22 | VERIFIED_REPORTED_EVENTS | 0 | 3/3 |
| SPY | 21 | VERIFIED_REPORTED_EVENTS | 0 | 0/0 |
| F | 1 | PARTIAL | 0 | 1/1 |

SCHX: split 3:1 del 2024-10-11 y split 2:1 del 2022-03-11 documentados por el emisor. El archivo muestra un salto de ~−50% el 2022-02-11. Esa fecha no coincide con el anuncio: SCHX queda en cuarentena y la evidencia de entrenamiento previo no se considera fiable. No desplazar el split ni escalar velas para encubrir el salto. Las observaciones ajustadas y no ajustadas comparten la anomalía; ADJUSTED_LAST no puede reparar automáticamente TRADES.
Precios derivados SCHX anteriores a 2024-10-11 ×3, volumen sin cambio y unidades de volumen UNKNOWN; el sidecar no es una serie limpia aprobada. Sin estrategias que atraviesen un split hasta contar con inventario/features causales consistentes. Flags incluyen el gap F 2024-07-25; no se elimina una pérdida auténtica por parecer anómala. Los detalles de calidad final se almacenan aparte de resultados de estrategias; no se abren señales ni P&L finales.
Dividendos: SCHX 22 eventos del emisor (extracción de tabla vía web; descarga directa HTTP403), SPY 21 del XLSX oficial, F solamente el suplementario US$0.18 documentado por OCC/MIAX. Feed Ford vacío y lookup HTTP403 no significan cero dividendos: ordinarios/calendario completo UNKNOWN. El navegador público no pudo inicializar su runtime; no se automatizó TWS/Portal.
Registro de receivables bruto para ocho resultados de selección ya examinados, sin modificar P&L, gates diarios, equity ni presupuestos. Ser LONG antes de apertura ex-date exige posesión previa; compra en ex-date no adquiere derecho. Pago publicado no prueba abono broker/retención ni fondos liquidados. Neto y retenciones UNKNOWN. ADJUSTED_LAST/total-return rechazan créditos de dividendos para impedir doble conteo. Componentes de capital gains ausentes no se imputan como cero.
Reconsulta acotada SCHX: {"source_sha256": "8d09879b29c56f21fd1a1aa7bea0175aef462b45955c71cf9c1dab500a61d031", "comparisons": [{"minutes": 60, "paired_bars": 434, "changed_ohlc": 0, "callback": "historicalDataEnd"}, {"minutes": 1440, "paired_bars": 62, "changed_ohlc": 0, "callback": "historicalDataEnd"}], "errors": []}. Independiente completitud de todos los eventos, ajuste de volumen, sesgo de supervivencia y conciliación fiscal siguen pendientes. No se promueve ningún candidato.

## Intervención humana exacta — solo Paper

1. TWS: confirmar banner Paper Trading y la identidad completa local de la cuenta vinculada terminada en 3784. Account → Account Window; expandir Balances con +, personalizar filas para Settled Cash. Registrar columna USD/moneda y fecha; expandir Available for Trading y Margin Requirements. Mostrar Day Trades Left/restricciones si existen. Campo ausente sigue UNKNOWN; no convertir Cash/AvailableFunds a Settled Cash.
2. Client Portal: iniciar sesión con el usuario Paper; comprobar que la cuenta seleccionada es exactamente la Paper vinculada antes de consultar ajustes. User menu → Settings → Trading → Trading Permissions → Stocks: leer permisos US y Global (Trade in Fractions), sin marcar casillas ni guardar cambios. Si Paper no expone ese panel, no entrar a Live como sustituto: solicitar confirmación escrita a soporte IBKR para ese usuario/cuenta Paper y canal TWS API.
3. En la misma sesión Paper: User menu → Settings → Account Configuration → IBKR Pricing Plan; registrar plan Pro y estructura Fixed/Tiered si están visibles, entidad y tipo Cash/Reg T/PM. No cambiar el plan. Si el panel exige cuenta Live, mantener UNKNOWN y pedir a soporte confirmación del plan efectivo Paper, cargos por ruta/odd lot/fracción y restricciones intradía/PDT/IMD aplicables. Una tabla pública no reemplaza esa respuesta.
4. TWS Paper durante RTH: observar cotización SCHX/SPY/F y su indicación de retraso/entitlement. Financial Instrument Info → Description para contrato; los controles Attach/Bracket/OCA solamente prueban disponibilidad UI. No pulsar Transmit ni Preview/what-if para demostrar margen/comisión/aceptación: what-if también usa placeOrder y está fuera de esta fase. Aceptación efectiva necesita prueba posterior expresamente autorizada o evidencia histórica Paper existente, no un ciclo nuevo.
5. Datos: exportar Dividend History de Ford por 2021–2026 desde su página oficial, con ex-date, payment date, monto y suplemento separado; conservar el archivo original. Para SCHX, pedir a IBKR revisión del salto 2022-02-11 versus split oficial 2022-03-11, adjuntando las fechas/consultas/hashes del artefacto split-verification. Contrastar exportación de gráfico TWS Paper y fuente oficial; no editar el corpus hasta tener evidencia de corrección. Completar dividendos, retenciones y unidades de volumen antes de nueva validación.

## Archivos y reproducción offline

`python/trading_agent/paper_account_capabilities.py`: lector aislado. `equity_data_integrity.py`: integridad/receivables. `equity_operational_review.py`: matriz e informe. Tres archivos de pruebas correspondientes. Artefactos en `artifacts/research/equity-operational/`; no cambios en RiskEngine, estrategias, AccountBinding ni límites.
Recrear el informe sin red ni órdenes: `.venv/Scripts/python.exe -m trading_agent.equity_operational_review --root .` con `PYTHONPATH=python`. `--collect` hace exclusivamente una nueva observación Paper de lectura. No es Run ni concede autorización.

## Fuentes primarias

- [ibkr_bars](https://interactivebrokers.github.io/tws-api/historical_bars.html).
- [schx_split](https://pressroom.aboutschwab.com/press-releases/press-release/2024/Schwab-Asset-Management-Announces-ETF-Share-Splits/default.aspx).
- [commissions](https://www.interactivebrokers.com/en/pricing/commissions-stocks.php).
- [margin_code](https://www.interactivebrokers.com/campus/trading-lessons/risk-navigator-alternative-margin-calculator/).
- [intraday](https://www.ibkrguides.com/ibkrdesktop/available-for-trading.htm).
- [settlement](https://www.interactivebrokers.com/campus/traders-insight/t1-settlement-what-it-means-for-traders-and-investors/).
- [paper](https://www.ibkrguides.com/advisorportal/aboutpapertradingaccount.htm).
- [adjusted_end_date](https://www.interactivebrokers.com/docs/tws-api/sync-doc/historical-market-data).
- [fractional_check](https://www.ibkrguides.com/clientportal/trade-in-fractions.htm).
- [fee_plan_check](https://www.ibkrguides.com/clientportal/pricingstructure.htm).
- [cash_check](https://ibkrguides.com/tws/usersguidebook/realtimeactivitymonitoring/balances.htm).
- [portfolio_summary](https://www.interactivebrokers.com/docs/web-api/api-reference/trading/trading-accounts/get-account-summary).
- [margin_scope](https://www.interactivebrokers.com/en/trading/margin-requirements.php).
- [schx_split_2022](https://pressroom.aboutschwab.com/press-releases/press-release/2022/Schwab-Asset-Management-Announces-ETF-Share-Splits/default.aspx).
- [spy_distributions](https://www.ssga.com/us/en/individual/resources/documents/etf-dividend-distributions).
- [ford_dividends](https://www.shareholder.ford.com/Information/stock/default.aspx).
- [ford_supplemental](https://www.miaxglobal.com/sites/default/files/alert-files/F_Dividend__54075.pdf).

## Verificación

533 Python + 240 C# = 773 aprobadas; fallos/omitidas 0/0. Build: 0 errores, 0 advertencias.
34 archivos/estados protegidos idénticos por SHA256. Emergencia activa, PaperAuto ausente, Live bloqueado; cero órdenes. PostgreSQL desechable detenido.
