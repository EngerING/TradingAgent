# Perfil experimental Paper: WIN_TO_CONTINUE / FIRST_LOSS_STOPS_DAY

Preparación posterior: [V1, excepción EUR, calendario y exposición](strategy-paper-readiness.md). Pol?tica diaria conservada, excepción StrategyPaper preparada sin registrar y exposición operativa 1× sin cambios.

Actualización operativa 2026-10-05: [StrategyPaper continuo y comandos protegidos](strategy-paper-continuous.md). El perfil ahora está integrado como selección protegida de Authorize/Run; su activación real continúa bloqueada por EUR sin conciliar, emergencia y ausencia de un plan aprobado. El contenido siguiente documenta la entrega offline anterior.

Fecha: 2026-10-05. `PAPER_EXPERIMENTAL_10_PERCENT` preparado como candidato **inactivo**, exclusivamente para StrategyPaper/IBKR/PAPER_TRADING. No se activó el perfil, no se registró ni renovó autorización, no se levantó emergencia, no se conectó a IBKR y no se enviaron órdenes. Live permanece bloqueado. ExecutionDiagnostics conserva su presupuesto y sus controles independientes.

## Política preparada

- Asignación inicial virtual: US$100. El saldo ficticio de IBKR Paper no participa en el dimensionamiento.
- Riesgo máximo por entrada: `min(equity StrategyPaper × 0.10, US$10)`. El presupuesto efectivo también descuenta la pérdida acumulada restante, reservas y buffer. Nunca se redondea una cantidad hacia arriba para forzar una entrada.
- La pérdida estimada incluye stop, comisión de apertura, comisión de cierre, spread, slippage, gap adverso y costos conocidos representados en el contrato de ejecución. Datos de costos, margen, contrato o restricciones desconocidos/no fiables bloquean la entrada; costos adicionales deben incorporarse antes de marcar la evidencia como fiable.
- Exposición máxima: 1× equity virtual. Máximo una posición o reserva pendiente. Se conservan margen virtual, mínimos, incrementos y restricciones equivalentes de cuenta real.
- Cada día permite una primera oportunidad elegible. Solo un resultado neto final estrictamente positivo permite continuar ese mismo día. No existe un máximo fijo de operaciones en el ciclo experimental offline.
- La primera pérdida neta activa `DAILY_FIRST_LOSS_STOP` hasta el siguiente día. Un neto exactamente cero produce `DAILY_WIN_REQUIRED` y tampoco habilita otra entrada ese día.
- Un resultado incierto, comisión pendiente o reserva sin resultado final produce `PAPER_RESULT_UNRESOLVED`. El cambio de día y el reinicio no liberan esa reserva.
- Las ganancias aumentan el equity contable y nunca reponen pérdidas realizadas consumidas. Al consumir US$20, `CUMULATIVE_LOSS_LIMIT` suspende la asignación independientemente del día y del equity recuperado.

**Convención de día:** medianoche UTC, igual que el sistema existente; no es un calendario de sesión IBKR. Cambiar el offset del reloj no inicia otro día. Los resultados se imputan al día en que se resuelven con certeza: una comisión que confirma tarde una pérdida detiene el día de su resolución. Fines de semana, horarios negociables y señales siguen sujetos a la elegibilidad habitual.

## Ciclo offline y persistencia

`PaperRiskProfile.Study` evalúa sin mutar el estado; devuelve `active=false`, `executionAuthorized=false`, `liveEnabled=false` y la política de continuación. `OperationCeiling` está limitado a US$10 aun con equity superior a US$100. El presupuesto real puede ser menor por el allowance restante o las restricciones económicas.

`PaperRiskProfile.Mark`, `Reserve` y `Settle` implementan el ciclo offline. `Reserve` exige riesgo elegible y registra una intención única con riesgo pendiente; `Settle` requiere esa intención y neto/costos finales con certeza. Neto y comisiones se contabilizan una sola vez: el neto ya contiene costos, y los costos se suman de vuelta únicamente para presentar el resultado bruto. Repetir una liquidación idéntica es idempotente; cambiar su resultado es un conflicto. Estos métodos no realizan I/O ni conceden permiso de ejecución.

`AccountState.PaperContinuation` persiste el día, contador, último neto, primera pérdida, intención pendiente e historial de resultados. El historial verifica coherencia con equity contable, comisiones y pérdidas acumuladas. Un snapshot antiguo con actividad y sin historial no obtiene una primera oportunidad automáticamente: exige revisión/migración explícita, sin borrar halts, pérdidas o reservas.

El journal PostgreSQL almacena el estado por cuenta, con CAS, bloqueo transaccional y auditoría. Ahora rechaza eliminar o alterar resultados anteriores, reducir pérdidas, retirar una intención pendiente sin resultado, borrar halts permanentes o sustituir el ledger experimental por uno nuevo. Un rechazo revierte toda la transacción y conserva la revisión. Reiniciar un consumidor vuelve a cargar ese estado; cambiar de sesión no crea otra asignación.

