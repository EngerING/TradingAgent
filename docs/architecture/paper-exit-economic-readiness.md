# Salidas originales y barrido económico de Paper

Preparación del 2026-10-05: StrategyPaper bloqueado; emergencia activa; autorización anterior vencida; exposición activa 1×; cero órdenes y solicitudes what-if; Live bloqueado.

## Equivalencia

`ResearchExitSemantics` centraliza las salidas originales D/D.1, sin cambiar parámetros: stop/target ATR; stop primero en velas ambiguas; gaps adversos al stop al precio de apertura; target sin mejora por gap; señales originales de cruce EMA contrario e invalidación multitemporal; salida de regla en siguiente apertura con la prioridad original. `StrategyPaperExitAdapter` comparte el evaluador.

El runner incorpora `RESEARCH_D_V1`: evalúa salidas mientras existe inventario propio, utiliza `research_analysis` existente y persiste la decisión antes de modificar únicamente su hijo TP, conservando stop/OCA, identidad y conciliación. Registra observación y retraso. No reemplaza fills reales por precios de modelo. Diagnostics conserva su cierre por tiempo y ledger independiente.

**Equivalencia del modelo comprobada; `STRATEGY_EXIT_SEMANTICS_NOT_EQUIVALENT` continúa activo para ejecución.** El informe está vinculado por SHA256 al código/tests y deja `execution_equivalence_verified=false`. El guard no acepta solamente una prueba del modelo.

- OHLC de investigación es MIDPOINT; disparadores nativos stop/target y secuencia OCA de IBKR no están certificados como equivalentes. No se reescribe un fill para imponer retrospectivamente stop-first.
- ATR original puede producir precios fuera del tick 0.00005. El modo exacto rechaza `STRATEGY_PRICE_GRID_NOT_EQUIVALENT`; no redondea las reglas originales.
- Modelo: precio exacto de apertura. Runner: primera quote conciliada disponible después de la apertura, con retraso declarado.
- Investigación contempla BUY/SELL; transporte protegido actual abre únicamente BUY. Las tres operaciones positivas de Trend en validación a 50× son SELL.

El cierre ordinario a 60–300 segundos contradice la estrategia original. Únicamente el nuevo modo, aún bloqueado, omite ese time exit; expiración y emergencia mantienen cierre protegido. No se modificó ninguna autorización existente.

## Evidencia económica

Se consultaron versiones V1 reales en PostgreSQL, sin crear versiones: Trend `9860cd16f4f43d38ca7c29f161aea82e17dea100da48bb78259457cc31133211`; Pullback `b622e9522da52b2aec358a4623d671b5398990d00e812a8fb81e2c71d155a9d3`; Mean Reversion `fcd256a67a14d26c3e58cf73e0906713c09ed50aef69f67b99e92f52fcac80c2`. Configuración `1e2784bd53f45ab47445bfeef2692329adf1ef4e0000e40ce469f2a98ce5349a`, parámetros `5e895fce513df2b084622e4a4d136c1af4a44e342b2e607486c10aba9f3e7bac`.

Archive auténtico IBKR: 2026-04-03 a 2026-10-03, validación desde 2026-08-03. Receipts, hashes, identidad, sesiones y configuración verificados. Se recalcularon señales/salidas y compararon con el artifact congelado. Dataset `bb95c4d5394704af60d7c4ccde15710f504daddf1463f3b9ac44c68f39e87c8c`.

54 escenarios: tres estrategias × seis exposiciones × desarrollo/validación/recorrido continuo. Las particiones mantienen las asignaciones independientes del protocolo original; el recorrido continuo nunca restaura su presupuesto al empezar validación. No sumar P&L ni trades de escenarios independientes.

RiskEngine dimensiona desde US$100, riesgo `min(10% equity, US$10, pérdida acumulada restante)`, pérdidas acumuladas US$20, una posición, costos incluidos y ganancias que no reponen pérdidas consumidas. Exposiciones 1/5/10/20/30/50× son hipótesis offline sin permiso de ejecución ni margen supuesto.

