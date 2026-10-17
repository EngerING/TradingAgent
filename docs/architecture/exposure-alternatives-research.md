# Exposición Forex y alternativas con capital experimental US$100

Resultado: **NO_VIABLE_STRATEGY_FOUND**. Sin promoción, órdenes, permisos ni cambios operativos.

Se evaluaron 17 riesgos (enteros 1–15%, más 7.5/12.5% anteriores), seis exposiciones y cinco escenarios: 9,180 simulaciones en seis particiones; 1,530 combinaciones en validación. Tres V1 sin cambios. Exposición mayor solo en el ejecutable ResearchLab, sin transporte.

Dataset `bb95c4d5394704af60d7c4ccde15710f504daddf1463f3b9ac44c68f39e87c8c`, 2026-04-03T00:00:00+00:00 a 2026-10-03T00:00:00+00:00; validación desde 2026-08-03T00:00:00+00:00.

## Costos, margen y restricciones

US$2 por lado observados en un único diagnóstico Paper. Base: spread estimado 0.00005, slippage conservador 0.00045 y gap reservado 0.00005 USD/EUR. Financiación estimada 10% anual ACT/360 sobre todo el notional, reserva de un día; se liquida el costo modelado por tiempo realmente mantenido. No se fuerza una salida al cumplir el plazo de reserva. Se informa cualquier exceso.

Spread de estrés del archivo: 0.0014. Se compara sin financiación, con reserva de cuatro días y en un quinto caso favorable sin financiación/margen 2.5% hipotético. Un costo de USD4 ya impide los riesgos iniciales 1–4% antes del movimiento del precio.

