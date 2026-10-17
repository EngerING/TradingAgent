# Bracket ExecutionDiagnostics: fill tardío y recuperación

Fecha: 2026-10-05. Graphify se consultó primero con `paper execution broker journal reconciliation pending orders`; su grafo anterior al laboratorio se contrastó con código y journal. Se aplicó senior-software-engineer.

**Estado observado a las 20:46:52 UTC: 100 EUR abiertos, ninguna orden abierta y ninguna protección activa.** El diagnóstico no completó el cierre. Emergencia de journal y archivo local activas, autorización vencida, Live bloqueado y StrategyPaper sin promoción ni cambios de exposición. Esta investigación no envió, modificó ni canceló órdenes.

## Identidad del experimento y evidencia auténtica

Cuenta Paper verificada por coincidencia completa protegida, presentada únicamente como `***3784`; clientId 82, conId 12087792, EUR/USD CASH IDEALPRO.

Intención: `834e28ff5a618ed7e9f06f974106f662c409f73265173ffd11bd18ee49404dd8`.

| Orden | orderId | permId | Estado confirmado mediante completedOrder |
| --- | --- | --- | --- |
| BUY LMT 100 EUR, 1.12185 | 1 | 1520205604 | Filled; texto original `Filled Size: 100` |
| ProfitTaker SELL LMT 100 EUR, 1.12335 | 2 | 1520205605 | Cancelled; texto original `Cancelled by Trader` |
| StopLoss SELL STP 100 EUR, 1.12080 | 3 | 1520205606 | Cancelled; texto original `Cancelled by Trader` |

El texto `Cancelled by Trader` no identifica por sí mismo qué actor solicitó la cancelación. No atribuirla al runner ni a una acción manual sin logs adicionales de TWS.

BUY confirmado mediante execDetails: `0000e215.6ac30098.01.01`, cantidad 100 EUR, precio 1.12185, hora del broker **20:20:22 UTC** (`20261005 16:20:22 US/Eastern`), comisión **2.0 USD**. No se observó ejecución SELL. La captura inicial 0/100 no excluía un fill posterior. No existe P&L realizado de un ciclo cerrado ni comisión SELL comprobada.

Antes de la recuperación el journal (revisión 28) decía `CANCELLED_NO_FILL`, sin execs, comisiones ni permIds. El journal corregido (revisión 36) dice **FILLED**, conserva las pruebas históricas y contiene exec, comisión, tres permIds, estados canónicos y callbacks completedOrder originales. Reserva **US$10**, experimentos consumidos **1**, presupuesto diagnosticado **US$10**, pérdida consumida todavía 0 porque no se liquidó el ciclo. Esto no elimina la comisión ya registrada ni certifica ausencia de pérdidas. El capital StrategyPaper conserva US$100, pérdida consumida 0 y su exposición 1×.

Archivos de evidencia en `artifacts/paper-lab/`:

- `pending-bracket-journal-before.json`: estado y auditoría anteriores a recuperar el fill.
- `pending-bracket-broker-before.json`: primera observación auténtica de broker, posiciones y órdenes completadas.
- `pending-bracket-recovered-fill.json`: recuperación inicial del exec y su comisión.
- `data-diagnostics.json`: lectura posterior con los callbacks normalizados y motivo `PROTECTION_UNCONFIRMED`.
- `pending-bracket-journal-after.json`: revisión 36 del journal persistente.
- `pending-bracket-protected-before.json`: hashes de autorización y excepción; ambos continuaron iguales. Contiene rutas y hashes, ninguna credencial.

## Secuencia y causa

| Hora UTC | Evento |
| --- | --- |
| 20:18:57.153794 y 20:18:58.347876 | Consultas completas; baseline inicial con EUR UNKNOWN/null aceptado bajo excepción protegida |
| 20:18:58.909373 | Intención y reserva persistidas; excepción vinculada al único intento antes de transmitir |
| 20:19:09.351254 | El runner inició cancelación del padre tras diez segundos sin fill registrado |
| 20:19:10.511867 | orderStatus local `ApiCancelled`, permId 0, filled 0, remaining 100 |
| 20:19:11.975696 | WORKER_SUSPENDED: EUR_CASH_RECONCILIATION_UNAVAILABLE |
| 20:20:22 | BUY real simulado confirmado después mediante consulta de ejecuciones |
| 20:46:52 | completedOrder confirma BUY Filled, ambos hijos Cancelled; posición 100 EUR y openOrders vacío |

No había openOrder ni Submitted ACK persistidos en el incidente original. Sí había el callback orderStatus indicado, que **no probaba cancelación del servidor**. La consulta posterior confirma que IBKR aceptó el bracket y ejecutó el padre; no permite afirmar que el runner recibió los ACK iniciales. TWS permanecía conectado e identidad verificada en las lecturas del incidente; sus consultas de cuenta terminaron. Solo quedaron códigos informativos 2104, 2106, 2158 y 2100, sin error de rechazo de órdenes registrado en ese intervalo.

El envío inicial utilizó la excepción de admisión existente: ausencia de EUR no equivale a cero, pero estaba permitida con consultas completas y sin exposición inicial. El error fue posterior: `can_prepare` exigía `not state['orders']`; al existir la intención, aun con **cero fills**, la consulta final volvía a exigir saldo EUR estricto. Además, el adaptador rechazaba el saldo antes de entregar eventos, y el `ApiCancelled` local permitía aparentar cancelación sin confirmación de las tres patas. No corresponde aumentar el timeout.

