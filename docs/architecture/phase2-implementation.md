# Fase 2 — primera entrega funcional

Fecha: 2026-10-03. Esta entrega implementa las dependencias fundamentales de la fase solicitada. No declara terminada la integración completa con IBKR ni la administración de producción. La ruta operativa de la API es exclusivamente simulación local; no existe ruta de envío de órdenes.

Actualización posterior: [informe de entregas A/B](virtual-capital-and-feasibility.md), política `research-capital-v3`, capital virtual y analizador de viabilidad. Los resultados y contratos de este documento son históricos; consultar el informe nuevo para el estado vigente.

## Inspección inicial y decisiones conservadas

Se aplicó `senior-software-engineer`. Graphify estaba disponible como skill, pero no había `graphify-out/graph.json`; se siguió la exploración selectiva expresamente autorizada por el usuario. Solo existían los dos documentos de fase 1. No había módulos funcionales que reescribir ni repositorio Git inicializado.

Se conservaron: riesgo determinista independiente de IA, dominio C#, investigación Python, PostgreSQL, separación de responsabilidades, evidencia inmutable, abstención ante incertidumbre, protección del capital y prohibición de Live autónomo. Se implementó una API de simulación local y un cliente de datos Paper separado, evitando que el proceso cuantitativo pueda enviar órdenes.

## Cambio de política solicitado

La política `research-v2` reemplaza para estas pruebas los valores preliminares de fase 1:

| Parámetro | Fase 1 histórica | Fase 2 implementada |
| --- | --- | --- |
| Riesgo ordinario | No separado del máximo | 0,25 % |
| Riesgo máximo | 0,50 % | 0,50 % |
| Límite diario | 1,5 % | 1 % |
| Límite semanal | 3 % | 2 % |
| Drawdown | 5 % | 5 % |
| Posiciones/reservas simultáneas | 1 | 1 |

Archivo: [research-policy.json](../../config/research-policy.json). Parámetros adicionales elegidos **solo para simulación**: reducción de riesgo a la mitad a partir de tres pérdidas consecutivas o 2 % de drawdown, tope nominal de una vez el patrimonio, margen de ejemplo 100 % en la demo, antigüedad máxima 30 segundos. Los buffers y el margen libre mínimo del ejemplo son cero; requieren calibración conservadora antes de una operación real. No representan requisitos de IBKR ni condiciones de una cuenta Forex concreta.

La política solo se carga por configuración de operador, no por respuesta IA ni endpoint de escritura. Se registra con versión inmutable en PostgreSQL; alterar su contenido bajo la misma versión se rechaza. Las cuentas quedan ligadas a su versión. La activación de una política diferente en cuentas existentes está bloqueada hasta implementar el flujo administrativo correspondiente. El límite de 0,50 % y una posición son techos rígidos de esta entrega.

## Módulos y evidencia de implementación

| Módulo | Implementado y verificable | Pendiente / límite |
| --- | --- | --- |
| RiskManagement | Equity por eventos simulados, índice ajustable por flujos, HWM, períodos UTC, costos, stop, gap/slippage, sizing decimal, nominal, margen, riesgo abierto, reducción preventiva, suspensiones y reserva transaccional | Valorización mark-to-market real, FX/margen por contrato y actualización continua de riesgo de posiciones desde IBKR |
| BrokerIntegration | Puerto configurable/verificado por operador, identidad Paper exacta, conexión/desconexión, reintentos acotados y lecturas mediante puerto read-only; simulador C# y transporte opcional Python TWS con callbacks | SDK oficial `ibapi` no instalado ni sesión TWS probada. No hay puente automático del transporte Python al estado de riesgo C#. No hay métodos de órdenes |
| MarketAnalysis | RSI Wilder, EMA20/50, MACD 12/26/9, ATR Wilder, volatilidad por barra, tendencia, extremos móviles de soporte/resistencia, cambios de spread y análisis 4H/1H/15M | Soportes/resistencias son extremos de 20 velas, no inferencia discrecional. Calendario Forex y normalización de sesiones reales pendientes |
| MarketExperienceEngine | Guardado/recuperación de decisiones aceptadas y rechazadas, estado previo, sesión, features, riesgo y costos; observaciones posteriores; similitud euclidiana normalizada y filtro temporal | Sin ML ni promesa predictiva. Escalas deben fijarse con datos de desarrollo. La API busca hasta 100 episodios previos por petición |
| StrategyResearch | Versiones inmutables con hash, condiciones, instrumentos, temporalidades, stops/targets, exposición y requisitos; estructura separada de review/evidencia/aprobación | Registro de candidatos funcional. Orquestación completa de etapas, evidencia firmada y aprobación administrativa Live no implementadas ni expuestas |
| Backtesting | EMA20/50 y señal sintética `always_long`, long-only, señal cerrada/entrada en siguiente apertura, stops/targets, stop-first, gaps, costos, ledger, equity, métricas, partición desarrollo/validación y comparación equivalente | Motor lineal monomoneda para investigación EUR/USD con cuenta USD; sin swaps/borrow, multiinstrumento, short, walk-forward ni Monte Carlo ejecutables aún |
| PostgreSQL | Npgsql, dos migraciones transaccionales con checksum/lock; las 13 entidades solicitadas, estado de cuenta, índices temporales, inmutabilidad y agregación/retención de velas | Esquema inicial de documentos JSONB con columnas indexadas, no modelo relacional exhaustivo. Roles DB separados, backups probados y almacenamiento WORM pendientes |
| OpenAI Sol | `IResearchAi`, contexto de mercado/indicadores/resultados/experiencias/política, respuesta estructurada, validación estricta, proveedor deshabilitado y schema JSON | No se crea cliente SDK ni se hacen llamadas. Modelo Sol concreto y acceso de cuenta se fijarán al activar una fase posterior |
| Seguridad | Live rechazado al arrancar, sin capacidades de orden, API loopback/token, secretos por entorno, parada durable, checks de política, cuenta y datos, idempotencia, recuperación y fallos cerrados | No es despliegue de producción: faltan OIDC/MFA, aislamiento de procesos/roles endurecido, auditoría independiente y reconciliación operativa real |

