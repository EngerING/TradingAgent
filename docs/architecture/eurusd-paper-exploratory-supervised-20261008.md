# EUR/USD Paper exploratory — preparación supervisada, 2026-10-08

**Resultado: BLOCKED, PREPARED_NOT_AUTHORIZED.** Cero órdenes enviadas durante esta
implementación, cero autorizaciones concedidas, EmergencyStop activo, Live bloqueado,
Sol US$0 / LOCAL_EVIDENCE_ONLY. No existe una estrategia económicamente validada.
No se declara IBKR Paper preparado para transmitir mientras persistan gates UNKNOWN.

La nueva preparación aceptada es `eurusd-explore-fc633912e01a491796bb420210054aaa`.
Es **PAPER_EXECUTION_DIAGNOSTIC**, protocolo v2, una apertura máxima y autorización
de hasta 30 minutos. R1 se salta con motivo persistente; siguiente perfil revisable:
EURUSD_R5. Esto no autoriza R5 ni convierte la prueba en señal de estrategia.
Todas las cohortes anteriores permanecen conservadas. La documentación del
[protocolo anterior](eurusd-paper-exploratory.md) describe v1; su rotación CLOSED_ONLY
se mantiene para reconstrucción histórica, pero sus grants no habilitan el protocolo v2.
La cohorte `eurusd-explore-891d6ef22a9f4470860d66f630bf452a` también se conserva;
quedó supersedida al corregir el resumen de errores del CLI. Ninguna recibió autorización.

## Auditoría del incidente EUR/USD

Fuente: journal Paper PostgreSQL revisión 96, las consultas completas del Inspect
aceptado y [recuperación histórica](paper-pending-bracket-recovery.md).
Artefactos: `artifacts/eurusd-exploratory-preparation-20261008/legacy-audit.json`,
`legacy-events-audit.json`, `assessment-delivery.json`.

| Orden | permId | Resultado confirmado |
|---|---:|---|
| BUY 1 | 1520205604 | 100 EUR @ 1.12185, fill 2026-10-05 20:20:22 UTC |
| Target SELL 2 | 1520205605 | Cancelled |
| Stop SELL 3 | 1520205606 | Cancelled |
| Recovery SELL 4 | 1520205617 | 100 EUR @ 1.12247, fill 2026-10-06 01:42:36 UTC |

BUY execId `0000e215.6ac30098.01.01`, SELL execId `0000e215.6ac416c5.01.01`.
Comisiones: US$2 BUY + US$2 SELL, ambas USD y registradas. P&L bruto US$0.062;
neto **−US$3.938**. Inventario histórico cero, sin comisiones/intenciones pendientes,
reserva diagnóstica cero. La pérdida consumida y el uso diagnóstico se conservan.
No debe registrarse este ciclo como éxito predictivo ni restaurar presupuesto perdido.

La causa original fue `EUR_CASH_RECONCILIATION_UNAVAILABLE`: la transmisión del
bracket sin fill se trató prematuramente como condición post-fill; cancelaciones
locales ApiCancelled/permId=0 no demostraban cancelación del servidor y un BUY tardío
se recuperó posteriormente. El registro también conserva el aviso IBKR 399.
La excepción EUR histórica fue consumida y no se reutiliza. Ahora las cuatro fuentes
de cash devolvieron EUR **0.00 explícito**: no se dedujo cero de una fila ausente.
EmergencyStop continúa activo aunque el inventario se haya cerrado. Requiere revisión
humana del incidente y una autorización nueva, independiente y protegida.

## Lecturas auténticas y matriz de capacidades

Inspect/Assess de 2026-10-08 11:43 UTC: identidad exacta Paper comprobada internamente
contra AccountBinding y la sesión protegida; puerto 7497, loopback, proceso TWS
verificado. EUR/USD CASH IDEALPRO conId 12087792. No se publica la cuenta completa.
Posiciones y órdenes abiertas vacías, journal anterior conciliado. El acceso al
PostgreSQL Paper local 55433 y al journal exploratorio append-only funcionó.

