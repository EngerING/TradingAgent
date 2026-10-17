# Tendencia V1: preparación PAPER_EXPERIMENTAL

Fecha: 2026-10-05. Se aplicó senior-software-engineer y se consultó Graphify primero. Su grafo anterior al laboratorio se contrastó con código, PostgreSQL y artifacts. No se renovó autorización, no se levantó emergencia, no se registró una excepción real y no se envió una orden. Live sigue bloqueado y exposición operativa máxima 1×.

## Identidad y plan de evidencia

StrategyVersion exacta recuperada por SELECT de PostgreSQL: `9860cd16f4f43d38ca7c29f161aea82e17dea100da48bb78259457cc31133211`.
StrategyId: `research-d-trend-1e2784bd53f4`; Name: Trend following; Version: 1; EUR/USD, marcos 15/60/240. No se insertó una versión ni aprobación SQL nueva. Se seleccionó la configuración final D.1, no las otras dos V1 históricas de distinto calendario/configuración.

StrategyEvidencePath exacto: `C:\Users\Enyer Payano\Desktop\Traiding Agent\artifacts\paper-lab\trend-v1-evidence.json`.

El archivo es un **plan de evidencia pendiente de aprobación**, exclusivamente para PAPER_EXPERIMENTAL y PAPER_EXPERIMENTAL_10_PERCENT. No es un permiso de ejecución. Authorize lo rechaza explícitamente con STRATEGY_EXIT_SEMANTICS_NOT_EQUIVALENT: el adaptador preparado usa bracket/tiempo y omite salidas V1 por cruce EMA opuesto e invalidación multitemporal. Además limita entradas a BUY; la investigación incluye BUY/SELL. Esa equivalencia debe resolverse/revisarse antes de promover V1. No se inventó otra versión para ocultar la diferencia.

ConfigHash: `1e2784bd53f45ab47445bfeef2692329adf1ef4e0000e40ce469f2a98ce5349a`. ParametersHash persistido: `5e895fce513df2b084622e4a4d136c1af4a44e342b2e607486c10aba9f3e7bac`. DatasetHash: `bb95c4d5394704af60d7c4ccde15710f504daddf1463f3b9ac44c68f39e87c8c`.

Se verificaron otra vez los hashes/procedencia de 76 respuestas auténticas del manifest local y el hash de sus originales contra D.1. Originales: 12.423 barras 15M, 3.138 1H, 915 4H. Período [2026-04-03T00:00:00Z, 2026-10-03T00:00:00Z): desarrollo hasta 3 de agosto, validación desde 3 de agosto. Parámetros congelados, sin optimización. Tendencia: 140 señales de desarrollo, 78 de validación, 218 total; ninguna operación admitida. No hay evidencia de rentabilidad, validación Live ni viabilidad con US$100 reales.

Fuente D.1: `artifacts/research/6dd3f0c7e256f1c86fdb397133513a2896ab57822250b0e2748ca1acd6e6ab40.extended.json`. Manifest: `.local/research-history/manifest.json`. Informe completo: `artifacts/paper-lab/trend-v1-readiness.json`. Los stopDistance/takeProfitDistance 0.00005 de la envoltura SQL son pisos; se usaron las distancias auténticas de señales ATR×2/ATR×3 documentadas en parametersJson.

## Excepción EUR

Inspección real desde 13:12:59 UTC. Identidad completa coincidente con el ancla protegida; solo sufijo 3784 en informes. Todas las consultas de cuenta/exposición finalizaron. Cero posiciones no cero y cero órdenes abiertas; journal inicial sin experiencias, reservas, pérdidas ni costos pendientes. Emergencia activa en journal/archivo y autorización vencida intacta. La API no reemplaza la atestación manual Paper de la sesión actual.

EUR permanece UNKNOWN/null, EUR_ROW_ABSENT. La evidencia inicial StrategyPaper cumple las condiciones para revisión excepcional, pero el permiso DPAPI está NOT_REGISTERED. No se convierte ausencia en cero ni se certifica automáticamente saldo EUR.

Se extendió la acción existente AuthorizeEurAbsence con -Mode StrategyPaper, StrategyVersion y StrategyEvidencePath. Alcance INITIAL_STRATEGY_PAPER_EUR_ABSENCE sellado por DPAPI, vinculado a cuenta completa, proceso TWS, versión, plan hash, sesión de revisión y una única sesión futura de ejecución. Vigencia ≤30 minutos, exposición 1×, riesgo 10, pérdidas acumuladas 20. Review -AllowAbsentEurStrategy y Authorize ... -AllowAbsentEurStrategy consumen el alcance, exclusivamente Paper. Registro separado de renovación/levantamiento de emergencia; ninguna acción sensible se ejecutó hoy.