Telegram y dashboard permanecen fuera de esta entrega. La API y sus reportes proporcionan la base para incorporarlos posteriormente.

## Precisiones de riesgo y backtesting

Con US$100, los presupuestos teóricos son US$0,25 ordinario y US$0,50 máximo. El motor toma el mínimo entre ese presupuesto, capacidad restante de día/semana/drawdown, exposición y margen. Con las cotizaciones/costos sintéticos de la demo, el límite nominal de 1x restringe la cantidad a 90 unidades; riesgo estimado US$0,135 y margen de ejemplo US$99,009. No confundir ese margen con la pérdida estimada. Un mínimo hipotético de 20.000 unidades se rechaza; no se afirma que ese mínimo sea universal en IBKR.

No se simula una martingala: la cantidad proviene exclusivamente de patrimonio, riesgo autorizado y restricciones. Cinco pérdidas se prueban como trayectoria contable y como racha de investigación. Cuatro pérdidas de US$0,25 ya alcanzan el 1 % sobre US$100: una quinta entrada se bloquea, aunque todavía deban registrarse pérdidas posteriores o ajustes. La reducción preventiva puede frenar antes el tamaño de nuevas entradas.

El estado de cuenta conserva suspensiones y referencias tras reinicio. Los períodos UTC toman el último NAV conocido al cambiar de día/semana para cargar el gap al nuevo período, una aproximación conservadora de simulación que deberá reemplazarse por referencias conciliadas del calendario real. Los flujos externos tienen función de dominio y prueba, pero no endpoint de modificación operativa.

La API solo acepta marcas de equity manuales sin reserva abierta; el cierre simulado es una operación explícita que recibe P&L neto. No constituye un feed de posiciones reales. El riesgo acumulado de las posiciones se calcula, pero esta entrega no admite agregar nuevas posiciones cuando ya existe una o una reserva.

El backtest usa OHLC de punto medio, spread conocido en la vela anterior, comisión y slippage de ida/vuelta. Stop/TP se deciden después de la entrada en la siguiente apertura. Si ambos se alcanzan, registra `STOP_AMBIGUOUS` y usa stop. Gaps más allá del stop se ejecutan al precio peor. Al final de datos se liquida la posición simulada y se registra la causa.

Su drawdown incorpora una envolvente conservadora high-before-low limitada por el target; al faltar trayectoria intravela, se etiqueta expresamente como estimación conservadora, no medición exacta por ticks. La reducción preventiva comparte las reglas iniciales con C#, pero la paridad general entre motor de investigación y riesgo operativo todavía necesita un conjunto mayor de casos antes de promoción de estrategias. Una ganancia de backtest no activa nada.

## Persistencia, versiones y retención

Las decisiones y evaluaciones se insertan junto con la reserva y estado bajo bloqueo transaccional de la cuenta. Mismo ID y mismo contenido devuelve el resultado previo; mismo ID con contenido distinto falla. Los cierres son también idempotentes. Las observaciones posteriores no reescriben decisiones y no aparecen al consultar una fecha de corte anterior a su registro.

