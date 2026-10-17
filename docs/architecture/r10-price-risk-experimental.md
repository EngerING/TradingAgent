# R10_PRICE_RISK_EXPERIMENTAL — 2026-10-08

Shadow iniciado: `r10-price-2c7ab9a16e0d4630924592f3fd46b703`.
Paper **BLOCKED**. Este perfil no dispone todavía de un adapter de transmisión ni
de una autorización protegida propios; no puede reutilizar los grants de R10 original.
No se transmitieron órdenes, no se concedió autorización, EmergencyStop sigue activo,
Live bloqueado y Sol LOCAL_EVIDENCE con presupuesto US$0.

## Contrato de riesgo

R10 original conserva su límite **all-in**. Este experimento separado usa un
presupuesto por movimiento del precio de `min(US$10, 10% del equity virtual)`.
Comisiones, spread, slippage, gap provisionado y financiación se presentan aparte.
Admisión Shadow: pérdida total prevista ≤US$15, costos previstos ≤US$5 y
exposición más reserva de costos ≤`min(US$100, equity virtual)`. No hay apalancamiento,
short ni más de una posición. Pérdidas acumuladas consumidas: máximo US$20, sin
restaurarlas con ganancias. Primera pérdida neta o break-even bloquea entradas
durante el resto del día de America/Santo_Domingo. Se sigue gestionando inventario.

**US$15 es un límite del cálculo previo, no una garantía de pérdida máxima.** Un
gap, un mercado sin precios utilizables o costos distintos de los estimados pueden
producir una pérdida superior. Shadow registra esa pérdida completa y no la recorta.
Los presupuestos no autorizan comisiones UNKNOWN ilimitadas en Paper.

Se conserva el stop/target técnico de Trend V1 y su versión
`9860cd16f4f43d38ca7c29f161aea82e17dea100da48bb78259457cc31133211`.
No se amplía la posición ni se ensancha el stop para forzar US$10. Es un presupuesto,
no una afirmación de riesgo utilizado. El investigador no modifica RiskEngine
productivo: este cálculo sólo admite fills internos explícitamente simulados.
Una futura transmisión necesitará un contrato experimental independiente y los
gates productivos correspondientes; no se considera aprobada por este cálculo.

## Evaluación auténtica de tamaño

Fuente: `artifacts/r10-price-risk-20261008/assessment.json`. Cotización IBKR Paper
LIVE del 2026-10-08 22:37:01 UTC: BID 1.12139, ASK 1.12142. El timestamp representa
recepción local; IBKR no expuso timestamp de origen para esos ticks.
Se usa el stop de una señal histórica auténtica del 2026-09-10, recalculado al
midpoint actual, **exclusivamente para evaluar tamaño; no es una señal vigente**.

| Concepto | Resultado USD salvo indicación |
|---|---:|
| Cantidad calculada, aceptación IBKR desconocida | 85.20 EUR |
| Midpoint de referencia | 1.121405 |
| Exposición | 95.543706 |
| Exposición + provisión de costos | 99.993926 |
| Stop técnico | 1.120729146586 |
| Target técnico | 1.122418780121 |
| PRICE_RISK alcanzable | 0.057582711 |
| Comisión de entrada estimada | 2.00 |
| Comisión de salida estimada | 2.00 |
| Spread conservador modelado | 0.119280 |
| Slippage modelado, ambos lados | 0.076680 |
| Gap provisionado | 0.004260 |
| Financiación provisionada, no tarifa verificada | 0.25 |
| ESTIMATED_ALL_IN_LOSS | 4.507802711 |
| Beneficio bruto al target | 0.086374066 |
| Beneficio neto previsto al target | −4.363845934 |

Resultado: `TARGET_DOES_NOT_COVER_COSTS`. La capacidad financiada no implica
viabilidad económica ni permiso efectivo para operar esa cantidad.
Alcanzar US$10 con este stop requeriría unos **14,796.11 EUR / US$16,592.43**:
incompatible con capital financiado de US$100. Con 85.20 EUR, una pérdida de US$10
requeriría una distancia de stop de 0.11737089 (1,173.71 pips), que cambiaría la
regla técnica y **no se aplicó**.

Los US$2 por lado proceden de un único ciclo histórico Paper de 100 EUR, no de una
tarifa verificada para 85.20 EUR. Referencia: [auditoría previa](eurusd-paper-exploratory-supervised-20261008.md).
El spread modelado mínimo es 0.0014 USD/EUR, slippage 0.00045 por lado y gap
0.00005. Son provisiones conservadoras de simulación, no ejecuciones observadas.

## Ejecución interna y trazabilidad

