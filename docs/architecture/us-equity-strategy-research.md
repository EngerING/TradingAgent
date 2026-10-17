# Investigación LONG de acciones y ETF — capital virtual US$100

**NO_VIABLE_STRATEGY_FOUND.** Ningún candidato aprobado; emergencia y límites productivos intactos. Órdenes enviadas: 0.

Configuraciones: 192; resultados por partición: 1152; familia estadística: 192.
Riesgos: 1%, 2%, 3%, 5%, 7.5%, 10%, 12.5%, 15%. Exposición 1×; presupuesto acumulado de pérdidas US$20, sin reposición por ganancias.

## Verificación de IBKR (solo lectura)

Identidad Paper coincidente: True. API: 226. Cuenta: ***3784. Consultas de cuenta completas: True.
AccountType de AccountSummary no acredita por sí mismo Cash/Margin, entidad ni régimen intradía. El saldo Paper no alimenta el dimensionamiento.

| Símbolo | conId | Mínimo / incremento publicados por contrato | Órdenes declaradas | Datos | Barras 1h / diario |
|---|---:|---|---|---|---|
| SCHX | 70083655 | 0.0001 / 0.0001 | LMT,STP,STPLMT,OCA | UNAVAILABLE | 882 / 126 |
| SPY | 756733 | 0.0001 / 0.0001 | LMT,STP,STPLMT,OCA | UNAVAILABLE | 882 / 126 |
| F | 9599491 | 0.0001 / 0.0001 | LMT,STP,STPLMT,OCA | DELAYED | 882 / 126 |

Cobertura de sesiones completa: True; 3024 velas originales. Detalle por instrumento y temporalidad en session_coverage del JSON. Precios OHLC y volumen preservados, duración de vela ajustada únicamente a las fronteras auténticas de sesión/siguiente vela.
Cotizaciones: SCHX/SPY sin BID/ASK (IBKR_READ_TIMEOUT); F DELAYED. Ninguna cotización ejecutable. Spread de F observado usado conservadoramente; para SCHX/SPY, estimación de 5 bps y stress, sin atribuirla a una observación histórica.
Avisos 2188 conservados: solo se aceptaron datos históricos archivados con historicalDataEnd. Códigos 162/366 también observados; se conservaron códigos/timestamps, sin texto bruto de broker. No se atribuye una causa definitiva al 162 sin su texto. 366 indica ausencia de consulta histórica al cancelar; 24 consultas de velas terminaron con callback y 3 SCHEDULE devolvieron sesiones.
Mínimo/incremento 0.0001 es metadato del contrato, no autorización de fracciones. La simulación admite únicamente cantidades enteras. SPY cuesta más de US$100 por acción en este histórico y queda fuera de acceso entero.

AccountSummary observado (no capital de estrategia):

| Campo | Valor | Moneda |
|---|---|---|
| AccountType | INDIVIDUAL |  |
| AccountType | INDIVIDUAL |  |
| AvailableFunds | 1000089.01 | USD |
| BuyingPower | 4000356.03 | USD |
| InitMarginReq | 0.00 | USD |
| MaintMarginReq | 0.00 | USD |
| AvailableFunds | 1000089.01 | USD |
| BuyingPower | 4000356.03 | USD |
| InitMarginReq | 0.00 | USD |
| MaintMarginReq | 0.00 | USD |

AccountDownloadEnd adicional completado; campos seleccionados:

| Campo | Valor | Moneda |
|---|---|---|
| AccountType | INDIVIDUAL |  |
| AvailableFunds | 1000089.01 | USD |
| AvailableFunds-S | 1000089.01 | USD |
| EquityWithLoanValue-S | 1000089.01 | USD |
| TradingType-S | STKNOPT |  |
Portfolio recibido: []. TradingType-S se conserva literalmente. STKNOPT es consistente con Reg T Margin según la nomenclatura publicada de IBKR (inferencia documentada); no acredita permisos geográficos ni restricciones intradía aplicables.
SettledCash / DayTradesRemaining ausentes permanecen UNKNOWN; AvailableFunds/BuyingPower no los sustituyen.

Permisos de acciones/ETF, plan Tiered aplicable, residencia/entidad, capacidad intradía, fracciones/API y restricciones efectivas de cuenta: **UNKNOWN**. Resolver contrato o recibir datos no confirma permiso de negociación. El modelo usa efectivo liquidado conservadoramente; no presupone préstamo o reutilización inmediata aun si STKNOPT corresponde a margen.
No se usó what-if: requiere placeOrder. Las capacidades stop/limit declaradas no prueban un bracket, OCA o protección efectiva en esta cuenta.

