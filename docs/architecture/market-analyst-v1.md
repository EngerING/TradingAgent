# Market Analyst V1 — diseño y registro de entrega

Base: `f67fa92086d10b9562df214f4e869344bf0753d8`. Fecha: 2026-10-20,
America/La_Paz. Rama: `codex/market-analyst-v1`. Estado: **OFFLINE / NO_TRADE**.
La especificación de alcance es la solicitud del usuario; no se cambia Core V3.

## Diseño previo a implementación

Paquete hermano `python/trading_agent/market_analyst/`, sin imports de Core V3.
Contrato frozen/slots, esquema cerrado V1, JSON canónico, Decimal como texto,
UTC explícito, límites de recursos y errores con códigos fijos.

| Módulo | Responsabilidad | Dependencia |
|---|---|---|
| contracts | Identidad, política, indicadores, calidad, procedencia y evaluación | biblioteca estándar |
| fixtures | Recetas sintéticas declaradas; generación local y verificación por regeneración | contracts |
| evaluator | Selección causal, validación, indicadores y clasificación | fixtures, research_indicators, market.Candle |

Orden: contrato → fixtures/evaluación → causalidad/adversarios → regresión/evidencia.
No habrá importador de OHLC externos ni método para convertir datos reales en
fixtures. Una marca JSON o un hash no autentican una fuente. Las recetas se
generan en memoria y se contrastan de nuevo antes de calcular indicadores.
El propietario del proceso puede alterar Python; esto no es un sandbox.

Se consideran solo barras cerradas y disponibles al cutoff; los datos futuros
quedan fuera de indicadores, hashes, períodos y contadores del resultado.
Se preserva el orden, sin sort, fill ni agregación. Un gap o duplicado rechaza
la evaluación; no se reinicia warmup silenciosamente. El calendario sintético
es continuo 24x7 y no acredita sesiones Forex. Temporalidades: 15, 60 y 240 min.
Inicialmente se admiten identidades sintéticas EUR/USD y GBP/USD, con identidad
esperada explícita; no se inventan conId ni detalles de contrato IBKR.

Indicadores reutilizados: EMA con semilla SMA, RSI/ATR Wilder, MACD, pendientes,
desviación poblacional de retornos logarítmicos, rango y ATR/precio.
El motor histórico usa float; se valida entrada Decimal, se convierte solo para
ese cálculo y se serializa el resultado finito mediante Decimal(str(value)).
No se afirma aritmética financiera exacta ni reproducibilidad binaria entre
distintas plataformas/libm. Versión del motor y hash de política acompañan la salida.
Warmup explícito por medida. No hay tamaños, liquidez, señales, P&L ni probabilidad.

Estados: COMPLETE, INSUFFICIENT_DATA, STALE_DATA, SOURCE_UNAVAILABLE,
UNVERIFIED_PROVENANCE y VALIDATION_ERROR. Todos conservan autoridad nula;
una salida serializada puede leerse como documento, nunca como fuente aceptada.
Kronos/Sol tienen solo un descriptor futuro de evidencia, sin ejecución ni consumo.

## Inspección y matriz de compatibilidad

Graphify primero: grafo histórico de 424 nodos, 1039 links, sin V3.x/R20/Kronos.
Vocabulario consultado: market, candle, ema, rsi, atr, indicators, validate.
La consulta BFS con presupuesto 1800 orientó a market.py/test_quant.py.
Las ubicaciones del grafo son históricas: se contrastaron con fuentes actuales.
reflect --if-stale no requirió regeneración; se leyeron las lecciones existentes.
No se reconstruye el grafo ni se consulta un proveedor remoto.

| Fuente inspeccionada | Capacidad | Dependencias / incompatibilidad / decisión |
|---|---|---|
| research_indicators.py + test_research.py | Indicadores, warmup y regímenes causales | market.py puro; reutilizar calculate/settings después de validar |
| market.py + test_quant.py | Candle, EMA/RSI/ATR | float y sin available_at/identidad; adaptar solo tras validación nueva |
| r20_market.py + test_r20_v2_market.py | Calidad de lectura y cierres 1H/4H | imports diferidos de transporte, configuración y señales; no importar ni ejecutar |
| Core V3.9 market_observation + tests V39 | Quotes por lado, journal, autorización separada | BID/ASK sin barras; no conectar ni inferir régimen OHLC |
| Core V3.8 historical_ingestion + tests V38 | Custodia, calidad, calendario y evidencia | contratos protegidos y formato real pendiente; no convertir ni modificar |
| strategy_indicators_v2.py | Snapshots y alineación con anterior | Candle float, falta disponibilidad/identidad; reutilizar primitivas inferiores |
| kronos/r20_source.py + tests de fuente | Validación del request, contrato 1H/4H | metadatos de proceso confiable; JSON no autentica; no importar |
| kronos/r20_bridge.py + tests del puente | Aislamiento y límites de worker | broker, subprocess y modelos al ejecutar; excluido |

## Amenazas y pruebas previstas

Procedencia falsa → tipos exactos, sello de creación y regeneración de receta;
lookahead → cierre Y disponibilidad <= cutoff, hash solo del prefijo;
identidad cruzada → instrumento/contrato/temporalidad por barra;
datos malos → OHLC positivo/finito, orden, alineación, duplicados, gaps;
reloj implícito → cutoff obligatorio, sin datetime.now;
recursos ilimitados → hasta 4096 barras y documentos JSON acotados;
promoción accidental → flags de autoridad siempre false y ausencia de acciones.

Pruebas nuevas por `python/tests/market_analyst_offline_check.py`, que compondrá
los guards históricos sin editarlos y añadirá barreras de escritura/DB/imports.
Regresión requerida, sin alterar selecciones:
`.venv/Scripts/python.exe -B python/tests/core_v39_offline_check.py`.
Los 394 resultados previos no se atribuyen a esta ejecución.

Se preservan los 691 archivos tracked de la base y los dos documentos untracked.
El inventario SHA-256 inicial queda en artifacts/market-analyst-v1/before.json
(artefacto local ignorado). No habrá push, merge, migración ni despliegue.