Bookmarks de cantidad cero son admisibles en la ruta StrategyPaper; posiciones no cero, órdenes conflictivas, consultas incompletas, reservas o fees pendientes bloquean. La excepción se consume durablemente antes del intent. Tras el primer fill vuelve la conciliación estricta; reinicios u otra excepción no borran consumo. Cash EUR ausente después de un round trip no habilita otra entrada ni libera riesgo sin conciliación posterior. Diagnostics conserva su alcance anterior.

## Calendario IBKR

Cotización LIVE recibida a 2026-10-05T13:13:49.134598Z: BID 1.12030 / ASK 1.12032, mercado OPEN al corte. No se reutiliza para una futura orden. SCHEDULE de 30 días más contractDetails.tradingHours contienen 34 intervalos explícitos, cobertura UTC 2026-08-24–2026-10-09. Sesión vigente al corte: [2026-10-04T21:15:00Z, 2026-10-05T21:00:00Z); siguiente apertura recibida 21:15 UTC.

El runner usa sesiones recibidas de IBKR, nunca PROVISIONAL_REGULAR_TEMPLATE. Actualiza SCHEDULE/contract hours y solicita la quote después del calendario. Falta de cobertura, conflictos, DST incierto, CLOSED/UNKNOWN o quote no LIVE bloquean entradas. Conserva timestamps UTC; no extrapola semanas ni fabrica festivos. `artifacts/paper-lab/market-evidence.json` conserva sesiones y OHLC nativos actuales.

## Tamaños del RiskEngine, sin autorización