## Protocolo congelado y candidatos

Universo de conveniencia congelado: SCHX (ETF amplio), SPY (ETF de control de accesibilidad) y F (acción). Liquidez histórica completa y universo sin supervivencia no demostrados.
LONG exclusivamente. Señal con vela completa; entrada siguiente apertura. EMA 10/20, SMA 50 de contexto, ATR 14. Stop antes de target si ambos se alcanzan; gap adverso al precio de apertura, sin limitar artificialmente pérdidas. Salida por EMA/contexto contrario en apertura siguiente (excepto reversión a la media) o máximo 20 velas. Tick de investigación US$0.01: BUY redondeado arriba, SELL/stop/target abajo; reserva adicional de dos ticks en riesgo y filtro de target.
| Candidato | Señal | Stop / target | Versión experimental |
|---|---|---|---|
| EQ_TREND_R0 | Cruce EMA10 sobre EMA20 y cierre sobre SMA50 | 1.5 ATR / 3 ATR | `10bc177864e8351001824ad7753d3954b9721dedce607762db140c8f39f4767e` |
| EQ_PULLBACK_R0 | Contexto alcista; retroceso EMA20 y recuperación confirmada | 1 ATR / 2 ATR | `e0399f5f3276f3a671385dfb225b5762e5cdcf7bc16a93892fa61496b1ff8b46` |
| EQ_BREAKOUT_R0 | Cierre sobre máximo previo de 20 velas; volumen ≥1.5× media previa | 1.5 ATR / 3 ATR | `292117eccb46c1658b62fb1107a300e5bcd5a5fdcab2c42c12cf7c06ce857202` |
| EQ_MEAN_REVERSION_R0 | Rebote desde banda −2σ previa; SMA50 relativamente plana | 1 ATR / media20 congelada | `82810f1859139e4d0fe46ef790935d3f22e485726d75d41015e51b1819f5391b` |

Se conserva 1 posición entre símbolos. T+1 según siguiente sesión IBKR auténtica: una ganancia habilita buscar señal, pero no vuelve líquidos sus ingresos inmediatamente. Una pérdida o break-even detiene entradas en America/Santo_Domingo. Datos/saldo ausentes no se convierten en cero.
Costo Tiered simulado: min(max(0.0035×acciones, 0.35), 1% notional) por lado, más envolvente conservadora de terceros US$0.02 + US$0.01/acción por lado. No representa la tarifa verificada de esta cuenta.
Spread: máximo de 5 bps y una observación IBKR; slippage 5 bps por lado; gap presupuestado 50 bps. Stress: doble spread, slippage 15 bps por lado, gap 100 bps. Fixed: mínimo público US$1 sujeto al techo 1%, mismos costos adicionales conservadores.

## Comparación fuera de muestra — Tiered base

