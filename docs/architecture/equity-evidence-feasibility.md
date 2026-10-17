# Evidencia operativa y económica bursátil

**EXECUTION_CONSTRAINT_BLOCKED**. Sin promoción ni autorización de ejecución.

En selección 2024 la muestra máxima es 19 operaciones por configuración; no se suman escenarios correlacionados. EQ_TREND_R0 60m/1% obtiene +US$0.0752 con una única ganadora (Wilson95: 20.65%–100.00%): no acredita edge ni acierto >80%. Los cuatro candidatos mantienen parámetros/versiones R0 intactos.

## Comparación de referencia, sin selección de perfil

Selección cronológica 2024, 1h, riesgo 15%, Tiered base estimado. Se muestra el mismo escenario para los cuatro; no es recomendación de riesgo.

| Candidato | Admitidas | Win % | Neto US$ | EV neta | PF | DD % | Días primer loss |
|---|---:|---:|---:|---:|---:|---:|---:|
| EQ_TREND_R0 | 18 | 50.00 | -9.43 | -0.5239 | 0.5507 | 12.93 | 9 |
| EQ_PULLBACK_R0 | 2 | 0.00 | -3.40 | -1.7000 | 0.0000 | 3.88 | 2 |
| EQ_BREAKOUT_R0 | 19 | 47.37 | -11.72 | -0.6168 | 0.3841 | 11.72 | 10 |
| EQ_MEAN_REVERSION_R0 | 10 | 20.00 | -13.06 | -1.3060 | 0.2180 | 15.00 | 8 |

Riesgo observado: EQ_BREAKOUT_R0 1440m/7.5%, F 2024-07-25T13:30:00+00:00, salida STOP_GAP. Riesgo restante presupuestado US$6.53, pérdida realizada US$15.56; pérdidas acumuladas US$28.53 y DD 28.53%. El motor congelado marca breach y bloquea nuevas entradas: el stop no garantiza el precio ni limita gaps. No se recortan pérdidas históricas para simular que se respetó US$20. Escenarios con breaches quedan descalificados. Probabilidad fiable de ruina y ejecución real: UNKNOWN.

## Hechos y alcance

