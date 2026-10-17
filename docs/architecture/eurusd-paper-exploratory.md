# EURUSD_PAPER_EXPLORATORY — cohorte de ejecución

La preparación supervisada v2 del 8 de octubre y sus bloqueos actuales se documentan
en [EUR/USD Paper supervisado](eurusd-paper-exploratory-supervised-20261008.md).
Este informe conserva la evidencia y el comportamiento del protocolo v1 anterior.

Preparación del 7 de octubre de 2026. No autorizada, no ejecutada. EmergencyStop
continúa activo y Live bloqueado. No se realizaron llamadas OpenAI.

## Cohorte y baseline

Cohorte final: `eurusd-explore-c89382197fc14b94b8d25b9c13299131`.
Las preparaciones anteriores se conservan, incluida `eurusd-explore-1716ac2ce4b5462ab7a2b3dd73965e09`. La preparación preliminar `eurusd-explore-98eac04b916448398011847a41670683`
permanece conservada; su versión de implementación anterior no debe ejecutarse.

Baseline técnica: Trend V1, `research-d-trend-1e2784bd53f4`, StrategyVersion
`9860cd16f4f43d38ca7c29f161aea82e17dea100da48bb78259457cc31133211`.
No existe un ganador económico validado entre las estrategias investigadas.
Se conserva Trend por su identidad, configuración y semántica de salida existentes;
no se seleccionó por el mayor beneficio histórico. No se modifican indicadores,
señales, distancias ATR ni reglas de salida originales.

Los precios ejecutables se cuantizan al tick declarado: entrada BUY hacia arriba,
stop hacia abajo y target hacia abajo. Se conservan los niveles originales y los
cuantizados, y se recalcula el riesgo; esto no es una optimización de parámetros.
La primera implementación limita entradas a LONG, plenamente financiadas, sin
apalancamiento. Las señales SELL originales quedan registradas como rechazadas.

Todo resultado se etiqueta `EXPLORATORY_NOT_VALIDATED`.
`STRATEGY_VALIDATION_GATE=NO_VIABLE_STRATEGY_FOUND` permanece. El
`PAPER_EXPLORATION_GATE` permite estudiar una señal no rentable solamente cuando
pasan las comprobaciones de riesgo y ejecución y existe autorización protegida.
No transforma esa operación en evidencia de rentabilidad ni aprobación Live.

## Rotación e inventario

R1 → R5 → R10 → R1. Una cuenta, una posición neta y una intención activa.
No se avanza por NO_TRADE, rechazo, ACK, timeout, cancelación sin fill o resultado
pendiente. Sólo se avanza tras inventario cero confirmado por dos lecturas,
órdenes vacías, órdenes propias terminales con permId, comisiones USD completas
y liberación de la reserva. Máximo tres cierres broker por día, globalmente.

Cada cartera comienza con US$100. Los porcentajes 1/5/10 se aplican a equity
actual y no aumentan después de pérdidas. Se conserva exposición y reservas
combinadas ≤US$100 y el presupuesto acumulado de pérdidas US$20 por perfil.
Las ganancias no restauran pérdida consumida. Primer cierre neto ≤0 bloquea ese
perfil hasta el siguiente día de America/Santo_Domingo. Un incidente de ejecución
bloquea la cohorte completa y enclava la emergencia Paper.

**R1 no puede ejecutar actualmente:** US$4 de comisiones estimadas a partir del
ciclo anterior exceden su riesgo US$1, antes de considerar movimiento de precio.
El rotador no salta automáticamente a R5. Cambiar el universo de perfiles de una
cohorte requiere una decisión posterior explícita; no se implementa un salto
silencioso ni un aumento de riesgo.

## Verificación auténtica y sizing

Inspect final:
`artifacts/research/eurusd-exploratory/eurusd-explore-c89382197fc14b94b8d25b9c13299131/inspect-9074f799b2954a5c84c062bd790d2964.json`.

