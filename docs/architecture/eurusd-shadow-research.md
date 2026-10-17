# EUR/USD: investigación shadow R1/R5/R10 con US$100

Resultado económico: **NO_VIABLE_STRATEGY_FOUND**. El sistema está preparado para recopilar cotizaciones, features, señales y decisiones NO_TRADE. No se inició el runner continuo. No hay estrategias promovidas ni autorizaciones de órdenes.

Cada cartera comienza con US$100 independientes. El capital de la cuenta IBKR nunca entra en el sizing. Las tres reciben la misma oportunidad, timestamp, régimen, stop, target y precios. Sólo cambia el presupuesto de riesgo; la exposición con costos/reservas está financiada dentro de US$100, sin aumentar apalancamiento.

| Perfil | Riesgo previsto inicial máximo | Presupuesto diario | Exposición máxima |
|---|---:|---:|---:|
| EURUSD_R1 | min(1% equity, US$1) | US$2 | US$100 incluyendo costos reservados |
| EURUSD_R5 | min(5% equity, US$5) | US$5 | US$100 incluyendo costos reservados |
| EURUSD_R10 | min(10% equity, US$10) | US$10 | US$100 incluyendo costos reservados |

Se conserva en cada cartera el presupuesto acumulado US$20: las ganancias no reponen pérdidas consumidas. FIRST_LOSS_STOPS_DAY bloquea entradas después de la primera pérdida o break-even reconciliado. La fecha usa America/Santo_Domingo. Una posición o resultado pendiente mantiene el bloqueo incluso al cambiar de día. Los límites son presupuestos previstos: un gap puede excederlos. El simulador registra esos excesos.

## Evidencia y economía

La consulta de lectura Paper confirmó identidad exacta de AccountBinding, posiciones/órdenes cero y reconciliación del ciclo EUR/USD anterior. La observación del **7 de octubre de 2026, 05:58:52 UTC** tuvo BID 1.12315 / ASK 1.12317, spread 0.00002, tipo LIVE y mercado OPEN. El timestamp es de recepción del callback; no se inventa un timestamp de bolsa. Esa cotización ya no sirve para una futura orden.

| Condición | Evidencia | Estado |
|---|---|---|
| Identidad Paper | AccountBinding + managedAccounts, coincidencia completa | VERIFIED |
| Posiciones y órdenes | Callbacks terminados; sin inventario ni órdenes | VERIFIED en la consulta |
| Comisión BUY / SELL | Ciclo Paper previo de 100 EUR: US$2 / US$2, ambas registradas | VERIFIED para ese ciclo simulado por IBKR |
| Tarifas en otros tamaños | Mínimo público US$2 por lado; condiciones particulares no expuestas | ESTIMATED conservador / UNKNOWN efectivo |
| Tamaño/incremento declarados | ContractDetails: 0.01 EUR / 0.01 EUR | VERIFIED metadata; no prueba de permiso |
| Lote estándar IDEALPRO | Mínimo público 20.000 EUR | VERIFIED público; odd lot es distinto |
| Odd lot | 100 EUR se ejecutaron en el ciclo anterior | VERIFIED sólo ese ciclo; otros tamaños UNKNOWN |
| Margen de una nueva orden | La cuenta plana reporta margen total cero | UNKNOWN: no equivale a margen requerido cero |
| SettledCash / fondos por orden | No expuestos de forma suficiente por estas consultas | UNKNOWN |
| Permiso Forex especulativo | La existencia del contrato no acredita el permiso | UNKNOWN |
| Protección efectiva | El bracket anterior acabó sin hijos activos | UNKNOWN para una nueva operación |