| Hecho | Estado | Valor / alcance |
|---|---|---|
| paper_identity | VERIFIED | "***3784"; THIS_PAPER_ACCOUNT_OBSERVATION |
| account_legal_type | VERIFIED | "INDIVIDUAL"; THIS_PAPER_ACCOUNT_OBSERVATION |
| trading_type_code | VERIFIED | "STKNOPT"; THIS_PAPER_ACCOUNT_OBSERVATION |
| account_margin_class | ESTIMATED | "REG_T_MARGIN_FROM_STKNOPT"; THIS_PAPER_ACCOUNT_OBSERVATION |
| SettledCash_USD | UNKNOWN | null; THIS_PAPER_ACCOUNT_OBSERVATION |
| AvailableFunds_USD | VERIFIED | "1000089.01"; THIS_PAPER_ACCOUNT_OBSERVATION |
| CashBalance_USD | UNKNOWN | null; THIS_PAPER_ACCOUNT_OBSERVATION |
| day_trades_remaining | UNKNOWN | null; THIS_PAPER_ACCOUNT_OBSERVATION |
| stock_etf_trading_permissions | UNKNOWN | null; THIS_PAPER_ACCOUNT_OBSERVATION |
| applicable_commission_plan | UNKNOWN | null; THIS_PAPER_ACCOUNT_OBSERVATION |
| effective_stock_commissions | UNKNOWN | null; THIS_PAPER_ACCOUNT_OBSERVATION |
| account_entity_and_restrictions | UNKNOWN | null; THIS_PAPER_ACCOUNT_OBSERVATION |
| applicable_intraday_regime | UNKNOWN | null; THIS_PAPER_ACCOUNT_OBSERVATION |
| fractional_order_permissions | UNKNOWN | null; THIS_PAPER_ACCOUNT_OBSERVATION |
| effective_stock_bracket_protection | UNKNOWN | null; THIS_PAPER_ACCOUNT_OBSERVATION |
| intraday_usd100_executability | UNKNOWN | null; THIS_PAPER_ACCOUNT_OBSERVATION |
| public_tiered_low_volume_tariff | VERIFIED | {"per_share_usd": ".0035", "minimum_usd": ".35", "additional_fees": true}; PUBLIC_US_SCHEDULE_NOT_ACCOUNT_PRICE |
| research_commission_envelope | ESTIMATED | {"extra_per_order_usd": ".02", "extra_per_share_usd": ".01", "base": "PUBLIC_TIERED_OR_FIXED_SENSITIVITY"}; SIMULATION_ONLY |
| settlement_cycle | VERIFIED | "T+1_US_STOCKS"; GENERAL_MARKET_RULE_NOT_ACCOUNT_CREDIT |
| virtual_allocation | VERIFIED | {"initial_usd": 100, "exposure_limit": 1, "loss_allowance_usd": 20}; RESEARCH_ONLY_NOT_BROKER_BUYING_POWER |
| cash_availability_model | ESTIMATED | "NO_SAME_DAY_REUSE_OF_SALE_PROCEEDS"; CONSERVATIVE_SIMULATION |
| SCHX_contract | VERIFIED | {"con_id": 70083655, "minimum_size": "0.0001", "size_increment": "0.0001", "min_tick": "0.01"}; THIS_PAPER_ACCOUNT_OBSERVATION |
| SCHX_declared_protective_types | VERIFIED | ["LMT", "OCA", "STP", "STPLMT"]; CONTRACT_CAPABILITIES_NOT_ACCOUNT_ORDER_ACCEPTANCE |
| SCHX_market_data_observation | VERIFIED | {"data_type": "DELAYED", "bid": "30.51", "ask": "30.65", "reason": null, "received_at": "2026-10-06T08:46:37.678551+00:00"}; THIS_PAPER_ACCOUNT_OBSERVATION |
| SCHX_realtime_execution_data | UNKNOWN | null; THIS_PAPER_ACCOUNT_OBSERVATION |
| SPY_contract | VERIFIED | {"con_id": 756733, "minimum_size": "0.0001", "size_increment": "0.0001", "min_tick": "0.01"}; THIS_PAPER_ACCOUNT_OBSERVATION |
| SPY_declared_protective_types | VERIFIED | ["LMT", "OCA", "STP", "STPLMT"]; CONTRACT_CAPABILITIES_NOT_ACCOUNT_ORDER_ACCEPTANCE |
| SPY_market_data_observation | VERIFIED | {"data_type": "DELAYED", "bid": "776.13", "ask": "776.17", "reason": null, "received_at": "2026-10-06T08:48:46.623547+00:00"}; THIS_PAPER_ACCOUNT_OBSERVATION |
| SPY_realtime_execution_data | UNKNOWN | null; THIS_PAPER_ACCOUNT_OBSERVATION |
| F_contract | VERIFIED | {"con_id": 9599491, "minimum_size": "0.0001", "size_increment": "0.0001", "min_tick": "0.01"}; THIS_PAPER_ACCOUNT_OBSERVATION |
| F_declared_protective_types | VERIFIED | ["LMT", "OCA", "STP", "STPLMT"]; CONTRACT_CAPABILITIES_NOT_ACCOUNT_ORDER_ACCEPTANCE |
| F_market_data_observation | VERIFIED | {"data_type": "DELAYED", "bid": "12.18", "ask": "12.19", "reason": null, "received_at": "2026-10-06T08:51:10.952065+00:00"}; THIS_PAPER_ACCOUNT_OBSERVATION |
| F_realtime_execution_data | UNKNOWN | null; THIS_PAPER_ACCOUNT_OBSERVATION |
| production_stock_adapter | VERIFIED | false; CODE_INSPECTION |

VERIFIED acredita exclusivamente el hecho observado y su alcance. ESTIMATED indica inferencia/modelo; UNKNOWN conserva null y bloquea admisión cuando es requisito. AvailableFunds/CashBalance no sustituyen SettledCash ni el capital aislado US$100. Contrato y datos no prueban permiso de negociación.
Bloqueos de ejecución: account_margin_class, SettledCash_USD, day_trades_remaining, stock_etf_trading_permissions, applicable_commission_plan, effective_stock_commissions, account_entity_and_restrictions, applicable_intraday_regime, fractional_order_permissions, effective_stock_bracket_protection, intraday_usd100_executability, SCHX_realtime_execution_data, SPY_realtime_execution_data, F_realtime_execution_data, production_stock_adapter.

