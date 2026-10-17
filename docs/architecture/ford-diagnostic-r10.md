# FORD_DIAGNOSTIC_R10: ensayo supervisado preparado, ejecución bloqueada

R10 es un diagnóstico de infraestructura, no una estrategia, promoción H40,
autorización PaperAuto ni evidencia de rentabilidad. H40 original, H40 R3,
RiskEngine productivo y el observador Ford mantienen sus fuentes/configuración.

## Perfil y cálculo

`config/ford-diagnostic-r10.json`: Paper exclusivamente, US$100 virtuales,
presupuesto previsto US$10, una acción completa F y una única apertura.
Sin SHORT, deuda ni aumento automático de tamaño/riesgo. Reserva de efectivo =
entrada más costos de ambos lados; no sumar dos veces riesgo y reserva.
El wrapper aislado invoca RiskEngine existente; no cambia la política productiva
de 0.5%. `ALLOW_SIMULATION` no concede permiso de enviar órdenes.

Consulta de solo lectura: **2026-10-07T01:35:26.374783Z**.
Evidencia: `artifacts/paper-diagnostics/ford/ford-diag-f57f454b55b34857a981018bdfcc760c/evidence/20261007T013521818697-337258ad.json`.
Identidad Paper exacta, conexión y cuatro consultas completas; posiciones,
órdenes abiertas y ejecuciones vacías. AvailableFunds es suficiente como chequeo,
pero su saldo ficticio nunca entra en el sizing virtual de US$100.

| Concepto, una acción | US$ / estado |
|---|---:|
| BID / ASK | 12.28 / 12.29, **DELAYED**, no ejecutable |
| Límite BUY / stop / target modelados | 12.31 / 12.15 / 12.56 |
| Movimiento hasta stop, geometría conservadora de spread | 0.175 |
| BUY / SELL estimados, sin cap confirmado | 1.54 / 1.54 |
| Slippage, ambos lados / ticks adicionales | 0.01229 / 0.02 |
| Gap presupuestado, 2% ASK | 0.2458 |
| Pérdida prevista total | **3.53309 ≤ 10** |
| Exposición / exposición más costos reservados | 12.31 / **15.39 ≤ 100** |
| Efectivo virtual restante al reservar | 84.61 |
| Gap adverso 10% | 4.51629 |
| Fallo de protección, caída 25% | 6.1575 |
| Pérdida total del inventario más costos modelados | **15.39 > 10** |
| Cantidad máxima del primer ensayo | **1**, aunque cupieran más por efectivo |

Resultado numérico: **NUMERIC_FORECAST_PASS**. Estas cifras no son una garantía
ni precios reutilizables. Se recalculan con LIVE fresco al admitir. Si se exige
una garantía absoluta de pérdida ≤US$10, este ensayo no la demuestra.
Los costos US$1.54 por lado incluyen mínimos Fixed sin cap, cargos conservadores
y contingencia US$0.50/lado. Son estimaciones, no comisión efectiva verificada.
La sensibilidad con cap produce US$1.77309 de riesgo, pero no habilita el cap.

