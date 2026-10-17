# AGGRESSIVE_GROWTH_R20 — diseño y contrato preregistrado

Fecha de diseño: 2026-10-09. Solicitud: laboratorio independiente con US$100 lógicos,
Shadow inmediato tras pruebas y preparación Paper sin transmisión. Esta especificación
concreta las diez fases ya autorizadas por el usuario; no concede autoridad al bróker.

## Auditoría antes del código

Graphify se consultó primero: 424 nodos, vocabulario capital/equity/exposure/risk/
policy/paper/research/strategy/loss. El índice local anterior a los módulos nuevos
localiza Risk, VirtualCapital, ExecutionFeasibility, PostgresStore y PaperDataBroker;
las incorporaciones Shadow/Kronos/Vue se inspeccionaron mediante búsquedas dirigidas.

* `Core/Risk.cs`: techo validado de riesgo 0.005, límite diario 1%, semanal 2%,
  drawdown 5%, exposición 1× y rechazo económico. No es el contrato R20.
* `Core/VirtualCapital.cs`: asignación 100 y consumo irreversible de allowance 20;
  reutilizarlo heredaría una suspensión ajena a R20.
* `python/trading_agent/eurusd_shadow_research.py`: exige probabilidad calibrada,
  EV y límite inferior positivos, costos/beneficio, aprobación contextual y presupuestos
  conservadores. Estas son restricciones de elegibilidad estratégica, no protecciones
  necesarias para observar resultados exploratorios.
* `python/trading_agent/r10_price_risk.py`: solo LONG, 1×, riesgo min(10,10% equity),
  costos ≤5, total previsto ≤15, pérdida acumulada 20, primera pérdida diaria y target
  suficiente. No cambiar ni usar como política R20.
* Identidad exacta Paper, reconciliación, inventario propio, idempotencia, protección,
  recuperación, EmergencyStop y bloqueo Live son protecciones operativas: se conservan.

El incidente EUR/USD consta en `paper-account-binding.md` y
`eurusd-paper-exploratory-supervised-20261008.md`: BUY 100 EUR a 1.12185, salida a
1.12247, bruto +US$0.062 y dos comisiones US$2: neto **−US$3.938**. La coma española
en «−US$3,938» es decimal; no hay evidencia de −US$3,938 enteros. Una intención sin
fill activó indebidamente conciliación estricta; los hijos fueron cancelados y se
perdió protección. La recuperación independiente cerró inventario. Mantener gates
antes de SEND_PENDING, estado pre-fill diferenciado, conciliación estricta desde el
primer fill parcial, no reenvío ciego y reserva hasta posición cero/sin pendientes.

## Mapa de capacidades y orden

| Módulo | Responsabilidad | Depende de |
|---|---|---|
| r20-domain | Perfil, sizing, estrategia causal, simulación y baseline | — |
| r20-journal | Persistencia append-only y recuperación | r20-domain |
| r20-runner | Observaciones auténticas y ciclo Shadow | r20-domain, r20-journal |
| r20-observation | Proyección, SignalR, Sol local, dashboard | r20-journal |
| r20-paper-plan | Preparación diagnóstica bloqueada y consentimiento futuro | r20-domain, observaciones |

Orden: contrato/pruebas → dominio y journal → runner → observación → verificación
completa → inicio único Shadow. Backend y frontend se implementan en paralelo
contra el contrato documentado. El directorio no tiene Git; hashes previos en
`artifacts/aggressive-growth-r20-20261009/before-hashes.json` y manifiesto final.

## Perfil y cálculo

Perfil inmutable `AGGRESSIVE_GROWTH_R20`; candidata `AGGRESSIVE_TREND_BREAKOUT_V1`.
Inicial 100 USD; riesgo previsto por precio ≤0.20 × equity actualizado; exposición
nominal a entrada ≤10 × equity. BuyingPower/NetLiquidation del bróker nunca alimentan
sizing. La cantidad es el menor de los límites por riesgo, exposición y margen con
reserva de costos, redondeado hacia abajo a la rejilla negociable. Rechazar si no
alcanza mínimo, margen, presupuesto o geometría; jamás subir de 10×.

Shadow usa condiciones declaradas y modelos explícitos, no las presenta como permiso
efectivo del bróker: comisión estimada 2 USD por lado (un único ciclo histórico),
spread observado con provisión conservadora, slippage por lado 0.00045 USD/EUR,
financiación provisionada 0.25 USD/ciclo, margen inicial modelado ≥10% nominal.
Conservar procedencia/status y valores desconocidos. Una restricción auténticamente
observada más estricta prevalece. Paper necesita costos/margen/permiso efectivos.

Riesgo por precio = cantidad × distancia stop. Pérdida total prevista agrega costos;
no es un máximo garantizado. Gaps y slippage pueden exceder stop/20%; registrar
pérdida completa incluso equity negativo. Equity incorpora P&L flotante y costos
modelados; drawdown contra máximo histórico. Si equity ≤0 no abrir nuevas posiciones.
Una reserva de margen no es una pérdida ni una comisión. Un exceso de apalancamiento
por caída de equity se marca como riesgo de liquidación y exige reducción/cierre
virtual al siguiente precio utilizable; no reescribir fills ni recortar pérdidas.