La consulta local de estado de Client Portal falló con URLError; no se inició login ni se cambiaron permisos. Se necesitan pruebas de cuenta desde una sesión local autorizada o extracto. ADJUSTED_LAST devolvió inicialmente IBKR 321 porque requiere endDateTime vacío: corregido y obtenido en la consulta suplementaria. La cola reciente se descarta antes de cualquier uso; los datos ajustados solo verifican calidad.

## Procedencia, separaciones y calidad

Universo fijo SCHX/SPY/F; IBKR TRADES RTH, timestamps UTC y calendario SCHEDULE auténtico. Entrenamiento 2021–2023, selección 2024, final 2025–2026-04-03. El archivo examinado 2026-04-03–2026-10-03 está en cuarentena, excluido de entrenamiento y selección. Sin optimización ni ajuste de parámetros.
Configuraciones reevaluadas: 192; resultados de entrenamiento/selección/tres folds: 960. Final sellado: True; resultados finales evaluados: 0.

| Instrumento | Sesiones | Velas 1h | Velas diario | Cobertura | ADJUSTED_LAST |
|---|---:|---:|---:|---|---|
| SCHX | 1318 | 9196 | 1318 | True | True |
| SPY | 1318 | 9196 | 1318 | True | True |
| F | 1318 | 9196 | 1318 | True | True |

SCHX: evento 3:1 verificado con el emisor, precio de cotización post-split desde 2024-10-11. Se restaura ×3 el OHLC anterior para dimensionar con notional histórico; estimación basada en TRADES ajustado por splits. Se excluyen entradas que puedan cruzar el evento y se reinicia warm-up causal por episodio. No se cambia ningún parámetro R0. Volumen permanece original; no se afirma reconstrucción completa de todas las acciones corporativas.
ADJUSTED_LAST no alimenta señales/P&L: sus ajustes futuros por dividendos no son precios negociables históricos. Calendario de dividendos/receivables y otras acciones corporativas sin conciliación independiente: UNKNOWN. Universo sin sesgo de supervivencia: no demostrado; se limita a estudio de casos. Estas carencias impiden abrir la prueba final.

## Selección 2024 — todos los riesgos, Tiered base