No se añadió una migración ni se tocaron datos/autorizaciones reales. Los tests usan scopes sintéticos en PostgreSQL desechable.

## Límites anteriores que entran en conflicto

| Límite anterior | Conflicto y tratamiento |
| --- | --- |
| Ordinario 0.25%, máximo 0.50% | Sustituidos por 10% y máximo absoluto US$10 únicamente en la evaluación experimental. Los servicios vigentes conservan 0.25%/0.50%. |
| Diario 1% | Reducía el presupuesto inicial a US$1 y suspendía antes de la política solicitada. La evaluación experimental usa primera pérdida/ganancia para continuar. |
| Semanal 2%, drawdown 5% | Impedían la primera oportunidad del día siguiente tras una pérdida. No se aplican en el candidato experimental; el allowance acumulado US$20 permanece. |
| Prevención: drawdown 2% o tres pérdidas, factor 0.5 | Reducía adicionalmente el riesgo después de pérdidas ya contabilizadas. No se aplica en el candidato experimental. |
| Equity US$95/90/85: REVIEW/REDUCED/RESTRICTED | Las reducciones de riesgo y exposición a 0.5/0.25 contradicen el nuevo esquema. El candidato mantiene exposición 1× y la reducción natural por equity × 10%; no borra pérdidas. |
| Máximo de experimentos por sesión y cola de propuestas | `max_experiments` y el default de un experimento pueden cortar una cadena ganadora. Permanecen en la autorización/runner operativos y en Diagnostics: no hay selección del perfil experimental en ejecución. Una integración futura deberá separar esa frecuencia del modo diagnóstico. |
| Vigencia/autorización, emergencia, conciliación, datos fiables, restricciones económicas | Son condiciones de elegibilidad independientes y se conservan. Ninguna ganancia permite omitirlas. |

Los valores conservadores permanecen en `RiskPolicy` y `config/research-policy.json`; la ruta experimental interna elige explícitamente su nueva lógica. Las entradas públicas de RiskEngine y ExecutionFeasibilityAnalyzer siguen rechazando el candidato por su techo de 10%. Los comandos operativos del laboratorio también rechazan un ledger experimental. Preparar o persistir un estado offline no activa StrategyPaper.

El comando `--paper-risk-profile-study` sigue siendo offline, sin PostgreSQL, DPAPI o transporte IBKR. Sus entradas son `profile`, `account`, `request`, `asOf`, `broker`, `mode` y `liveEnabled`. La evaluación no guarda el ledger ni constituye autorización.

## Ejemplos y verificación

| Caso | Resultados netos finales | Resultado |
| --- | --- | --- |
| A | +4, +3, -10 | Tres liquidaciones, luego DAILY_FIRST_LOSS_STOP |
| B | -10 inicial | Una liquidación, luego DAILY_FIRST_LOSS_STOP |
| C | +2, 0 | Dos liquidaciones, luego DAILY_WIN_REQUIRED |
| D | +5, segunda con comisión pendiente | Reserva bloqueada incluso tras reiniciar/cambiar de día; solo un resultado final positivo permite continuar |

Los casos A–D usan asignaciones independientes. Si A y B ocurren consecutivamente en una misma asignación, equity US$97 implica riesgo máximo estimado US$9.70 al iniciar B. Un resultado adverso observado de -US$10 se contabiliza íntegro aunque exceda la reserva: no justifica reservar US$10 con equity inferior a US$100.

Regresiones: **353 pruebas aprobadas, 159 C# + 194 Python, cero omitidas**, incluidas todas las anteriores. Hay cobertura de medianoche UTC, offsets, pérdidas pendientes resueltas al día siguiente, reinicios JSON y PostgreSQL, CAS, reservas, rechazo de resets, liquidación idempotente, ganancias sin reposición y suspensión US$20 incluso con equity mayor que US$100. Se comprobaron costos incluidos una sola vez, exposición 1×, saldo ficticio excluido, alcance StrategyPaper y rechazo del perfil en comandos operativos. Build: cero errores/advertencias; compileall y demostración conservadora aprobados.

Las primeras ejecuciones de fixtures Python encontraron permisos de carpetas temporales en el sandbox; la suite completa se repitió con acceso adecuado y pasó. El script verify.ps1 también interrumpió Python por cómo PowerShell trata stderr; sus comprobaciones se ejecutaron individualmente hasta completarlas. Las pruebas de ejecución usan simuladores, nunca órdenes IBKR.

Activación futura pendiente de una petición explícita e integración con autorización protegida, conciliación y ejecución. Esta entrega no agrega esa selección al runner ni modifica la sesión real.