| Estrategia | TF | Riesgo % | Admitidas / rechazadas | Win % / Wilson95 | P&L neto | EV | PF | DD % | Comisiones | Días primer loss |
|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|
| EQ_TREND_R0 | 60m | 1 | 1 / 14 | 0.0000 / [0.0, 79.3] | -0.7034 | -0.7034 | 0.0000 | 0.7434 | 0.3434 | 1 |
| EQ_TREND_R0 | 60m | 2 | 2 / 13 | 50.0000 / [9.5, 90.5] | -1.0568 | -0.5284 | 0.2268 | 2.3468 | 1.4468 | 1 |
| EQ_TREND_R0 | 60m | 3 | 5 / 10 | 20.0000 / [3.6, 62.4] | -7.4800 | -1.4960 | 0.1190 | 9.6300 | 4.2600 | 4 |
| EQ_TREND_R0 | 60m | 5 | 5 / 10 | 20.0000 / [3.6, 62.4] | -7.8900 | -1.5780 | 0.1470 | 10.4700 | 4.3200 | 4 |
| EQ_TREND_R0 | 60m | 7.5 | 5 / 10 | 20.0000 / [3.6, 62.4] | -7.8900 | -1.5780 | 0.1470 | 10.4700 | 4.3200 | 4 |
| EQ_TREND_R0 | 60m | 10 | 5 / 10 | 20.0000 / [3.6, 62.4] | -7.8900 | -1.5780 | 0.1470 | 10.4700 | 4.3200 | 4 |
| EQ_TREND_R0 | 60m | 12.5 | 5 / 10 | 20.0000 / [3.6, 62.4] | -7.8900 | -1.5780 | 0.1470 | 10.4700 | 4.3200 | 4 |
| EQ_TREND_R0 | 60m | 15 | 5 / 10 | 20.0000 / [3.6, 62.4] | -7.8900 | -1.5780 | 0.1470 | 10.4700 | 4.3200 | 4 |
| EQ_PULLBACK_R0 | 60m | 1 | 0 / 7 | N/D / N/D | 0.0000 | N/D | N/D | 0.0000 | 0.0000 | 0 |
| EQ_PULLBACK_R0 | 60m | 2 | 1 / 6 | 0.0000 / [0.0, 79.3] | -1.5500 | -1.5500 | 0.0000 | 2.0000 | 0.8000 | 1 |
| EQ_PULLBACK_R0 | 60m | 3 | 1 / 6 | 0.0000 / [0.0, 79.3] | -2.3600 | -2.3600 | 0.0000 | 3.2600 | 0.8600 | 1 |
| EQ_PULLBACK_R0 | 60m | 5 | 1 / 6 | 0.0000 / [0.0, 79.3] | -2.3600 | -2.3600 | 0.0000 | 3.2600 | 0.8600 | 1 |
| EQ_PULLBACK_R0 | 60m | 7.5 | 1 / 6 | 0.0000 / [0.0, 79.3] | -2.3600 | -2.3600 | 0.0000 | 3.2600 | 0.8600 | 1 |
| EQ_PULLBACK_R0 | 60m | 10 | 1 / 6 | 0.0000 / [0.0, 79.3] | -2.3600 | -2.3600 | 0.0000 | 3.2600 | 0.8600 | 1 |
| EQ_PULLBACK_R0 | 60m | 12.5 | 1 / 6 | 0.0000 / [0.0, 79.3] | -2.3600 | -2.3600 | 0.0000 | 3.2600 | 0.8600 | 1 |
| EQ_PULLBACK_R0 | 60m | 15 | 1 / 6 | 0.0000 / [0.0, 79.3] | -2.3600 | -2.3600 | 0.0000 | 3.2600 | 0.8600 | 1 |
| EQ_BREAKOUT_R0 | 60m | 1 | 1 / 5 | 0.0000 / [0.0, 79.3] | -0.7514 | -0.7514 | 0.0000 | 1.3514 | 0.6514 | 1 |
| EQ_BREAKOUT_R0 | 60m | 2 | 1 / 5 | 0.0000 / [0.0, 79.3] | -1.1600 | -1.1600 | 0.0000 | 2.9600 | 0.8600 | 1 |
| EQ_BREAKOUT_R0 | 60m | 3 | 2 / 4 | 0.0000 / [0.0, 65.8] | -3.4600 | -1.7300 | 0.0000 | 5.2600 | 1.7200 | 2 |
| EQ_BREAKOUT_R0 | 60m | 5 | 2 / 4 | 0.0000 / [0.0, 65.8] | -3.4600 | -1.7300 | 0.0000 | 5.2600 | 1.7200 | 2 |
| EQ_BREAKOUT_R0 | 60m | 7.5 | 2 / 4 | 0.0000 / [0.0, 65.8] | -3.4600 | -1.7300 | 0.0000 | 5.2600 | 1.7200 | 2 |
| EQ_BREAKOUT_R0 | 60m | 10 | 2 / 4 | 0.0000 / [0.0, 65.8] | -3.4600 | -1.7300 | 0.0000 | 5.2600 | 1.7200 | 2 |
| EQ_BREAKOUT_R0 | 60m | 12.5 | 2 / 4 | 0.0000 / [0.0, 65.8] | -3.4600 | -1.7300 | 0.0000 | 5.2600 | 1.7200 | 2 |
| EQ_BREAKOUT_R0 | 60m | 15 | 2 / 4 | 0.0000 / [0.0, 65.8] | -3.4600 | -1.7300 | 0.0000 | 5.2600 | 1.7200 | 2 |
| EQ_MEAN_REVERSION_R0 | 60m | 1 | 0 / 24 | N/D / N/D | 0.0000 | N/D | N/D | 0.0000 | 0.0000 | 0 |
| EQ_MEAN_REVERSION_R0 | 60m | 2 | 2 / 22 | 50.0000 / [9.5, 90.5] | -1.0300 | -0.5150 | 0.2945 | 2.4400 | 1.6000 | 1 |
| EQ_MEAN_REVERSION_R0 | 60m | 3 | 4 / 20 | 25.0000 / [4.6, 69.9] | -4.6900 | -1.1725 | 0.2544 | 5.5800 | 3.4800 | 3 |
| EQ_MEAN_REVERSION_R0 | 60m | 5 | 4 / 20 | 25.0000 / [4.6, 69.9] | -4.6900 | -1.1725 | 0.2544 | 5.5800 | 3.4800 | 3 |
| EQ_MEAN_REVERSION_R0 | 60m | 7.5 | 4 / 20 | 25.0000 / [4.6, 69.9] | -4.6900 | -1.1725 | 0.2544 | 5.5800 | 3.4800 | 3 |
| EQ_MEAN_REVERSION_R0 | 60m | 10 | 4 / 20 | 25.0000 / [4.6, 69.9] | -4.6900 | -1.1725 | 0.2544 | 5.5800 | 3.4800 | 3 |
| EQ_MEAN_REVERSION_R0 | 60m | 12.5 | 4 / 20 | 25.0000 / [4.6, 69.9] | -4.6900 | -1.1725 | 0.2544 | 5.5800 | 3.4800 | 3 |
| EQ_MEAN_REVERSION_R0 | 60m | 15 | 4 / 20 | 25.0000 / [4.6, 69.9] | -4.6900 | -1.1725 | 0.2544 | 5.5800 | 3.4800 | 3 |
| EQ_TREND_R0 | 1440m | 1 | 0 / 5 | N/D / N/D | 0.0000 | N/D | N/D | 0.0000 | 0.0000 | 0 |
| EQ_TREND_R0 | 1440m | 2 | 2 / 3 | 0.0000 / [0.0, 65.8] | -1.4189 | -0.7095 | 0.0000 | 1.5789 | 1.0089 | 2 |
| EQ_TREND_R0 | 1440m | 3 | 3 / 2 | 0.0000 / [0.0, 56.1] | -5.4300 | -1.8100 | 0.0000 | 5.4300 | 2.3800 | 3 |
| EQ_TREND_R0 | 1440m | 5 | 3 / 2 | 0.0000 / [0.0, 56.1] | -6.5100 | -2.1700 | 0.0000 | 6.5100 | 2.4400 | 3 |
| EQ_TREND_R0 | 1440m | 7.5 | 3 / 2 | 0.0000 / [0.0, 56.1] | -7.1400 | -2.3800 | 0.0000 | 7.1400 | 2.4600 | 3 |
| EQ_TREND_R0 | 1440m | 10 | 3 / 2 | 0.0000 / [0.0, 56.1] | -7.1400 | -2.3800 | 0.0000 | 7.1400 | 2.4600 | 3 |
| EQ_TREND_R0 | 1440m | 12.5 | 3 / 2 | 0.0000 / [0.0, 56.1] | -7.1400 | -2.3800 | 0.0000 | 7.1400 | 2.4600 | 3 |
| EQ_TREND_R0 | 1440m | 15 | 3 / 2 | 0.0000 / [0.0, 56.1] | -7.1400 | -2.3800 | 0.0000 | 7.1400 | 2.4600 | 3 |
| EQ_PULLBACK_R0 | 1440m | 1 | 0 / 6 | N/D / N/D | 0.0000 | N/D | N/D | 0.0000 | 0.0000 | 0 |
| EQ_PULLBACK_R0 | 1440m | 2 | 0 / 6 | N/D / N/D | 0.0000 | N/D | N/D | 0.0000 | 0.0000 | 0 |
| EQ_PULLBACK_R0 | 1440m | 3 | 2 / 4 | 0.0000 / [0.0, 65.8] | -3.5500 | -1.7750 | 0.0000 | 3.7300 | 1.6000 | 2 |
| EQ_PULLBACK_R0 | 1440m | 5 | 2 / 4 | 0.0000 / [0.0, 65.8] | -3.5500 | -1.7750 | 0.0000 | 3.7300 | 1.6000 | 2 |
| EQ_PULLBACK_R0 | 1440m | 7.5 | 2 / 4 | 0.0000 / [0.0, 65.8] | -3.5500 | -1.7750 | 0.0000 | 3.7300 | 1.6000 | 2 |
| EQ_PULLBACK_R0 | 1440m | 10 | 2 / 4 | 0.0000 / [0.0, 65.8] | -3.5500 | -1.7750 | 0.0000 | 3.7300 | 1.6000 | 2 |
| EQ_PULLBACK_R0 | 1440m | 12.5 | 2 / 4 | 0.0000 / [0.0, 65.8] | -3.5500 | -1.7750 | 0.0000 | 3.7300 | 1.6000 | 2 |
| EQ_PULLBACK_R0 | 1440m | 15 | 2 / 4 | 0.0000 / [0.0, 65.8] | -3.5500 | -1.7750 | 0.0000 | 3.7300 | 1.6000 | 2 |
| EQ_BREAKOUT_R0 | 1440m | 1 | 0 / 0 | N/D / N/D | 0.0000 | N/D | N/D | 0.0000 | 0.0000 | 0 |
| EQ_BREAKOUT_R0 | 1440m | 2 | 0 / 0 | N/D / N/D | 0.0000 | N/D | N/D | 0.0000 | 0.0000 | 0 |
| EQ_BREAKOUT_R0 | 1440m | 3 | 0 / 0 | N/D / N/D | 0.0000 | N/D | N/D | 0.0000 | 0.0000 | 0 |
| EQ_BREAKOUT_R0 | 1440m | 5 | 0 / 0 | N/D / N/D | 0.0000 | N/D | N/D | 0.0000 | 0.0000 | 0 |
| EQ_BREAKOUT_R0 | 1440m | 7.5 | 0 / 0 | N/D / N/D | 0.0000 | N/D | N/D | 0.0000 | 0.0000 | 0 |
| EQ_BREAKOUT_R0 | 1440m | 10 | 0 / 0 | N/D / N/D | 0.0000 | N/D | N/D | 0.0000 | 0.0000 | 0 |
| EQ_BREAKOUT_R0 | 1440m | 12.5 | 0 / 0 | N/D / N/D | 0.0000 | N/D | N/D | 0.0000 | 0.0000 | 0 |
| EQ_BREAKOUT_R0 | 1440m | 15 | 0 / 0 | N/D / N/D | 0.0000 | N/D | N/D | 0.0000 | 0.0000 | 0 |
| EQ_MEAN_REVERSION_R0 | 1440m | 1 | 0 / 3 | N/D / N/D | 0.0000 | N/D | N/D | 0.0000 | 0.0000 | 0 |
| EQ_MEAN_REVERSION_R0 | 1440m | 2 | 0 / 3 | N/D / N/D | 0.0000 | N/D | N/D | 0.0000 | 0.0000 | 0 |
| EQ_MEAN_REVERSION_R0 | 1440m | 3 | 0 / 3 | N/D / N/D | 0.0000 | N/D | N/D | 0.0000 | 0.0000 | 0 |
| EQ_MEAN_REVERSION_R0 | 1440m | 5 | 0 / 3 | N/D / N/D | 0.0000 | N/D | N/D | 0.0000 | 0.0000 | 0 |
| EQ_MEAN_REVERSION_R0 | 1440m | 7.5 | 0 / 3 | N/D / N/D | 0.0000 | N/D | N/D | 0.0000 | 0.0000 | 0 |
| EQ_MEAN_REVERSION_R0 | 1440m | 10 | 0 / 3 | N/D / N/D | 0.0000 | N/D | N/D | 0.0000 | 0.0000 | 0 |
| EQ_MEAN_REVERSION_R0 | 1440m | 12.5 | 0 / 3 | N/D / N/D | 0.0000 | N/D | N/D | 0.0000 | 0.0000 | 0 |
| EQ_MEAN_REVERSION_R0 | 1440m | 15 | 0 / 3 | N/D / N/D | 0.0000 | N/D | N/D | 0.0000 | 0.0000 | 0 |