## Flujo corregido

1. Después de consultar contrato y calcular riesgo, volver a conciliar cuenta, órdenes, posiciones, identidad y excepción. Verificar autorización, emergencia, quote reciente, límites y reserva antes de crear SEND_PENDING. El SDK vuelve a aplicar los guards al serializar.
2. Vincular la excepción a una única intención/sesión antes de transmitir. La vinculación durable impide otro experimento; no desaparece con un reinicio.
3. Mientras no exista ningún exec real, permitir únicamente observar/conciliar el bracket vinculado con EUR UNKNOWN/null. Exigir todas las consultas completas, posiciones cero y ausencia de órdenes ajenas; validar referencias, instrumento, clientId y patas. Esta ruta nunca admite una nueva entrada ni permite limpiar emergencia mediante Review.
4. Entregar e incorporar los eventos de la consulta antes de aplicar gates de efectivo. El primer exec, parcial o completo, invalida la reconciliación anterior y exige conciliación estricta; nunca una captura, ACK o simple transmisión.
5. Antes de cancelar un padre pendiente por plazo, volver a consultar broker y exigir ACK con permId positivo. Si el estado no está confirmado, suspender y conciliar; no reintentar envío ni cancelación a ciegas.
6. Conservar reserva ante ApiCancelled local o cancelaciones incompletas. Solo liberar la reserva de un bracket sin fills cuando todas sus patas tengan evidencia completedOrder de cancelación/rechazo vinculada, con permIds positivos, consultas completas, posiciones cero y ninguna orden abierta. Una ejecución tardía restaura reserva y emergencia y se registra duraderamente.
7. completedOrder conserva texto original, normaliza estados y valida identidad de la pata. No utiliza su totalQuantity restante para inferir ausencia de fills.

La excepción `544d4449fbe04152aa4bacfdd998b9f0` ya estaba consumida a las 20:18:58.909365 y permanece vinculada al mismo intento y sesión. **No es reutilizable para una nueva entrada.** Ahora hay un fill y EUR 100.00 explícitos: exigir conciliación estricta. Registrar otra excepción no permitiría repetir este diagnóstico.

IBKR reportó en las patas completadas OCA group `1520205604`, type 2. El guard de protección de una posición abierta sigue exigiendo la vinculación original; no se relajó para inventar protección ni para reenviar hijos cancelados. Actualmente no hay stop/TP activos: `PROTECTION_UNCONFIRMED` es un bloqueo real. El deadline de cierre 20:21:22 UTC ya venció.

## Recuperación segura existente

Desde la raíz del proyecto:

```powershell
.\scripts\paper-lab.ps1 -Action Diagnose
```

Diagnose descubre identidad actual y utiliza el SDK con placeOrder, cancelOrder y sus variantes Protobuf bloqueadas. Ahora incorpora al journal los execs, fees y completedOrders de intenciones propias, comprueba efectivo/exposición/protección y conserva emergencia. Funciona como inspección aun si la autorización expiró, sin extenderla. El bloqueo actual observado es `PROTECTION_UNCONFIRMED`.

**Este comando no cierra la posición.** No ejecutar Run, Review ni Authorize como recuperación de este incidente. Resolver la exposición necesita una decisión posterior explícita del propietario; esta investigación recibió la instrucción de no ejecutar órdenes.

El helper `exposure_check` del informe describe admisión inicial de cuenta plana; su rechazo de saldo EUR no cero no significa que EUR siga UNKNOWN. Para recuperar una intención propia, consultar `owned_reconciliation`, los execs, EUR 100.00 y las posiciones observadas.

Al comenzar la investigación faltaba el archivo local de emergencia aunque el journal estaba suspendido. Se ejecutó únicamente EmergencyStop existente para restablecer ese marcador; no canceló órdenes ni modificó la autorización. Los hashes de autorización y excepción permanecieron idénticos. Status final: expired=true, revoked=false, emergency=true, liveEnabled=false.

## Verificación

**510 pruebas aprobadas, sin omitidas: 311 Python y 199 C#.** Bases de pruebas PostgreSQL separadas de Paper; adaptadores y fills sintéticos en todas las pruebas de transporte.

Las 17 pruebas nuevas cubren bracket con cero fills, ACK y suspensión/reinicio, parcial y completo, transición de excepción a conciliación estricta, fill tardío tras ApiCancelled y tras cancelación conciliada, comisión tardía recuperada, liberación de reserva con las tres confirmaciones, órdenes ajenas, consultas incompletas, fallos de admisión antes de SEND_PENDING, quote/excepción vencidos, cancelación protegida y prohibición de reintento sin ACK, normalización de completedOrder, Diagnose sin mutaciones y persistencia PostgreSQL de un fill que no puede borrarse reiniciando.

Regresiones completas: `artifacts/test-results/pending-bracket-python.txt`, `pending-bracket-dotnet.txt` y `pending-bracket.trx`. Se conservaron todas las regresiones de WIN_TO_CONTINUE, StrategyPaper, equivalencia de salidas, autorización, Live bloqueado y reconciliación de comisiones.
