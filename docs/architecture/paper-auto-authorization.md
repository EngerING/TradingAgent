# PaperEligibility y autorización PaperAuto persistente

Preparación solicitada el 2026-10-05 local, completada con timestamps UTC. No se concede permiso real, no se limpia emergencia y no se ejecuta Run en esta fase.

`Candidate`, `PaperEligible` y `LiveApproved` representan alcances diferentes. La nueva evaluación técnica Paper no es promoción a PAPER_EXPERIMENTAL, certificación de rentabilidad, viabilidad de US$100 reales ni aprobación Live. Nunca asigna LiveApproved. El permiso PaperAuto y una estrategia PaperEligible siempre se rechazan en Live.

La evaluación lee las versiones originales de PostgreSQL en una transacción de solo lectura, verifica su hash y las relaciona con el artifact auténtico de seis meses. Se utilizan exclusivamente las versiones 1 de la configuración `1e2784bd53f4`, sin crear versiones ni modificar señales, indicadores, parámetros o salidas:

| Estrategia | StrategyVersion |
| --- | --- |
| Trend following | `9860cd16f4f43d38ca7c29f161aea82e17dea100da48bb78259457cc31133211` |
| Trend pullback | `b622e9522da52b2aec358a4623d671b5398990d00e812a8fb81e2c71d155a9d3` |
| Mean reversion | `fcd256a67a14d26c3e58cf73e0906713c09ed50aef69f67b99e92f52fcac80c2` |

`config/paper-eligibility.json` habilita la evaluación de las tres estrategias existentes y selecciona trend como candidata predeterminada. Se comprueban registro, habilitación, estructura, parámetros completos, reproducción de Signal/NoSignal del artifact y pruebas asociadas. Los resultados quedan en `artifacts/paper-lab/paper-eligibility.json`; STRATEGY_PAPER_ELIGIBLE/INELIGIBLE se auditan con motivos y cuenta enmascarada en `session-events.jsonl`. Un rechazo explícito STRATEGY_PAPER_EVIDENCE_REQUIRED del perfil se comunica como veto, cantidad cero; cualquier error no reconocido sigue bloqueando.

El nuevo plan técnico usa el adaptador RESEARCH_D_V1 existente. No cambia cuerpos de generación de señales/salidas ni el RiskEngine C#. La prueba modelada no se presenta como equivalencia efectiva del broker. Los planes anteriores de promoción y sus validaciones siguen separados. Se conservan la rejilla de precios del adaptador, datos actuales, semántica original, calendario auténtico IBKR y todos los vetos de admisión/transporte.

## Permiso operativo y emergencia

`.local/paper-auto-authorization.dpapi` es independiente de los permisos vencidos de ExecutionDiagnostics y RecoveryClose. DPAPI CurrentUser protege identidad completa, AccountBindingId, operador, alcance PAPER_AUTO_ONLY, sesión, versión, hashes, fecha de concesión, vencimiento y estado. El consentimiento explícito cubre múltiples operaciones durante su vigencia, sin autorización por orden. Duración predeterminada 480 minutos; máximo 1440. El reinicio o la reconexión no cambian el vencimiento ni la sesión. Cada gate relee revocación y rechaza cuenta, versión, componentes o entorno diferentes. Una identidad de proceso fresca es un certificado efímero, nunca una renovación de permiso.

La emergencia persiste en archivo/journal y nunca se limpia por reinicio, concesión o diagnóstico. ClearPaperEmergency reutiliza Review con permiso protegido, comprobación de cuenta completa, lecturas frescas, órdenes/posiciones conocidas y conciliación. Registra EMERGENCY_STOP_CLEARED con UTC y entorno. Una lectura conciliada de órdenes históricas preserva el estado actual de emergencia; una conciliación fallida la activa.