Estimaciones: US$2 apertura + US$2 cierre según [tarifa pública Tier I](https://www.interactivebrokers.com/en/pricing/commissions-spot-currencies.php), sin certificar tarifa efectiva de cuenta. Spread observado 0.00002; ASK límite se redondea a 1.12035, elevando el diferencial presupuestado a 0.00005. Slippage ida/vuelta estimado, no medido: 0.00045 USD/EUR; gap adverso 0.00005 USD/EUR. Estos supuestos pueden cambiar; no se registran como costos verificados.

ATR auténtico 15M del cierre 13:00 UTC: 0.0009186231219500883. Geometría actual según V1: stop 1.11845 y target 1.12315. **No existe una nueva señal válida de entrada al corte.** Los valores son neto condicionado a alcanzar target, no expectativa estadística. El time limit de 60–300 s puede cerrar antes; no prueba que ese target sea alcanzable en ese plazo.

### LATEST_ATR_GEOMETRY_NO_ENTRY_SIGNAL

Referencia: 2026-10-05T13:00:00+00:00; entrada diagnóstica 1.12035, stop 1.11845, target 1.12315. No elegible ahora.

| Escenario | EUR | Notional USD | Exposición | Stop sin costos USD | Costos USD | Riesgo total USD | Bruto target USD | Neto target USD | Margen máximo asequible |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| EXPOSURE_1X | 89.25 | 99.99 | 1.00× | 0.17 | 4.04 | 4.22 | 0.25 | -3.79249375 | 95.96% |
| CASH_COLLATERAL_1X | 85.64 | 95.95 | 0.96× | 0.16 | 4.04 | 4.21 | 0.24 | -3.80088700 | 100.00% |
| FIRST_STRICTLY_POSITIVE_TARGET | 1720.44 | 1927.49 | 19.27× | 3.23 | 4.86 | 8.17 | 4.86 | 0.00002300 | 4.94% |
| TARGET_NET_USD_1 | 2150.54 | 2409.36 | 24.09× | 4.03 | 5.08 | 9.22 | 6.08 | 1.00000550 | 3.94% |
| MAXIMUM_RISK_QUANTITY | 2474.22 | 2771.99 | 27.72× | 4.64 | 5.24 | 10.00 | 6.99 | 1.75256150 | 3.42% |

### LAST_ELIGIBLE_HISTORICAL_BUY

Referencia: 2026-09-10T02:30:00+00:00; entrada diagnóstica 1.12035, stop 1.11960, target 1.12140. No elegible ahora.

| Escenario | EUR | Notional USD | Exposición | Stop sin costos USD | Costos USD | Riesgo total USD | Bruto target USD | Neto target USD | Margen máximo asequible |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| EXPOSURE_1X | 89.25 | 99.99 | 1.00× | 0.06 | 4.04 | 4.11 | 0.10 | -3.94868125 | 95.96% |
| CASH_COLLATERAL_1X | 85.64 | 95.95 | 0.96× | 0.06 | 4.04 | 4.11 | 0.09 | -3.95075700 | 100.00% |
| FIRST_STRICTLY_POSITIVE_TARGET | 6956.53 | 7793.75 | 77.94× | 5.04 | 7.48 | 12.87 | 7.48 | 0.00000475 | 1.19% |
| TARGET_NET_USD_1 | 8695.66 | 9742.18 | 97.42× | 6.30 | 8.35 | 15.09 | 9.35 | 1.00000450 | 0.94% |
| MAXIMUM_RISK_QUANTITY | 4705.88 | 5272.23 | 52.72× | 3.41 | 6.35 | 10.00 | 5.06 | -1.29411900 | 1.78% |

La última BUY elegible histórica es del 2026-09-10T02:30:00Z. Para el diagnóstico se trasladaron solo sus distancias al BID/ASK del corte, sin reactivar esa señal. Con esa geometría subir exposición tampoco permite neto positivo dentro de riesgo US$10. Una señal nueva exige recalcular.

Todos los tamaños son odd lot, inferiores al [mínimo IDEALPRO publicado de 20.000 EUR](https://investors.interactivebrokers.com/en/?f=5479). Contrato Paper actual: mínimo e incremento 0.01 EUR, tick 0.00005. No prueban permisos/condiciones odd lot de cuenta real. InitMarginReq y MaintMarginReq actuales son cero por falta de exposición; no son tasas de una orden futura. Margen/eligibilidad/restricciones efectivos continúan no verificados; no se envió what-if.

La columna de margen máximo es un umbral calculado con US$100 menos costos; no una tasa concedida por IBKR. El escenario de US$1 neto con ATR actual necesita margen ≤3.94%; el máximo riesgo necesita ≤3.42%. Con colateral virtual al 100%, reservando costos, el techo de caja es 85.64 EUR, menor que los 89.25 EUR de exposición nominal. El millón de Paper no participa.

**Recomendación operativa del motor: 0 EUR / no entrada.** 2150.54 EUR / US$2409.36 / 24.09× ilustra condicionalmente US$1 neto al target con el ATR actual y costos indicados. No se recomienda autorizarlo sin señal nueva, límites decididos por el propietario, evidencia verificable y promoción correcta.

## Bloqueos y pruebas

Bloqueos: NO_FRESH_VALID_APPROVED_SIGNAL; NO_ECONOMIC_ENTRY_WITHIN_CURRENT_LIMITS; STRATEGY_EXIT_SEMANTICS_NOT_EQUIVALENT; EXECUTION_EVIDENCE_INCOMPLETE; EUR_EXCEPTION_NOT_REGISTERED; AUTHORIZATION_EXPIRED; EMERGENCY_STOP. Los guards adicionales de autorización conservan máximos 100 EUR y US$250 nominales, y time limit máximo 300 s. Una decisión futura de subir 1× requiere revisar explícitamente esos límites; no se modificaron.

WIN_TO_CONTINUE / FIRST_LOSS_STOPS_DAY permanece: entrada inicial solo con señal válida; neto final estrictamente positivo permite continuación; primera pérdida o neto cero bloquean el día; costos pendientes, fills parciales/posición incierta y reservas bloquean. Una posición y US$20 acumulados que ganancias/reinicios no restauran. ExecutionDiagnostics separado. Live absolutamente bloqueado.

**406 pruebas aprobadas, cero fallos y cero omitidas:** 166 C# y 240 Python. Incluyen A/B/C/D, cambio UTC de día, replay, reinicios, journal PostgreSQL, pérdida acumulada irreversible, fees pendientes, reservas, protección OCA/partial fills, emergency/Live guards; además nueva excepción StrategyPaper (scope/cuenta/versión/plan/sesión, DPAPI real en fixture aislado, primer fill y post-reconciliación), calendario SCHEDULE/horarios/UTC/DST/conflictos y sizing económico.

Build sin errores/advertencias; compileall, parser PowerShell y demo offline aprobados. Primera corrida detectó tres fixtures desactualizados por la nueva lectura de calendario; se corrigieron y la suite completa se repitió con éxito. No se relajan guards para hacer pasar tests.

Comandos ejecutados: dotnet build TradingAgent.sln -m:1; dotnet test TradingAgent.sln --no-build -m:1 (con TRADING_TEST_DB aislado); python -m unittest discover -s python/tests -v; python -m compileall -q python; parser de scripts/paper-lab.ps1; dotnet run --project src/TradingAgent.Api --no-build -- --demo. Lectura auténtica: scripts/paper-lab.ps1 -Action Diagnose -StrategyMarketEvidence. Verificación de plan: paper_strategy --validate-file ... --version ... devuelve el rechazo esperado STRATEGY_EXIT_SEMANTICS_NOT_EQUIVALENT.

Evidencias: artifacts/test-results/paper-readiness.trx, paper-readiness-python.log, paper-readiness-demo.jsonl; artifacts/paper-lab/data-diagnostics.json, market-evidence.json, trend-versions-postgres.txt, trend-v1-readiness.json. Hashes de archivo/manifest verificados sin actualizar los originales. Pruebas de órdenes/fills/comisiones/protección sintéticas; no hay fills/comisiones reales nuevos que acrediten el transporte efectivo. Ambos clústeres locales iniciados se detienen al finalizar.