| Candidato | TF | Riesgo % | Admitidas/rechazadas | Win % | Wilson95 % | Neto US$ | EV | PF | DD % | Comisiones | Días primer loss |
|---|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|
| EQ_TREND_R0 | 60m | 1 | 1/84 | 100.0000 | 20.6549/100.0000 | 0.0752 | 0.0752 | N/D | 0.3948 | 0.3048 | 0 |
| EQ_TREND_R0 | 60m | 2 | 11/74 | 45.4545 | 21.2713/71.9908 | -6.0600 | -0.5509 | 0.3098 | 6.8774 | 9.0600 | 6 |
| EQ_TREND_R0 | 60m | 3 | 18/67 | 50.0000 | 29.0310/70.9690 | -10.5900 | -0.5883 | 0.4734 | 12.9745 | 15.9000 | 9 |
| EQ_TREND_R0 | 60m | 5 | 18/67 | 50.0000 | 29.0310/70.9690 | -9.4300 | -0.5239 | 0.5507 | 12.9302 | 16.1200 | 9 |
| EQ_TREND_R0 | 60m | 7.5 | 18/67 | 50.0000 | 29.0310/70.9690 | -9.4300 | -0.5239 | 0.5507 | 12.9302 | 16.1200 | 9 |
| EQ_TREND_R0 | 60m | 10 | 18/67 | 50.0000 | 29.0310/70.9690 | -9.4300 | -0.5239 | 0.5507 | 12.9302 | 16.1200 | 9 |
| EQ_TREND_R0 | 60m | 12.5 | 18/67 | 50.0000 | 29.0310/70.9690 | -9.4300 | -0.5239 | 0.5507 | 12.9302 | 16.1200 | 9 |
| EQ_TREND_R0 | 60m | 15 | 18/67 | 50.0000 | 29.0310/70.9690 | -9.4300 | -0.5239 | 0.5507 | 12.9302 | 16.1200 | 9 |
| EQ_PULLBACK_R0 | 60m | 1 | 0/105 | N/D | N/D | 0.0000 | N/D | N/D | 0.0000 | 0.0000 | 0 |
| EQ_PULLBACK_R0 | 60m | 2 | 1/104 | 0.0000 | 0.0000/79.3451 | -1.3000 | -1.3000 | 0.0000 | 1.7800 | 0.9000 | 1 |
| EQ_PULLBACK_R0 | 60m | 3 | 2/103 | 0.0000 | 0.0000/65.7620 | -3.4000 | -1.7000 | 0.0000 | 3.8800 | 1.8000 | 2 |
| EQ_PULLBACK_R0 | 60m | 5 | 2/103 | 0.0000 | 0.0000/65.7620 | -3.4000 | -1.7000 | 0.0000 | 3.8800 | 1.8000 | 2 |
| EQ_PULLBACK_R0 | 60m | 7.5 | 2/103 | 0.0000 | 0.0000/65.7620 | -3.4000 | -1.7000 | 0.0000 | 3.8800 | 1.8000 | 2 |
| EQ_PULLBACK_R0 | 60m | 10 | 2/103 | 0.0000 | 0.0000/65.7620 | -3.4000 | -1.7000 | 0.0000 | 3.8800 | 1.8000 | 2 |
| EQ_PULLBACK_R0 | 60m | 12.5 | 2/103 | 0.0000 | 0.0000/65.7620 | -3.4000 | -1.7000 | 0.0000 | 3.8800 | 1.8000 | 2 |
| EQ_PULLBACK_R0 | 60m | 15 | 2/103 | 0.0000 | 0.0000/65.7620 | -3.4000 | -1.7000 | 0.0000 | 3.8800 | 1.8000 | 2 |
| EQ_BREAKOUT_R0 | 60m | 1 | 2/103 | 0.0000 | 0.0000/65.7620 | -0.6514 | -0.3257 | 0.0000 | 1.1414 | 0.6114 | 2 |
| EQ_BREAKOUT_R0 | 60m | 2 | 7/98 | 14.2857 | 2.5680/51.3128 | -6.1524 | -0.8789 | 0.0639 | 6.3924 | 5.4624 | 6 |
| EQ_BREAKOUT_R0 | 60m | 3 | 19/86 | 47.3684 | 27.3298/68.2922 | -11.9500 | -0.6289 | 0.3495 | 11.9500 | 16.6200 | 10 |
| EQ_BREAKOUT_R0 | 60m | 5 | 19/86 | 47.3684 | 27.3298/68.2922 | -11.7200 | -0.6168 | 0.3841 | 11.7200 | 16.8000 | 10 |
| EQ_BREAKOUT_R0 | 60m | 7.5 | 19/86 | 47.3684 | 27.3298/68.2922 | -11.7200 | -0.6168 | 0.3841 | 11.7200 | 16.8000 | 10 |
| EQ_BREAKOUT_R0 | 60m | 10 | 19/86 | 47.3684 | 27.3298/68.2922 | -11.7200 | -0.6168 | 0.3841 | 11.7200 | 16.8000 | 10 |
| EQ_BREAKOUT_R0 | 60m | 12.5 | 19/86 | 47.3684 | 27.3298/68.2922 | -11.7200 | -0.6168 | 0.3841 | 11.7200 | 16.8000 | 10 |
| EQ_BREAKOUT_R0 | 60m | 15 | 19/86 | 47.3684 | 27.3298/68.2922 | -11.7200 | -0.6168 | 0.3841 | 11.7200 | 16.8000 | 10 |
| EQ_MEAN_REVERSION_R0 | 60m | 1 | 4/125 | 50.0000 | 15.0039/84.9961 | -0.4111 | -0.1028 | 0.4533 | 1.3311 | 1.5811 | 2 |
| EQ_MEAN_REVERSION_R0 | 60m | 2 | 5/124 | 40.0000 | 11.7621/76.9276 | -1.6600 | -0.3320 | 0.5089 | 3.9600 | 4.1800 | 3 |
| EQ_MEAN_REVERSION_R0 | 60m | 3 | 10/119 | 20.0000 | 5.6682/50.9838 | -12.9800 | -1.2980 | 0.2190 | 15.0000 | 8.7800 | 8 |
| EQ_MEAN_REVERSION_R0 | 60m | 5 | 10/119 | 20.0000 | 5.6682/50.9838 | -13.0600 | -1.3060 | 0.2180 | 15.0000 | 8.8200 | 8 |
| EQ_MEAN_REVERSION_R0 | 60m | 7.5 | 10/119 | 20.0000 | 5.6682/50.9838 | -13.0600 | -1.3060 | 0.2180 | 15.0000 | 8.8200 | 8 |
| EQ_MEAN_REVERSION_R0 | 60m | 10 | 10/119 | 20.0000 | 5.6682/50.9838 | -13.0600 | -1.3060 | 0.2180 | 15.0000 | 8.8200 | 8 |
| EQ_MEAN_REVERSION_R0 | 60m | 12.5 | 10/119 | 20.0000 | 5.6682/50.9838 | -13.0600 | -1.3060 | 0.2180 | 15.0000 | 8.8200 | 8 |
| EQ_MEAN_REVERSION_R0 | 60m | 15 | 10/119 | 20.0000 | 5.6682/50.9838 | -13.0600 | -1.3060 | 0.2180 | 15.0000 | 8.8200 | 8 |
| EQ_TREND_R0 | 1440m | 1 | 5/8 | 20.0000 | 3.6224/62.4465 | -2.4892 | -0.4978 | 0.1579 | 2.7892 | 1.5092 | 4 |
| EQ_TREND_R0 | 1440m | 2 | 6/7 | 16.6667 | 3.0053/56.3503 | -5.3869 | -0.8978 | 0.1530 | 5.5569 | 3.0969 | 5 |
| EQ_TREND_R0 | 1440m | 3 | 7/6 | 28.5714 | 8.2219/64.1066 | -8.6781 | -1.2397 | 0.1956 | 9.2800 | 5.2781 | 5 |
| EQ_TREND_R0 | 1440m | 5 | 9/4 | 33.3333 | 12.0584/64.5798 | -13.3470 | -1.4830 | 0.2914 | 14.2700 | 7.1570 | 6 |
| EQ_TREND_R0 | 1440m | 7.5 | 8/5 | 37.5000 | 13.6844/69.4258 | -12.9000 | -1.6125 | 0.3264 | 15.3000 | 6.7200 | 5 |
| EQ_TREND_R0 | 1440m | 10 | 8/5 | 37.5000 | 13.6844/69.4258 | -12.9000 | -1.6125 | 0.3264 | 15.3000 | 6.7200 | 5 |
| EQ_TREND_R0 | 1440m | 12.5 | 8/5 | 37.5000 | 13.6844/69.4258 | -12.9000 | -1.6125 | 0.3264 | 15.3000 | 6.7200 | 5 |
| EQ_TREND_R0 | 1440m | 15 | 8/5 | 37.5000 | 13.6844/69.4258 | -12.9000 | -1.6125 | 0.3264 | 15.3000 | 6.7200 | 5 |
| EQ_PULLBACK_R0 | 1440m | 1 | 5/14 | 40.0000 | 11.7621/76.9276 | -1.5404 | -0.3081 | 0.2297 | 1.5704 | 1.5204 | 3 |
| EQ_PULLBACK_R0 | 1440m | 2 | 6/13 | 33.3333 | 9.6771/70.0007 | -5.2004 | -0.8667 | 0.1611 | 5.2604 | 4.0804 | 4 |
| EQ_PULLBACK_R0 | 1440m | 3 | 7/12 | 42.8571 | 15.8220/74.9542 | -4.8545 | -0.6935 | 0.4133 | 4.9445 | 5.6045 | 4 |
| EQ_PULLBACK_R0 | 1440m | 5 | 7/12 | 42.8571 | 15.8220/74.9542 | -5.4400 | -0.7771 | 0.5482 | 5.6500 | 5.9400 | 4 |
| EQ_PULLBACK_R0 | 1440m | 7.5 | 7/12 | 42.8571 | 15.8220/74.9542 | -5.9500 | -0.8500 | 0.5259 | 6.1900 | 5.9600 | 4 |
| EQ_PULLBACK_R0 | 1440m | 10 | 7/12 | 42.8571 | 15.8220/74.9542 | -5.9500 | -0.8500 | 0.5259 | 6.1900 | 5.9600 | 4 |
| EQ_PULLBACK_R0 | 1440m | 12.5 | 7/12 | 42.8571 | 15.8220/74.9542 | -5.9500 | -0.8500 | 0.5259 | 6.1900 | 5.9600 | 4 |
| EQ_PULLBACK_R0 | 1440m | 15 | 7/12 | 42.8571 | 15.8220/74.9542 | -5.9500 | -0.8500 | 0.5259 | 6.1900 | 5.9600 | 4 |
| EQ_BREAKOUT_R0 | 1440m | 1 | 2/7 | 0.0000 | 0.0000/65.7620 | -1.6665 | -0.8333 | 0.0000 | 1.8465 | 0.6365 | 2 |
| EQ_BREAKOUT_R0 | 1440m | 2 | 3/6 | 0.0000 | 0.0000/56.1497 | -5.2933 | -1.7644 | 0.0000 | 5.2933 | 1.1833 | 3 |
| EQ_BREAKOUT_R0 | 1440m | 3 | 4/5 | 0.0000 | 0.0000/48.9891 | -12.6114 | -3.1528 | 0.0000 | 12.6114 | 2.7614 | 4 |
| EQ_BREAKOUT_R0 | 1440m | 5 | 4/5 | 0.0000 | 0.0000/48.9891 | -21.6200 | -5.4050 | 0.0000 | 21.6200 | 3.3000 | 4 |
| EQ_BREAKOUT_R0 | 1440m | 7.5 | 4/5 | 0.0000 | 0.0000/48.9891 | -28.5300 | -7.1325 | 0.0000 | 28.5300 | 3.4000 | 4 |
| EQ_BREAKOUT_R0 | 1440m | 10 | 4/5 | 0.0000 | 0.0000/48.9891 | -28.5300 | -7.1325 | 0.0000 | 28.5300 | 3.4000 | 4 |
| EQ_BREAKOUT_R0 | 1440m | 12.5 | 4/5 | 0.0000 | 0.0000/48.9891 | -28.5300 | -7.1325 | 0.0000 | 28.5300 | 3.4000 | 4 |
| EQ_BREAKOUT_R0 | 1440m | 15 | 4/5 | 0.0000 | 0.0000/48.9891 | -28.5300 | -7.1325 | 0.0000 | 28.5300 | 3.4000 | 4 |
| EQ_MEAN_REVERSION_R0 | 1440m | 1 | 3/9 | 33.3333 | 6.1492/79.2340 | -1.0837 | -0.3612 | 0.3329 | 1.6157 | 0.8537 | 2 |
| EQ_MEAN_REVERSION_R0 | 1440m | 2 | 4/8 | 50.0000 | 15.0039/84.9961 | -1.7974 | -0.4493 | 0.4328 | 3.1259 | 2.3874 | 2 |
| EQ_MEAN_REVERSION_R0 | 1440m | 3 | 4/8 | 50.0000 | 15.0039/84.9961 | -2.3446 | -0.5861 | 0.5982 | 5.6378 | 3.2546 | 2 |
| EQ_MEAN_REVERSION_R0 | 1440m | 5 | 5/7 | 60.0000 | 23.0724/88.2379 | -1.3400 | -0.2680 | 0.8707 | 8.4787 | 4.3600 | 2 |
| EQ_MEAN_REVERSION_R0 | 1440m | 7.5 | 5/7 | 60.0000 | 23.0724/88.2379 | -2.5400 | -0.5080 | 0.7803 | 9.5918 | 4.4000 | 2 |
| EQ_MEAN_REVERSION_R0 | 1440m | 10 | 5/7 | 60.0000 | 23.0724/88.2379 | -2.5400 | -0.5080 | 0.7803 | 9.5918 | 4.4000 | 2 |
| EQ_MEAN_REVERSION_R0 | 1440m | 12.5 | 5/7 | 60.0000 | 23.0724/88.2379 | -2.5400 | -0.5080 | 0.7803 | 9.5918 | 4.4000 | 2 |
| EQ_MEAN_REVERSION_R0 | 1440m | 15 | 5/7 | 60.0000 | 23.0724/88.2379 | -2.5400 | -0.5080 | 0.7803 | 9.5918 | 4.4000 | 2 |