La [tarifa pública IBKR](https://www.interactivebrokers.com/en/pricing/commissions-stocks.php)
documenta mínimos, topes porcentuales y cargos; no demuestra la tarifa de esta
cuenta. [Stops y órdenes complejas Paper son simulados](https://www.interactivebrokers.com/en/software/paperTrader2.php).
No se ejecutó un nuevo What-If. El anterior conserva márgenes nulos y comisión
sin moneda/advertencia, sin evidencia utilizable de margen/costo efectivo.

## Matriz de bloqueos y comprobaciones

| Condición | Estado | Verificación/resolución |
|---|---|---|
| Identidad vinculada, conexión, consultas completas | VERIFIED | Inspect antes del consentimiento y Run; comparar cuenta completa en TWS Paper; cualquier cambio bloquea |
| Posiciones y órdenes | VERIFIED vacías | Repetir lectura/conciliación estricta; cero reservas ajenas |
| Calendario auténtico IBKR | VERIFIED, RTH cerrado | Próxima apertura observada 2026-10-07 13:30 UTC; exigir sesión activa y ≥180 s restantes |
| BID/ASK ejecutables | DELAYED, tipo 3 | Revisar suscripción/datos Paper en TWS; exigir tipo 1 LIVE y campos bid/ask ≤15 s. Recepción reciente no convierte DELAYED en LIVE |
| Permisos efectivos acciones USA | UNKNOWN | Revisar configuración/restricciones de cuenta **Paper** en TWS o Portal que identifique explícitamente Paper. No usar contrato disponible ni permisos de cuenta real |
| Restricciones intradía/tipo Cash-Margin | UNKNOWN | `INDIVIDUAL` no verifica Cash/Margin. Revisar restricciones intradía y reutilización de fondos para la cuenta Paper |
| SettledCash | UNKNOWN | TWS Paper → Account Window → Market Value/Cash: efectivo liquidado USD. No sustituir por AvailableFunds o CashBalance |
| AvailableFunds | VERIFIED suficiente | Disponibilidad solamente; sizing limitado a US$100 virtuales |
| Mínimo/incremento contractual | VERIFIED declarados 0.0001 | Una acción completa es compatible; permiso fraccionario sigue UNKNOWN y no se utiliza |
| Margen efectivo F | UNKNOWN | TWS Paper → vista previa/Check Margin o evidencia oficial vinculada a esta cuenta/contrato; descartar sentinels o valores sin moneda. Nada de financiación/apalancamiento |
| Tarifa/cargos aplicables | UNKNOWN | Verificar Fixed/Tiered, cargos de mercado/regulatorios/intermediario y regla del cap para Paper; comprobar cobertura por el escenario conservador. Comisión efectiva solo después del fill/report |
| LMT/STP/OCA declarados | VERIFIED | ContractDetails no prueba aceptación efectiva |
| Protección/parciales efectivamente aceptados | UNKNOWN | Única excepción procedimental: ensayo explícito supervisado; ACK con permId, precio, tipo, cantidad y OCA. Un rechazo previo nunca se omite |
| PostgreSQL Paper | BLOCKED, clúster detenido | Preparar/migrar con comando existente; migración 005 y grants no se aplicaron allí durante este trabajo |
| EmergencyStop | Activo, intacto | Revisión protegida manual posterior; R10 no elimina ni omite emergencia |
| Consentimiento R10 | No concedido | DPAPI independiente, exacto trial/cuenta/proceso/fuentes/recibos, un uso, máximo 30 min |

Si TWS/Portal tampoco permiten verificar expresamente una condición para Paper,
mantener UNKNOWN y bloqueada la apertura. No certificar un permiso por inferencia.

## Recibos y protocolo

`-EvidencePath` acepta el formato existente, con scope **FORD_DIAGNOSTIC_R10**:

```json
{"environment":"PAPER_TRADING","binding_id":"BINDING_ID_DEL_INSPECT","scope":"FORD_DIAGNOSTIC_R10","capabilities":{}}
```

Añadir solamente condiciones comprobadas: `status: VERIFIED`, `compatible: true`,
`source: OPERATOR_PAPER_TWS` o `OPERATOR_PAPER_CLIENT_PORTAL`, referencia trazable,
`observed_at` UTC ≤24 h y `value`. Valores admitidos: stock_permission=true,
account_restrictions=WHOLE_SHARE_CASH_LONG_ALLOWED, settled_cash≥100,
contract_margin entre 0 y 1 y effective_fees=FIXED/TIERED. Verificar también cargos
adicionales y que el forecast cubre ambos lados. No marcar UNKNOWN como VERIFIED.
Guardar un archivo nuevo, sin sobrescribir evidencia; el consentimiento vincula
su hash y revalida alcance/vigencia. Mínimos y fondos recibidos auténticamente del
broker no necesitan un recibo inventado.

1. Operador revisa perfil y riesgo de cola, prepara PostgreSQL, reúne recibos y
   repite Inspect durante RTH con LIVE. Cero pendientes/reservas ajenas.
2. Revisión protegida existente de emergencia, manual y posterior; nunca borrar
   archivos de emergencia/consumo. Si falla, mantener bloqueo.
3. Consentimiento específico de una apertura de una acción, 30 minutos, con
   supervisión y reconocimiento de que stop no garantiza US$10. Confirmación:
   `AUTHORIZE_ONE_FORD_PAPER_EXECUTION_DIAGNOSTIC_1_SHARE_10_USD_NO_STRATEGY_NO_LIVE`.
4. Run revalida identidad/proceso, calendario/cotización, recibos, efectivo,
   margen, inventario, reservas, geometría y RiskEngine. Replica el journal y
   SEND_PENDING en PostgreSQL antes del BUY. Fallo antes del envío: cero placeOrder.
5. Bracket BUY LMT + SELL TP LMT + SELL STP ligados/OCA. Solo último hijo transmite
   el conjunto. ACK requerido en 5 s; apertura GTD 30 s. Fill no equivale a
   protección: exigir ambos hijos aceptados con cantidades y geometría correctas.
6. Conciliar execId/permId, inventario y comisiones. Fracciones inesperadas,
   sobrellenado, órdenes ajenas, cambio de identidad o desconexión suspenden.
7. Iniciar cierre alrededor de +30 s del primer fill, nunca iniciarlo
   automáticamente después de +60 s. Con datos/RTH inutilizables conservar
   protección y suspender. Cancelar hermanos, conciliar terminales/posición y
   después SELL que solo reduce LONG propio. Posición cero nunca produce SELL.
8. Timeout o SELL intentado: conciliar, nunca repetir Run/orderId/SELL a ciegas.
   Recovery usa consentimiento separado, ligado al BUY execId/permId/intención.
   SELL previo incierto impide un segundo intento automático: intervención humana.
9. Reserva retenida hasta posición cero, órdenes cero y comisiones definitivas.
   Comisión tardía conserva FLAT_COMMISSION_PENDING. El ciclo mide infraestructura,
   sin señal H40 ni éxito de estrategia.

## Comandos existentes, desde la raíz

Trial R10 preparado, sin autorización: `ford-diag-f57f454b55b34857a981018bdfcc760c`.
Su hash de protocolo es `792666cdb5f4d91562b655b733260036dd334359967f98584b848db882f79343`.
No repetir Prepare para reutilizarlo. Cambios de fuentes/binarios invalidan el
trial; preregistrar otro conservando los anteriores.

```powershell
$trial = 'ford-diag-f57f454b55b34857a981018bdfcc760c'
$profile = 'FORD_DIAGNOSTIC_R10'
.\scripts\ford-execution-diagnostic.ps1 -Action Status -Profile $profile -TrialId $trial
.\scripts\ford-execution-diagnostic.ps1 -Action Inspect -Profile $profile -TrialId $trial

# Preparación PostgreSQL, sin órdenes ni autorización:
.\scripts\paper-lab-database.ps1 -Action Prepare
$receipts = '.local\ford-r10-paper-receipts.json' # Crear solo con datos Paper verificados
.\scripts\ford-execution-diagnostic.ps1 -Action Assess -Profile $profile -TrialId $trial -EvidencePath $receipts

# Fase posterior MANUAL; no ejecutada aquí. Si falla Review, no avanzar:
.\scripts\paper-lab.ps1 -Action Review -Mode ExecutionDiagnostics

# SOLO después de resolver bloqueos y aprobación local explícita:
.\scripts\ford-execution-diagnostic.ps1 -Action Authorize -Profile $profile -TrialId $trial -EvidencePath $receipts
.\scripts\ford-execution-diagnostic.ps1 -Action Run -Profile $profile -TrialId $trial

# Parada/revocación de entradas; seguir gestionando pendientes:
.\scripts\ford-execution-diagnostic.ps1 -Action Stop -Profile $profile -TrialId $trial
.\scripts\ford-execution-diagnostic.ps1 -Action Revoke -Profile $profile -TrialId $trial
.\scripts\ford-execution-diagnostic.ps1 -Action Reconcile -Profile $profile -TrialId $trial

# Parent pendiente sin fill: cancelar propio, conciliar; nunca SELL plano:
.\scripts\ford-execution-diagnostic.ps1 -Action CancelPending -Profile $profile -TrialId $trial
.\scripts\ford-execution-diagnostic.ps1 -Action Reconcile -Profile $profile -TrialId $trial

# Solo LONG propio confirmado; permiso independiente, emergencia no se omite para abrir:
.\scripts\ford-execution-diagnostic.ps1 -Action RecoveryInspect -Profile $profile -TrialId $trial
.\scripts\ford-execution-diagnostic.ps1 -Action RecoveryAuthorize -Profile $profile -TrialId $trial
.\scripts\ford-execution-diagnostic.ps1 -Action RecoveryRun -Profile $profile -TrialId $trial
.\scripts\ford-execution-diagnostic.ps1 -Action Reconcile -Profile $profile -TrialId $trial
```

El Review existente concilia el laboratorio previo, incluso con autorización
vencida; no concede una nueva. R10 exige además su consulta STOCK actual.
La excepción EUR nunca sustituye inventario o saldo bursátil. Stop/Revoke no
liquidan a ciegas. Recovery está disponible para reducir aun con emergencia,
pero no puede abrir ni usar autorización diagnóstica vencida como permiso nuevo.

## PostgreSQL y memoria de investigación

`paper_lab.ford_diagnostic_events` conserva eventos exactos del journal:
trial/scope/binding, revisión, timestamps UTC, hash anterior/actual y payload
completo de órdenes, fills, comisiones, P&L y conciliaciones. Append transaccional
con bloqueo, replay idéntico idempotente, conflictos/gaps rechazados,
UPDATE/DELETE prohibidos y rol Paper con SELECT/INSERT solamente.
SQLite FULL/WAL es el outbox durable. PostgreSQL caído bloquea BUY; protección,
cancelación y reducción propias conservan registro local y no dependen de OpenAI
ni del DB. El cierre puede terminar con réplica pendiente explícita; reanudar
Reconcile para replicar antes de publicar evidencia al investigador.

Solo tras posición/órdenes cero, comisiones definitivas y réplica confirmada se
crea una observación inmutable por hash en
`artifacts/research/ai-strategy-research/execution-observations`.
Incluye precios previstos/ejecutados, BUY/SELL/moneda/execId/permId, señal de
diagnóstico, stop/target, cotizaciones/spread/timestamps, costos modelados y
observados, discrepancias, P&L y decisión diaria. No inventa slippage causal si
falta cotización auténtica en el fill; diferencias contra límites se etiquetan.

AI_Strategy_Researcher verifica la cadena origen y recibe el resumen compacto
en la próxima sesión explícitamente autorizada y presupuestada. El ejecutor
no llama al modelo ni consume crédito automáticamente. GPT-6.1 Sol puede proponer
mejoras offline de costos/ejecución para backtesting y validación independiente;
el diagnóstico aporta **cero operaciones** a métricas/ranking de estrategias.
No desbloquea familias descartadas por sí solo ni modifica riesgo/estrategias.
Prueba final sellada y memoria DEFER_RESEARCH intactas.

PaperAuto estratégico queda pendiente de estrategia/version con evidencia
independiente, adapter/protecciones observados, permisos/fondos/datos vigentes,
capital protegido y consentimiento específico. Ni R10 ni su diagnóstico promueven
H40. WIN_TO_CONTINUE exige neto definitivo >0; pérdida o break-even bloquea nuevas
entradas del día America/Santo_Domingo y continúa la gestión de pendientes.

## Verificación

**1,334 pruebas aprobadas: 959 Python + 375 C#, cero fallos/omisiones.**
62 nuevas respecto de las 1,272 anteriores (37 Python + 25 C#).
Compilación .NET final: cero errores/advertencias; compileall y sintaxis PowerShell
aprobados. Los 65 archivos/estados protegidos conservan sus hashes.

`artifacts/test-results/ford-diagnostic-r10/verification.json` registra compilación,
suites completas, hashes protegidos, evidencia y archivos modificados. Transporte
probado con broker sintético, sin afirmar aceptación efectiva en TWS. La base
Paper permaneció detenida; la base desechable se detiene al terminar. No se
concedieron autorizaciones ni se limpió emergencia; cero órdenes y llamadas
OpenAI facturables durante esta preparación.