PaperAutoReady exige PASS en las nueve condiciones: IBKR_CONNECTED, ACCOUNT_VERIFIED, ENVIRONMENT_PAPER, RECONCILIATION, EMERGENCY_STOP, PAPER_AUTHORIZATION, STRATEGY_PAPER_ELIGIBLE, RISK_ENGINE y EXECUTION_GUARD. La autorización válida o la elegibilidad técnica no significan que una señal tenga permiso de ejecución. Cada entrada conserva el flujo Strategy → Signal → RiskEngine → ExecutionFeasibility → PaperExecutionGuard → IBKR. NO_TRADE se registra y nunca fuerza una cuota.

La concesión exige conciliación flat; no se concede sobre inventario incierto. La gestión tras reinicio solo acepta inventario/órdenes de la misma sesión y conciliación completa de las fuentes. La revocación bloquea inmediatamente nuevas entradas; únicamente puede continuar la gestión protegida de inventario ya propio. StopPaperAuto activa emergencia duradera y solicita terminar el proceso cuando las intenciones estén resueltas, sin matar a ciegas un runner con inventario.

## Comandos del operador

Ejecutar desde la raíz. Esta secuencia es explícita: ninguno fue ejecutado para conceder permisos, limpiar emergencia o operar durante la preparación.

```powershell
# 1. Estado y diagnóstico actual, cuenta enmascarada
.\scripts\paper-lab.ps1 -Action Di
# 2. Revisión protegida para limpiar únicamente la emergencia Paper
.\scripts\paper-lab.ps1 -Action ClearPaperEmergency
# 3. Un consentimiento PaperAuto con vencimiento
.\scripts\paper-lab.ps1 -Action GrantPaperAuto -PaperAutoMinutes 480 -PaperAutoStrategy trend
# 4. Estado agregado actualizado
.\scripts\paper-lab.ps1 -Action PaperAutoStatus
# 5. Runner continuo; exige PaperAutoReady
.\scripts\paper-lab.ps1 -Action RunPaperAuto
# 6. Desde otra terminal: kill switch y parada segura
.\scripts\paper-lab.ps1 -Action StopPaperAuto
# 7. Revocación persistente inmediata
.\scripts\paper-lab.ps1 -Action RevokePaperAuto
```

GrantPaperAuto exige GRANT_PAPER_AUTO y la comprobación explícita del operador de Paper, permisos FX y API no Read-Only; no pide el Account ID. Una sesión activa impide conceder otro permiso. ClearPaperEmergency conserva las confirmaciones protegidas existentes de Review. Ningún comando habilita Live ni renueva el permiso diagnóstico vencido.

## Riesgo y límites efectivos

US$100 iniciales, presupuesto acumulado US$20, exposición 1×, una posición, riesgo min(10% equity, US$10) con costos; WIN_TO_CONTINUE / FIRST_LOSS_STOPS_DAY. Ganancias no restauran pérdidas consumidas. Comisiones pendientes, parciales e incertidumbre bloquean entradas. Nunca se dimensiona con el saldo IBKR ficticio.

Las restricciones equivalentes de cuenta real, margen y permisos efectivos siguen UNKNOWN; no se rellenan con supuestos favorables. Se conservan los costos observados Paper US$2 por lado y estimaciones conservadoras, sin declararlos confiables para Live. Por ello el veto actual de admisión sigue siendo STRATEGY_PAPER_EVIDENCE_REQUIRED. Limpiar emergencia y conceder PaperAuto permite análisis autónomo sujeto a guards; no garantiza ni fuerza una orden. Las tres estrategias siguen sin promoción económica/Live.

Los artifacts de verificación son `artifacts/test-results/paper-auto-build.txt`, `paper-auto-csharp.txt`, `paper-auto-python.txt`, `paper-auto-new-tests.txt`, `paper-eligibility-tests.json` y el diagnóstico `artifacts/paper-lab/paper-auto-status.json`.

## Verificación final

623 pruebas: 585 anteriores y 38 nuevas; 421 Python y 202 C#, cero fallos y cero omitidas. PostgreSQL desechable se utilizó para todas las integraciones existentes. Build sin advertencias/errores; sintaxis PowerShell y compilación Python comprobadas. Las 70 pruebas asociadas a elegibilidad también pasan y quedan vinculadas a hashes de los componentes finales. Las transmisiones en pruebas usan exclusivamente fixtures; la lectura real utiliza transporte con mutaciones bloqueadas.

