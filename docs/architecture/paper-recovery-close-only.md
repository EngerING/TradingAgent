# RecoveryClose: cierre exclusivo de inventario Paper confirmado

Preparado el 2026-10-05, America/La_Paz; comprobación final **2026-10-06 01:18:31 UTC**. Graphify se consultó primero y se contrastó su grafo anterior al laboratorio con fuentes actuales. Se aplicaron senior-software-engineer y sus invariantes de trading.

**No se registró autorización RecoveryClose ni se envió una orden.** Emergencia activa, autorización diagnóstica vencida e intacta, StrategyPaper bloqueado, ninguna promoción ni cambio de exposición 1×; Live bloqueado. La inspección utilizó el SDK en modo de solo lectura con placeOrder/cancelOrder y variantes Protobuf rechazadas.

## Estado auténtico y propuesta de cierre

| Dato | Observación |
| --- | --- |
| Cuenta | Coincidencia completa contra identidad protegida, presentada como `***3784` |
| Instrumento | EUR/USD CASH IDEALPRO, conId 12087792 |
| Inventario | LONG 100 EUR en reqPositions, reqPositionsMulti y efectivo EUR conciliado |
| BUY original | orderId 1, permId 1520205604, execId `0000e215.6ac30098.01.01` |
| Fill original | 100 EUR @ 1.12185; comisión 2 USD |
| Intención | `834e28ff5a618ed7e9f06f974106f662c409f73265173ffd11bd18ee49404dd8` |
| Hijos originales | TP 2 y stop 3 cancelados, confirmados en completedOrder |
| Órdenes abiertas | Ninguna |
| Reserva diagnóstica | US$10 retenidos, un experimento consumido |
| BID / ASK | 1.12262 / 1.12263, LIVE / OPEN, 01:18:31 UTC |
| Cantidad propuesta | 100 EUR; se vuelve a calcular desde inventario confirmado al ejecutar |
| Salida propuesta | Un SELL LMT IOC, referencia `RECOVERY-<id de autorización>` |

Con aquella cotización, el precio límite calculado es 1.12260, redondeando BID hacia abajo al tick 0.00005. Es una observación, no un precio fijado para una ejecución futura. Execute obtiene otra cotización y vuelve a conciliar antes de SEND_PENDING. La cantidad jamás proviene del saldo ficticio de IBKR ni del dimensionamiento StrategyPaper.

Evidencia de lectura: `artifacts/paper-lab/recovery-close-preview.json`. No hay fill ni comisión SELL nuevos; P&L bruto/neto de un ciclo cerrado todavía son null.

## Autorización independiente

`scripts/paper-recovery-close.ps1` expone Inspect, Authorize, Execute y Status. Su valor predeterminado es Inspect. No utiliza ExecutionDiagnostics Run, Review ni Authorize.

Authorize:

1. Consulta identidad protegida exacta y posición actual mediante Inspect.
2. Pide cuenta completa oculta y atestación local `PAPER_RECOVERY_CLOSE_ONLY`, tras verificar Paper, permisos FX, API habilitada y detener otras operaciones EUR/USD.
3. Repite descubrimiento e inspección después de la entrada del propietario. Rechaza identidad, origen, proceso TWS o cantidad mayor cambiados.
4. Crea exclusivamente `.local/paper-recovery-close.dpapi`, protegido con Windows DPAPI CurrentUser. No modifica el permiso diagnóstico, la excepción EUR ni la emergencia.

El permiso tiene modo RecoveryClose y scope RECOVERY_CLOSE_ONLY; vincula cuenta exacta, proceso TWS/start time, instrumento, BUY orderId/permId, intención, hash de los execs BUY originales y cantidad máxima conciliada. Admite únicamente SELL LMT IOC, un uso, vigencia predeterminada 15 minutos y máximo 30. Autorizarlo no transmite una orden.

## Ejecución y fallos

La ruta comparte el mutex `paper-lab.run.lock`, conserva emergency=true y usa la contabilidad del diagnóstico existente. No crea otra estrategia, sesión diagnóstica ni oportunidad. El SDK aplica guards específicos antes de serializar; las rutas BUY, bracket, modificación del TP cancelado y cancelación independiente quedan fuera del permiso de recovery.

Antes del envío exige cuenta exacta, todas las consultas de efectivo completas, EUR explícito y conciliado, posiciones reqPositions/reqPositionsMulti iguales al inventario de fills, origen confirmado y ningún conflicto. Cantidad negativa, mayor que el BUY, reducida sin execs reconocidos, moneda/posición diferente, orden desconocida o estado incierto suspenden. EUR UNKNOWN no puede utilizar la excepción inicial. Si el broker ya está plano, no envía SELL; una reducción a cero sin evidencia de salida conserva la reserva y requiere revisión.