Cotización recibida **2026-10-07 18:24:10 UTC**, BID 1.11981 / ASK 1.11982,
LIVE y OPEN en ese instante. El calendario proviene de
`IBKR historicalSchedule + contractDetails.tradingHours`, sin plantilla provisional.
Esta cotización caduca para ejecución; Run exige otra cotización contemporánea.

La tabla usa las distancias de una señal Trend auténtica del **2026-09-10
02:30 UTC**, repriciada exclusivamente para estimar factibilidad. **No es una
señal actual ni una propuesta de orden.** Los cálculos provienen del módulo de
riesgo exploratorio separado; RiskEngine productivo y su límite 0.5% no cambian.

| Perfil | Presupuesto | EUR teóricos | Notional USD | Fricción y gap modelados | Pérdida prevista hasta stop | Exposición + reserva | Target neto modelado |
|---|---:|---:|---:|---:|---:|---:|---:|
| R1 | 1.00 | 0 | 0 | Comisiones 4.00 > riesgo | NO_TRADE | 0 | No evaluable |
| R5 | 5.00 | 85.54 | 95.7920 | 4.2010 | 4.2651 | 99.9930 | −4.1197 |
| R10 | 10.00 | 85.54 | 95.7920 | 4.2010 | 4.2651 | 99.9930 | −4.1197 |

R5 y R10 tienen igual cantidad por el techo de exposición; presupuesto de riesgo
no equivale a notional ni a obligación de consumirlo. Stop cuantizado 1.11910,
target 1.12080, límite BUY modelado 1.11985. Apertura/cierre US$2 cada lado son
**observaciones del único ciclo anterior de 100 EUR**, extrapoladas
conservadoramente; la tarifa efectiva para 85.54 EUR sigue UNKNOWN.
Spread de estrés 0.0014 USD/EUR, slippage 0.00045 por lado, gap presupuestado
0.00005. El spread observado 0.00001 no sustituye el escenario conservador.
El presupuesto previsto no garantiza pérdida máxima: gaps, financiación no
acotada y fallos de protección pueden producir pérdidas superiores.

VERIFIED: identidad exacta de AccountBinding, posiciones cero, órdenes vacías,
journal anterior conciliado, reservas y comisiones pendientes cero, cotización
usable y calendario auténtico. En la consulta sólo se expuso `InitMarginReq`;
no es margen incremental para esta orden. No se obtuvieron SettledCash ni
AvailableFunds verificables mediante esta ruta.

UNKNOWN: permisos especulativos Forex de esta cuenta Paper, tamaño/incremento
efectivamente aceptados, margen para la cantidad, fondos liquidados, límites
de tarifas y aceptación efectiva de stop/OCA. `minSize=0.01` e incremento 0.01
son metadatos declarados del contrato, no permiso efectivo. Las cantidades son
odd lot frente al tamaño estándar IDEALPRO; la aceptación histórica de 100 EUR
no prueba aceptación de 85.54 EUR. **R5/R10 superan sólo el filtro numérico.**

## Protección, crash y recuperación

Se reutiliza el SDK oficial detrás del guard existente, con un adapter separado
que captura auxPrice real en openOrder. El bracket conserva parentId, orderRef,
OCA y transmisión conjunta. SEND_PENDING, IDs y reserva se escriben primero en
PostgreSQL, tras los gates. El mutex `paper-lab.run.lock` evita competencia con
las rutas Forex existentes. Otra cohorte con intención/reserva pendiente bloquea
admisión incluso si todavía no hay fill visible.

Un ACK con cero fills conserva la reserva y no representa exposición. La cohorte
no reutiliza la excepción EUR antigua. EUR UNKNOWN bloquea conciliación; no se
convierte en cero. Después del primer fill se exige la lectura estricta, cantidad
atribuible al journal y ACK real de ambas protecciones. No se da una protección
por verificada usando el precio solicitado. Fills parciales requieren protección
de la cantidad real; un parent remainder desconocido impide SELL de salida.