Lectura real del 2026-10-06 02:56:57 UTC: cuenta ***3784 verificada, EUR/USD CASH con posición cero, EUR cash confirmado 0.00, ninguna orden abierta, reserva diagnóstica cero, calendario IBKR_AUTHENTIC_SESSIONS y BID/ASK LIVE 1.12138/1.12141 con mercado OPEN. Esta cotización es evidencia de esa lectura; el runner solicita otra actual antes de una entrada. Las tres versiones están PaperEligible técnico, sin promoción económica o Live.

| Condición | Estado |
| --- | --- |
| IBKR_CONNECTED | PASS |
| ACCOUNT_VERIFIED | PASS |
| ENVIRONMENT_PAPER | PASS |
| RECONCILIATION | PASS |
| EMERGENCY_STOP | BLOCKED |
| PAPER_AUTHORIZATION | NOT_GRANTED |
| STRATEGY_PAPER_ELIGIBLE | PASS |
| RISK_ENGINE | PASS |
| EXECUTION_GUARD | PASS |

PAPER_AUTO_READY=false. El permiso antiguo continúa vencido; el nuevo permiso PaperAuto no existe todavía. El probe de admisión conserva allowed=false, quantity=0 y STRATEGY_PAPER_EVIDENCE_REQUIRED. Los hashes de AccountBinding, autorización antigua, RecoveryClose, excepción EUR y marca de emergencia coinciden con los anteriores a la preparación. Cero órdenes enviadas, cero permisos concedidos, emergencia activa y Live bloqueado.

Archivos añadidos: `config/paper-eligibility.json`, `python/trading_agent/paper_eligibility.py`, `python/trading_agent/paper_auto.py`, `python/tests/test_paper_auto.py` y este documento. Archivos modificados: `src/TradingAgent.Api/PaperLabCommand.cs`, `python/trading_agent/paper_lab.py`, `python/trading_agent/paper_lab_runner.py`, `python/trading_agent/paper_strategy.py`, `python/trading_agent/paper_lab_diagnostics.py`, `scripts/paper-lab.ps1` y `docs/architecture/paper-execution-laboratory.md`. Sin cambios en AccountBinding, configuración de cuenta, código C# de riesgo, capital/presupuesto/exposición, parámetros, generación de señales, indicadores ni cuerpos de decisión de salida.

## Revalidación del 2026-10-06

La solicitud adjunta repite exactamente la preparación anterior. No se duplicó la implementación ni se añadieron pruebas: se ejecutaron nuevamente el build y las suites completas. Resultado: 623 aprobadas, 421 Python y 202 C#, cero omitidas, build sin errores/advertencias; sintaxis PowerShell y compilación Python también comprobadas. Los logs de esta ejecución están en `artifacts/test-results/paper-auto-revalidation/`.

Diagnóstico de solo lectura observado a las 06:51:31 UTC (02:51:31 America/La_Paz): cuenta ***3784 verificada, sin posiciones ni órdenes abiertas, EUR cash CONFIRMED_ZERO, reserva diagnóstica cero y calendario IBKR_AUTHENTIC_SESSIONS. Cotización LIVE a las 06:51:35 UTC: BID 1.12093, ASK 1.12094, mercado OPEN, sin errores de cotización IBKR. La cotización describe únicamente esa lectura.

Las nueve condiciones conservan los estados de la tabla anterior: siete PASS, emergencia BLOCKED y autorización PaperAuto NOT_GRANTED; PaperAutoReady=false. Las tres estrategias siguen PaperEligible técnico, ninguna LiveApproved ni promovida económicamente. STRATEGY_PAPER_EVIDENCE_REQUIRED mantiene quantity=0 y allowed=false por restricciones equivalentes de cuenta/margen desconocidas. No se eliminó ese veto. Los hashes de AccountBinding, permisos anteriores, excepción EUR y emergencia no cambiaron; el permiso PaperAuto sigue ausente. No se ejecutaron ClearPaperEmergency, GrantPaperAuto ni RunPaperAuto. Cero órdenes nuevas y Live bloqueado.
