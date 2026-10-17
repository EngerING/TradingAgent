# AccountBinding y sesión IBKR Paper

Esta fase conserva estrategias, indicadores, salidas, RiskEngine y límites: capital
StrategyPaper US$100, pérdidas acumuladas US$20, exposición 1× y política diaria
WIN_TO_CONTINUE / FIRST_LOSS_STOPS_DAY. ExecutionDiagnostics y RecoveryClose siguen
separados. No se habilita Live ni se renueva una autorización al reconocer una cuenta.

## Identidad y sesión

`AccountBinding` migra la identidad completa previamente cotejada y protegida en
DPAPI a `.local/ibkr-account-binding.dpapi`. La migración compara las atestaciones
históricas del laboratorio y del lector; identidades diferentes son HARD STOP.
Una cuenta candidata sin atestación no sirve para vincular. Caducidad y revocación
de un permiso de ejecución no borran la identidad histórica ni renuevan el permiso.

Cada conexión exige exactamente una cuenta administrada y que coincida por su
identidad completa con el vínculo protegido. Ausencia, cuentas adicionales,
duplicadas o distintas suspenden. No se selecciona por sufijo, prefijo o puerto.
Un cambio del vínculo/atestación durante la sesión vuelve a bloquear el transporte.
Los eventos muestran solamente `***3784` o el sufijo correspondiente.

`IbkrSessionGuard` complementa `Authorization`, que conserva vencimiento, proceso
TWS, consentimiento, permisos, alcance y gestión limitada. El guard exige endpoint
configurado y autorizado, conexión e identidad activas, Paper y modo permitido.
`config/ibkr-session.json` permite configurar host/puerto de TWS local; se admiten
127.0.0.1 y ::1. Un endpoint distinto del permiso protegido exige una nueva
atestación local por los mecanismos existentes. El puerto jamás acredita Paper.
No se extiende la atestación de un proceso local a un servidor remoto.

Los scripts Authorize, Review, AuthorizeEurAbsence y RecoveryClose Authorize
resuelven automáticamente el vínculo; conservan sus consentimientos de propósito.
Solo una primera vinculación sin ninguna identidad histórica puede solicitar el
Account ID completo. No hay cambio automático de cuenta.

## Modos y pipeline

| Modo | Transporte |
|---|---|
| Research | Consultas; ningún envío o cancelación de órdenes |
| PaperAuto | Envío solo con cuenta Paper y todos los gates existentes |
| LiveApproval | Envío automático bloqueado; falta mecanismo independiente por orden |

No existe LiveAuto. El modo operativo no sustituye la categoría de permiso:
StrategyPaper, ExecutionDiagnostics y RECOVERY_CLOSE_ONLY conservan sus alcances.

El pipeline utiliza los componentes existentes:

```text
IBKR market data → paper_strategy.signal → PaperLab.strategy_proposal
→ C# RiskEngine / ExecutionFeasibility → PaperLab.begin y reserva persistente
→ PaperOrderBuilder → Wire.guard / IbkrSessionGuard / authorize_transport
→ SDK TWS → openOrder/orderStatus/execDetails/comisiones
→ PaperLab.ingest/exposure/derive → PostgreSQL (CAS) y P&L
```

`PaperOrderBuilder` serializa cantidad y geometría aprobadas. `Wire.guard` verifica
su igualdad antes de cada envío, además del vínculo y del registro durable. No
redimensiona ni altera el riesgo. El guard de modo también se comprueba antes de
reservar o asignar orderId para una entrada. Los métodos Protobuf directos y otras
mutaciones sin alcance siguen bloqueados.

PAPER_AUTO_READY requiere permiso vigente, StrategyPaper con evidencia aprobada,
conciliación satisfactoria, ausencia de intenciones/comisiones pendientes,
presupuesto restante y emergencia levantada mediante su revisión protegida.
Cada señal sigue pasando nuevamente por RiskEngine, factibilidad y gates de admisión;
READY no obliga a operar ni acredita rentabilidad.

## Reinicio, desconexión y auditoría

Las intenciones siguen usando IDs deterministas y journal PostgreSQL. Reiniciar no
borra pérdidas, reservas ni una intención UNKNOWN. Nunca se retransmite esa intención.
`SessionReconnect` realiza hasta tres intentos de conectar y recuperar órdenes,
posiciones y fills mediante la conciliación existente. También cubre fallos de
lectura de mercado del runner continuo. PermissionError es HARD STOP, aunque en
Python hereda de OSError: no se reintenta un fallo de autorización o identidad.