Si no se confirma protección en diez segundos desde el primer fill, se enclava
emergencia y se inicia recuperación propia. Un broker UNKNOWN impide mutaciones
y mantiene observación/reconciliación; no permite una orden ciega de recuperación.
La recuperación cancela únicamente IDs persistidos propios, espera ACK y
conciliación de esas cancelaciones y transmite un único SELL IOC del LONG restante.
Nunca coexiste ese SELL independiente con hijos pendientes. Parciales/timeout no
reutilizan una orden; otro intento necesita nueva autorización y confirmación de
que el anterior terminó. Inventario cero no genera SELL. No se libera reserva con
comisiones pendientes ni se abandona la gestión por una parada de nuevas entradas.

La autorización inicial incluye gestión explícita sólo reductora hasta 24 horas
después del vencimiento; revocación/expiry prohíben nuevas entradas. Después, o
para un nuevo IOC tras parcial, `AuthorizeRecovery` crea permiso independiente
de 30 minutos, una utilización, ligado a intención, fills BUY/permIds y cantidad
restante. No consume otra oportunidad diagnóstica ni inicia StrategyPaper.

## Twins y dashboard

El primer fill broker fija timestamp y señal. Los otros perfiles reciben fills
SIMULATED_SHADOW sólo si existe quote auténtico anterior o contemporáneo al fill,
con máximo cinco segundos de antigüedad, misma geometría y sizing propio. Falta
de quote o tamaño viable se registra NO_TRADE. No se usa una cotización posterior
a un fill recuperado tardíamente. Salidas de barras posteriores aplican la misma
precedencia conservadora de Research; una liquidación al cierre broker se marca
`PAIRED_BROKER_EXIT_TIME`, no como validación autónoma de la estrategia.

PostgreSQL conserva señal, probabilidades/EV desconocidos como null, régimen,
versiones, tamaños, precios, cotizaciones, ACKs, execId/permId, comisiones,
reservas, incidentes y resultados. El histórico de callbacks se deduplica sin
borrar pérdidas. Una corrección histórica de ejecución/comisión suspende para
revisión, no reescribe la evidencia.

Dashboard muestra próximo perfil, rol BROKER PAPER / SHADOW / WAITING / BLOCKED /
STOPPED_FOR_DAY, métricas broker separadas del antiguo Shadow y origen por fila.
P&L bruto abierto se marca con BID LIVE fresco; P&L neto definitivo permanece null
mientras falten comisiones. Sol permite consultas Paper, comisiones y slippage
con respuesta determinista del journal; no llama a OpenAI automáticamente.
Su presupuesto actual sigue cero y no puede conceder permisos ni enviar órdenes.
El observador Shadow usa su cliente original; el lector exploratorio usa 89 y
Inspect usa 90. No se detuvo ni se inició el observador original.

## Comandos y comprobaciones pendientes

Desde la raíz, consultar sin autorización ni órdenes:

```powershell
$cohort = 'eurusd-explore-c89382197fc14b94b8d25b9c13299131'
.\scripts\eurusd-paper-exploratory.ps1 -Action Inspect -Cohort $cohort
.\scripts\eurusd-paper-exploratory.ps1 -Action Status -Cohort $cohort
```

El operador debe comprobar en **TWS Paper**, con identidad completa comparada
localmente: permisos Forex, API read-only, fondos liquidados, requisitos y tamaño
para la cantidad exacta, usando un ticket de Preview sin transmitir. Preview
produce estimaciones de margen/comisiones, no comisiones reales ni ACK protector.
No copiar permisos/saldos de la cuenta real. La aceptación efectiva de protecciones
necesita evidencia de un ensayo supervisado separado con autorización explícita;
el incidente anterior con hijos CANCELLED no la proporciona. No existe aquí un
flag para sustituir ese requisito por una afirmación favorable.