CAPITAL_PROTECTION_R3 queda ARCHIVED_NOT_APPLICABLE en esta cohorte. No se reescriben
las políticas, archivos, resultados, autorizaciones o hashes de las cohortes históricas.

## Estrategia, datos y salidas

EUR/USD, velas completas 60/240 minutos; EMA20/EMA50; cierre rompe estrictamente el
máximo/mínimo de las veinte velas anteriores excluyendo vela señal. ATR14 causal;
stop 1.5 ATR y target 2 distancias stop, simétricos LONG/SHORT. Calentamiento suficiente,
precios decimales, timestamps UTC, sin barras futuras ni señales fabricadas. Parámetros
fijados antes de mirar resultados; dataset histórico ya examinado no es holdout nuevo.
EMA inicializada con SMA de sus primeras n velas y actualización 2/(n+1); ATR14
Wilder con media de los primeros 14 true ranges (cada uno usa cierre anterior),
después alpha 1/14. Usar alineación nativa de sesión de barras normalizadas; no
remuestrear ni rellenar huecos. Stop/target se anclan al midpoint de entrada virtual
posterior al cierre de señal, conservando distancia ATR calculada en ese cierre.

Una señal forward entra al primer precio observado válido posterior a su cierre,
nunca al cierre retroactivo: tolerancia señal 180 segundos, quote 30 segundos.
Se registra toda vela evaluada, señal auténtica y rechazo, incluidos posición ocupada,
ausencia de ruptura, datos insuficientes o señal vencida. Orden determinista por
timestamp y timeframe; máximo una posición por cartera. Baseline independiente con
100 USD y techo 1× recibe idénticas oportunidades, reglas de salida y costos.
No es posible inferir causalidad financiera de una comparación pequeña.

Stop antes de target si ambos aparecen en una vela completa; gap adverso a apertura.
Excluir de comprobación OHLC una vela que empezó antes de la entrada. Cotizaciones
posteriores pueden disparar salida. Comisiones/spread/slippage se deducen una vez;
gaps reales ya incluidos en precio. Stop de operador persistente bloquea nuevas
entradas y gestiona cierre virtual con precio válido, sin inventar precio desconectado.
HISTORICAL y FORWARD usan identificadores y clasificación distintos; ninguna ejecución
Shadow se llama fill IBKR. XAU/USD queda pendiente de calidad de datos y condiciones
verificadas, con motivo visible; no sustituirlo por otro instrumento.

## Elegibilidad y Kronos

RESEARCH_ELIGIBLE independiente de ECONOMICALLY_VIABLE y STATISTICALLY_VALIDATED.
Expectativa negativa/desconocida y target menor que costos generan advertencias,
no veto estratégico Shadow. PAPER_EXECUTION_ELIGIBLE siempre false en esta entrega.
Los datos, causalidad, capital, margen modelado, journal y exclusión de duplicados
sí son gates operativos. No heredar parada diaria, allowance 20 o requisitos EV de R3/R10.

Kronos es observador independiente: RAW_ONLY, CALIBRATED_PROBABILITY=null. Capturar
identificador, timestamp, vencimiento, dirección y acuerdo solo si compatible y vigente;
un forecast vencido no apoya una señal actual. La unión es as-of: created_at ≤ hora
de decisión; conservar candle timestamp/horizonte/edad y rechazar una predicción
posterior. Jamás recomputar apoyo pasado usando el forecast más reciente.
No usar frecuencias de trayectorias
para admitir entradas. Su caída no inventa probabilidades ni exige detener investigación
determinista. Diagnosticar el proceso existente sin iniciar duplicados.

## Persistencia y frontera de seguridad

Nuevo schema `aggressive_growth.events`, hash encadenado, revisión CAS, lock PostgreSQL,
SELECT/INSERT para rol local Paper. Configuración, versión motor, señales vistas,
trades cerrados e inventario pendiente sobreviven reinicio. El servidor valida alcance,
límites, identidad de experimento, capital y transiciones; no acepta autoridad Paper
ni Live de un payload. Escritura incierta implica recarga antes de continuar.
Lock por experimento y singleton R20 impiden duplicar procesos/consumo de señales.
Cada decisión conserva quote original, timestamp de decisión, referencia/hash del
archivo inmutable de velas, indicadores, señal y evidencia Kronos recibida. Esto
permite reconstruir la decisión causal; una referencia mutable no es evidencia suficiente.
No se añaden librerías ni servicios externos.

Amenazas: datos manipulados/futuros → validación causal; journal falseado → hash/CAS/
invariantes; mezcla de cohortes → ids/schema independientes; UI/LLM intenta ejecutar →
solo lectura, sin transmisión; reinicio → estado durable; APIs → autenticación local
existente, SQL parametrizado, sin secretos en métricas o logs. EmergencyStop conserva
autoridad sobre el bróker; la investigación virtual no puede quitarlo ni autorizar órdenes.

