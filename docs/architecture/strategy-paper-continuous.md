# StrategyPaper continuo: preparación operativa

Actualización posterior: [V1 exacta, excepción StrategyPaper, calendario IBKR y economía](strategy-paper-readiness.md). Sustituye los estados EUR/calendario/estrategia del corte anterior conservado abajo. La excepción existe en código pero no está registrada; exposición sigue 1× y la promoción está bloqueada por equivalencia de salidas y evidencia económica.

Fecha: 2026-10-05. Perfil `PAPER_EXPERIMENTAL_10_PERCENT` integrado en los mecanismos existentes `Authorize`, `Review` y `Run`. **No se creó una nueva autorización real, no se levantó emergencia y no se inició el runner real.** Live continúa bloqueado. La activación efectiva requiere los pasos protegidos del propietario y conciliación satisfactoria.

## Estado real observado

Inspección de solo lectura a las 08:04 del 5 de octubre de 2026 (America/La_Paz), equivalente a 12:04 UTC:

- La identidad completa recibida coincidió exactamente con la identidad protegida original; solo se muestra terminación **3784**.
- TWS cambió de proceso: la autorización vencida falla con `UNVERIFIED_PAPER_SESSION`. El handshake actual no concede permiso de órdenes. Se requiere nueva comprobación manual de Paper/identidad.
- BID/ASK LIVE: 1.12070 / 1.12070, sesión EUR/USD OPEN. Es una observación histórica al corte indicado, no una cotización reutilizable para una orden futura.
- Cero órdenes abiertas y cero posiciones con cantidad distinta de cero en posiciones, cartera y consulta específica.
- `EUR_ROW_ABSENT`, saldo EUR null/UNKNOWN: `EUR_CASH_RECONCILIATION_UNAVAILABLE`. Posiciones y órdenes vacías no prueban EUR=0. La excepción diagnóstica inicial sigue excluida de StrategyPaper.
- Emergencia activa en journal y archivo local. Capital virtual US$100, consumo acumulado US$0.
- El contrato informó mínimo e incremento Paper 0.01 EUR. Con ese ASK, exposición US$100 impone un techo teórico de 89.22 EUR redondeado hacia abajo; no valida costos, stop, permisos o restricciones equivalentes reales. La cantidad ejecutable actual es cero por los bloqueos.
- No existe un plan operativo protegido y aprobado para esta sesión. La configuración de calendario existente es `PROVISIONAL_REGULAR_TEMPLATE`; no se convierte automáticamente en evidencia verificada. Faltan selección/aprobación de estrategia y evidencia vigente de comisiones, slippage, mínimos, margen y restricciones.

`artifacts/paper-lab/data-diagnostics.json` conserva la evidencia del corte. Diagnose usa un vínculo nuevo de inspección al proceso actual y la identidad protegida solo como ancla. El adaptador bloquea place/cancel y Protobuf; la inspección no puede servir como autorización de ejecución. La autorización de órdenes y emergencia se conservan.

## Integración y reglas

`Authorize -Mode StrategyPaper -RiskProfile PAPER_EXPERIMENTAL_10_PERCENT -Continuous` selecciona y activa el perfil dentro de una **nueva autorización DPAPI**, junto con aprobación explícita de una versión y el hash de un plan declarativo validado. No existe una acción separada `Activate`: inventar ese comando sería incorrecto. `Run` lee exclusivamente el perfil y plan de esa autorización; pasar parámetros de perfil a un Run sin autorización no lo activa.

El protocolo C# añade operaciones puras `experimental-*` al journal existente para calcular inicialización, mark, riesgo, reserva, liquidación y liberación sin fill. No tienen transporte ni permisos de ejecución. Los comandos conservadores siguen rechazando el ledger experimental y la configuración global conservadora no se relaja. La autoridad de órdenes permanece en la autorización protegida y los guards del adaptador Python.

El ciclo continuo descarga velas MIDPOINT nativas 15m/1h/4h cerradas y calcula indicadores con el motor causal existente. Admite planes BUY de trend, pullback o mean_reversion, explícitamente aprobados para el motor `research-d-v1-long-paper-v1`, con salidas bracket/tiempo. No supone que una aprobación de una estrategia de investigación cubra esta variante operativa. Señales SELL u otros motores son rechazados, no transformados en BUY. Sin una señal reciente válida, no hay orden ni cuota diaria.