| Condición | Estado | Evidencia o limitación |
|---|---|---|
| AccountBinding, identidad Paper y proceso | VERIFIED | Coincidencia completa local; no basta prefijo DU ni puerto |
| Inventario y órdenes actuales | VERIFIED al Inspect | Dos lecturas de exposición, cash completo, cero órdenes |
| Journal histórico y reserva | VERIFIED | Revisión 96, cero pendientes; nuevas cohortes sin inventario |
| Calendario | VERIFIED | IBKR SCHEDULE + contract trading hours; timestamps UTC |
| Cotización | VERIFIED en ese instante | LIVE, OPEN, BID 1.11810 / ASK 1.11812, 11:43:46.882812 UTC |
| Timestamp de precio | Limitación explícita | Receipt del callback local; source_timestamp del mercado ausente |
| AvailableFunds | VERIFIED, valor informado | US$1,000,089.01 ficticios; jamás capital lógico ni permiso de riesgo |
| SettledCash | UNKNOWN | Tag solicitado; no recibido. CashBalance no lo sustituye |
| AccountType | VERIFIED = INDIVIDUAL | No prueba que el régimen sea CASH o MARGIN |
| Init/Maint margin global | VERIFIED = 0 | No demuestra margen incremental de la orden propuesta |
| Permiso efectivo Forex especulativo | UNKNOWN | ContractDetails no lo demuestra; conversión no es especulación |
| Margen incremental y restricciones | UNKNOWN | BuyingPower no demuestra autorización ni apalancamiento permitido |
| Mínimo/incremento efectivo | UNKNOWN | Contrato declara 0.01 EUR; aceptación de esa cuenta/tamaño no verificada |
| Tarifas efectivas acotadas | UNKNOWN | US$2/lado observado sólo en el ciclo histórico de 100 EUR |
| Protección efectiva del nuevo ensayo | UNKNOWN | No hay ACK nuevo de stop/target ni prueba de aceptación |
| API Read-Only y recuperación supervisada | Verificación humana pendiente | No se modifica TWS automáticamente |

La captura adicional de accountSummary recupera tags antes de que el parser heredado
de cash los filtre. Conserva callback End, errores, moneda y cuenta; restaura el
callback original. La ausencia de un tag permanece UNKNOWN.