Costos estimados: US$2 por cada lado; spread 0.00005; slippage ida/vuelta 0.00045; gap reservado 0.00005 USD/EUR. Spread observado al corte: 0.00001; el barrido conserva la estimación superior. La [tarifa pública IBKR](https://www.interactivebrokers.com/en/pricing/commissions-spot-currencies.php) no certifica costos efectivos de esta cuenta. Gap reservado entra en riesgo/target conservador, no como comisión realizada; un gap puede superar la reserva.

Todas las métricas solicitadas y las 54 filas están en [paper-strategy-economic-sweep.md](paper-strategy-economic-sweep.md), `artifacts/paper-lab/economic-sweep.csv` y `economic-sweep.json`. JSON conserva mínimos por señal, cada primera pérdida diaria, trades, precios de modelo y rechazos. Sin trades las estadísticas son n/a; PF sin pérdidas es n/a.

| Estrategia | Lado del mínimo histórico | EUR | Nominal USD | Exposición | Riesgo USD | Target neto conservador USD |
|---|---|---:|---:|---:|---:|---:|
| Trend V1 | BUY | 1864.82 | 2147.80 | 21.48× | 8.38 | 0.00001293 |
| Pullback V1 | SELL | 1358.70 | 1592.99 | 15.93× | 7.91 | 0.00000478 |
| Mean Reversion V1 | SELL | 1467.15 | 1694.75 | 16.95× | 8.01 | 0.00001132 |

Estos umbrales matemáticos casi break-even pertenecen a señales históricas diferentes; no son tamaños recomendados hoy. Restringiendo a BUY: Trend 21.48× / 1864.82 EUR; Pullback 19.17× / 1675.40 EUR; Mean Reversion 25.58× / 2216.04 EUR. Margen siempre desconocido.

Ninguna estrategia admite entradas hasta 10×. A 50×, validación Trend tiene tres SELL y US$2.24 netos; recorrido continuo: tres operaciones, US$−16.02. Pullback/Mean Reversion son negativos en validación y recorrido continuo. Tres ganancias no acreditan validación suficiente. Ninguna recibe promoción `PAPER_EXPERIMENTAL`; el draft anterior queda `NOT_ELIGIBLE_NO_PROMOTION_PLAN_ISSUED`.

Recomendación operativa: ninguna estrategia; 0 EUR y riesgo US$0. Los mínimos superarían también guards existentes de autorización 100 EUR / US$250 y evidencia de cuenta equivalente de máximo 1×. No se cambiaron estos límites. Ninguna conclusión de rentabilidad, viabilidad con US$100 reales o aprobación Live.

## IBKR y Diagnostics

Inspección de solo lectura iniciada 2026-10-05T14:11:04.026524Z: identidad Paper exacta confirmada, sufijo público 3784; consultas completas; posiciones/órdenes vacías; journal sin reservas/pérdidas; equity StrategyPaper US$100. EUR ausente permanece `UNKNOWN/null`; excepción elegible y `NOT_REGISTERED`.

Calendario auténtico SCHEDULE + contract hours, 34 intervalos UTC, cobertura 2026-08-24–2026-10-09. Quote LIVE OPEN recibida 14:11:54.336387Z: BID 1.11936 / ASK 1.11937. Datos del corte, no reutilizables para una orden futura. Calendario/quote desconocidos bloquean entrada.

Contrato 12087792, tick 0.00005, metadata mínimo/incremento 0.01 EUR. Tamaños económicos menores al [mínimo IDEALPRO publicado de 20.000 EUR](https://investors.interactivebrokers.com/en/?f=5479): tratamiento odd lot. Desconocidos: tarifas de cuenta de ambos lados, routing/mínimo realmente ejecutable odd lot, permisos de venta EUR, margen inicial/mantenimiento de la orden, fill/slippage y disparadores stop/OCA. Margen plano cero no acredita una posición futura.

ExecutionDiagnostics preparado técnicamente: un ciclo hasta 100 EUR, nominal US$150, presupuesto US$10 e inicio de cierre a 60 segundos. **No ejecutable ahora:** autorización vencida, emergencia activa y excepción EUR ausente. Requiere nueva autorización y revisión protegida del propietario. Tras primer fill vuelve conciliación estricta. Puede obtener fills, comisiones simuladas y slippage; registra snapshots de margen si IBKR los entrega, sin garantizar una tasa incremental ni certificar todos los odd lots con una sola observación.

No se ejecutó Authorize, Review, Revoke, AuthorizeEurAbsence ni Run. Hashes autorización/emergencia idénticos antes/después. Transporte Diagnose bloquea órdenes incluso por Protobuf. PostgreSQL reales y de prueba iniciados quedaron detenidos.

## Pruebas

445 aprobadas: 194 C# + 251 Python, sin fallos ni omitidas; 39 nuevas. Equivalencia BUY/SELL con secuencias sintéticas y dataset auténtico para tres estrategias; prioridad regla/gap/stop/target; causalidad; riesgo/costos/mínimos; separación offline; bloqueo de equivalencia/tick/Diagnostics; runner con inventario sin time exit artificial y modificación protegida de hijo OCA. Las salidas de seguridad del riesgo ordinario se excluyen de la comparación histórica de reglas de estrategia.

Regresiones existentes incluyen A/B/C/D, día UTC, reinicios, journal PostgreSQL, pérdidas irreversibles, fees pendientes, parciales, reservas, emergencia y Live. Transporte probado con fixtures; ningún fill real nuevo acredita TWS.

Build sin errores/advertencias, compileall, parser PowerShell y demo offline aprobados. Evidencias en `artifacts/test-results`: `paper-exit-sweep.trx`, `authentic-exit-equivalence.trx`, `paper-exit-sweep-python.log`, `research-exit-equivalence.json`, hashes protegidos antes/después. Reproducción offline: `PYTHONPATH=python` y `.venv\Scripts\python.exe -m trading_agent.paper_economic_sweep --root .`.
