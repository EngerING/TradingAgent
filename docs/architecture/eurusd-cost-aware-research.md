# EUR/USD: búsqueda acotada con costos y evidencia

Resultado: **NO_VIABLE_STRATEGY_FOUND**. Ningún candidato se activa, sustituye Trend V1 ni se promueve. Se preservan las carteras EURUSD_R1/R5/R10, los controles productivos y el preregistro anterior. El dashboard ya existente sigue funcionando; no se detuvo su proceso. No se encontró un proceso del runner Shadow activo al revisar esta sesión.

## Implementación

Graphify se consultó primero. El índice de 424 nodos es anterior al laboratorio actual y la consulta quedó truncada; búsquedas dirigidas identificaron los componentes faltantes. Se reutilizan `Simulator`, sizing/funding, FIRST_LOSS_STOPS_DAY, comisiones/settlement, `Calibrator`, indicadores y archivos históricos auténticos. Sus archivos no se editan: cambiar el motor sellado invalidaría el estudio anterior.

Nuevos componentes:

- `python/trading_agent/eurusd_cost_aware_search.py`: catálogo fijo, señales causales, trayectorias, gate de EV, replay y reportes.
- `python/trading_agent/eurusd_cost_aware_forward.py`: consumidor de lectura del journal Shadow existente; inventarios candidatos independientes, persistencia y controles de reinicio.
- `scripts/eurusd-cost-aware-research.ps1`: Search / Prepare / Run / Once / Status / Stop.
- `python/tests/test_eurusd_cost_aware.py`: 48 pruebas de señales, costos, calibración, diarios, persistencia, consumo de fuente y contrato Sol.

No se modifica RiskEngine, ExecutionGuard, AccountBinding, H40, Forex V1, configuraciones protegidas, autorizaciones ni emergencia. No hay un cliente de órdenes o proveedor OpenAI en los nuevos entrypoints. El consumidor no se conecta a TWS: usa las cotizaciones y archivos auténticos que ya persiste el runner original.

## Protocolo previo a resultados

Dieciséis hipótesis: trend, breakout, momentum y mean reversion × 1H/4H × swing/position. No se amplía el catálogo hasta encontrar un ganador ni se ajustan parámetros tras observar resultados. Las versiones de candidato son hashes de configuración, independientes de versiones productivas.

Indicadores: EMA20/50, RSI14, MACD12/26/9 y ATR14. Estructura de las últimas 20 velas anteriores. Entradas entre 07:00 y 20:00 UTC; el calendario de admisión forward procede del quote validado por el lector Paper original. Se mantienen timestamps UTC y días de política en America/Santo_Domingo.

| Familia | Hipótesis de entrada |
|---|---|
| Trend | Cruce EMA, MACD compatible y RSI dentro de bandas prefijadas |
| Breakout | Cierre rompe máximo/mínimo anterior, MACD y contexto compatibles |
| Momentum | Movimiento de cuatro velas superior a 2 ATR, tendencia/MACD/RSI compatibles |
| Mean reversion | Contexto lateral, sin volatilidad alta, RSI retorna desde extremo y precio puede volver a EMA20 |

Stop = máximo de 2 ATR, distancia a la estructura anterior y piso técnico. Target swing = 12 ATR; target position = 36 ATR. En mean reversion se limita al retorno a EMA20, sin ampliar el target para pagar comisiones. Ambos niveles se calculan usando la vela cerrada y quedan fijos durante esa operación candidata. No se implementa un trailing stop diferente de esta especificación.

Horizontes máximos: cinco y veinte **días naturales**, con salida en la siguiente apertura realmente observada. Se incluyen fines de semana como tiempo de mantenimiento; no se inventan velas. Stop primero cuando una vela toca ambos niveles, gaps adversos al precio de apertura, sin acreditar ejecución favorable por encima del target. La salida por horizonte respeta también el stop/target alcanzado en ese opening.

Datos: archivo auténtico EUR/USD de seis meses ya verificado por hashes y recibos; partición existente desarrollo/validación y tres ventanas walk-forward cronológicas. Ningún parámetro se refita en las ventanas. Esta validación ya se examinó previamente; es reproducción retrospectiva fuera del segmento de desarrollo, **no una nueva prueba final intacta**. La prueba final sellada permanece cerrada.

Se ejecutan 240 escenarios: 16 candidatos × 3 perfiles × desarrollo/validación/3 folds. Las ventanas y candidatos son experimentos financiados independientemente. Nunca se suman como una cartera continua ni como capital disponible para IBKR.

## Costos y gates