El runner refresca mercado en límites de vela, descarta señales de más de 30 segundos y evita generar una entrada desde una vela futura/incompleta. Se mantienen las restricciones multitimeframe. Cotización no ejecutable, calendario/evidencia desconocidos o costos superiores al potencial de beneficio producen bloqueo/rechazo observable. El máximo de experimentos de Diagnostics no limita la cadena de señales ganadoras del perfil continuo.

El tamaño se obtiene del RiskEngine con el máximo de cantidad/nominal autorizado, nunca de una cantidad fija. Se aplica `min(10% equity StrategyPaper, US$10)`, pérdida acumulada restante, stop, ambas comisiones, spread, slippage, gap, margen virtual y exposición máxima 1×. El mínimo/incremento del contrato actual se vuelve a comprobar antes de reservar. Un ASK más fino que la rejilla conservadora de orden se redondea hacia arriba a 0.00005, y ese precio se incorpora al spread/riesgo/nominal del cálculo; no se dimensiona al ASK antiguo para enviar un precio superior.

La intención estable usa cuenta interna + versión + instante de señal; renovar la sesión no permite repetir la señal. La reserva de capital y la intención se guardan juntas mediante CAS antes del primer envío. Una reserva pendiente, partial fill, comisión ausente/indisponible, estado incierto o conciliación incompleta impiden otra entrada. Un intento cancelado/rechazado sin fills solo libera la reserva después de confirmar que sus órdenes ya no existen; no se registra un break-even ficticio y su ID no se reutiliza.

Solo neto final positivo permite continuar. Neto negativo fija `DAILY_FIRST_LOSS_STOP`; cero fija `DAILY_WIN_REQUIRED`. El runner continúa recopilando cotizaciones/velas durante el bloqueo diario. El día sigue siendo medianoche UTC. Un resultado resuelto tarde se imputa al día de resolución. Ganancias no reponen pérdidas consumidas; US$20 suspenden la asignación independientemente del día o de la renovación de sesión. Review y Authorize no reinician ese allowance; una futura autorización para otra asignación requeriría un cambio explícito distinto.

Emergencia, revocación, pérdida de conexión, protección no confirmada, journal conflictivo y resultado adverso por encima de la reserva conservan los bloqueos adicionales. Las posiciones propias conservan protección y gestión limitada después del vencimiento; no hay renovaciones automáticas. Al vencer autorización o evidencia, termina cuando queda plano; si faltan costos mantiene reserva/bloqueo y exige resolución.

## Permiso nuevo de Review

`Review` pide nuevamente la identidad completa oculta y la comprobación manual de Paper, descubre la cuenta actual y vincula el permiso DPAPI de dos minutos al PID/instante actual de TWS. El permiso es de un uso y solo lectura; no renueva el permiso antiguo ni autoriza entradas. Esto permite revisar una sesión cuyo TWS cambió, sin reutilizar su autorización vencida para ejecutar.

La emergencia solo se limpia con cuenta plana, órdenes/costos/journal conciliados y permiso de Review vigente. Con EUR todavía ausente, **Review ordinario fallará y conservará emergencia**. No utilizar `-AllowAbsentEurDiagnostic` para eludir este bloqueo de StrategyPaper. No se ejecutaron Revoke, Review ni Authorize reales en esta preparación.

## Plan requerido para Authorize

La ruta y versión deben corresponder a evidencia revisada por el propietario, no a los fixtures de tests. El validador implementado está en `python/trading_agent/paper_strategy.py`. El JSON exige exactamente:

| Campo | Contenido requerido |
| --- | --- |
| schema_version | 1 |
| engine | research-d-v1-long-paper-v1 |
| strategy_version / strategy_id / name | Versión identificable aprobada; trend, pullback o mean_reversion; nombre |
| instrument / side / exit_policy | EUR/USD / BUY / BRACKET_OR_TIME_LIMIT |
| indicators | Parámetros completos del indicador existente, revisados para esa versión |
| calendar | ForexCalendar con cobertura suficiente para el warmup histórico y fecha actual; source y status VERIFIED_EXPLICIT_SESSIONS o VERIFIED_REGULAR_SESSIONS respaldados por evidencia |
| evidence_at / evidence_expires_at | Instantes con zona, vigencia máxima 24 h, sin fecha futura |
| execution_requirements | quoteToAccountFx, multiplier, minQuantity, quantityStep, marginRate, availableMargin, commissionFixedRoundTrip, commissionPerUnitRoundTrip, slippagePerUnit, adverseGapPerUnit y execution |
| execution | ExecutionFacts PAPER_TRADING, fuente independiente, STANDARD/ODD_LOT, ambas comisiones, confiabilidad explícita de costos/margen/contrato, permiso de entrada y EquivalentRealAccount completo |