Todos los costos stress/Fixed, medias de ganancias/pérdidas, rechazos, drawdowns, bootstrap/intervalos ajustados de familia y folds se conservan en `artifacts/research/equity-evidence/report.json`. El presupuesto de pérdidas acumuladas US$20 puede detener el experimento antes de completar el año; no se reinicia para fabricar muestra. No sumar asignaciones independientes de folds.

## Cambios que podrían mejorar factibilidad

| Candidato / TF | Señales selección con target neto potencial positivo | Capital mínimo estimado en una señal a 15% | Dentro de US$100 |
|---|---:|---:|---:|
| EQ_TREND_R0 / 60m | 67 | 12.3550 | 25 |
| EQ_TREND_R0 / 1440m | 13 | 11.1844 | 9 |
| EQ_PULLBACK_R0 / 60m | 38 | 73.0400 | 5 |
| EQ_PULLBACK_R0 / 1440m | 18 | 11.6114 | 7 |
| EQ_BREAKOUT_R0 / 60m | 71 | 12.4468 | 38 |
| EQ_BREAKOUT_R0 / 1440m | 8 | 12.3614 | 6 |
| EQ_MEAN_REVERSION_R0 / 60m | 57 | 10.6647 | 17 |
| EQ_MEAN_REVERSION_R0 / 1440m | 12 | 10.8354 | 6 |