## Robustez y walk-forward

Tres folds cronológicos de validación; sin ajustar parámetros. Warm-up causal del pasado, señales purgadas en frontera. Asignaciones independientes, no sumar sus ganancias como un único portfolio. Todos los costos, riesgos, métricas, rechazos, operaciones, intervalos ajustados y resultados continuos/desarrollo/validación/folds están en `artifacts/research/us-equities/report.json`.
| Candidato / TF | Costo | Mejor P&L validación descriptivo (entre riesgos; no selección) | Fold 1 / 2 / 3 neto | N validación |
|---|---|---:|---|---:|
| EQ_TREND_R0 / 60m | TIERED_BASE | -0.7034 | 0.0000 / 0.0000 / 0.0000 | 1 |
| EQ_TREND_R0 / 60m | TIERED_SPREAD_SLIPPAGE_STRESS | -0.7434 | 0.0000 / 0.0000 / 0.0000 | 1 |
| EQ_TREND_R0 / 60m | FIXED_FEE_STRESS | -0.7034 | 0.0000 / 0.0000 / 0.0000 | 1 |
| EQ_TREND_R0 / 1440m | TIERED_BASE | 0.0000 | 0.0000 / 0.0000 / 0.0000 | 0 |
| EQ_TREND_R0 / 1440m | TIERED_SPREAD_SLIPPAGE_STRESS | 0.0000 | 0.0000 / 0.0000 / 0.0000 | 0 |
| EQ_TREND_R0 / 1440m | FIXED_FEE_STRESS | 0.0000 | 0.0000 / 0.0000 / 0.0000 | 0 |
| EQ_PULLBACK_R0 / 60m | TIERED_BASE | 0.0000 | 0.0000 / 0.0000 / 0.0000 | 0 |
| EQ_PULLBACK_R0 / 60m | TIERED_SPREAD_SLIPPAGE_STRESS | 0.0000 | 0.0000 / 0.0000 / 0.0000 | 0 |
| EQ_PULLBACK_R0 / 60m | FIXED_FEE_STRESS | 0.0000 | 0.0000 / 0.0000 / 0.0000 | 0 |
| EQ_PULLBACK_R0 / 1440m | TIERED_BASE | 0.0000 | 0.0000 / 0.0000 / 0.0000 | 0 |
| EQ_PULLBACK_R0 / 1440m | TIERED_SPREAD_SLIPPAGE_STRESS | 0.0000 | 0.0000 / 0.0000 / 0.0000 | 0 |
| EQ_PULLBACK_R0 / 1440m | FIXED_FEE_STRESS | 0.0000 | 0.0000 / 0.0000 / 0.0000 | 0 |
| EQ_BREAKOUT_R0 / 60m | TIERED_BASE | -0.7514 | -0.7514 / 0.0000 / 0.0000 | 1 |
| EQ_BREAKOUT_R0 / 60m | TIERED_SPREAD_SLIPPAGE_STRESS | -0.4357 | -0.4357 / 0.0000 / 0.0000 | 1 |
| EQ_BREAKOUT_R0 / 60m | FIXED_FEE_STRESS | -0.7514 | -0.7514 / 0.0000 / 0.0000 | 1 |
| EQ_BREAKOUT_R0 / 1440m | TIERED_BASE | 0.0000 | 0.0000 / 0.0000 / 0.0000 | 0 |
| EQ_BREAKOUT_R0 / 1440m | TIERED_SPREAD_SLIPPAGE_STRESS | 0.0000 | 0.0000 / 0.0000 / 0.0000 | 0 |
| EQ_BREAKOUT_R0 / 1440m | FIXED_FEE_STRESS | 0.0000 | 0.0000 / 0.0000 / 0.0000 | 0 |
| EQ_MEAN_REVERSION_R0 / 60m | TIERED_BASE | 0.0000 | 0.0000 / 0.0000 / 0.0000 | 0 |
| EQ_MEAN_REVERSION_R0 / 60m | TIERED_SPREAD_SLIPPAGE_STRESS | 0.0000 | 0.0000 / 0.0000 / 0.0000 | 0 |
| EQ_MEAN_REVERSION_R0 / 60m | FIXED_FEE_STRESS | 0.0000 | 0.0000 / 0.0000 / 0.0000 | 0 |
| EQ_MEAN_REVERSION_R0 / 1440m | TIERED_BASE | 0.0000 | 0.0000 / 0.0000 / 0.0000 | 0 |
| EQ_MEAN_REVERSION_R0 / 1440m | TIERED_SPREAD_SLIPPAGE_STRESS | 0.0000 | 0.0000 / 0.0000 / 0.0000 | 0 |
| EQ_MEAN_REVERSION_R0 / 1440m | FIXED_FEE_STRESS | 0.0000 | 0.0000 / 0.0000 / 0.0000 | 0 |