No se entregó un plan con comisiones o permisos inventados. Los indicadores predeterminados y el calendario provisional del repositorio no constituyen aprobación. El propietario debe revisar la fuente de costos conocidos/estimados conservadoramente y las restricciones equivalentes. El plan se copia dentro de la autorización DPAPI; editar posteriormente el JSON externo no cambia el plan autorizado. La vigencia de sesión queda limitada también por el vencimiento de la evidencia.

## Comandos existentes, en el orden requerido

Ejecutarlos localmente en la raíz del proyecto. **Hoy están condicionados a resolver EUR y disponer del plan aprobado**. No ejecutar Run esperando que ignore esos bloqueos.

```powershell
.\scripts\paper-lab.ps1 -Action Diagnose
.\scripts\paper-lab.ps1 -Action Revoke
.\scripts\paper-lab.ps1 -Action Review
```

Review solicita `PAPER_REVIEW_CHECKED` y `REVIEW_FLAT_PAPER`, además de la identidad completa oculta. Si falla conciliación, detenerse aquí.

Después de definir `$StrategyVersion` y `$StrategyEvidencePath` con la versión y el JSON de evidencia real revisados:

```powershell
.\scripts\paper-lab.ps1 -Action Authorize -Mode StrategyPaper `
  -RiskProfile PAPER_EXPERIMENTAL_10_PERCENT -Continuous `
  -StrategyVersion $StrategyVersion -StrategyEvidencePath $StrategyEvidencePath `
  -DiagnosticLossBudget 0 -MaxQuantity 100 -MaxNotionalUsd 250 `
  -MaxHoldSeconds 60 -SessionMinutes 1440

.\scripts\paper-lab.ps1 -Action Status
.\scripts\paper-lab.ps1 -Action Run
```

100 EUR y US$250 son límites superiores del permiso, no cantidades de órdenes; el RiskEngine reduce cantidad/nominal al equity actual y demás restricciones. La sesión dura como máximo 24 h y puede durar menos por evidencia. Authorize pide sus comprobaciones manuales originales y `APPROVE_STRATEGY_PAPER_PLAN` después de mostrar versión/hash/alcance. No se solicita confirmación por cada orden una vez autorizada y vigente la sesión.

Run es continuo en primer plano. La terminal debe permanecer abierta; no hay un servicio de Windows ni un comando existente de daemon al que atribuir un arranque automático. Después de ejecutar los pasos y confirmar sesión válida, se puede iniciar/observar este mismo runner sin autorizaciones por orden. Evitar dos runners simultáneos: bloqueo de proceso y CAS lo impiden. Status es lectura de la autorización, no certificación de que todas las barreras de ejecución estén superadas.

Para detener nuevas entradas conservando protecciones:

```powershell
.\scripts\paper-lab.ps1 -Action EmergencyStop
```

## Registro por operación

Se guardan versión y nombre, señal/motivo e indicadores en contexto causal, precio esperado, cantidad, stop/objetivo, fills con precio ejecutado y hora recibida/raw del bróker, ambas comisiones, spread de llegada, diferencias de ejecución por fill y slippage estimado, P&L bruto/neto, equity resultante, allowance restante, motivo de cierre y decisión WIN_TO_CONTINUE/DAILY_FIRST_LOSS_STOP/DAILY_WIN_REQUIRED/CUMULATIVE_LOSS_LIMIT. Experiencias finalizadas son inmutables. Pendientes permanecen en órdenes/reservas y auditoría sin inventar neto o comisión cero.

## Verificación

Regresión final: **385 pruebas aprobadas, 161 C# + 224 Python, cero omitidas**. Se preservaron todas las regresiones anteriores. Build sin errores/advertencias. Las pruebas incluyen el ciclo A–D con motor C# real y bróker sintético, también contra PostgreSQL desechable; reinicios/cambio de sesión, journal, cuota de un experimento sustituida solo en el perfil, bloqueo diario con recopilación continua, cancelaciones sin fill, costos pendientes, redondeo/precio conservador, cantidades automáticas, aprobación/expiración y separación Live/Diagnostics. El SDK serializa las brackets/OCA y guards en pruebas sin red; esas pruebas no certifican fills, comisiones ni OCA efectivas en TWS. Solo identidad, mercado y exposición se observaron hoy en IBKR mediante lectura.