Estos mínimos son geometría de UNA señal y costos estimados, no rentabilidad de portfolio ni capital recomendado. Más capital puede reducir costo fijo relativo; no demuestra edge, acierto >80% ni permiso intradía. Instrumento: SPY entero es caro para US$100; fracciones requieren permiso/route/costos específicos. Frecuencia: el modelo T+1 reduce reutilización intradía; no se presupone crédito o cuota diaria. Costos: verificar el plan real y los cargos antes de cambiar el modelo. Estrategia: no crear/optimizar otra hasta cerrar evidencia operativa y calidad.

## Recomendación concreta

Siguiente fase: evidencia de cuenta desde Portal/extracto autorizado de solo lectura (permisos US Stocks/ETF, entidad/Reg T/Cash, tarifa efectiva, settled USD y reglas de intradía), BID/ASK real time durante RTH y calendario/acciones corporativas íntegros de proveedor auténtico. No hace falta una orden para certificar ajustes de cuenta; what-if requeriría placeOrder y se mantiene prohibido. Protección efectiva bursátil exige una futura validación controlada separada, todavía sin autorizar.
Conservar el test final cerrado hasta que selección y calidad lo justifiquen. Después ejecutar una sola evaluación congelada; si falla, no volver a entrenar o seleccionar sobre ese test. Mantener FIRST_LOSS_STOPS_DAY en America/Santo_Domingo, una posición y gestión/reconciliación de pendientes.