La tasa inicial/mantenimiento 5% es **hipotética**, con margen más pérdida completa al stop financiados por los US$100. IBKR calcula margen por saldos netos de moneda y puede exigir más; sus ejemplos 2.5% no certifican una tasa actual. [IBKR Forex margin](https://www.interactivebrokers.co.uk/en/trading/margin-forex.php?ex=uk&hm=ot&pm=0&rgt=1&rsk=0&rst=120104010408080801).

El [tipo de cuenta](https://www.interactivebrokers.com/en/accounts/configuring-your-account.php) puede impedir préstamos; [Spot Currencies requiere permisos adicionales](https://www.interactivebrokers.com/en/accounts/trading-and-market-data.php). Para determinadas entidades/cuentas IBLLC se exige ECP; la entidad, residencia, tipo de cuenta y permisos aplicables siguen sin verificar. El margen archivado 0 estando flat no prueba capacidad para abrir.

El mínimo/incremento del contrato archivado es 0.01 EUR/0.01 EUR; tick 0.00005. [IDEALPRO estándar](https://investors.interactivebrokers.com/en/?f=5479) publica 20,000 EUR; todos los tamaños del estudio hasta 20× quedan por debajo. Solo 100 EUR se probó en el diagnóstico previo; otros tamaños, protección, min tick efectivo y short permanecen sin confirmar.

## Exposición mínima para target neto positivo

Umbrales mínimos en los seis meses completos; no representan mínimos confirmados fuera de muestra. La validación se distingue en la tabla siguiente.

| Costos | Estrategia | EUR mínimo | Notional USD | Exposición | Stop USD | Costos USD | Gap / financiación USD | Riesgo total USD | Target bruto / neto USD | Margen máximo financiable % | Umbrales ≤20×/≤US15 / financiados al margen supuesto |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| CONSERVATIVE_1_DAY/trend | trend | 2191.7200 | 2524.3026 | 25.2430 | 3.9378 | 5.0959 | 0.1096 / 0.7012 | 9.8444 | 5.9067 / 1.372e-05 | 3.5658 | 0 / 0 (5%) |
| ARCHIVE_SPREAD_STRESS/trend | trend | 8423.3700 | 9707.2601 | 97.0726 | 15.1339 | 19.5832 | 0.4212 / 2.6965 | 37.8348 | 22.7009 / 7.190e-07 | 0.6394 | 0 / 0 (5%) |
| OPTIMISTIC_NO_FINANCING/trend | trend | 1864.8200 | 2147.7971 | 21.4780 | 3.3504 | 4.9324 | 0.0932 / 0.0000 | 8.3761 | 5.0257 / 1.293e-05 | 4.2591 | 0 / 0 (5%) |
| FINANCING_4_DAY_STRESS/trend | trend | 4622.8400 | 5324.3329 | 53.2433 | 8.3057 | 6.3114 | 0.2311 / 5.9159 | 20.7641 | 12.4585 / 2.027e-06 | 1.4858 | 0 / 0 (5%) |
| OPTIMISTIC_MARGIN_2_5_PERCENT/trend | trend | 1864.8200 | 2147.7971 | 21.4780 | 3.3504 | 4.9324 | 0.0932 / 0.0000 | 8.3761 | 5.0257 / 1.293e-05 | 4.2591 | 0 / 0 (2.5%) |
| CONSERVATIVE_1_DAY/pullback | pullback | 1527.7000 | 1791.1289 | 17.9113 | 3.5585 | 4.7638 | 0.0764 / 0.4975 | 8.8963 | 5.3378 / 3.963e-06 | 5.0761 | 3 / 1 (5%) |
| ARCHIVE_SPREAD_STRESS/pullback | pullback | 3154.2600 | 3700.2939 | 37.0029 | 7.3473 | 9.8354 | 0.1577 / 1.0279 | 18.3683 | 11.0210 / 1.239e-05 | 2.2016 | 0 / 0 (5%) |
| OPTIMISTIC_NO_FINANCING/pullback | pullback | 1358.7000 | 1592.9874 | 15.9299 | 3.1649 | 4.6794 | 0.0679 / 0.0000 | 7.9121 | 4.7473 / 4.780e-06 | 5.7691 | 9 / 5 (5%) |
| FINANCING_4_DAY_STRESS/pullback | pullback | 2437.1100 | 2857.3531 | 28.5735 | 5.6768 | 5.2186 | 0.1219 / 3.1748 | 14.1921 | 8.5152 / 7.173e-07 | 2.9970 | 0 / 0 (5%) |
| OPTIMISTIC_MARGIN_2_5_PERCENT/pullback | pullback | 1358.7000 | 1592.9874 | 15.9299 | 3.1649 | 4.6794 | 0.0679 / 0.0000 | 7.9121 | 4.7473 / 4.780e-06 | 5.7691 | 9 / 9 (2.5%) |
| CONSERVATIVE_1_DAY/mean_reversion | mean_reversion | 1662.8500 | 1920.8079 | 19.2081 | 3.6321 | 4.8314 | 0.0831 / 0.5336 | 9.0802 | 5.4481 / 6.519e-06 | 4.7243 | 1 / 0 (5%) |
| ARCHIVE_SPREAD_STRESS/mean_reversion | mean_reversion | 3790.3100 | 4380.8592 | 43.8086 | 8.2790 | 11.0121 | 0.1895 / 1.2169 | 20.6975 | 12.4185 / 9.033e-06 | 1.8067 | 0 / 0 (5%) |
| OPTIMISTIC_NO_FINANCING/mean_reversion | mean_reversion | 1467.1500 | 1694.7490 | 16.9475 | 3.2046 | 4.7336 | 0.0734 / 0.0000 | 8.0116 | 4.8069 / 1.132e-05 | 5.4174 | 1 / 1 (5%) |
| FINANCING_4_DAY_STRESS/mean_reversion | mean_reversion | 2772.1900 | 3202.2398 | 32.0224 | 6.0552 | 5.3861 | 0.1386 / 3.5580 | 15.1379 | 9.0828 / 4.599e-06 | 2.6450 | 0 / 0 (5%) |
| OPTIMISTIC_MARGIN_2_5_PERCENT/mean_reversion | mean_reversion | 1467.1500 | 1694.7490 | 16.9475 | 3.2046 | 4.7336 | 0.0734 / 0.0000 | 8.0116 | 4.8069 / 1.132e-05 | 5.4174 | 1 / 1 (2.5%) |

El mínimo cubre costos por un excedente infinitesimal a causa del paso de cantidad. No acredita beneficio razonable, muestra suficiente, permisos ni ejecución. La oportunidad mínima financiada, si existe, y cada señal/versión exacta están en JSON. Todas siguen executionAuthorized=false.

### Umbrales en validación exclusivamente

| Costos / estrategia | Señales elegibles | Menor exposición de target positivo | Riesgo a ese umbral USD | Umbrales ≤20×/≤US15 | Financiados al margen supuesto |
|---|---:|---:|---:|---:|---:|
| CONSERVATIVE_1_DAY/trend | 20 | 31.8689 | 10.7183 | 0 | 0 (5%) |
| ARCHIVE_SPREAD_STRESS/trend | 20 | 620.9278 | 208.7088 | 0 | 0 (5%) |
| OPTIMISTIC_NO_FINANCING/trend | 20 | 26.0940 | 8.7760 | 0 | 0 (5%) |
| FINANCING_4_DAY_STRESS/trend | 20 | 94.8299 | 31.8936 | 0 | 0 (5%) |
| OPTIMISTIC_MARGIN_2_5_PERCENT/trend | 20 | 26.0940 | 8.7760 | 0 | 0 (2.5%) |
| CONSERVATIVE_1_DAY/pullback | 266 | 21.3859 | 9.3928 | 0 | 0 (5%) |
| ARCHIVE_SPREAD_STRESS/pullback | 266 | 59.3176 | 26.0370 | 0 | 0 (5%) |
| OPTIMISTIC_NO_FINANCING/pullback | 266 | 18.6205 | 8.1782 | 3 | 0 (5%) |
| FINANCING_4_DAY_STRESS/pullback | 266 | 38.5703 | 16.9403 | 0 | 0 (5%) |
| OPTIMISTIC_MARGIN_2_5_PERCENT/pullback | 266 | 18.6205 | 8.1782 | 3 | 3 (2.5%) |
| CONSERVATIVE_1_DAY/mean_reversion | 6 | 37.1343 | 11.3886 | 0 | 0 (5%) |
| ARCHIVE_SPREAD_STRESS/mean_reversion | 6 | n/a | n/a | 0 | 0 (5%) |
| OPTIMISTIC_NO_FINANCING/mean_reversion | 6 | 29.5214 | 9.0538 | 0 | 0 (5%) |
| FINANCING_4_DAY_STRESS/mean_reversion | 6 | 164.0424 | 50.3095 | 0 | 0 (5%) |
| OPTIMISTIC_MARGIN_2_5_PERCENT/mean_reversion | 6 | 29.5214 | 9.0538 | 0 | 0 (2.5%) |

## Margen de capacidad por exposición (sin costos ni reserva de pérdida)

| Exposición | Notional capacidad USD | Margen hipotético 2.5% | 5% | 10% | 20% | Sin préstamo 100% |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1× | 100 | 2.5 | 5 | 10 | 20 | 100 |
| 2× | 200 | 5.0 | 10 | 20 | 40 | 200 |
| 5× | 500 | 12.5 | 25 | 50 | 100 | 500 |
| 10× | 1000 | 25.0 | 50 | 100 | 200 | 1000 |
| 15× | 1500 | 37.5 | 75 | 150 | 300 | 1500 |
| 20× | 2000 | 50.0 | 100 | 200 | 400 | 2000 |

La tabla usa equity inicial US$100. Durante la simulación, riesgo porcentual y exposición se calculan sobre equity virtual actual; las ganancias aumentan equity, pero no restauran pérdidas consumidas. Se agregan comisión, spread, slippage, gap y pérdida al stop. A 20×, 5% consume US$100 antes de esas reservas: el tamaño efectivo debe reducirse. El CSV contiene margen inicial/mantenimiento y sensibilidad para las cantidades realmente admitidas. No se utiliza la capacidad de compra ficticia de IBKR.

## Backtesting cronológico con política diaria

America/Santo_Domingo; una posición y bloqueo hasta resultado final. Ganancias permiten buscar otra señal; primera pérdida neta o break-even bloquea entradas hasta el día siguiente. NO_TRADE no cuenta. Pérdidas acumuladas US$20 no se restauran con beneficios. La cuenta continua atraviesa desarrollo/validación sin reiniciarse.

Celdas: operaciones admitidas / P&L neto USD. Cada celda es un experimento independiente, no una cartera. Rechazos, fees, spread, slippage, financiación, riesgo, DD, primera pérdida y todas las particiones figuran en CSV/JSON.

### Resultado continuo observado

| Estrategia / costos / riesgo % | Trades / rechazadas | EUR | Margen inicial / al stop USD | Riesgo reservado USD | Bruto / neto USD | Comisión / spread / slippage / financiación USD | Win % / PF / EV | DD intrabar % | Días detenidos |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| pullback / CONSERVATIVE_1_DAY / 9 (20×) | 1 / 761 | 1549.7400 | 90.8485 / 91.0328 | 8.9669 | -3.6099 / -8.3952 | 4.0000 / 0.0775 / 0.6974 / 0.0105 | 0.0000 / 0.0000 / -8.3952 | 8.3952 | 1 |
| pullback / OPTIMISTIC_NO_FINANCING / 8 (20×) | 1 / 761 | 1389.2100 | 81.4379 / 81.6032 | 8.0000 | -3.2359 / -7.9305 | 4.0000 / 0.0695 / 0.6251 / 0.0000 | 0.0000 / 0.0000 / -7.9305 | 7.9305 | 1 |
| pullback / OPTIMISTIC_NO_FINANCING / 9 (20×) | 1 / 761 | 1561.6000 | 91.6905 / 91.8585 | 8.1409 | -1.2102 / -5.9910 | 4.0000 / 0.0781 / 0.7027 / 0.0000 | 0.0000 / 0.0000 / -5.9910 | 7.8572 | 1 |
| pullback / OPTIMISTIC_MARGIN_2_5_PERCENT / 8 (20×) | 1 / 761 | 1389.2100 | 40.7190 / 40.8016 | 8.0000 | -3.2359 / -7.9305 | 4.0000 / 0.0695 / 0.6251 / 0.0000 | 0.0000 / 0.0000 / -7.9305 | 7.9305 | 1 |
| pullback / OPTIMISTIC_MARGIN_2_5_PERCENT / 9 (20×) | 2 / 760 | 1682.4550 | 50.0000 / 50.0916 | 8.5162 | 3.6253 / -6.0572 | 8.0000 / 0.1682 / 1.5142 / 0.0000 | 50.0000 / 0.0185 / -3.0286 | 11.8997 | 1 |
| mean_reversion / OPTIMISTIC_NO_FINANCING / 9 (20×) | 1 / 22 | 1584.0900 | 91.4915 / 91.6685 | 8.3313 | -3.4601 / -8.2521 | 4.0000 / 0.0792 / 0.7128 / 0.0000 | 0.0000 / 0.0000 / -8.2521 | 8.2521 | 1 |
| mean_reversion / OPTIMISTIC_MARGIN_2_5_PERCENT / 9 (20×) | 1 / 22 | 1731.4000 | 49.9998 / 50.0965 | 8.7341 | -3.7818 / -8.6475 | 4.0000 / 0.0866 / 0.7791 / 0.0000 | 0.0000 / 0.0000 / -8.6475 | 8.6475 | 1 |

Se muestran una vez los resultados idénticos entre riesgos; cada celda del barrido y cada trade están disponibles completos.

En la base, pullback desde riesgo 9% realiza SELL de 1549.7400 EUR en 2026-04-21T19:45:00+00:00, cierra por STOP y registra neto US$-8.3952. Margen al stop + riesgo reservado US$99.99976: colchón adicional US$0.00024. La admisión histórica 1/762 (0.131%) no es una probabilidad de fill.

Lados de entrada admitidos en el modelo: ['SELL']. El adapter StrategyPaper vigente acepta únicamente BUY y cierre SELL del inventario propio; entradas short SELL **no son ejecutables con el transporte protegido actual**. La investigación conserva ambos lados originales de V1, sin habilitar SELL independiente.

En la base 5% de margen y reserva de un día, validación y los tres folds fuera de muestra tienen cero admisiones. El quinto escenario favorable se presenta por separado abajo; no verifica la tasa real IBKR. Los resultados continuos no prueban rentabilidad ni el objetivo >80%.

### continuous_six_months: trend, CONSERVATIVE_1_DAY

| Riesgo % | 1× | 2× | 5× | 10× | 15× | 20× |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 2 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 3 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 4 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 5 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 6 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 7 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 7.5 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 8 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 9 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 10 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 11 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 12 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 12.5 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 13 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 14 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 15 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |

### continuous_six_months: pullback, CONSERVATIVE_1_DAY

| Riesgo % | 1× | 2× | 5× | 10× | 15× | 20× |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 2 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 3 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 4 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 5 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 6 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 7 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 7.5 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 8 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 9 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 1 / -8.3952 |
| 10 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 1 / -8.3952 |
| 11 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 1 / -8.3952 |
| 12 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 1 / -8.3952 |
| 12.5 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 1 / -8.3952 |
| 13 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 1 / -8.3952 |
| 14 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 1 / -8.3952 |
| 15 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 1 / -8.3952 |

### continuous_six_months: mean_reversion, CONSERVATIVE_1_DAY

| Riesgo % | 1× | 2× | 5× | 10× | 15× | 20× |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 2 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 3 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 4 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 5 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 6 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 7 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 7.5 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 8 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 9 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 10 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 11 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 12 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 12.5 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 13 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 14 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 15 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |

### validation: trend, CONSERVATIVE_1_DAY

| Riesgo % | 1× | 2× | 5× | 10× | 15× | 20× |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 2 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 3 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 4 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 5 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 6 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 7 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 7.5 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 8 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 9 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 10 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 11 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 12 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 12.5 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 13 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 14 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 15 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |

### validation: pullback, CONSERVATIVE_1_DAY

| Riesgo % | 1× | 2× | 5× | 10× | 15× | 20× |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 2 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 3 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 4 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 5 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 6 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 7 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 7.5 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 8 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 9 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 10 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 11 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 12 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 12.5 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 13 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 14 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 15 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |

### validation: mean_reversion, CONSERVATIVE_1_DAY

| Riesgo % | 1× | 2× | 5× | 10× | 15× | 20× |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 2 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 3 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 4 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 5 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 6 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 7 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 7.5 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 8 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 9 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 10 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 11 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 12 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 12.5 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 13 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 14 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |
| 15 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 | 0 / 0.0000 |

## Estadística y robustez: todas las configuraciones con trades en validación

| Estrategia / costos | Expo / riesgo % | n / días | Win % | Win CI familia | Ganancia / pérdida media | PF / EV | Neto / fees / financiación | DD intrabar % | Días primera pérdida | Brechas riesgo / financiación |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|
| pullback / OPTIMISTIC_MARGIN_2_5_PERCENT | 20 / 9 | 2 / 2 | 50.0000 | [0.026678730676028883, 0.9733212693239711] | 0.3849 / 8.2358 | 0.0467 / -3.9255 | -7.8509 / 8.0000 / 0.0000 | 8.2042 | 1 | 0 / 0 |
| pullback / OPTIMISTIC_MARGIN_2_5_PERCENT | 20 / 10 | 2 / 2 | 50.0000 | [0.026678730676028883, 0.9733212693239711] | 0.3849 / 8.2358 | 0.0467 / -3.9255 | -7.8509 / 8.0000 / 0.0000 | 8.2042 | 1 | 0 / 0 |
| pullback / OPTIMISTIC_MARGIN_2_5_PERCENT | 20 / 11 | 2 / 2 | 50.0000 | [0.026678730676028883, 0.9733212693239711] | 0.3849 / 8.2358 | 0.0467 / -3.9255 | -7.8509 / 8.0000 / 0.0000 | 8.2042 | 1 | 0 / 0 |
| pullback / OPTIMISTIC_MARGIN_2_5_PERCENT | 20 / 12 | 2 / 2 | 50.0000 | [0.026678730676028883, 0.9733212693239711] | 0.3849 / 8.2358 | 0.0467 / -3.9255 | -7.8509 / 8.0000 / 0.0000 | 8.2042 | 1 | 0 / 0 |
| pullback / OPTIMISTIC_MARGIN_2_5_PERCENT | 20 / 12.5 | 2 / 2 | 50.0000 | [0.026678730676028883, 0.9733212693239711] | 0.3849 / 8.2358 | 0.0467 / -3.9255 | -7.8509 / 8.0000 / 0.0000 | 8.2042 | 1 | 0 / 0 |
| pullback / OPTIMISTIC_MARGIN_2_5_PERCENT | 20 / 13 | 2 / 2 | 50.0000 | [0.026678730676028883, 0.9733212693239711] | 0.3849 / 8.2358 | 0.0467 / -3.9255 | -7.8509 / 8.0000 / 0.0000 | 8.2042 | 1 | 0 / 0 |
| pullback / OPTIMISTIC_MARGIN_2_5_PERCENT | 20 / 14 | 2 / 2 | 50.0000 | [0.026678730676028883, 0.9733212693239711] | 0.3849 / 8.2358 | 0.0467 / -3.9255 | -7.8509 / 8.0000 / 0.0000 | 8.2042 | 1 | 0 / 0 |
| pullback / OPTIMISTIC_MARGIN_2_5_PERCENT | 20 / 15 | 2 / 2 | 50.0000 | [0.026678730676028883, 0.9733212693239711] | 0.3849 / 8.2358 | 0.0467 / -3.9255 | -7.8509 / 8.0000 / 0.0000 | 8.2042 | 1 | 0 / 0 |

El caso favorable que admite trades OOS (OPTIMISTIC_MARGIN_2_5_PERCENT, pullback, 20×) tiene n=2, win rate 50%, neto US$-7.8509, PF 0.0467 y expectativa US$-3.9255. Wilson familiar: [0.026678730676028883, 0.9733212693239711]. Sin cinco días de trades no se estima bootstrap. El 2.5% de margen y financiación cero siguen siendo hipótesis favorables, no condiciones demostradas IBKR.

Usando solo esas medias observadas, la tasa de equilibrio sería 95.54%: superar 80% no bastaría con ese reparto de ganancias/pérdidas. Con n=2 esto es una identidad descriptiva, no un pronóstico ni una estimación robusta.

La selección exige n≥100 OOS, ≥30 días, tres folds netamente positivos, win rate >80% y límites inferiores ajustados/bootstrap >80%, expectativa y límite inferior >0, PF>1, DD intrabar≤20%, margen/permisos comprobados y nueva muestra nunca examinada. Wilson supone IID; bootstrap por bloques de cinco días es aproximado. La validación ya se examinó antes, y las 1,530 comparaciones se corrigen conjuntamente; ningún resultado puntual alto se fuerza a aprobación. Métodos: [Wilson/NIST](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm) y [Bonferroni/NIST](https://www.itl.nist.gov/div898/handbook/prc/section4/prc473.htm).

## Probabilidad de filtros y agotamiento de capital

Con emergencia activa, permiso PaperAuto ausente y veto económico, ninguna entrada puede superar los gates actuales: 0 por condición determinista. Para una futura sesión autorizada la probabilidad de aceptación/fill IBKR es UNKNOWN; el porcentaje histórico admitido por el modelo no la estima. Tampoco existe muestra suficiente para inferir probabilidad de ruina.

El presupuesto acumulado de US$20 suspende nuevas entradas; no garantiza pérdidas máximas si falla el stop. Un gap adverso 1%/2%/5%, sin stop efectivo, genera pérdidas antes de costos de US$20/40/100 a exposición 20×. Tabla de estrés completa y flags de agotamiento/brechas en JSON. La política de primera pérdida reduce nuevas entradas; no protege por sí sola la posición abierta.

## Alternativas de menor costo relativo

Screen de tarifas con notional ilustrativo US$90, sin señal ni precio real; las tarifas de cuenta y los costos variables no están verificados. No se trasladan V1 Forex a estos instrumentos ni se implementan estrategias nuevas.

| Instrumento | Comisión ida/vuelta ilustrativa USD | Movimiento bruto mínimo para solo comisión % | Mínimos / restricciones |
|---|---:|---:|---|
| EURUSD_CASH | 4.0000 | 4.4444 | 0.01 EUR metadata; odd lot, préstamo/permiso Cash Forex desconocidos |
| US_WHOLE_SHARES_TIERED | 0.7000 | 0.7778 | Una acción/cuota; precio debe caber en cash. Requiere stock permissions, USD liquidado, market data y adapter nuevo |
| US_WHOLE_SHARES_FIXED | 1.8000 | 2.0000 | Una acción/cuota; USD liquidado; same-day reutilización del cash no asumida |
| US_FRACTIONAL | 1.8000 | 2.0000 | Marketing desde USD1; incremento, SMART, API/stop/bracket y permisos por contrato por verificar |
| SPOT_CRYPTO | 1.8000 | 2.0000 | Proveedor/residencia, mínimo e incremento por contrato, Paper/API y protección por verificar |
| US_LONG_OPTION | 2.0000 | 2.2222 | Un contrato; prima, multiplicador, spread, griegas/expiración. Riesgo total prima+costos, sin ventas descubiertas |

Las [acciones/ETF estadounidenses completos](https://www.interactivebrokers.com/en/pricing/commissions-stocks.php) tienen mínimos publicados USD0.35 Tiered o USD1 Fixed, cap 1% por lado; fractions tienen su propia regla mayor de 1% o USD0.01. El ejemplo supone pocas acciones y excluye cargos externos. Lite no se asume disponible para esta cuenta.

Las [fracciones](https://www.interactivebrokers.com/en/trading/fractional-trading.php) caben por importe, pero [errores API 10242–10249](https://www.interactivebrokers.com/docs/tws-api/doc/error-handling/error-codes) documentan restricciones de modificación, colocación, SMART, instrumentos y permisos; no se presume que una orden protectora fraccional funcione.

[Crypto IBKR](https://www.interactivebrokers.com/en/trading/products-cryptocurrencies.php) publica mínimo USD1.75 con cap 1% por orden; depende de proveedor y residencia. [Opciones](https://www.interactivebrokers.com/en/pricing/commissions-options.php) publican mínimo USD1 por orden más cargos externos. Menor comisión no prueba una ventaja estadística ni soporte Paper de este proyecto.

El [micro EUR/USD M6E](https://www.cmegroup.com/markets/microsuite/fx.html?trk=test) representa 12,500 EUR por contrato entero: con el midpoint archivado ≈1.12 supera US$14,000/140×, fuera del techo investigado 20×. Margen actual y permiso futuros no están confirmados. No reduce automáticamente la barrera de US$100.

Para instrumentos en cash se requiere saldo liquidado; vender con beneficio no vuelve utilizable automáticamente todo el efectivo. [Restricciones de acciones/margen](https://www.interactivebrokers.com/en/trading/margin-stocks.php?ex=us&hm=us&pm=1&rgt=1&rsk=0&rst=101004100808) y reglas de day trading dependen de entidad, residencia, plan y normativa vigente; no se infieren de la cuenta Paper grande.

Prioridad de investigación siguiente: acciones/ETF completos en USD con precio y liquidez compatibles, plan Tiered y evidencia auténtica nueva. Solo es una candidatura para investigar costos y datos: **ninguna configuración alternativa está demostrada viable ni autorizada**.

Ejemplo concreto para esa siguiente investigación: [SCHX, Schwab U.S. Large-Cap ETF](https://www.schwabassetmanagement.com/products/schx), NYSE Arca. El emisor publica midpoint US$30.03 al 2026-09-09 y spread mediano de 30 días 0.03%; esos datos son antiguos, no BID/ASK actuales de IBKR. Tres cuotas a ese precio serían US$90.09 y comisión Tiered ilustrativa US$0.70 por ciclo antes de cargos externos/spread/slippage. Cabe por capital y evita fracciones; no demuestra señal rentable, permiso de cuenta, protección ni disponibilidad efectiva del contrato en Paper. No se usan sus retornos de inversión como resultados de una estrategia TradingAgent.

## Condiciones que impiden operar

- Verificadas/preservadas: EmergencyStop activo, PaperAuto no concedido, veto de evidencia económica, exposición operativa 1× y riesgo operativo protegido sin cambios.
- Investigación: Trend requiere exposición superior a 20× en todos los escenarios de costos considerados; muestras positivas potenciales de las otras V1 no bastan para certificar 80%/expectativa/robustez.
- Pendientes bloqueantes: tasa efectiva de margen/maintenance, entidad y permisos de préstamo, odd lot, cantidades, tick/protección/short, comisiones por tamaño y financiación real, BID/ASK y mercado frescos.
- Alternativas: sin adapter aprobado, estrategia/dataset/evidencia fuera de muestra, reconciliación y protección específicas. No están en la autorización/allowlist existente.
- No eliminar estos controles para convertir una simulación condicional en permiso. No promover ninguna V1 ni activar PaperAuto. Live permanece bloqueado.

## Limitaciones

- Virtual allocation USD100 and persistent consumed losses USD20; no broker buying power is used.
- Initial/maintenance 5% is a hypothesis, NOT verified IBKR EURUSD margin. Loss to stop and costs also need collateral.
- Full-notional ACT/360 financing at 10% is a scenario, not broker accrual reconstruction. One-day/four-day reserves do not change V1 exits.
- Estimated financing uses elapsed calendar days. Actual broker settlement, interest tiers, minimum financing, rollover and fee changes remain unknown.
- Current observed Paper fees are replayed counterfactually on historical MIDPOINT candles. Limit fill probability and liquidity are not reconstructed.
- One-tick spread is an estimate; archive maximum spread and four-day financing are disclosed stress cases.
- Reported model admission shares are deterministic historical frequencies, not probabilities of IBKR acceptance or fill.
- Current execution cannot pass emergency/no-authorization/economic-evidence gates. Future execution probability and capital ruin probability are unknown.
- Existing validation was examined before this study. It is retrospective OOS replay, not a fresh untouched confirmation.
- 1530 validation comparisons, Bonferroni-adjusted Wilson and moving-block intervals; no parameters optimized.
- The favorable 2.5% margin case was added after initial 5% results to check sensitivity. This is exploratory, not preregistered confirmation; family correction does not erase adaptive selection bias.
- Expanding past-only folds with 15-minute separation; folds start independent USD100/USD20, and results cannot be summed.
- Continuous six-month run does not replenish losses or restart equity at validation boundary.
- Shared V1 stop/target/EMA/multiframe/next-open/gap semantics preserved. Actual broker protection, tick rounding and short entry support remain unverified.
- All quantities under the 20x ceiling are odd lot. Contract minimum 0.01/increment0.01 is metadata, not verified permission for every size.
- Cash settlement may block a second same-day trade despite a first net winner. Daily policy never overrides cash/permission gates.
- Stops cannot guarantee loss caps under gaps or disconnection. A 20x position can consume USD100 on a 5% adverse gap before fees.
- Alternative tariff calculations do not imply a strategy, current executable quotes or net profitability. No alternative dataset/backtest was created.

## Versiones exactas

- trend: `9860cd16f4f43d38ca7c29f161aea82e17dea100da48bb78259457cc31133211`; config `1e2784bd53f45ab47445bfeef2692329adf1ef4e0000e40ce469f2a98ce5349a`.
- pullback: `b622e9522da52b2aec358a4623d671b5398990d00e812a8fb81e2c71d155a9d3`; config `1e2784bd53f45ab47445bfeef2692329adf1ef4e0000e40ce469f2a98ce5349a`.
- mean_reversion: `fcd256a67a14d26c3e58cf73e0906713c09ed50aef69f67b99e92f52fcac80c2`; config `1e2784bd53f45ab47445bfeef2692329adf1ef4e0000e40ce469f2a98ce5349a`.

## Reproducción sin órdenes

```powershell
dotnet build TradingAgent.sln -m:1
$env:PYTHONPATH = "python"
.venv/Scripts/python.exe -m trading_agent.exposure_economic_research --root .
```

Resultados completos: `artifacts/research/exposure-alternatives/report.json`, `comparison.csv` y `minimum-opportunities.json`. Logs/regresiones en `artifacts/test-results/exposure-alternatives/`.

## Verificación y archivos de esta entrega

2026-10-06T08:04:25.636044+00:00: **690 pruebas aprobadas** (450 Python + 240 C#); cero fallos y cero omisiones. Build cero warnings/errores y compileall correcto. PostgreSQL desechable 55432 iniciado/detenido; base Paper sin utilizar. Conservadas las 665 anteriores; 25 nuevas (11 Python, 14 C#).

Pruebas nuevas: exposición/costos/margen dentro del capital virtual, financiaciones y excesos, gaps con agotamiento sin ocultar pérdidas, límites de ámbito, redondeo estricto del umbral, tipos de costo, corrección estadística, frontera real del ejecutable y persistencia de los gates anteriores.

Los 19 controles/archivos protegidos verificados permanecen idénticos. AccountBinding, emergencia, autorizaciones y fuentes operativas sin cambios. No hubo conexión IBKR ni órdenes; no se certificaron condiciones nuevas de cuenta.

Código/documentación agregado o modificado:

- `src/TradingAgent.ResearchLab/ExposureStudy.cs`
- `src/TradingAgent.ResearchLab/ProgressiveRisk.cs`
- `src/TradingAgent.ResearchLab/Program.cs`
- `python/trading_agent/progressive_risk_research.py`
- `python/trading_agent/exposure_economic_research.py`
- `tests/TradingAgent.Tests/ExposureStudyTests.cs`
- `python/tests/test_exposure_economic_research.py`
- `docs/architecture/exposure-alternatives-research.md`
- `docs/architecture/paper-execution-laboratory.md`