Para futura autorización, el operador proporciona un JSON con siete entradas:
`permissions`, `margin`, `settled_funds`, `minimum_size`, `fees_bounded`,
`protection`, `api_write_allowed`; cada una contiene `status=VERIFIED`, `environment=PAPER_TRADING`,
`binding_id` de esta cohorte, fecha UTC de menos de 30 minutos y `source` concreta.
Margin añade `required_usd`; settled_funds `usd`; minimum_size `minimum_quantity`
y `quantity_increment`; protection `paper_ack_artifact_sha256` de evidencia real. `api_write_allowed` exige `read_only_disabled_checked=true`, comprobado expresamente en TWS Paper.
No existe un archivo preparado que afirme esos datos: permanecen UNKNOWN.

Los comandos siguientes están implementados pero **no se ejecutaron**, y no deben
usarse como una instrucción para saltar los bloqueos. Authorize solicita confirmación
local; ReviewEmergency muestra Inspect y solicita otra confirmación independiente.
Ninguno reutiliza la autorización diagnóstica vencida. Review sólo limpia la
emergencia Paper después de autorización nueva válida y conciliación flat estricta.

```powershell
.\scripts\eurusd-paper-exploratory.ps1 -Action Authorize -Cohort $cohort -Minutes 30 -EvidencePath .\operator-evidence-paper.json
.\scripts\eurusd-paper-exploratory.ps1 -Action ReviewEmergency -Cohort $cohort
.\scripts\eurusd-paper-exploratory.ps1 -Action Run -Cohort $cohort
.\scripts\eurusd-paper-exploratory.ps1 -Action Stop -Cohort $cohort
.\scripts\eurusd-paper-exploratory.ps1 -Action Revoke -Cohort $cohort
# Sólo si existe inventario propio confirmado que requiere cierre:
.\scripts\eurusd-paper-exploratory.ps1 -Action AuthorizeRecovery -Cohort $cohort -Minutes 30
.\scripts\eurusd-paper-exploratory.ps1 -Action Recovery -Cohort $cohort
# Dashboard de lectura; no inicia el rotador ni el observador:
.\scripts\start-dashboard.ps1 -SolBudget 0 -CopyAccessCode
```

No arrancar una segunda instancia del dashboard si ya escucha en 5080. El backend
necesita esta compilación para proyectar el nuevo journal. Durante la verificación
se inició y detuvo exclusivamente el servidor temporal de Playwright; el puerto
estaba libre. El frontend nunca ofrece autoridad de ejecución.

Próxima decisión: resolver tarifas/mínimos y evidencias operativas. Con costos
US$4 no existe ruta que permita R1 respetando US$1; para recopilar fills de R5/R10
habría que autorizar expresamente una cohorte distinta que omita R1. Esa modificación
no se hizo. No se requiere ni se propone aumentar automáticamente riesgo.

## Archivos y verificación

Nuevos: `eurusd_exploratory.py`, `eurusd_exploratory_runner.py`,
`eurusd_exploratory_wire.py`, `eurusd_exploratory_projection.py`, script PowerShell,
`ExploratoryStore.cs`, `ExploratoryCommand.cs`, migración 008, pruebas Python/C#.
Integración: Program, DashboardStore/Service/Realtime, SolChat, dashboard_projection,
tipos/stores y tarjetas/tabla/frontend, pruebas Vue y Playwright.
No cambia ningún archivo de la lista de 70 controles/evidencias protegidos;
también se verifica intacta la preregistración del observador Shadow original.
Logs de compilación y suites en
`artifacts/research/eurusd-exploratory/verification/`.

Resultado final: **1,626 pruebas aprobadas**, sin omitidas: 1,164 Python, 429 C#, 24 Vue y 9 Playwright. Compilación C# y frontend correctas. El bundle ECharts conserva su aviso de tamaño, sin error de compilación. Auditoría PostgreSQL: SELECT/INSERT permitidos; UPDATE/DELETE denegados en el nuevo journal. EmergencyStop=true y reservas diagnósticas=0.