## Limitaciones

- Universe remains SCHX/SPY/F, chosen among survivors. No broad strategy viability inference.
- SCHX split restored from verified issuer event; no position crosses the action; prior feature warmup restarts. Other actions/dividend cash ledger incomplete.
- ADJUSTED_LAST used only for data-quality comparison, never as executable prices or receivable cash.
- Selection is chronological retrospective unseen history, not a prospective confirmation. Earlier April–October 2026 results never train or select.
- Missing effective tariffs/permitted intraday funds remain execution blockers; simulations use frozen conservative cash T+1/cost assumptions.
- Risk of capital exhaustion cannot be assigned a reliable probability from policy-stopped, sparse/dependent samples.
- Maximum loss allowance remains 20 and gains do not replenish it. Five independent study allocations cannot be summed as one portfolio.

## Fuentes primarias

- [ibkr_bars](https://interactivebrokers.github.io/tws-api/historical_bars.html).
- [schx_split](https://pressroom.aboutschwab.com/press-releases/press-release/2024/Schwab-Asset-Management-Announces-ETF-Share-Splits/default.aspx).
- [commissions](https://www.interactivebrokers.com/en/pricing/commissions-stocks.php).
- [margin_code](https://www.interactivebrokers.com/campus/trading-lessons/risk-navigator-alternative-margin-calculator/).
- [intraday](https://www.ibkrguides.com/ibkrdesktop/available-for-trading.htm).
- [settlement](https://www.interactivebrokers.com/campus/traders-insight/t1-settlement-what-it-means-for-traders-and-investors/).
- [paper](https://www.ibkrguides.com/advisorportal/aboutpapertradingaccount.htm).
- [adjusted_end_date](https://www.interactivebrokers.com/docs/tws-api/sync-doc/historical-market-data).

## Regresiones y seguridad

499 Python + 240 C# = 739 aprobadas. Fallos/omitidas: 0/0. Build: 0 errores, 0 advertencias.
RiskEngine, candidatos R0/Forex V1, límites, AccountBinding, EmergencyStop y archivos previos permanecen idénticos por SHA256. Emergencia activa, PaperAuto ausente, Live bloqueado y órdenes transmitidas 0. PostgreSQL desechable detenido.