Inspect no llama placeOrder ni What-If. El mecanismo What-If existente está limitado
a Ford y no se reutiliza silenciosamente para EUR/USD. La API de IBKR realiza el
credit preview mediante placeOrder con whatIf=true: no es una ejecución de mercado,
pero tampoco una lectura ordinaria de contrato. En esta fase no se invocó.
Una estimación What-If no acredita permisos ni aceptación de protecciones ni un tope
de comisión. Véase [IBKR What-If / margin](https://interactivebrokers.github.io/tws-api/margin.html).

La tarifa pública Forex indica un mínimo US$2 por orden en el primer tramo;
no constituye una comprobación de las condiciones efectivas de esta cuenta.
Fuente: [IBKR Spot Currencies](https://www.interactivebrokers.com/en/pricing/commissions-spot-currencies.php).
No se asumieron caps, exenciones, permisos o mínimos favorables.

## Capital y costos: R1/R5/R10

Baseline técnica conservada: Trend V1 `research-d-trend-1e2784bd53f4`, versión
`9860cd16f4f43d38ca7c29f161aea82e17dea100da48bb78259457cc31133211`.
Se conserva su configuración, entradas y semántica de salida. No fue seleccionada
por rentabilidad: `STRATEGY_VALIDATION_GATE=NO_VIABLE_STRATEGY_FOUND` permanece.

El cálculo siguiente repricia las distancias de una señal auténtica del
2026-09-10 02:30 UTC para factibilidad; **no es una señal actual ni una orden**.
El diagnóstico emplearía una geometría preregistrada, identificada como infraestructura,
sin atribuirla a una señal predictiva H40, Trend o Kronos.

| Perfil | Riesgo inicial USD | EUR teóricos | Notional USD | Costos + gap USD | Riesgo total al stop USD | Capital + reserva USD | Target neto USD | Estado |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| R1 | 1.00 | 0 | 0 | Fees 4 > 1 | NO_TRADE | 0 | No evaluable | BROKER_INELIGIBLE |
| R5 | 5.00 | 85.67 | 95.7919105 | 4.2013245 | 4.2655770 | 99.9932350 | −4.1199380 | NUMERIC_ONLY_EXECUTION_UNVERIFIED |
| R10 | 10.00 | 85.67 | 95.7919105 | 4.2013245 | 4.2655770 | 99.9932350 | −4.1199380 | NUMERIC_ONLY_EXECUTION_UNVERIFIED |

Límite BUY modelado 1.11815, stop 1.11740, target 1.11910. Beneficio bruto al target
US$0.0813865. Comisiones modeladas US$4 round-trip; spread conservador 0.0014 USD/EUR,
slippage 0.00045/lado, gap presupuestado 0.00005. El spread observado 0.00002 no sustituye
el escenario conservador. R5 y R10 tienen igual tamaño por capital financiado, no por edge.
85.67 EUR sigue siendo odd lot, cuya aceptación efectiva y restricciones quedan UNKNOWN.

Sólo los costos equivalen a aproximadamente 490 pips sobre 85.67 EUR. El target bruto
no cubre costos. Un experimento desfavorable requeriría consentimiento separado explícito
`bounded_unfavorable_experiment_consent`; no se convierte en validación económica.
No se recomienda aumentar riesgo, tamaño ni apalancamiento para compensar ese déficit.

Cada cartera inicia US$100. El sizing aplica 1/5/10% fijo al equity actualizado, limitado
por pérdida acumulada restante de US$20 y capital financiado/exposición + reservas ≤US$100.
Una sola intención/inventario para toda la cuenta; LONG solamente. Ganancias no restauran
pérdidas consumidas. Net <= 0 termina entradas del perfil ese día de America/Santo_Domingo.
Fees pendientes o resultado incierto no habilitan continuar. La cohorte v2 termina después
de una apertura consumida; el máximo histórico de tres cierres diarios no concede otra apertura.

Los US$4.265577 son una **pérdida prevista modelada**, no una garantía. Un gap superior al
presupuesto o fallo de protección puede exponer hasta el notional financiado más costos.
No se puede garantizar pérdida máxima US$5/US$10 con un stop. Si no se puede acreditar
riesgo acotado razonablemente y recuperación fiable, permanece NO_TRADE.

## Rotador, transporte y conciliación

- Política v2 SKIP_WITH_REASON: R1→R5→R10. Un rechazo determinista de sizing/daily stop
  persiste motivo, oportunidad y timestamp antes de avanzar. No se salta incertidumbre
  de permisos, margen, fees, protección o autorización para buscar otra cartera.
- Todos los perfiles reciben la misma oportunidad y sizing; el perfil específico autorizado
  es el único que podría transmitir. Las muestras secuenciales no son aleatorias ni comparables
  automáticamente. Se preservan cantidades de trades y saltos reales por perfil.
- Gates y certificado de conciliación de hasta cinco segundos preceden SEND_PENDING.
  Intent, orderRef, IDs, reserva y consumo de uso se guardan antes del primer envío.
  Timeout/crash no permiten reintento automático ni restaurar el uso consumido.
  Ante error de Run/Once/Recovery el CLI informa orders_sent=null y exige conciliación:
  un fallo posterior al envío no puede anunciar falsamente cero transmisiones.
- Bracket vincula parent/children/OCA. ACK no es fill. Sólo callbacks reales con identidad,
  referencias, precios stop y cantidades exactas confirman protección. ACK sin fill no
  se trata como posición ni libera reserva.
- Después del fill real se exige inventario/cash estricto. Parciales requieren protección
  de cantidad efectiva; un parent remainder incierto bloquea SELL independiente.
- ApiCancelled local y permId=0 nunca bastan para liberar una reserva. Cierre/cancelación
  requieren órdenes propias terminales confirmadas, permId positivo y lecturas conciliadas.
- Uncertainty/desconexión activa parada global y emergencia; no abre otra operación.
  No se envía recuperación ciega con broker UNKNOWN.
- Recuperación cancela sólo órdenes propias identificadas, espera terminales confirmados
  y concilia antes de un SELL IOC del LONG restante. No excede inventario, no abre short,
  cero posición no produce orden. Un IOC anterior parcial/incierto requiere reconciliación
  y nuevo permiso; jamás se reutiliza un orderId después de timeout.
- Stop/expiry/revocación bloquean entradas y conservan gestión reductora previamente
  consentida hasta 24 h posteriores al expiry; después necesita RecoveryClose independiente.
  Fees USD pendientes conservan reserva; sólo cierre flat sin órdenes y fees definitivos
  permite liberarla. No se abandona gestión por una parada diaria.

La protección supervisada de primera prueba es una excepción **de protocolo diagnóstico**,
no una excepción general: SUPERVISED_FIRST_TRIAL, consentimiento explícito, recuperación
VERIFIED y las demás condiciones verificadas. Exige ACK efectivo tras transmisión.
Sin protección confirmada después del umbral de diez segundos se suspende y recupera
cuando existe certificado seguro. El cierre diagnóstico se inicia al umbral de 60 segundos
después del fill; polling/red/conectividad pueden retrasarlo. No se afirma garantía temporal
ni protección efectiva antes de una prueba autorizada.

## Evidencia y controles de almacenamiento

Se reutilizan PostgreSQL, CAS, advisory locks, hash chain y restricciones append-only existentes
(migración 008, sin alterarla). ExploratoryInvariants añade protocolo v2 inmutable y no
degradable ni eliminable, uso/loss
no decreciente, reservas acotadas, intención persistente y fills que no desaparecen ni cambian.
La preparación real y Assess escribieron el journal con esos controles. No se ejecutó una
integración order-to-fill con IBKR: sólo callbacks simulados en pruebas y lecturas reales.

Receipt local: cada sección permisos/margen/fondos/mínimo/fees/protección/API/recuperación
debe incluir status, environment=PAPER_TRADING, binding_id, profile, source, at,
artifact y artifact_sha256. El JSON de artifact debe contener los mismos valores,
estar dentro del repositorio, tener hash correcto y fecha de hasta 30 minutos.
No se crearon recibos VERIFIED favorables. What-If estimado no se admite como límite verificado.
Cantidad cubierta `quantity_up_to`, efectivo `usd`, margen `required_usd`, mínimo e incremento
y comisiones máximas `opening_bound/closing_bound` USD deben corresponder al ensayo.
Si las tarifas exceden lo preregistrado, la autorización se rechaza: requiere nueva preparación
y revisión, no cambiar el sizing silenciosamente. Protección VERIFIED requiere ACK reales
stop/target y permIds positivos; una primera prueba requiere el consentimiento diagnóstico estrecho.

## Kronos, Shadow, Sol y Dashboard

Kronos queda OBSERVER_ONLY. Cada entrada preparada conserva forecast anterior o contemporáneo,
modelo/versión/id/1H/horizonte12/trayectorias/régimen/dirección/consenso/calibración/antigüedad.
No usa forecasts futuros. `calibrated_probability=null` y EV sin evidencia permanece null.
La muestra real registrada tiene 32 trayectorias: 26 válidas, 6 inválidas, Kronos-base;
la versión exacta del artefacto es
`2b554741eca47781b64468546e77fef3e85130e6`.
Forecast creado 09:00:39 UTC, dirección SHORT, DOWNTREND, RAW_ONLY; sin señal técnica
elegible, TP_FIRST/SL_FIRST brutos no disponibles. A las 11:26 UTC el pipeline notificaba
TypeError y forecast stale: **UNAVAILABLE**, CALIBRATION_INSUFFICIENT. No se oculta ese estado
ni se afirma Kronos recuperado. Continúa su proceso, no se cambia el modelo ni sus controles.

Cada oportunidad rechazada conserva sizing/NO_TRADE, no un fill ficticio. Los twins emparejados
se crean sólo después del primer fill broker, con quote contemporáneo y reglas propias.
Si falta esa quote se registra NO_TRADE. Sus P&L y fees estimados no se copian del perfil broker.
Las métricas del estudio Shadow original permanecen separadas; un diagnóstico tampoco entra
en win rate, expectancy ni profit factor predictivos. Sí conserva P&L/fees de infraestructura.

Shadow ya estaba suspendido antes de esta tarea: PAPER_API_TIMEOUT a las 10:00:26 UTC,
última observación 09:59:45 UTC, sin stop del operador. Se reanudó el **mismo estudio** tras
comprobar lecturas Paper, y volvió a observar desde 11:03:53 UTC. Kronos y Cost-Aware
conservan sus PIDs previos. Sólo se reinició el API local para cargar los cambios compilados;
no se pararon estos investigadores. No se alteró el estudio preregistrado del observador Ford.

El Dashboard existente recibe PostgreSQL → proyección Python → API → SignalR → Pinia.
HOME/PAPER EXPERIMENT presenta cohort, purpose, siguiente perfil, elegibilidad, bloqueos,
autorización/expiry, emergencia, conteos broker/twins/fees/saltos y sesgo. Trading/Operaciones
mantienen inventario broker y SIMULATED_SHADOW separados. Feed PAPER usa IDs durables,
deduplica snapshots/reconexiones, conserva los últimos 200 eventos de la proyección;
el journal conserva el historial completo. Intent persistido, solicitud enviada y ACK son
eventos distintos; no se fabrica un ACK de una llamada exitosa a placeOrder.

Los controles ASSESS/AUTHORIZE/STOP/REVOKE/RECOVERY_INSPECT muestran los comandos locales
protegidos. **No transmiten desde el navegador**; START sigue deshabilitado. Un endpoint de
acciones UI no fue habilitado: requeriría una fase posterior con autoridad, confirmación
y auditoría separadas. La cookie Dashboard sólo tiene lectura; Sol no concede permisos.
Estados del read model incluyen BLOCKED, RECOVERY_REQUIRED, PAPER_EXECUTING, PROTECTED,
EXITING, RECONCILING y AWAITING_AUTHORIZATION, según evidencia. No se inventa READY.

Sol responde a preguntas Paper con números del journal, blockers y limitaciones Kronos.
Presupuesto cero devuelve LOCAL_EVIDENCE_ONLY y tokens/costo cero: no es una respuesta de GPT.
Ningún fill dispara una llamada pagada. Propuestas futuras seguirán backtest → walk-forward
→ shadow-forward, sin modificar estrategias ni controles automáticamente.

## Procedimiento humano pendiente, antes de cualquier autorización

1. En **TWS Paper**, confirmar cabecera/cuenta exacta contra el binding local, entorno Paper,
   proceso/puerto y ausencia de posiciones u órdenes. Nunca sustituir datos de la cuenta real.
2. Account → Balances/Available for Trading/Market Value: obtener efectivo liquidado USD,
   disponibilidad, régimen CASH/MARGIN y restricciones específicas Forex. INDIVIDUAL no resuelve esto.
3. Consultar permisos Forex de la cuenta Paper seleccionada en TWS/Client Portal. Si la pantalla
   sólo expone permisos Live, no usarla como sustituto: permanece UNKNOWN.
4. En ticket EUR.USD CASH IDEALPRO, cantidad propuesta recalculada, abrir **Preview**, no Transmit.
   Registrar mínimo/incremento, odd-lot warnings, margen incremental y comisiones estimadas.
   Un preview no demuestra fill/protección ni un máximo de fees; obtener la condición efectiva
   de tarifas de esa cuenta y documentar cualquier cargo adicional. Si no puede verificarse, bloquear.
5. Revisar configuración API Read-Only sin cambiarla en esta implementación. Cualquier modificación
   local posterior debe formar parte del protocolo aprobado, limitada a Paper.
6. Acreditar recuperación propia y supervisión. No marcar protección VERIFIED por orderTypes.
   Si sólo se verificará en el primer ensayo, revisar y aceptar el protocolo diagnóstico estrecho,
   terminales/permIds/recovery y contingencia de desconexión, sin permitir broker UNKNOWN.
7. Crear evidencia local auténtica y acotada, con fecha/hash/binding/profile. Repetir Inspect y Assess;
   las quotes actuales, efectivo y cantidad cubierta deben seguir cumpliendo límites.
8. Revisar el incidente anterior y la pérdida potencial bajo fallo de protección. Sólo entonces
   autorizar un único ensayo. Cerrar/conciliar y exigir nueva aprobación antes de investigación Paper.

**Condición necesaria antes de enviar:** identidad exacta, calendario/quote fresca LIVE,
journal/cash/posiciones/órdenes conciliados, riesgo y capital financiado dentro de límites,
permiso/tamaño/margen/fondos/fees verificados, recuperación acreditada, protocolo de protección
válido, grant fresco del perfil/purpose/cohorte/proceso exactos y revisión protegida de emergencia.
Todo UNKNOWN crítico produce NO_TRADE. No se activó ninguna excepción genérica.

## Comandos existentes desde la raíz de TradingAgent

Seguros ahora, sin transmisión ni concesión de autorización:

```powershell
$cohort = 'eurusd-explore-fc633912e01a491796bb420210054aaa'
.\scripts\eurusd-paper-exploratory.ps1 -Action Inspect -Cohort $cohort
.\scripts\eurusd-paper-exploratory.ps1 -Action Assess -Cohort $cohort
.\scripts\eurusd-paper-exploratory.ps1 -Action Status -Cohort $cohort
.\scripts\eurusd-paper-exploratory.ps1 -Action RecoveryInspect -Cohort $cohort
```

**No ejecutar todavía.** Secuencia futura únicamente después de resolver los blockers,
revisar los recibos auténticos y aprobar el protocolo:

```powershell
# Sustituir la ruta por evidencia auténtica local revisada; no es un archivo generado favorablemente.
.\scripts\eurusd-paper-exploratory.ps1 -Action Authorize -Cohort $cohort -Profile EURUSD_R5 -EvidencePath '.\artifacts\operator\paper-eurusd-receipts.json' -Minutes 30
.\scripts\eurusd-paper-exploratory.ps1 -Action ReviewEmergency -Cohort $cohort
.\scripts\eurusd-paper-exploratory.ps1 -Action Run -Cohort $cohort
```

Authorize exige frase local `AUTORIZAR PAPER EXPLORATORY`; vincula AccountBinding,
cohorte, perfil, purpose, hash del protocolo/engine y proceso TWS, guarda DPAPI y audita.
ReviewEmergency hace Inspect fresco, exige inventario/órdenes/reservas cero y grant vigente,
y frase humana `REVISADO LEVANTAR PAPER`. Sólo revisa la emergencia Paper; no reutiliza la
autorización diagnóstica vencida ni modifica una emergencia Live. Estos comandos no se ejecutaron.
Run consume una apertura aunque el envío termine en timeout y no abre otra tras el cierre.

Parada y revocación para una sesión futura:

```powershell
.\scripts\eurusd-paper-exploratory.ps1 -Action Stop -Cohort $cohort
.\scripts\eurusd-paper-exploratory.ps1 -Action Revoke -Cohort $cohort
```

No abandonar inventario: un runner activo conserva gestión reductora preaprobada. Si se
perdió el proceso o la autorización reductora requiere renovación, usar la ruta independiente:

```powershell
.\scripts\eurusd-paper-exploratory.ps1 -Action RecoveryInspect -Cohort $cohort
# Sólo si existe LONG propio confirmado y tras revisión local; actualmente no existe.
.\scripts\eurusd-paper-exploratory.ps1 -Action AuthorizeRecovery -Cohort $cohort -Minutes 15
.\scripts\eurusd-paper-exploratory.ps1 -Action Recovery -Cohort $cohort
```

AuthorizeRecovery requiere `CERRAR SOLO PAPER PROPIO`, source intent y BUY fills/permIds
confirmados, cantidad restante y conciliación reciente. Cero inventario no autoriza SELL.
La ruta histórica distinta puede inspeccionarse mediante
`.\scripts\paper-recovery-close.ps1 -Action Inspect`; no se debe reutilizar su antiguo grant.

Dashboard actual: http://127.0.0.1:5080. Acceso local de lectura protegido; HOME, Trading,
Operaciones, Experimentos y Sol muestran la evidencia. Si el API estuviera detenido:

```powershell
.\scripts\start-dashboard.ps1 -SolBudget 0 -CopyAccessCode
```

No iniciar un segundo API si el existente está activo. CopyAccessCode copia exclusivamente
el código de lectura local al portapapeles; no imprime OpenAI/API/IBKR credenciales.

## Verificación y archivos

**1.861 pruebas aprobadas, cero fallos y cero omitidas:** Python 1.293, C# 460,
Vue/Vitest 77 y Playwright 31. Compilación C# Release y frontend aprobadas.
Suites finales y compilaciones: resultados exactos en
`artifacts/eurusd-exploratory-preparation-20261008/verification.json` y sus logs.
Los fixtures broker y de UI están identificados como simulados; las pruebas E2E del
Dashboard usan el backend real y verifican SignalR/journal/estado, no una orden real.
La aceptación efectiva de nuevas órdenes/protecciones sigue **NO EJECUTADA**.
Hay advertencia de tamaño de bundle ECharts; no se hicieron cambios de dependencias ni rediseño.

Componentes modificados:

- Python: `eurusd_exploratory.py`, `eurusd_exploratory_runner.py`, `eurusd_exploratory_wire.py`,
  `eurusd_exploratory_projection.py`; nuevo `eurusd_exploratory_evidence.py`.
- C#: `ExploratoryStore.cs`, nuevo `ExploratoryInvariants.cs`, `TradingAgent.Api/SolChat.cs`.
- Vue: `types.ts`, `PaperReadiness.vue`, `stores/activity.ts`, `TradeFeed.vue`,
  `AgentCard.vue`, `HomePage.vue`.
- Pruebas: `test_eurusd_exploratory.py`, nuevo `test_eurusd_supervised.py`,
  `ExploratorySupervisedTests.cs`, `paper-supervised.test.ts`, `paper-supervised.spec.ts`,
  `e2e/dashboard.spec.ts`.
- CLI: `scripts/eurusd-paper-exploratory.ps1`, acciones Assess/RecoveryInspect,
  selección explícita de perfil/purpose y confirmaciones locales protegidas.
- Documentación: este informe, enlace desde el informe anterior y feedback Graphify.

74 hashes protegidos idénticos antes/después. No cambios en RiskEngine, H40/Forex V1,
AccountBinding, EmergencyStop, grants previos, autorización PaperAuto ni Live.
La preparación v2 guarda hashes de sus cuatro módulos de ejecución y exige igualdad al Run.
Graphify se consultó primero (424 nodos); carece de cobertura de estos componentes recientes.
Se siguieron imports y contratos mediante búsquedas dirigidas, sin inventar aristas ni extracción facturable.

La siguiente decisión es **resolver UNKNOWN operativos con evidencia auténtica**, no enviar
la primera orden ni afirmar que 85.67 EUR son efectivamente aceptables. Si ese tamaño/margen/fees
no cabe, declarar NO_TRADE sin aumentar capital, riesgo ni apalancamiento.