`MarketReader` consulta identidad exacta Paper, contrato, calendario, cuenta,
históricos 15m/60m/240m y cotizaciones con un cliente de solo lectura independiente
(91). El transporte deniega mutaciones. Los históricos auténticos mantienen sus
archivos y hashes. No hay red OpenAI ni generación de candidatos nuevos.

Una entrada exige cotización LIVE, mercado abierto, edad ≤5 segundos, señal
técnica auténtica reciente ≤5 segundos, geometría válida, costos acotados,
target superior a costos y presupuesto acumulado suficiente. Señales vencidas,
short, datos ausentes y objetivos insuficientes producen NO_TRADE persistente.
Este experimento de infraestructura no demuestra expectativa estadística positiva.

Los fills son referencias midpoint **SIMULATED_SHADOW**. Spread y slippage se
deducen una vez como costos modelados. Los gaps realizados están en el precio;
no se vuelve a descontar su provisión. Stop antes que target si ambos se alcanzan
en la misma vela completa; gaps adversos al precio de apertura. Se conserva la
salida por contexto original al siguiente precio observado. Se añade un límite
experimental de mantenimiento de 24 horas; no se afirma equivalencia exacta con
ResearchSimulation ni resultados de la estrategia original.

Journal PostgreSQL `price_risk.events`: append-only, hash encadenado, CAS,
protocolo y hash de motor inmutables. Impide borrar pérdidas, señales ya evaluadas
u operaciones; inventario pendiente no puede desaparecer. Ante escritura incierta,
se recarga el estado persistido antes de continuar. Reiniciar no reinicia equity,
pérdidas, bloqueo diario ni duplicados. Dos runners de este experimento no pueden
adquirir simultáneamente el mismo lock.

La orden Stop es persistente: bloquea entradas y, si existe inventario Shadow,
continúa hasta obtener un precio utilizable para cerrarlo; no inventa un precio
de salida cuando está desconectado. No cancela ni modifica órdenes IBKR.

PostgreSQL → proyección Python → API `/api/ui/dashboard` → `priceRisk.updated`
por SignalR → Pinia → tarjeta independiente y feed de ciclo de vida. Un heartbeat
ausente/futuro o antiguo >120 segundos se marca STALE. Los costos ausentes son
UNKNOWN, nunca cero. Sol explica evidencia local y preserva la comparación original
R1/R5/R10; las consultas específicas incluyen «¿Cuánto arriesga realmente R10?»
o «R10 Experimental».

## Estado operativo observado

A las 22:46 UTC, revisión 18: SHADOW_RUNNING, cotizaciones LIVE/OPEN, cero cierres y cero
posiciones virtuales. Se registraron oportunidades sin señal vigente como
`NO_CURRENT_AUTHENTIC_SIGNAL`; no se fabricaron operaciones. El P&L realizado
de una operación inexistente sigue sin estar disponible.

Los procesos originales Shadow, Cost-Aware y Kronos se conservaron. Kronos
continúa **KRONOS_UNAVAILABLE**, con forecast persistido de 09:00:39 UTC y
predicción obsoleta. No se le atribuye acuerdo con señales nuevas ni probabilidad
calibrada. Su proceso activo no demuestra inferencia saludable.

## Gates Paper y revisión humana

| Condición, consulta del 22:36–22:37 UTC | Evidencia |
|---|---|
| Identidad exacta AccountBinding / managedAccounts | VERIFIED, coincidencia exacta Paper |
| Posiciones y órdenes | VERIFIED: consultas completas, ambas vacías |
| Datos | VERIFIED: LIVE/OPEN en la observación indicada; renovar antes de cualquier ensayo |
| Mínimo/incremento | 0.01 declarados por contrato; aceptación efectiva UNKNOWN |
| Permiso especulativo Forex | UNKNOWN; existencia del contrato no es permiso |
| SettledCash | UNKNOWN: sin fila disponible; no sustituir por saldo ficticio |
| Margen incremental de la orden | UNKNOWN; margen agregado 0 no lo demuestra |
| Fees y financiación para la cantidad | ESTIMATED/UNKNOWN; sin cota efectiva verificada |
| Aceptación de bracket/stop/OCA | UNKNOWN; los hijos históricos cancelados no la verifican |
| Autorización del perfil nuevo | NO CONCEDIDA; ruta específica todavía no implementada |

El operador debe comprobar en **TWS Paper**, con la cuenta vinculada visible,
los permisos Forex especulativos (no conversión de divisas), fondos liquidados,
restricciones de cantidad y el preview/What-If del contrato, cantidad y tipo de
orden exactos. Un preview sólo ofrece estimaciones de margen/comisión; no demuestra
protección aceptada. Guardar evidencia con cuenta Paper, fecha UTC, contrato,
cantidad, moneda, costos y limitaciones. No usar permisos de la cuenta real.

