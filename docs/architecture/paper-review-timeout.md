# Review: causa de PAPER_API_TIMEOUT, 2026-10-05

Se investigó con `senior-software-engineer` y consulta Graphify previa. No se ejecutó Review, Authorize ni Run durante la investigación. Autorización vencida/revocada, emergencia activa, Live bloqueado y ninguna orden enviada. StrategyPaper sigue bloqueado y su exposición permanece 1×.

## Journal original

| Revisión | Timestamp UTC | Evento |
| --- | --- | --- |
| 11 | 2026-10-05 17:18:58.108764 | START_SUSPENDED |
| 12 | 2026-10-05 17:18:59.228602 | INITIAL_EUR_ABSENCE_ACCEPTED_WITH_UNCERTAINTY |
| 13 | 2026-10-05 17:18:59.629507 | OWNER_REVIEW_PERMIT_CONSUMED |
| 14 | 2026-10-05 17:19:10.101771 | WORKER_SUSPENDED |

La primera conciliación completó todas las consultas y aceptó EUR_ROW_ABSENT con EUR `null`. El fallo se produjo durante la segunda conciliación realizada por `review_flat`, antes de cualquier limpieza de emergencia. El evento histórico WORKER_SUSPENDED tiene `data=null`: no conservó request, callback, errores ni estado del socket. Por ello, los detalles siguientes están comprobados en reproducciones posteriores del mismo flujo, no son telemetría recuperada del fallo histórico.

El journal contiene cero intenciones, cero órdenes/IDs asignados, cero sesiones/reservas/pérdidas diagnósticas y cero experiencias. `next_order_id=1` es un ID candidato anunciado por el broker y guardado al conciliar; no se asignó a una orden ni se envió. `eur_absence_consumed` está vacío. El permiso temporal de Review sí fue consumido; repetir Review exige un permiso nuevo generado por sus confirmaciones protegidas, no reutilizar ese permiso.

## Reproducción y causa

Se reprodujo dos veces con `execution_wire(..., read_only=True)`, bloqueo exclusivo y dos secuencias de `connect → snapshot(diagnostic=True) → additional_exposure`, sin construir PaperLab ni escribir el journal. Ambas fallaron en:

```text
segunda reqAccountSummary(requestId=6007, group=All, tags=$LEDGER:EUR)
callback esperado: accountSummaryEnd(6007)
IBKR code: 322
Maximum number of account summary requests exceeded
timeout: 10 segundos
```

La primera secuencia completó SUMMARY_6002, SUMMARY_6003, ACCOUNT_UPDATES, ACCOUNT_UPDATES_MULTI y posiciones. La segunda completó identidad, órdenes abiertas, posiciones, ejecuciones 6006 y órdenes completadas. Luego TWS rechazó el resumen 6007; no existió su callback de fin. Los códigos 2104/2106/2158 fueron avisos de servicios conectados y 2100 de desuscripción de datos de cuenta. No se observaron códigos de desconexión. El socket y la identidad seguían verificados al vencer el plazo; la desconexión posterior fue la limpieza local deliberada de la inspección.