Fuentes públicas consultadas: [comisiones de spot currencies](https://www.interactivebrokers.com/en/pricing/commissions-spot-currencies.php) y [mínimos estándar](https://investors.interactivebrokers.com/en/?f=5479). Una conversión de moneda o un permiso para convertir efectivo no prueban acceso a Forex especulativo.

El modelo conserva US$4 por ciclo, spread de estrés del archivo auténtico **0.0014 USD/EUR**, slippage de **0.00045 USD/EUR** y gap reservado de **0.00005 USD/EUR**. Spread/slippage/gap son estimaciones conservadoras, no reconstrucción de todos los fills históricos. El spread LIVE observado se registra por separado; nunca se transforma la falta de datos en fricción cero.

R1 es imposible con ese escenario: las comisiones solas son cuatro veces su presupuesto. R5/R10 permiten presupuestar algunos tamaños, pero sus targets no cubren los costos bajo exposición financiada 1×. Aun la cota favorable anterior, ignorando spread/slippage/gaps y riesgo, sólo daba US$0.22464 de target bruto máximo para Trend, US$0.28610 para Pullback y US$0.27230 para Mean Reversion frente a US$4 de comisión.

Ejemplo explícitamente favorable **histórico**, no señal vigente ni recomendación: Trend del 31/07/2026 17:00 UTC, elegido para comprobar su mayor target relativo:

| Perfil | Cantidad calculada EUR | Notional USD | Riesgo total USD | Costos USD | Target bruto USD | Target neto conservador USD | Decisión |
|---|---:|---:|---:|---:|---:|---:|---|
| R1 | 0 | 0 | — | comisión prevista 4 | — | — | NO_TRADE: comisión > presupuesto |
| R5 | 83.16 | 95.83525 | 4.30741 | 4.15385 | 0.22412 | -3.93389 | NO_TRADE: target no cubre costos |
| R10 | 83.16 | 95.83525 | 4.30741 | 4.15385 | 0.22412 | -3.93389 | NO_TRADE: target no cubre costos |

## Señal y validación

La referencia inicial es **Trend following V1**, intacta y sin promoción:

`StrategyVersion = 9860cd16f4f43d38ca7c29f161aea82e17dea100da48bb78259457cc31133211`

`StrategyId = research-d-trend-1e2784bd53f4`

No se eligió por rentabilidad. Se reutilizan sus EMA, confirmación 1H/contexto 4H, ATR stop/target y salidas originales. Las pruebas comparan decisiones con ResearchExitSemantics C#, incluyendo ambigüedad stop/target y gaps. Los fills OHLC son estimados, no ejecuciones del broker. La prueba final bursátil continúa sellada.

El archivo auténtico EUR/USD comprende 03/04–03/10/2026. Desarrollo hasta 03/08 y validación desde esa fecha. Se ejecutaron **45 escenarios**: tres estrategias originales × tres perfiles × desarrollo/validación/tres ventanas walk-forward. Las ventanas se financian independientemente; no sumar sus resultados como una cartera continua. Esta validación ya había sido examinada y no se presenta como una prueba final nueva.

| Estrategia | Señales desarrollo / validación por perfil | Rechazo económico R1 en validación | Rechazo económico R5/R10 en validación | Entradas |
|---|---:|---:|---:|---:|
| Trend V1 | 140 / 78 | 20 por comisiones | 20 por target insuficiente | 0 |
| Pullback V1 | 902 / 436 | 266 por comisiones | 266 por target insuficiente | 0 |
| Mean Reversion V1 | 17 / 6 | 6 por comisiones | 6 por target insuficiente | 0 |

Los demás casos son señales originales NO_TRADE por calentamiento/contexto/etc. Con cero operaciones, P&L y comisiones realizadas son cero contable; win rate, expectativa, profit factor, riesgo de ruina y calibración forward son **no evaluables**. No constituyen resultados favorables.

## Probabilidad, EV y Sol

Python calcula EMA/RSI/MACD/ATR, momentum, volatilidad, estructura de máximos/mínimos, soporte/resistencia, spread, sesión y geometría stop/target. La liquidez y el riesgo macro permanecen UNKNOWN sin fuentes auténticas. No se envían gráficos ni credenciales a Sol.

Las etiquetas históricas evalúan TP antes de SL con precedencia conservadora y salidas originales. Las salidas de regla son riesgos competitivos: no desaparecen del denominador para inflar acierto; para EV se consideran pérdida conservadora. Sólo se usan resultados resueltos antes del timestamp de la señal y comparables por estrategia, lado y régimen.

La estimación exige 100 muestras, 30 días, tres ventanas terminadas, riesgo competitivo ≤10% y comprobaciones prequential de las últimas tres ventanas cronológicas: ≥10 predicciones por ventana, Brier ≤0.25 y diferencia tasa prevista/observada ≤0.15. Se informa Wilson 95% como referencia IID, con dependencia explícita; no es una garantía estadística independiente. Tres nuevas ventanas forward de 30 días quedan preregistradas. No se eligen ventanas por su beneficio.

Las 43 etiquetas históricas Trend se dividen en grupos de 0–19 muestras. Todas quedan en **INSUFFICIENT_EVIDENCE**. Los resultados contrafactuales forward pueden aportar nuevas etiquetas aun cuando la señal sea NO_TRADE, pero no se contabilizan como trades o éxitos de estrategia. La misma señal cerrada en dos carteras se cuenta una sola vez para probabilidad. Se registran buckets 50–55, 55–60, 60–65, 65–70, 70–75, 75–80 y 80%+.

Antes de admitir: comisiones+spread+slippage+stop+gap dentro del presupuesto; target neto positivo; costos ≤50% del target bruto; reward/risk neto ≥1; y:

`EV = P(TP) × target neto − (1−P(TP)) × pérdida total prevista`.

También debe ser positivo usando el límite inferior del intervalo, y Sol debe recomendar TRADE. Sol sólo puede vetar: su JSON no admite probabilidades/confidence, cambios de parámetros ni acciones de ejecución. Un fallo, falta de presupuesto o respuesta incierta significa NO_TRADE. Costos/insuficiencia de datos se comprueban antes de gastar tokens.

La evaluación contextual usa Responses API con JSON Schema estricto, GPT-6.1 Sol, sin herramientas, máximo 512 tokens de salida y 6.000 bytes de contexto. El presupuesto se reserva durablemente antes de llamar; ante timeout/HTTP/permisos/facturación se conserva la reserva y se abre el circuito sin reintento. Por defecto **US$0 y cero llamadas**. [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs) y [modelo](https://developers.openai.com/api/docs/models/gpt-6.1-sol). Se usa una cota conservadora 5/15 US$/millón para reservar; no se modifica el pricing de sesiones anteriores.

Cada 100 oportunidades shadow cerradas y distintas se prepara un handoff hash-linked para AI_Strategy_Researcher. La memoria distingue SIMULATED_SHADOW de BROKER_FILL y preserva research-openai-001/002/003 y DEFER_RESEARCH. Las recomendaciones Forex siguen siendo propuestas de investigación: el esquema existente de candidatos bursátiles no se amplía para ejecutar Forex. Nada adopta automáticamente cambios ni inicia una investigación facturable.

## Persistencia e inicio

PostgreSQL `research_shadow.events` es un journal separado, append-only, con cadenas hash y replay idempotente. El rol Paper sólo tiene SELECT/INSERT en esa tabla. Una outbox SQLite permite recuperar un fallo de persistencia; ninguna nueva decisión se admite hasta igualar la cabeza PostgreSQL. Un journal local perdido o discordante suspende; reiniciar no borra pérdidas. Los originales de mercado se archivan con hashes. Los hashes del motor/configuración sellan el estudio: cambios requieren una nueva preregistración conservando la anterior.

Estudio preparado, **no iniciado**, presupuesto OpenAI **US$0**:

`eurusd-shadow-3786f123021b41e491fc1c9a0b29e6fd`

Desde la raíz, con TWS Paper conectado al endpoint protegido y PostgreSQL local preparado:

```powershell
# Iniciar las tres carteras simultáneamente; captura continua, sin órdenes ni llamadas OpenAI.
.\scripts\eurusd-shadow-research.ps1 -Action Run -Study eurusd-shadow-3786f123021b41e491fc1c9a0b29e6fd

# Consultar progreso en otra terminal.
.\scripts\eurusd-shadow-research.ps1 -Action Status -Study eurusd-shadow-3786f123021b41e491fc1c9a0b29e6fd

# Detener este observador; conserva inventario shadow y evidencia.
.\scripts\eurusd-shadow-research.ps1 -Action Stop -Study eurusd-shadow-3786f123021b41e491fc1c9a0b29e6fd

# Reproducir el backtest aislado; crea un identificador nuevo.
.\scripts\eurusd-shadow-research.ps1 -Action Comparison
```

El runner procesa cotizaciones cada 30 segundos y despierta en fronteras de velas. Una entrada fuera de los cinco segundos de su siguiente apertura se rechaza. No rellena entradas anteriores al inicio. Fallos de identidad, conexión o persistencia suspenden y se registran; no existe un reintento de órdenes. Sin una señal válida registra NO_TRADE. El estudio Ford preregistrado permanece separado.

Para PostgreSQL: `.\scripts\paper-lab-database.ps1 -Action Prepare`. No levanta EmergencyStop ni autoriza órdenes. Para la prueba R1 original: `.\scripts\eurusd-paper-research.ps1 -Action Backtest`.

## Incidente y requisitos posteriores para broker

El incidente original transmitió BUY1/TP2/SL3 antes de una comprobación EUR que se activó incorrectamente por existir una intención sin fill. Hubo finalmente BUY 100 EUR a 1.12185 (permId 1520205604), hijos cancelados y pérdida de protección. La recuperación independiente cerró el inventario; hoy el journal muestra CLOSED, dos fills/dos comisiones y reserva activa cero. El campo histórico reserve=10 no es una reserva vigente. La excepción EUR inicial ya no habilita otra entrada.

Los controles existentes corregidos exigen gates completos antes de SEND_PENDING/placeOrder; ACK/0 fills conserva la ruta pre-fill excepcional; el primer exec real, incluso parcial, exige reconciliación estricta. Un fallo post-envío nunca autoriza repetir a ciegas. Sólo se reduce inventario propio confirmado y las reservas no se liberan hasta posición cero y ausencia de órdenes pendientes.

**No existe ruta BROKER_EXECUTION en este laboratorio.** Una futura implementación necesita autorización Paper independiente, selección de un único perfil y asociación inequívoca de los fills a la oportunidad común. Los otros dos perfiles seguirían shadow para evitar netting. La recalibración debe conservar tarifas/slippage observados frente a estimados y jamás aplicar esos resultados retroactivamente como fills reales.

Antes de siquiera autorizar: verificar en TWS/Client Portal **Paper** el permiso Forex especulativo, tamaños odd lot, restricciones y fondos; revisar estimaciones de margen y comisión mediante Order Preview sin Transmit, conservándolas como ESTIMATED. La aceptación efectiva de protección/partial fills sólo puede acreditarse con un protocolo diagnóstico supervisado separado y recuperación reduce-only autorizada. Además, resolver la incompatibilidad económica y con el RiskEngine productivo 0.5% mediante mecanismos experimentales expresos; este laboratorio no lo altera.

Antes de dinero real: evidencia fuera de muestra nueva, suficientes trades netos e intervalos, expectativa/PF positivos y robustez a costos/gaps; forward independiente; riesgo de cola y drawdown aceptables; permisos, financiación y protecciones efectivos; auditoría y autorización Live independiente. Un acierto alto o equity final positivo por sí solos no cumplen esos requisitos. Live permanece bloqueado.

## Verificación y componentes

**1.408 pruebas aprobadas: 1.026 Python + 382 C#, cero omitidas.** Compilación cero errores/advertencias; 67 pruebas EUR/USD nuevas y siete PostgreSQL C# nuevas. Se ejecutaron consultas Paper de lectura, comparación de 45 escenarios y validación de heads PostgreSQL. Ninguna llamada real OpenAI ni orden durante esta implementación. EmergencyStop y los 70 archivos protegidos comprobados permanecen intactos.

Archivos nuevos: dos configuraciones (`eurusd-paper-research-100.json`, `eurusd-shadow-research.json`); módulos `eurusd_paper_research.py`, `eurusd_shadow_research.py`, `simulation_memory.py`; scripts de ambos laboratorios; `EurusdShadowCommand.cs`, `EurusdShadowStore.cs`, migración `006_eurusd_shadow.sql`; pruebas Python EUR/USD y `EurusdShadowStoreTests.cs`; este documento. Integraciones acotadas: `ai_strategy_researcher/{memory,data,providers}.py`, `TradingAgent.Api/Program.cs` y `paper-lab-database.ps1`. Los artifacts se conservan con identificadores nuevos.

La fuente/API compilada cambió al añadir el journal. Un protocolo R10 de Ford vinculado al hash de despliegue anterior debe volver a revisarse antes de una futura autorización; no se actualizó ni reutilizó automáticamente.

Evidencia verificable: `artifacts/research/eurusd-paper-research-100/preparation-20261007T024145Z/metrics-release-verification.json`; comparación final: `artifacts/research/eurusd-shadow/comparison-4fb4140f0e2749989a161d3c406c4ba8/report.json`. Las verificaciones anteriores se conservaron. PostgreSQL Paper quedó disponible; sólo se detuvo el cluster de pruebas. El replay lento inicial se marcó INCOMPLETE y se conservó. Una regresión de contexto Sol se corrigió compactando, sin ampliar su límite de 24 KB.