La reconexión no elimina la emergencia. Si el incidente la activó, únicamente
vuelve a observar/conciliar; nuevas entradas siguen bloqueadas hasta revisión.
El SDK puede transformar un fallo de serialización/envío en callback y retornar:
el adaptador ahora detecta ese fallo, detiene las siguientes patas del bracket y
exige conciliación; nunca lo interpreta como envío confirmado ni repite la orden.

Los eventos de conexión, identidad, envío/ACK, fill parcial/completo y cancelación
se guardan en `artifacts/paper-lab/session-events.jsonl` con timestamps UTC y cuenta
enmascarada. El journal conserva intención, riesgo bloqueado y conciliación,
incluyendo un nombre estructurado adicional sin sustituir los eventos históricos.

Read-Only se detecta mediante errores reales del SDK y permanece bloqueado después
de reconectar: `PAPER_AUTO_BLOCKED: TWS API is read-only.` IBKR no ofrece aquí una
consulta verificada del checkbox de TWS; se conserva la atestación local del permiso
y no se envía una orden de prueba para averiguarlo. No se modifica TWS.

## Comandos existentes

Solo lectura, sin activar ejecución:

```powershell
.\scripts\paper-identity.ps1 -Action Discover
.\scripts\paper-lab.ps1 -Action Status
.\scripts\paper-lab.ps1 -Action Diagnose
```

Después de obtener una estrategia aprobada y completar los mecanismos protegidos
existentes de revisión/autorización, el runner permite seleccionar modo:

```powershell
.\scripts\paper-lab.ps1 -Action Run -ExecutionMode PaperAuto
```

Este comando no autoriza, no levanta emergencia y no sustituye RecoveryClose.
Research y LiveApproval pueden seleccionarse con el mismo parámetro y bloquean
mutaciones. El Action predeterminado del script continúa siendo Status.

## Archivos de esta fase

Creados: `python/trading_agent/ibkr_session.py`,
`python/tests/test_ibkr_session.py`, `scripts/ibkr-session.ps1`,
`config/ibkr-session.json` y este documento.

Modificados: `python/trading_agent/paper_identity.py`, `paper_execution_wire.py`,
`paper_lab.py`, `paper_lab_runner.py`, `paper_lab_diagnostics.py`,
`paper_recovery_close.py`, `broker.py`, `tws.py`; scripts
`paper-identity.ps1`, `paper-lab.ps1`, `paper-recovery-close.ps1`; fixtures existentes
`test_review_request_timeout.py`, `test_paper_data_diagnostics.py`,
`test_pending_bracket_reconciliation.py`, `test_paper_eur_registration.py`; índice
`docs/architecture/paper-execution-laboratory.md`.

El archivo DPAPI de vínculo es estado local cifrado, no un artefacto para publicar.
No se modificaron clases C# de riesgo ni archivos de estrategias/indicadores.

## Comprobación de preparación

Consulta auténtica del 2026-10-06 02:20:15 UTC: identidad ***3784 verificada sin
entrada interactiva; EUR/USD CASH posición cero, ninguna orden abierta, EUR cash
CONFIRMED_ZERO, reserva diagnóstica cero y FLAT_CONFIRMED. El cierre recovery
orderId 4 ya consta en el journal previo: BUY 100 @1.12185, SELL 100 @1.12247,
comisiones USD2 por lado, P&L bruto USD0.062 y neto -USD3.938. Esta fase solo leyó
esa evidencia; no transmitió órdenes.

PaperAuto permanece bloqueado por SESSION_STOPPED_OR_EXPIRED, EMERGENCY_STOP y
STRATEGY_EVIDENCE_REQUIRED. No se promovió ninguna estrategia. Hashes de permisos
diagnóstico/recovery, excepción EUR y marcador de emergencia coinciden antes/después.
Evidencia en `artifacts/paper-lab/data-diagnostics.json` y
`artifacts/test-results/account-binding-protected-after.json`.

Base anterior: 539 pruebas (337 Python + 202 C#). Esta fase añade 46 pruebas Python
de identidad/persistencia, modos, endpoints, SDK sin red, riesgo bloqueado, límite
US$20, idempotencia/reinicio, reconexión, Read-Only e historial conciliado. Los
resultados completos se registran en `artifacts/test-results/account-binding-*`.

Resultado final: **585 aprobadas, cero fallos y cero omisiones: 383 Python + 202 C#**.
`dotnet build TradingAgent.sln -m:1` completó con cero advertencias y errores.
Se ejecutó toda la suite C# y Python con PostgreSQL descartable en 55432; las
consultas reales se limitaron a Paper en 7497 y al journal Paper en 55433.