Después de obtener BID/ASK vuelve a conciliar. Verifica frescura de quote/evidencia, permiso, identidad y revisión del journal. Persiste el orderId nuevo, vínculo de origen, precio, cantidad, referencia y consumo de autorización en una transacción **antes del único placeOrder**. Los guards verifican la solicitud contra esa copia inmutable y contra el LONG conciliado; no permiten ampliar cantidad ni cambiar a BUY.

No declara un atributo reduce-only nativo de IBKR CASH. La reducción se controla en el proyecto mediante inventario, conciliación, guards, referencia y mutex. Ese mutex no controla órdenes manuales de TWS ni otros programas externos; el propietario debe mantener EUR/USD sin operaciones paralelas durante el cierre, como exige la atestación protegida. Un cambio observado bloquea la ruta. No afirmar una garantía atómica del broker frente a actores externos.

La orden es IOC para evitar un SELL persistente desatendido. Se registra execId, permId, fill, precio, precio solicitado, quote, latencia y moneda/comisión de salida. Se conserva la evidencia original. Los callbacks de fills se archivan incluso si el mismo lote incluye desconexión. Comportamiento IOC/odd lot del cierre auténtico todavía no está verificado mediante una orden: las pruebas de serialización son sintéticas.

Un parcial conciliado finaliza con `PARTIAL_OR_NO_FILL_RECONCILED` y cantidad restante. No modifica ni repite la orden automáticamente. Antes de otro permiso local para el remanente exige completedOrder terminal con permId positivo, ausencia de órdenes activas y nueva conciliación. Timeout/envío ambiguo consume el permiso, mantiene reserva/emergencia y bloquea reenvío incluso con otro permiso hasta resolver el envío anterior. No usar otra autorización para eludir esta condición.

## Liquidación

La reserva solamente se libera cuando se verifican efectivo/posición finales cero, consultas completas, ninguna orden pendiente y todas las comisiones reconocidas y utilizables en USD. Se calcula P&L bruto con execs; neto al disponer de costos. Si la salida está llena pero la comisión tarda, devuelve `FLAT_COMMISSION_PENDING` y retiene US$10 hasta otra inspección y conciliación. Una comisión extranjera sin conversión fiable no permite inventar neto ni liberar la reserva.

La experiencia conserva categoría diagnóstica, closing_reason RECOVERY_CLOSE_ONLY y recovery_close_only=true. Incluye los nuevos IDs, referencias, solicitud, quote y evidencia por fill. No presenta este cierre tardío como un diagnóstico que cumplió el plazo original de 60 segundos. La emergencia sigue activa incluso tras CLOSED.

C# impide borrar permisos consumidos, reescribir solicitudes de recovery o eliminar IDs de recuperación. Mantiene las garantías anteriores de intención/fills/comisiones originales inmutables y máximo un experimento diagnóstico.

## Comandos exactos

Desde la raíz del proyecto, primero el propietario registra el permiso local nuevo:

```powershell
.\scripts\paper-recovery-close.ps1 -Action Authorize -SessionMinutes 15
```

Después puede revisar el permiso:

```powershell
.\scripts\paper-recovery-close.ps1 -Action Status
```

Y ejecutar únicamente el cierre autorizado:

```powershell
.\scripts\paper-recovery-close.ps1 -Action Execute
```

Para inspeccionar o resolver una comisión tardía, sin enviar órdenes:

```powershell
.\scripts\paper-recovery-close.ps1 -Action Inspect
```

Inspect/Authorize/Execute inician la base Paper cuando hace falta y la detienen si la iniciaron; preservan el journal en disco. El servicio nunca levanta emergencia ni habilita StrategyPaper/Live.

## Verificación

**539 pruebas aprobadas sin omitidas: 337 Python y 202 C#.** Build sin errores ni advertencias, parser PowerShell comprobado y comando Inspect ejecutado contra IBKR Paper con mutaciones bloqueadas. La nueva autorización interactiva y Execute auténtico no se ejecutaron.

26 pruebas Python nuevas cubren permiso independiente, identidad exacta, expiración/proceso/Live, precio/cantidad/lado del SDK, cantidad remanente, inventario cero inexplicable, parcial, comisión tardía/moneda extranjera, fuente/permId/hash, desconocidos e incompletos, cambio durante quote, conflicto del journal, timeout de único uso, conservación de fill al desconectar, IOC pendiente modificado, no reenvío y persistencia PostgreSQL sin otra oportunidad diagnóstica. Tres pruebas C# nuevas impiden resetear autorización, cambiar cantidad o borrar el ID de recovery.

Logs: `artifacts/test-results/recovery-python.txt`, `recovery-dotnet.txt`, `recovery-close.trx`, `recovery-final-focused.txt`, `recovery-build.txt`. Hashes anteriores en `artifacts/paper-lab/recovery-protected-before.json`; autorización diagnóstica, excepción y emergencia permanecieron iguales, y recovery-close.dpapi continúa ausente.