Se conserva la evidencia de una apertura/cierre Paper anterior: US$2 por lado, US$4 por ciclo. Generalizar esa observación a otros tamaños no verifica una tarifa efectiva particular. La [tarifa pública spot de IBKR](https://www.interactivebrokers.com/en/pricing/commissions-spot-currencies.php), consultada el 7/10/2026, publica mínimo Tier I US$2 por orden y advierte sobre nuevos mínimos para órdenes que persisten overnight. No se confunden estos trades con auto-conversión de moneda.

Escenario conservador heredado: spread 0.0014 USD/EUR (máximo del archivo), slippage 0.00045 y reserva de gap 0.00005. Son estimaciones, no reconstrucciones de todos los fills. Los precios históricos son midpoint; fills de backtest son SIMULATED. Una reserva de gap no garantiza un máximo de pérdida.

Para cada señal y perfil se calculan `gross_expected_win`, `net_expected_win`, `expected_loss`, `fees`, `spread`, `slippage`, `reward_risk`, `expected_value`, `conservative_expected_value` y `break_even_win_rate`. «Win» es el payoff condicional al target, no una predicción de ganancia media. El costo/target, tamaño, stop y presupuesto se comprueban antes del gate probabilístico.

Se mantienen los filtros anteriores: target neto positivo, costos ≤50% del target bruto y relación neta beneficio/riesgo ≥1. Se agrega:

`EV = P(TP) × beneficio neto al target − (1 − P(TP)) × pérdida prevista total`.

EV puntual y EV con límite inferior de probabilidad deben superar **US$0.25**. El segundo usa Wilson ajustado por las 16 hipótesis; no se usa solamente una tasa de acierto favorable. El break-even es pérdida total / (pérdida total + beneficio neto al target); si el beneficio neto no es positivo, el umbral es inalcanzable y se informa como tal.

Financiación overnight, débitos cash y costos de mantenimiento particulares siguen UNKNOWN. No se sustituyen por cero: `HOLDING_COST_EVIDENCE_UNKNOWN` impide una entrada Shadow aun con EV favorable. Los cálculos de movimiento y geometría describen el escenario de costos disponible; no son un costo all-in ya verificado para mantener Forex varias semanas.

R1/R5/R10 reciben el mismo ID, lado, timestamp, stop y target para cada candidato. Sólo cambia el sizing con el equity de su cartera y los presupuestos protegidos existentes. US$100 incluyen exposición y reservas; no se usa el saldo ficticio del broker ni aumenta apalancamiento. Las ganancias no reponen pérdidas acumuladas. Se mantienen riesgo 1/5/10%, caps US$1/5/10, presupuestos diarios US$2/5/10 y acumulados US$20.

Una ganancia neta conciliada permite otra señal; pérdida o break-even detienen entradas ese día. Posición o comisión pendiente impide una nueva entrada. El cambio de día usa America/Santo_Domingo y no borra inventario ni pérdidas al reiniciar. La gestión de inventario pendiente continúa cuando sólo está bloqueada la entrada.

## Probabilidad y oportunidades rechazadas

P(TP antes de SL) usa exclusivamente resultados resueltos antes del timestamp de la decisión, comparables por versión, lado y régimen. No recibe valores subjetivos de GPT. Se exigen los umbrales existentes: 100 muestras, 30 días, tres folds concluidos, muestras de fiabilidad por fold, Brier ≤0.25 y error absoluto medio por fold ≤0.15. Se reportan tamaño, probabilidad, régimen, bucket, intervalos y error; ausencia de muestra implica INSUFFICIENT_EVIDENCE.

Las salidas por horizonte son riesgos competitivos y cuentan conservadoramente como pérdidas para EV; no desaparecen del denominador. Los resultados sin resolver también bloquean suficiencia si superan el 10%. Wilson es una referencia IID: señales y días siguen teniendo dependencia serial, por lo que no acredita independencia ni edge por sí solo.

Se conservan **todas** las decisiones programadas: warmup, sin señal, filtro horario/régimen, tamaño imposible, target insuficiente, EV y muestra insuficientes, además de entradas/cierres que llegasen a admitirse. También se calculan trayectorias contrafactuales de señales rechazadas. Las superpuestas se guardan, pero no multiplican el tamaño de muestra de calibración; las tres carteras tampoco cuentan como tres observaciones independientes del mismo precio.

El barrido conserva 38.772 registros de evidencia y 796 trayectorias de señales válidas. El log JSONL tiene cadena de hashes; cada reporte, catálogo y handoff conserva procedencia. Los inventarios forward tienen journals SQLite append-only propios. La fuente original conserva su journal PostgreSQL: el consumidor exige concordancia de cabecera antes de procesar, sin escribir en ese estudio. No se afirma que los journals candidatos estén replicados en PostgreSQL.

## Resultado económico y estadístico

Se rechazaron los 16 candidatos. 99 geometrías cubren costos con target neto nominal positivo en R10, pero **cero** superan conjuntamente la relación neta beneficio/riesgo y los demás filtros geométricos existentes. Ninguna alcanza calibración suficiente; el mayor grupo comparable contiene 16 muestras. Las comisiones de mantenimiento UNKNOWN son un bloqueo adicional.

Mean reversion 1H ofrece 6 TP / 7 trayectorias no superpuestas resueltas (85.7%; Wilson 95% aprox. 48.7–97.4%), pero su mejor target neto conservador sigue siendo **−US$3.86**. Eso no es win rate neto de una cartera ni evidencia económica positiva. Los candidatos position de 4H alcanzan targets potenciales superiores a costos, pero no muestran TP en sus pequeñas muestras comparables y no cumplen el payoff/riesgo requerido. Ninguno merece promoción por su target teórico.

En las carteras con gates aplicados: cero operaciones completas o pendientes; P&L bruto/neto realizado y comisiones realizadas US$0, drawdown realizado US$0; win rate, expectativa neta y profit factor **no evaluables**. Estos ceros contables no demuestran rentabilidad. Los 144 escenarios walk-forward (16 × 3 × 3) tampoco admitieron operaciones. El informe comparativo generado incluye las 16 configuraciones, intervalos, muestras, rechazos y umbrales de break-even cuando el payoff permite calcularlos.

No hay mejor candidato aprobado, ranking estadístico válido ni perfil ganador. R1 no admite cantidad por US$4 de comisiones frente a US$1 de riesgo. R5/R10 permiten algunas cantidades geométricas, pero siguen NO_TRADE por economía/evidencia/costos no acotados. Incrementar riesgo no crea edge y, bajo la exposición máxima, frecuentemente no cambia la cantidad.

## Magnitud del movimiento

Referencia **histórica**, no cotización vigente: midpoint 1.12556, stop dinámico ilustrativo 0.006195013 (2 ATR 4H de la última vela disponible). Cálculo con US$100 iniciales; no es una señal ni autorización.

| Perfil | Cantidad geométrica EUR | Notional USD | Pérdida al stop, escenario USD | Break-even pips | +US$1 neto pips | +US$3 netos pips | +US$5 netos pips |
|---|---:|---:|---:|---:|---:|---:|---:|
| R1 | 0 | — | — | No admisible | — | — | — |
| R5 | 85.09 | 95.83 | 4.69 | 489.09 | 606.61 | 841.66 | 1076.70 |
| R10 | 85.09 | 95.83 | 4.69 | 489.09 | 606.61 | 841.66 | 1076.70 |

Costos/reserva de incertidumbre usados: US$4.161671. Las cuatro distancias son 0.048909 / 0.060661 / 0.084166 / 0.107670 USD por EUR; equivalen aproximadamente a 4.35%, 5.39%, 7.48% y 9.57% del precio de referencia. Los objetivos netos retornan 0/1/3/5% sobre los US$100, respectivamente. Para otro equity, stop o precio, el motor recalcula el tamaño: no fija 85.09 EUR ni 100 EUR.

Estas cantidades no prueban permiso, margen, lote mínimo efectivo ni fracciones de EUR aceptadas por la cuenta Paper. Los requisitos de IBKR permanecen UNKNOWN donde no hay evidencia particular. Los costos de mantener y modificar órdenes varios días necesitan acotarse antes de considerar una entrada.

## Shadow forward y Sol

El nuevo consumidor tiene preregistro propio, presupuesto OpenAI US$0 y está **PREPARED_NOT_RUNNING**. Cada candidato tiene tres carteras de investigación independientes; no constituyen una cartera conjunta ni sustituyen las tres originales. No hay selección automática de estrategia activa. Su finalidad inicial es obtener cotizaciones, oportunidades rechazadas y etiquetas nuevas, aunque todas las entradas sigan bloqueadas.

Lee en lotes de hasta 100 eventos de la fuente, valida cadena hash y cabecera PostgreSQL, verifica el archivo de mercado auténtico y reanuda desde su checkpoint. Archivos desconocidos, discrepancia de inventario/head, corrupción o pérdida de persistencia suspenden. Un retraso de mirror hace esperar; una divergencia real bloquea. No rellena entradas anteriores al preregistro ni acepta una ejecución tardía: después de cinco segundos de la apertura sólo conserva evidencia, sin fill Shadow retroactivo. Ese plazo puede rechazar entradas por latencia de la fuente/consumidor y queda explícito en el journal.

El catálogo y los archivos del motor se sellan por hashes. Una modificación requiere otro Search y Prepare, conservando los anteriores. Una interrupción entre journals de inventario y checkpoint requiere conciliación explícita; no se reintenta a ciegas. `Stop` sólo afecta al consumidor candidato, preserva inventario y no detiene el runner original.

Se preparan `sol-handoff.json` y `sol-request-prepared.json`: resumen compacto de costos, muestras, resultados, memoria anterior y limitaciones; contrato de recomendación TRADE/NO_TRADE/INSUFFICIENT_EVIDENCE e hipótesis separada. El validador rechaza confidence/probability/risk adicionales. Sol no puede alterar el resultado determinista, activar una estrategia o ejecutar. **No está ejecutándose GPT para este estudio y no hay solicitudes facturables.**

Pendiente para un futuro análisis GPT: autorización explícita de sesión/presupuesto, clave disponible sólo en backend, integración del handoff con el orquestador y validación del proveedor/costos en esa sesión. No se registraron automáticamente conclusiones nuevas en la memoria protegida ni se inició AI_Strategy_Researcher. Una hipótesis nueva necesita evidencia materialmente diferente de los descartes anteriores y debe pasar backtest → walk-forward → forward independiente. La prueba final permanece sellada.

## Siguiente fase

Continuar la observación, sin forzar operaciones, para medir spreads/costos comparables y ampliar evidencia causal. Acotar financiación/costos overnight y aceptación efectiva de tamaños/protecciones con procedimientos Paper de lectura/preview separados. No enviar diagnósticos de ejecución en esta fase. Extender datos auténticos para hipótesis de semanas requiere más historia y un periodo nuevo de confirmación: seis meses con 1–45 trayectorias comparables no bastan.

Si las comisiones efectivas y el capital se conservan, R1 sigue matemáticamente bloqueado y R5/R10 necesitan movimientos de varios puntos porcentuales sólo para cubrir costos. Reducir la fricción relativa, investigar otros instrumentos o capitales en estudios futuros separados puede ser una hipótesis económica; no implica cambiar hoy ningún límite ni seleccionar un candidato por beneficio histórico máximo.

Los identificadores finales, comandos exactos, tabla completa y verificaciones están en el informe comparativo de esta ejecución, bajo `artifacts/research/eurusd-cost-aware/`. Los borradores/replays anteriores permanecen conservados y no habilitan ejecución.

## Identificadores y comandos finales

Informe: `artifacts/research/eurusd-cost-aware/search-9e522bed235749889f782ab82033dc8b/report.md` y `report.json`. Verificación: `artifacts/research/eurusd-cost-aware/verification-v1/verification.json`.

El estudio original sigue PREPARED_NOT_RUNNING. No se inició un runner ni se detuvo uno del operador. Si el original ya está activo cuando se usen estos comandos, conservarlo y no lanzar una segunda instancia. Si no está activo, iniciar su lector en una terminal desde la raíz:

```powershell
.\scripts\eurusd-shadow-research.ps1 -Action Run -Study eurusd-shadow-3786f123021b41e491fc1c9a0b29e6fd
```

El nuevo consumidor preregistrado puede ejecutarse en otra terminal; sigue sin capacidad de broker/OpenAI:

```powershell
.\scripts\eurusd-cost-aware-research.ps1 -Action Run -Campaign forward-a14466fba41f4a1091438964d3db5899
```

Progreso y parada exclusivamente del consumidor:

```powershell
.\scripts\eurusd-cost-aware-research.ps1 -Action Status -Campaign forward-a14466fba41f4a1091438964d3db5899
.\scripts\eurusd-cost-aware-research.ps1 -Action Stop -Campaign forward-a14466fba41f4a1091438964d3db5899
```

Para crear otra preregistración del mismo catálogo, sin iniciarla:

```powershell
.\scripts\eurusd-cost-aware-research.ps1 -Action Prepare -Search search-9e522bed235749889f782ab82033dc8b -Study eurusd-shadow-3786f123021b41e491fc1c9a0b29e6fd
```

Compilación sin errores/advertencias. **1.540 pruebas aprobadas y ninguna omitida**: 1.095 Python (48 nuevas), 416 C#, 22 Vue, 7 E2E. Se conservan los intentos iniciales y sus fallos de entorno: el TestServer C# necesitó sus variables completas; el servidor E2E temporal encontró 5080 ocupado. Las suites finales pasaron con el cluster de pruebas y el dashboard existente, cuyo presupuesto cero se verificó antes de preguntar al chat. Sólo se detuvo PostgreSQL desechable 55432. El dashboard del operador y PostgreSQL Paper permanecieron activos.