`broker_accounts`, `market_candles`, `market_snapshots`, `strategies`, `strategy_versions`, `backtest_runs`, `backtest_trades`, `trading_decisions`, `risk_policies`, `risk_evaluations`, `equity_snapshots`, `strategy_approvals` y `system_events` tienen almacenamiento genérico tipado/JSONB e índices. Las rutas de usuario cubren los flujos principales; no todos los tipos tienen un endpoint CRUD público.

Las versiones, políticas y evidencia crítica tienen triggers que rechazan UPDATE/DELETE desde SQL normal. Un administrador de base de datos puede alterar triggers: no se presenta esto como inmutabilidad frente a superusuarios. Un cambio de parámetros exige nuevo hash y número de versión. Los resultados y motivos de suspensión son registros separados; no modifican el artefacto aprobado.

`aggregate_and_prune_candles(cutoff)` agrupa velas antiguas por cuenta/instrumento/temporalidad/día, guarda número de muestras, extremos, media de cierre y volumen solo cuando existe para todas las muestras. Elimina únicamente raw no fijado como `pinned=true`, con retención mínima de 90 días. No se ejecuta automáticamente. Antes de archivar datasets de validación, fijar sus velas y conservar el dataset original y su hash. El agregado estadístico no sustituye un dataset reproducible de backtesting. Las decisiones y resultados no se purgan en esta fase.

## Pruebas y criterios de aceptación

Las suites automatizadas abarcan los 15 casos obligatorios: US$100; riesgo 0,25/0,50 %; ganancias/pérdidas; cinco pérdidas; suspensión; riesgo excesivo; mínimo incompatible; mercado incompleto; caída del bróker; cuenta Live; cambio de estrategia; indicadores conocidos; backtest verificable; y persistencia/recuperación.

Comprobaciones ejecutadas durante esta entrega:

- Compilación de Core, Infrastructure, API y Tests con .NET 9: **0 errores y 0 advertencias** en la ejecución final.
- **34 pruebas C# aprobadas, 0 omitidas**, incluidas **10 contra PostgreSQL real** en cluster desechable local; resultados detallados en `artifacts/test-results/phase2.trx` al ejecutar `scripts/verify.ps1`.
- **27 pruebas Python aprobadas** sobre indicadores, backtesting, series inválidas, separación temporal y conexión Paper simulada.
- Prueba HTTP real con token: registro, evaluación, repetición, cierre, experiencias y parada; reinicio del proceso y recuperación de estado desde PostgreSQL.
- Demostración del motor de riesgo con datos sintéticos y comprobación de que `Trading:LiveEnabled=true` impide el arranque.

No ejecutado: integración del transporte con SDK/TWS real, lecturas de una cuenta IBKR, ejecución Paper, llamadas OpenAI, pruebas de rendimiento, auditoría de dependencias/penetración y validación de rentabilidad. La restauración de paquetes usa versiones fijadas; el análisis de vulnerabilidades NuGet está deshabilitado para esta verificación offline y debe habilitarse en CI con acceso al servicio de auditoría antes de despliegue.

## Sol y referencias verificadas

El usuario solicita la familia Sol. Se consultó [GPT-6 Sol](https://developers.openai.com/api/docs/models/gpt-6-sol) y la guía oficial de [respuestas estructuradas](https://developers.openai.com/api/docs/guides/structured-outputs). Esta consulta orientó un contrato estricto de propuestas, sin campo de órdenes ni permisos. No se presupone acceso a un modelo desde la cuenta ni se activa automáticamente un identificador de API.

El cliente opcional TWS sigue la firma actual de errores con `errorTime` y usa callbacks de lectura; ver [cambios de TWS API](https://www.interactivebrokers.com/docs/tws-api/changelog) y [recepción de barras históricas](https://www.interactivebrokers.com/docs/tws-api/doc/market-data-historical/historical-bars/receiving-historical-bars). Los permisos se detectan por respuestas/errores, no se infiere una lista completa de permisos de trading.

## Continuación concreta

Las instrucciones reproducibles de arranque están en [README.md](../../README.md). La próxima entrega debe instalar/verificar el SDK oficial, confirmar TWS Paper read-only y la cuenta exacta, leer EUR/USD y validar moneda, tiempos, huecos de sesión, spread y volumen ausente. Después conectar esos snapshots al puerto de negocio con conciliación y pruebas de contrato. Solo entonces alimentar simulaciones con datos reales.

Antes de cualquier fase de órdenes futura: reemplazar políticas/costos sintéticos, implementar autorización y operación endurecidas, terminar el ciclo de evidencia y pruebas faltantes, y obtener autorización humana independiente. En este repositorio no hay una implementación de envío de órdenes que pueda activarse cambiando una configuración.