## Bloqueos y próxima fase

No existe candidato seleccionado ni tamaño autorizado. Los parámetros son nuevos R0 de investigación, nunca versiones Forex V1 ni estrategias PaperEligible.
Pendiente: confirmar plan/comisiones reales, permisos/entidad/régimen intradía, settled USD, mínimos/fracciones y soporte de protección por contrato. Datos tardíos/frozen no habilitan ejecución.
Adapter productivo pendiente (sin implementar): contratos STK/SMART/conId, ticks/reglas de precio, sesiones y acciones corporativas, MarketData real time, inventario/settled cash por divisa y T+1, guard de intradía, bracket/OCA y close-only por posición, fills parciales/comisiones y reconciliación bursátil. El adapter actual admite exclusivamente EUR/USD CASH IDEALPRO; no basta con cambiar un símbolo.
Próxima fase: universo point-in-time con bajas y acciones corporativas, históricos BID/ASK/liquidez, más muestra OOS nueva y auditoría solo lectura de permisos/tarifas. No optimizar para alcanzar 80%; repetir protocolo congelado. Riesgo de ruina no estimable con esta muestra; stops no garantizan pérdida máxima frente a gaps.

## Fuentes primarias consultadas

- [Tarifas de acciones y cargos de terceros IBKR](https://www.interactivebrokers.com/en/pricing/commissions-stocks.php). Tarifas públicas; plan de cuenta desconocido. No se asume Lite.
- [Paper: permisos/datos heredados y limitaciones de simulación](https://www.ibkrguides.com/advisorportal/aboutpapertradingaccount.htm).
- [Liquidación T+1 y fondos en la divisa necesaria](https://www.interactivebrokers.com/campus/traders-insight/t1-settlement-what-it-means-for-traders-and-investors/). El modelo no presupone acceso a facilidades de crédito ni reutilización instantánea.
- [Margen de acciones y transición del régimen intradía](https://www.interactivebrokers.com/en/trading/margin-stocks.php). La transición hasta octubre 2027 impide aplicar indiscriminadamente una regla PDT única; verificar la cuenta.
- [API oficial: cuenta, históricos, contratos y órdenes](https://www.interactivebrokers.com/docs/tws-api/doc/introduction).
- [Códigos IBKR 2188/162/366](https://www.interactivebrokers.com/docs/tws-api/doc/error-handling/error-codes).
- [Restricciones intradía en transición](https://www.ibkrguides.com/ibkrdesktop/available-for-trading.htm). No inferir un número de day trades permitidos cuando el campo está ausente.
- [Código STKNOPT y nomenclatura Reg T de IBKR](https://www.interactivebrokers.com/campus/trading-lessons/risk-navigator-alternative-margin-calculator/). Interpretación del código observado, no prueba de permisos de ejecución.

## Limitaciones explícitas

- Development/validation and candidates defined before examining equity bars; not a preregistered external study.
- SCHX, SPY, F are a fixed surviving convenience sample, not a point-in-time liquid universe. No generalization to all stocks.
- TRADES split adjustment and corporate actions/dividends not independently reconciled; no dividend/interest income credited.
- Hourly gaps, missing sessions and historical quote/liquidity depth are not independently verified.
- Risk scenarios and cost families are multiple comparisons, not optimization; adjusted family=192.
- 2000 bootstrap resamples have limited resolution at extreme family-adjusted tails; intervals remain approximate and insufficient for promotion.
- Walk-forward uses preceding bars only for causal warm-up; no refit. Purged signal boundaries; independent $100/$20 fold allocations.
- Commission minima plus conservative extra-fee envelope are estimates; real tiered plan, venue fees, fractional permissions unknown.
- Orders are modeled as one fill per side. Partial-fill modifications/overnight minimum resets, tax and market-data subscriptions are not account-verified; fixed-fee stress is not a bound on every possible fee.
- 100 OOS trades / 30 days / 3 positive folds are research thresholds, not guarantees. Ruin probability unidentifiable.
- Targets are assumed limit fills with conservative stop priority; actual liquidity/queue probability not measured.
- Cash-account T+1 model is conservative. No reuse of sale proceeds before settlement; margin intraday regime unknown.

## Verificación ejecutada

480 Python + 240 C# = **720 aprobadas**, fallos 0, omitidas 0. Compilación .NET: 0 errores, 0 advertencias.
Controles protegidos comparados por SHA256; DB de regresiones detenida. No se modificó el ejecutor, Forex V1, AccountBinding, EmergencyStop ni autorizaciones. Live bloqueado.