PaperPlan enumera contrato real, binding exacto, entorno Paper, permisos, mínimo/paso,
margen incremental, apertura/cierre, ACK bracket, reconciliación, parciales, disconnect,
restart y recuperación. UNKNOWN bloquea. Primera futura ejecución requiere consentimiento
explícito de un uso, expiración ≤30 minutos, ligado a cohorte/versión/binding/contrato/
lado/cantidad/stop/target/costos/evidencia. Ningún grant R10 es reutilizable. Esta entrega
no incluye una ruta de transmisión; los ensayos efectivos de protección siguen pendientes.

## Contrato de observación

Snapshot opcional `aggressiveGrowth`; SignalR `aggressiveGrowth.updated`. Cadenas decimales
para dinero/tamaños, null para métricas no observadas. Campos: experiment/profile/strategy/
version/classification/runKind/status/evidenceQuality/startedAt/updatedAt; initialCapital,
equity, priceRiskFraction, maxLeverage, exposure, effectiveLeverage, priceRisk, commissions,
spread, slippage, margin, financing, anticipatedTotalLoss, realizedLoss, liquidationRisk,
grossPnl, netPnl, shadowTrades, paperTrades, winRate, expectancy, drawdown, maxDrawdown,
opportunities, signals; eligibility, market, kronos, baseline, lastNoTrade, lastAssessment,
recentSignals, trades, paper. `classification=SHADOW_SIMULATED`; Paper = `IBKR_PAPER`,
cero operaciones de esta cohorte sin evidencia. Datos retenidos offline aparecen STALE.
Sol responde consultas R20 localmente sin llamadas OpenAI/presupuesto adicional.

## Alternativas y justificación

Modificar RiskEngine/R10 reduciría aislamiento y reinterpretaría historia: descartado.
Exigir viabilidad/calibración antes de Shadow impediría el objetivo experimental:
separar dimensiones. Usar BuyingPower Paper falsearía presupuesto: descartado.
Copiar cada servicio antiguo completo duplicaría autoridad y bugs: reutilizar lectores
de datos solo lectura y contratos journal, mantener política/estado específicos pequeños.
Ausencia de adapter Paper limita preparación a un plan verificable; evita que esta
implementación pueda transmitir mientras quedan requisitos sin verificar.

## Estilo, pruebas y comandos

Python Decimal/funciones puras + unittest; C# .NET9/Npgsql/xUnit, SQL parametrizado;
Vue3/TypeScript/Pinia/Vitest/Playwright existentes. Ejemplo de invariante:
`quantity = floor_to_step(min(risk_cap, exposure_cap, margin_cap), step)`.

Pruebas: sizing/equity actual/10×/fees separados/decimales/slippage>stop/margen/equity
insuficiente; señales simétricas/no lookahead/deduplicación; brackets simulados,
restart/CAS/immutabilidad/permiso/Live/EmergencyStop; separación clases; PostgreSQL,
SignalR, respuestas locales, Vue, navegador. Conservar suites históricas completas.

Build: `dotnet build TradingAgent.sln -m:1`.
DB tests: `scripts/test-database.ps1 -Action Start` y TRADING_TEST_DB de loopback55432.
C#: `dotnet test TradingAgent.sln --no-build -m:1`.
Python: `PYTHONPATH=python .venv/Scripts/python.exe -m unittest discover -s python/tests`.
Frontend, desde frontend: `npm test`, `npm run build`, `npm run test:e2e`.
Operación: `scripts/aggressive-growth.ps1 -Action Prepare|Status|Run|Once|Stop|PaperPlan`.

Siempre: validar evidencia, registrar rechazos, probar antes de iniciar. Nunca: transmitir,
conceder grants, levantar EmergencyStop, habilitar Live, usar saldos millonarios, cambiar
políticas históricas, inventar métricas o señales. Nueva ejecución Paper requiere su
autorización futura específica; ninguna autorización se solicita/concede aquí.

## Resultados y limitaciones

Implementación por fases en curso. Estado y pruebas ejecutadas al 2026-10-10:
[progreso breve](../../tasks/r20-progress.md). La proyección local y el ciclo de
dominio/runner ↔ journal están verificados con PostgreSQL55432 y configuración R20;
Migración011 y Dashboard operativo quedaron integrados en la fase siguiente;
su verificación y bloqueos están en
[informe operativo](../../artifacts/aggressive-growth-r20-20261010/operational-verification/report.md).
La continuación corrigió selección/latencia de cabeceras, ARIA de Kronos y espaciado
móvil: Playwright global38/38. Estado final y suites en
[cierre de integración](../../artifacts/aggressive-growth-r20-20261010/operational-fixes/report.md).
El11/oct se realizó el primer arranque supervisado con datos auténticos Paper y
cohorte FORWARD `aggressive-r20-b6675940304348228168514f1409c173`.
[Estado y comandos](../../artifacts/aggressive-growth-r20-20261010/supervised-start-20261011/report.md).
Solo SHADOW_SIMULATED; ninguna ejecución IBKR Paper autorizada o iniciada.