Protocolo futuro de primer ensayo, aún bloqueado:

1. Resolver las evidencias anteriores y repetir conciliación completa, incluida
   reserva/intención histórica. Revisar el incidente EUR/USD y su cierre recuperado.
2. Implementar y probar el adapter/grant exclusivo `R10_PRICE_RISK_EXPERIMENTAL`,
   vinculados a identidad, experimento, versión, cantidad calculada, US$100 financiados,
   precio-riesgo ≤US$10, all-in previsto ≤US$15 y costos acotados. No reutilizar
   `ExecutionDiagnostics Run` ni autorizaciones anteriores.
3. Presentar ese plan concreto al operador: una apertura LONG, un cierre sólo del
   inventario propio, una autorización de un uso y ≤30 minutos. Etiquetar siempre
   diagnóstico de infraestructura; no éxito de estrategia.
4. Revisión humana protegida de EmergencyStop y autorización explícita separada.
   Este trabajo no concede ninguna de ambas.
5. Si la protección sólo puede verificarse enviando Paper, aprobar previamente
   un ensayo supervisado, ACK exigido, timeout acotado y recuperación close-only
   ya probada. Ante fill parcial/ACK incierto, reconectar y conciliar antes de
   modificar/reintentar; jamás SELL mayor que el LONG propio confirmado.
6. Cerrar, conciliar inventario cero y ausencia de órdenes; registrar comisiones
   verificadas o pendientes, P&L bruto y neto definitivo cuando corresponda.
   Liberar reserva sólo con conciliación final. Mantener emergencia al terminar.

No se entrega un comando Authorize/Run Paper para este perfil: **no existe aún
una ruta autorizable implementada**. El bloqueo explícito es
`R10_PRICE_RISK_PAPER_ADAPTER_NOT_RELEASED`. No se sustituye silenciosamente por
el ejecutor de R10 original.

## Comandos Shadow desde la raíz

El runner ya está iniciado. No lanzar un duplicado:

```powershell
$experiment = 'r10-price-2c7ab9a16e0d4630924592f3fd46b703'
.\scripts\r10-price-risk.ps1 -Action Status -Experiment $experiment
.\scripts\r10-price-risk.ps1 -Action PaperPlan -Experiment $experiment

# Iniciar/recuperar el mismo journal si el proceso cayó; no resetea pérdidas.
.\scripts\r10-price-risk.ps1 -Action Run -Experiment $experiment

# Detención persistente del experimento nuevo, conserva la evidencia.
.\scripts\r10-price-risk.ps1 -Action Stop -Experiment $experiment
```

Run no elimina un Stop persistente ni reinicia presupuestos. No borrar marcadores
o crear otro experimento para eludir pérdidas; una reanudación posterior al Stop
requiere una revisión explícita del estado. Estos comandos no afectan a los
otros observadores ni conceden autoridad Paper.

## Verificación y archivos

Resultados finales y manifiesto: `artifacts/r10-price-risk-20261008/verification.json`
y `files.json`. Pruebas Python, C#, Vue y Playwright incluyen los recorridos
preexistentes: **1.318 Python + 478 C# + 80 Vue + 34 Playwright = 1.910 aprobadas**,
sin fallos, omisiones o reintentos en los resultados finales. Compilación .NET
sin warnings/errores; Vite conserva su aviso de chunk mayor a 500 kB.
La primera pasada de Playwright detectó una comparación Sol mal
enrutada; se conservó su log, se corrigió y se repitió el recorrido completo.
Las 74 huellas de archivos protegidos permanecen iguales.

Componentes nuevos: configuración JSON, motor/runner Python de simulación,
wrapper PowerShell, journal/migración C#, comando stdin, respuesta local Sol,
tarjeta Vue y pruebas en los cuatro niveles. Integraciones modificadas:
Program, DashboardStore/Service/Realtime, proyección Python, tipos/Pinia/feed,
Home y Experiments. No hay cambios en RiskEngine productivo, H40, R10 original,
AccountBinding, autorizaciones o EmergencyStop.

Graphify se consultó antes del código. Su índice local de 424 nodos permitió
localizar Risk/Account/Broker/PostgreSQL, pero no cubre las incorporaciones
Shadow/Vue recientes; se ampliaron búsquedas dirigidas y se registró feedback.
Tokens facturables de OpenAI/Graphify/Sol consumidos por este trabajo: **0**.