La [documentación oficial de account summary](https://interactivebrokers.github.io/tws-api/account_summary.html) permite solo dos suscripciones activas y exige cancelarlas. En la combinación observada **TWS API 226 + SDK Python 10.50.2**, `cancelAccountSummary` en Protobuf no liberó las suscripciones previas. Una comparación que cambió únicamente esa cancelación al formato legacy del SDK oficial permitió completar ambas secuencias. No se afirma una causa interna de IBKR ni que ocurra en otras versiones.

## Corrección y verificación real de lectura

El adaptador selecciona formato legacy únicamente para `CANCEL_ACCOUNT_SUMMARY` cuando serverVersion=226. Las solicitudes de resumen, el transporte de órdenes y el resto del protocolo conservan su negociación original. No se aumentó el timeout ni se eliminó la segunda conciliación, sus fuentes o sus marcadores de fin.

Un rechazo de resumen ahora termina la espera inmediatamente como `PAPER_ACCOUNT_SUMMARY_REQUEST_FAILED`, con request y código; no fabrica `accountSummaryEnd` ni una fuente completada. Las esperas registran nombre de solicitud, requestId, callback esperado, resultado, timestamps UTC, duración, socket e identidad. WORKER_SUSPENDED persiste estos datos y códigos sanitizados antes de desconectar.

La verificación del adaptador corregido, sin overrides temporales, completó dos conciliaciones reales de lectura a las 17:34:38 UTC: SUMMARY_6007/6008 y posiciones adicionales 6010 terminaron sin 322; el journal permaneció en revisión 14. El comando existente `Diagnose` completó a las 17:35:14 UTC con consultas COMPLETE, posición/órdenes vacías, sin errores, cotización LIVE/OPEN y cero órdenes enviadas. Guardó únicamente su auditoría de lectura, llevando el journal a revisión 15. La conciliación ordinaria sigue BLOCKED por EUR_ROW_ABSENT; la ruta inicial protegida se observó elegible y válida para revisión. EUR sigue UNKNOWN/null.

## Excepción EUR y siguiente paso

La excepción registrada no fue consumida ni quedó vinculada a una autorización de ejecución. Conserva su proceso TWS y es reutilizable para una **nueva revisión protegida** hasta **2026-10-05 17:44:45.7911162 UTC** (**13:44:45 America/La_Paz**). El timeout no obliga por sí solo a registrarla de nuevo. Después del vencimiento, un cambio de proceso/identidad o exposición nueva, debe volver a comprobarse el estado y registrarse una aceptación nueva mediante el mecanismo existente; no se extiende la anterior.

El paso seguro que mantiene emergencia y autorización intactas es:

```powershell
.\scripts\paper-lab.ps1 -Action Diagnose
```

No ejecuta órdenes, no renueva autorización y no levanta emergencia. Ese comando se comprobó durante esta investigación.

Solo si posteriormente el propietario decide autorizar otra revisión que pueda levantar la emergencia, y la excepción sigue vigente:

```powershell
.\scripts\paper-lab.ps1 -Action Review -AllowAbsentEurDiagnostic
```

Si ya venció la excepción, el mecanismo de aceptación existente es `AuthorizeEurAbsence -Mode ExecutionDiagnostics -ExceptionMinutes 30`, con sus confirmaciones manuales; no se ejecutó aquí. No corresponde ejecutar Authorize ni Run en este paso.

## Regresiones y evidencia

Ocho pruebas nuevas: serialización legacy acotada a API226; preservación de los otros protocolos; liberación de ambas suscripciones en lecturas repetidas; rechazo 322 inmediato sin fin inventado; errores tardíos aislados; timeout identificado con socket capturado; distinción de positionEnd; y auditoría persistida de un Review fallido con emergencia y journal sin órdenes/reservas.

Regresiones completas ejecutadas: **493 pruebas aprobadas**, cero fallos y cero omitidas: **199 C# + 294 Python**, con PostgreSQL desechable habilitado. Incluyen las ocho pruebas nuevas. Los hashes SHA-256 de autorización DPAPI, emergencia y excepción EUR antes/después coinciden: permanecen intactos.

Artefactos:

- `artifacts/paper-lab/review-timeout-journal.json`: journal y vigencia de excepción.
- `artifacts/paper-lab/review-timeout-reproduction.json` y `review-timeout-reproduction-confirmation.json`: reproducciones y 322.
- `artifacts/paper-lab/review-timeout-cancel-compatibility.json`: comparación de cancelación.
- `artifacts/paper-lab/review-timeout-fixed-transport.json`: adaptador corregido, ambas conciliaciones completas.
- `artifacts/paper-lab/data-diagnostics.json`: Diagnose de lectura posterior.
- `artifacts/test-results/review-timeout.trx` y `review-timeout-python.txt`: regresiones.
