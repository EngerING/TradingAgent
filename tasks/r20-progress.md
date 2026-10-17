# R20 — punto de continuación

Actualizado 2026-10-14. Fases pequeñas, Astra High, Graphify primero y lectura
selectiva. Una fase por entrega. No iniciar otra sin instrucción del usuario.
No transmitir órdenes Paper/Live, conceder autorizaciones ni editar los 74 protegidos.

## Continuación vigente: fase 3, validación técnica Shadow — 2026-10-14

Informe: `artifacts/aggressive-growth-r20-20261010/r20-v2-phase3-20261014/report.md`.
TECHNICAL_VALIDATION sólo omite target neto no positivo; preparación validada,
contexto y permiso Shadow independientes ligados en Python/SQL. Asignación USD
conectada al sizing; costos UNKNOWN y restantes límites conservados. Sin selección
operativa de riesgo/pérdida diaria/posiciones ni activación automática.
Runner replay registra rechazos, libera reservas abandonadas sin fabricar fills
y conserva gestión/Stop. ReadOnly reutiliza lector auténtico sin admitir posiciones.
159 Python +112 Vitest +4 Playwright =275 finales; reinicio test55432 conserva
ocho tablas y posiciones; Dashboard HTTP=DB, capturas desktop/móvil revisadas.
Último diagnóstico auténtico19:46:07UTC, AccountBinding exacto***3784,688/149
barras completas1H/4H; es corte histórico, no feed continuo. Cero órdenes.
74/74 protegidos y3/3V1 coinciden. Relectura V1/seguridad actual NO completada:
55433 y5080 no escuchaban; no se reiniciaron. Última evidencia histórica V1:
STOPPED3858 yhead ec20e823…118176830d. No afirmar una lectura nueva de ese journal.
Host5182 ytest55432 cerrados; sin runners. Forward auténtico y Paper pendientes
de store/frontera/roles/políticas y autorizaciones posteriores; no declarar listo.

## Corte histórico: fase 2, configuración económica — 2026-10-14

Informe: `artifacts/aggressive-growth-r20-20261010/r20-v2-phase2-20261014/report.md`.
Seis controles en la página existente; documento v2 separado, asignación USD y
multiplicador independientes del cap agregado. Save/Validate nunca activa.
Riesgo, límite diario y posiciones vacíos al entrar;100/20/20 es sólo el ejemplo.
Persistencia append-only/CAS/idempotente exclusiva test55432; lector no edita,
admin no obtiene ejecución. Controles Start/Stop/Switch deshabilitados y backend
denegado. UNKNOWN conservado; costos/margen operativos pendientes.
Python144 distintos,Vitest110,Playwright9; typecheck/build lab aprobados. Reinicio
test conserva hashes; API recupera revisión10 sin perfil activo. Capturas reales.
V1 STOPPED3858, head final intacto;74 protegidos y3V1 coinciden. EmergenciaACTIVE,
LiveBLOCKED,Paper no autorizado. Sin cohortes,IBKR,deploy5080 o migracionesPaper.
Hostlab yDBtest cerrados al final; launcher manual documentado. Siguiente fase3
requiere nueva aprobación; no arranque automático ni heredar valores sintéticos.

## Corte histórico: V2 preparación operativa sin activación — 2026-10-13

Informe: `artifacts/aggressive-growth-r20-20261010/r20-v2-readiness-20261013/report.md`.
Lectura IBKR auténtica controlada en r20_market: identidad exacta, calendario,
quotes y barras; jamás concede apertura. Runner de replay en r20_runner y control
PostgreSQL test: preregistro de fuentes inmutable, Stop append-only, exclusión local,
rechazo SQL de nuevas reservas/aperturas tras Stop. Gestiona inventario y cambio
de día sin perfil vigente; no hay Run operativo, permiso automático ni cohorte.
Panel de seguimiento real dentro de R20ConfigurationPage, GET autenticado del
ledger, desktop/móvil y STALE; build/host sólo laboratorio. Refresco explícito,
sin SignalR V2 nuevo ni despliegue5080.

Wrapper V1 Prepare denegado; store rechaza nuevo ID operativo head0, Debug/R20
compilados. Lectura/recuperación existente conservadas. SQL directo/binarios
históricos no equivalen a exclusividad global; no grants ni cambios011.
Política de costos propuesta sin reducir supuestos: financiación/slippage/margen
siguen sin cota suficiente; entradas auténticas BLOCKED. V1 STOPPED3858 intacto.
Checklist y límites: `docs/architecture/r20-v2-operational-readiness.md`.
Final: Python184, C#528, Vitest107, Playwright3; 822 aprobadas, sin fallos ni
omisiones finales. Reinicio físico test55432 conserva siete conjuntos y proyección;
clúster de pruebas y host5182 detenidos, datos conservados. Protegidos74/74 y
V1 fuentes3/3 coinciden; EmergencyStop ACTIVE y Live BLOCKED_BY_BACKEND.
Detenerse tras evidencia final; siguiente despliegue/activación requiere aprobación.

## Corte histórico: V2 ciclo Shadow de laboratorio — 2026-10-13

Informe: `artifacts/aggressive-growth-r20-20261010/r20-v2-shadow-cycle-20261013/report.md`.
Ciclo sintético reserva→posición→seguimiento→cierre, contabilidad atómica, CAS,
idempotencia y lectura conjunta REPEATABLE READ. Reutiliza signal R20 sin cambios;
IDs por estrategia/timeframe/cierre; conserva perfil/SL/TP/costos de entrada.
La admisión incluye exposición y margen de posiciones persistidas. Precio/perfil
cambiados después de reserva exigen reevaluación. Activar perfil no crea permiso.
Datos inválidos conservan inventario; apalancamiento administrativo no liquida;
salidas defensivas modeladas conservadas. Medianoche sin referencia verificable
bloquea entradas, no gestión. V1 sigue STOPPED3858, head/ec20e823…830d, inventario0.
74 protegidos y3 archivos V1 intactos. Sin órdenes/migraciones/cohortes operativas.

Regresión focalizada final:169 Python (140 previas+29 de ciclo), sin omisiones;
ver resultado final en test-results.json. Reinicio real sólo test55432 conserva
hashes de perfiles, reservas, contabilidad y ciclo; recuperación conserva abierto,
cerrado y pendiente, luego cierra virtualmente sin doble cargo. Base UUID preservada.
No API/frontend nuevos: panel de seguimiento y contratos de lectura propuestos en
`docs/architecture/r20-v2-shadow-monitoring-proposal.md`; ciclo/gates documentados
en `r20-v2-shadow-cycle.md` y `r20-v2-shadow-cost-margin-gates.md`.

Probes IBKR Paper read_only/Research verifican cuenta exacta***3784, LIVE/OPEN y
675/146 velas nativas completas1H/4H sin gaps esperados; NO_BREAKOUT en el corte.
Clientes desconectados; evidencia auténtica no insertada como posiciones. Slippage,
financiación y margen no acotados: normal Shadow BLOCKED. No habilitar fuente real
quitando el guard sintético. Falta aprobación de política/ingestión/store operativo,
frontera económica, Stop V2/singleton y contrato de salida intrabar antes de un Run.
Persisten creación/arranque de otras V1 y emisores heredados: no afirmar exclusividad
R20-Only ni exclusión por cuenta. Esperar aprobación nueva; no arrancar V2.

## Corte histórico: V2 brechas de laboratorio — 2026-10-12

Informe: `artifacts/aggressive-growth-r20-20261010/r20-v2-gaps-20261012/report.md`.
250 pruebas distintas aprobadas:140 Python,104 Vitest,6 Playwright/HTTP. Reserva
atómica de pruebas comparte lock/CAS con perfiles/contabilidad, sin fills/cohortes.
Dos procesos: un ganador. Costos RESERVED y riesgo pendiente excluyentes; ACK
perdido recupera recibo, conexión perdida revierte. Restart preserva89 scopes y43
recibos finales. Roles DB NOLOGIN: reader/perfiles/Shadow/Paper-disabled separados;
API escoge rol desde principal, cliente no lo elude. UI real,5 controles, historial
y recuperación tras recarga desktop/móvil. Login limitado y Vitest4.1.11; audit0.
Propuesta EURUSD_COST_PROPOSAL_V1 no activada: comisión pública estimada y piso de
spread V1 conservado; slippage/financiación siguen bloqueados, sin cota empírica.
Profile/día requieren conciliación, inventario abierto incompleto bloquea entradas.
V1 leído STOPPED3858;74 protegidos/motor/config/core V2 intactos; EmergencyStop activo,
Live bloqueado. Sin migraciones/fixtures operativos ni órdenes. Contrato futuro:
`docs/architecture/r20-v2-shadow-boundary.md`; política:
`docs/architecture/r20-v2-cost-policy.md`. No listo para Shadow: falta ciclo de vida,
fuente auténtica, costos/margen adoptados y store/credenciales operativos. No quitar
guard TestStore para apuntarlo a Paper. No declarar exclusión por cuenta/R20-Only
global ni iniciar V2 sin aprobación nueva. Host/testDB cerrados; datos conservados.

## Corte histórico: V2 API y configuración diaria en pruebas — 2026-10-12

Informe: `artifacts/aggressive-growth-r20-20261010/r20-v2-api-dashboard-20261012/report.md`.
Host ASP.NET Core ConfigurationLab5182 y sección Vue/Pinia reutilizan núcleo V2;
ledger de configuración independiente, sin autoridad de órdenes ni arranque.
Cinco valores explícitos, DRAFT/VALIDATED/ACTIVATED_FOR_SHADOW, caducidad Santo
Domingo, hashes/CAS/idempotencia y bloqueos. UNKNOWN deniega activación y deja
preview sin cálculo. Latch bajo límite reducido conserva cruces históricos aunque
equity se recupere; prueba RED→GREEN, núcleo matemático sin cambios.
120 Python +104 Vitest +5 Playwright/HTTP =229 aprobadas; builds correctos.
Reinicio real de test55432 conserva configuración rev7 y contabilidad rev1;
capturas desktop/móvil revisadas. Fixtures sólo en base nueva r20_v2_test_*.
74 protegidos, motor/config V1 y núcleo matemático V2 intactos. V1 leído STOPPED3858;
EmergencyStop ACTIVE y Live bloqueado. Cero cohortes/órdenes/migraciones operativas.
Host de laboratorio y test55432 cerrados; datos conservados. Dashboard5080 y
Paper55433 intactos. No se desplegó frontend/dist operativo. Diseño/limitaciones:
`docs/architecture/r20-v2-configuration-lab.md`. Persisten calibración, integración
atómica del motor, privilegios DB, auth operativa y vías V1 pendientes. No declarar
R20-Only global ni iniciar V2/ejecución Paper sin aprobación nueva.

## Corte histórico: V2 persistencia aislada y costos — 2026-10-12

Informe: `artifacts/aggressive-growth-r20-20261010/r20-v2-persistence-20261012/report.md`.
V1 sigue STOPPED3858, sin inventario ni runner. Núcleo matemático V2 previo intacto.
Nuevo TestStore/snapshot y schema exclusivo de test55432: perfiles inmutables,
equity/costos/reservas/latch, CAS, idempotencia y hashes. 109 pruebas focalizadas
aprobadas, sin fallos/omisiones; reinicio real de test55432 conserva cabeceras y
detección de corrupción deliberada. Base de pruebas conservada; clúster detenido.
No nuevas cohortes, no cambios011 ni migraciones/fixtures operativos.
74/74 protegidos y motor/config V1 intactos; EmergencyStop ACTIVE, Live bloqueado.
3644 quotes históricas: spread mediano0.2pip, p990.3pip; slippage/financiación sin
calibración empírica. Cuatro entradas V1 rechazadas por V2 incluso con estimación
optimista de comisiones mínimas solamente. Cotas de estrés son demostraciones,
no cantidades admitidas ni políticas operativas. No declarar listo para activar.
Documentos: `docs/architecture/r20-v2-test-persistence.md` y
`docs/architecture/r20-v2-eurusd-cost-evidence.md`. Persisten vías Prepare/Python/
CLI/SQL para otras cohortes V1: no exclusividad global. API/Dashboard, política
operativa y ejecución requieren aprobación nueva. Esta fase queda cerrada.

## Corte histórico: R20 V1 retirado mediante Stop — 2026-10-12, 15:39 local

Por instrucción explícita del usuario, se ejecutó una vez el Stop persistente
existente de aggressive-r20-b6675940304348228168514f1409c173. Revisión3858:
STOPPED, stop_requested=true. Antes ya estaban cerradas todas las posiciones:
dos trades por cartera, equity R20 87.68945520USD y BASELINE_1X 91.10183185USD.
Cero aperturas/cierres adicionales desde Stop; runner terminó por flujo normal,
sin Stop-Process/reinicio. 3858 hashes encadenados verificados; 74 protegidos y
motor/config/protocolo intactos. Dashboard confirma STOPPED, EmergencyStop ACTIVE
y Live bloqueado. TWS7497, PostgreSQL55433 y Dashboard5080 permanecen activos.
Informe: `artifacts/aggressive-growth-r20-20261010/r20-v1-retirement-20261012/report.md`.
No iniciar V2, otra cohorte ni ejecución Paper sin instrucción nueva. La retirada
de esta cohorte no declara exclusividad global R20-Only. Los cortes siguientes
son históricos y no autorizan reiniciar esta cohorte STOPPED.

## Corte histórico: datos recuperados — 2026-10-12, 07:02 local

Informe: `artifacts/aggressive-growth-r20-20261010/data-recovery-20261012/report.md`.
TWS23884/7497 volvió a estar disponible. R20 se recuperó por reintentos existentes
sin reinicio, misma cohorte y árbol30028→23480→25472. Sondeo read-only client192
verificó managedAccounts exacto contra AccountBinding***3784 y terminó desconectado.
Journal2105 DATA_UNAVAILABLE→2118 SHADOW_RUNNING,13 revisiones sin interrupciones
posteriores; quotes LIVE/OPEN frescas, barras1H/4H sin huecos esperados.

Ahora hay15 evaluaciones,2 SHORT: barra06:00local rechazada SIGNAL_STALE;
barra07:00local admitida, primera posición virtual R20 SHORT839.17EUR y
BASELINE_1X85.46EUR. Cero trades cerrados. Equity modelada al corte93.987743USD
y95.570534USD respectivamente, capital inicial100USD cada una. No órdenes IBKR.
IDs únicos, evaluaciones previas intactas; motor/protocolo/config y74 protegidos
sin cambios. Singleton ocupado comprobado. EmergencyStop ACTIVE/Live bloqueado.
No modificar ni reiniciar Shadow: ya gestiona inventario virtual.

Fase1 sigue parcial; fase2 solo evaluación de decisiones, sin adapter ni grants.
Esperar aprobación antes de cambios de ejecución. Los cortes siguientes son historia.

## R20-Only fase 1 parcial — 2026-10-12

Usuario aprobó únicamente retirada operativa gradual, no fase2 ni órdenes.
Informe: `artifacts/aggressive-growth-r20-20261010/r20-only-phase1-20261012/report.md`.
Cinco wrappers con política explícita (14 combinaciones denegadas); R10 Price Risk
solo Prepare bloqueado, Run/Once preservados porque también gestionan inventario
virtual previo. Tres POST de creación /simulation devuelven410 en el host operativo.
Quedan pendientes Python directo, CLI/binaries antiguos y PaperLab/H40/Ford,
cuyos scripts y Program.cs entran en manifiestos históricos: restaurados exactamente.
No declarar retirada completa ni exclusividad por cuenta.

131 pruebas focalizadas aprobadas. Sin suite global, Playwright ni migraciones.
Dashboard sustituido por build aislado R20Only, PID10928/5080; launch habitual
start-dashboard.ps1 actualizado. Debug permanece intacto para journal/recovery.
Autenticación401/lectura200, retirada410, negociación SignalR200; EmergencyStop
ACTIVE, Live BLOCKED_BY_BACKEND, órdenes deshabilitadas y Sol presupuesto0.

R20 no detenido: misma cohorte aggressive-r20-b6675940304348228168514f1409c173,
misma cadena de procesos30028→23480→25472. Corte06:35local revisión2026 frente1747;
13 evaluaciones idénticas, cero señales direccionales/posiciones/trades,
BASELINE_1X conservada. Engine_hash e20ab2563683ec5dce55f842fde7abe131b21d0007e682dd032ec28042e2adbd.
74/74 protegidos intactos. Ahora DATA_UNAVAILABLE: TWS sin listener7497/4002,
CURRENT_TWS_PROCESS_UNVERIFIED, última quote05:59:56local. Reabrir TWS Paper y
verificar identidad/quotes; no crear otra cohorte ni repetir Run.

Evaluación técnica sin implementación: `phase2-assessment.md` junto al informe.
Detenerse: esperar aprobación para siguiente fase y alternativas de retirada
de fuentes protegidas/hash-bound. La revisión independiente de esta iteración
se interrumpió por límite de uso; no se acredita revisión adversarial completa.
Las secciones siguientes son cortes históricos y no sustituyen este estado.

## Continuación: diseño de adapter Paper — 2026-10-11

Solicitud nueva: implementar R20 → IBKR Paper sin transmitir ni autorizar órdenes.
Se consultaron Graphify, journal y módulos dirigidos. Corte21:17:42 local: revisión132,
SHADOW_RUNNING, tres evaluaciones NO_BREAKOUT, cero trades, equity100. TWS7497,
Paper55433 y Dashboard5080 activos; 74/74 protegidos intactos y motor sin cambios.
No se reinició Shadow ni se creó otra cohorte.

Propuesta y alternativas en `docs/architecture/r20-paper-capability-map.md`.
El transporte Forex protegido fija LONG y el journal011 solo admite Shadow;
no basta conectar el PaperPlan a ese transporte. Revisión adversarial independiente
registró seis puntos pendientes. La skill spec-driven-development solicitada exige
revisión humana del mapa antes de specs/implementación; aprobación pendiente.
Segunda opinión entre modelos ofrecida por doubt-driven-development, pendiente.
Todavía NO hay adapter, Inspect/Assess/Stop/Recovery Paper R20 ni tests nuevos.
Solo documentación/evidencia; EmergencyStop ACTIVE, Live bloqueado, sin migraciones.
Evidencia: `artifacts/aggressive-growth-r20-20261010/paper-adapter-design-20261011/`.

## Estado vigente: primer arranque Shadow realizado — 2026-10-11

**SHADOW_RUNNING, dejar en marcha.** ID FORWARD real:
`aggressive-r20-b6675940304348228168514f1409c173`.
Cuenta Paper***3784 verificada exactamente, reader92 solo lectura, quotes LIVE/OPEN
y últimos históricos completos auténticos1H/4H sin gaps.011 no reaplicada; journal
vacío antes del preregistro. Preregistro20:38:01 America/La_Paz; primer ciclo20:39:11.
Corte20:46:14: revisión26,25 observaciones,2 evaluaciones NO_TRADE/NO_BREAKOUT,
0 señales direccionales,0 posiciones/trades/órdenes. Equity R20 US$100.

Un singleton: PowerShell30028→venv launcher23480→Python25472. Segunda adquisición
del lock rechazada sin lanzar otro runner. TWS20708, Dashboard13216, Paper15432
siguen activos. Stop no probado sobre esta cohorte para preservar continuidad;
evidencia de Stop persistente/CAS/restart anterior vigente. No repetir Run/Prepare.

Se corrigió únicamente frontend/src/realtime.ts: funciones de animación necesitan
window como receptor, evitándose Illegal invocation y falsa alerta STALE.
Regresión RED→GREEN, Vitest99, Playwright38 y build aprobados. R20 visible fresco en
desktop/móvil y SignalR, sin fixtures operativos. Cabecera general todavía refleja
estudio antiguo detenido; no confundirla con la sección Aggressive Growth.

74/74 protegidos intactos; engine_hash e20ab2563683ec5dce55f842fde7abe131b21d0007e682dd032ec28042e2adbd
sin cambios. EmergencyStop ACTIVE, Live bloqueado, Kronos UNAVAILABLE/RAW_ONLY y
probabilidad calibrada null. Ninguna autorización Paper ni fase de ejecución iniciada.
Informe y comandos Status/Stop con ID real:
`artifacts/aggressive-growth-r20-20261010/supervised-start-20261011/report.md`.
Los estados sin cohorte/sin listener siguientes son evidencia histórica superada.

## Preflight de primer arranque — 2026-10-10 20:04 America/La_Paz

**Actualización20:08:** TWS activo PID18648/listener7497. Reader R20 de solo lectura
client92 verificó managedAccounts exacto contra cuenta Paper***3784,0 órdenes y
0 posiciones. Cotización: MARKET_CLOSED/NO_BID_ASK_TICKS, bid/ask/timestamp=null,
sin errores API. Cliente de diagnóstico desconectado; TWS conservado.
No Prepare/Run ni ID operativo:0 cohortes/0 eventos. Repetir cuando sesión OPEN y
quote auténtica fresca; históricos aún pendientes por corte en gate de quote.
74/74 protegidos, EmergencyStop ACTIVE, Live bloqueado. Detalle/evidencia en
`first-start-preflight/reader-probe.json` y actualización del informe del preflight.
La ausencia de listener indicada debajo es el estado del intento anterior.

Usuario autorizó primer arranque exclusivamente Shadow después de verificar gates.
Detenido **antes de preregistro**: no TWS/Gateway ni listener127.0.0.1:7497.
Cuenta protegida local ***3784 válida; identidad actual managedAccounts y datos
frescos todavía no verificables. Pedir al operador una sesión PAPER con API local
en7497 y Read-Only API activo. No volver a pedir autorización Shadow ya concedida;
continuar tras preparar sesión y verificar los gates, sin ejecución IBKR Paper.

Paper55433/Dashboard5080 activos, journal R20:0 eventos/0 cohortes. Cero runners.
74/74 hashes y engine/protocol coinciden. EmergencyStop ACTIVE, Live bloqueado.
No cambios de código, servicios, migraciones, grants ni pruebas globales repetidas.
Evidencia: `artifacts/aggressive-growth-r20-20261010/first-start-preflight/report.md`.

## Última continuación: cierre de integración, 2026-10-10

Informe vigente: `artifacts/aggressive-growth-r20-20261010/operational-fixes/report.md`.
Migración011 permanece aplicada a Paper55433, identidad7692664583620497868,
journal R20 vacío. Ningún Prepare/Run/Once/Stop operativo. EmergencyStop ACTIVE,
Live bloqueado, sin órdenes ni autorizaciones de trading.

Se corrigió DashboardStore para leer las revisiones máximas por cohorte Shadow/R10
antes de ordenar timestamps. PostgreSQL RED→GREEN; mismos payloads en Paper,
snapshot HTTP161–171ms frente a4–7s. ARIA Kronos estable tras resize y espaciado
móvil360px corregidos. SignalR de observadores inactivos exige heartbeat conectado
y evidencia sin cambios; no se inicia un observer para satisfacer los tests.

C# global511, Python1375, Vitest98 y Playwright global38/38 aprobadas:2022 en total,
cero fallos/omitidas. Evidencia en el informe vigente/verification.json.
Builds Debug/Vue aprobados.
74/74 protegidos intactos; dominio/runner/config R20 conservan hashes.

Dashboard5080 PID13216 y PostgreSQL Paper55433 PID15432 quedan activos;
test55432 detenido, PostgreSQL5432 ajeno intacto. No hay R20 duplicado. Kronos
UNAVAILABLE/RAW_ONLY, probabilidad calibrada null. El recorrido sintético real
journal55432→API→SignalR→Vue pasó4/4 en la etapa anterior; Paper final continúa
sin cohorte y muestra DATA_UNAVAILABLE honestamente.

**No listo para primer arranque:** recuperar lectura IBKR Paper auténtica y fresca,
preregistrar cohorte FORWARD nueva y recibir instrucción nueva para supervisarlo.
Los gates globales de navegador y latencia ya están cerrados. No limpiar
EmergencyStop ni habilitar Live. Detener la fase aquí.

## Evidencia conservada: primera etapa de integración operativa

Migración011 aplicada explícitamente a Paper127.0.0.1:55433/postgres, identidad
7692664583620497868 y checksums001–010 verificados. Esquema previo sin cambios;
journal R20 vacío, cero preregistros/inicios. EmergencyStop ACTIVE, Live bloqueado.
Dashboard5080 activo (PID32908, launcher33068), compilación Debug verificada,
IBKR_DATA_ENABLED=false, SolBudget0. No hay R20 ni observadores duplicados.

Journal real → proyección Python → API autenticada → SignalR → Vue verificado
con fixture sintético únicamente en clúster limpio test55432: Playwright4/4.
En Paper, Playwright R20 también4/4 (desktop/móvil, ausencia honesta de métricas).
La DB de pruebas original tiene fixtures exploratorios incompletos; se preservó,
usó clúster temporal y restauró el original. Ambos test clusters detenidos al final.
Paper y Dashboard quedan activos; PostgreSQL5432 ajeno no se tocó.

Global: C#510, Python1375 y Vitest97 aprobadas; builds R20 por proyecto/Debug/Vue,
compileall y demo aprobados. Playwright global **22/38, 16 fallos, 0 omitidas**:
13 esperas de carga/sesión, 2 gráficos Kronos sin nombre accesible y 1 espera de
priceRisk.updated sin observador R10. Snapshot tarda4–7s; consultas existentes
Shadow/R10 hacen scans de miles de payloads. No relajar los tests para ocultarlo.
Kronos UNAVAILABLE/heartbeat antiguo; probabilidades calibradas R20 siguen null.
74/74 hashes protegidos intactos. Motor/config R20 sin cambios productivos.

Evidencia nueva: `artifacts/aggressive-growth-r20-20261010/operational-verification/`
(report.md, migration-plan.md, verification.json, global.trx, browser-failures.json,
capturas test-browser/global-browser, protected-final.json, engine-manifest.json).

Siguiente continuación: resolver gates globales de navegador y latencia, recuperar
lectura Paper auténtica (IBKR DATA_UNAVAILABLE, sin puertos TWS/Gateway), preregistrar
cohorte FORWARD nueva y solo entonces primer arranque supervisado con instrucción
nueva. Kronos caído no veta por sí solo Shadow determinista. No autorizar órdenes,
no limpiar EmergencyStop y no habilitar Live. Los pendientes antiguos sobre aplicar
011 y arrancar/refrescar Dashboard quedan sustituidos por este estado.

## Evidencia conservada: dominio/runner ↔ journal

Verificado Python → DLL C# R20 → PostgreSQL de pruebas **55432**, sin Reader/bróker.
Señales, inventario, costos y trades sobreviven restart. Stop queda persistido:
con quote inválida retiene inventario; una quote fresca permite cierre virtual;
STOPPED es terminal y repetir Stop/observe no escribe ni duplica trades.
CAS concurrente acepta un escritor; perder ACK tras INSERT invalida memoria y
exige recargar. Repetir observación conserva señales y posiciones.
El lock Windows bloquea un segundo proceso y se libera al salir, sin crecer.

Corregidos SHORT target≤0, calidad de velas ausente/inválida, gaps en todo el
prefijo EMA/ATR, timestamps/timeframes inválidos y Stop con barras corruptas
(solo puede cerrar desde quote fresca; registra INVALID_EXIT_BARS). Sin relleno.
Stop persistente ya no permite borrar su marca ni reintentar sin pausa cuando
la quote falta. El journal rechaza retroceso temporal y cambios de run_kind
en posiciones/trades que contradigan la cohorte.

Kronos conserva timeframe nativo/normalizado, pred_len y fechas del mismo forecast.
Concordancia exige horizonte coherente, partition FORWARD, disponibilidad causal,
frescura y timeframe de señal compatible. Metadata ausente/incompatible conserva
agreement=null; RAW_ONLY y probabilidad=null siempre. Forecast posterior no altera
evidencia congelada. No se ejecutó inferencia ni se acreditó evidencia forward real.

Pruebas finales: **89 aprobadas, 0 fallos, 0 omitidas**:
- Python: 57 (21 dominio, 6 runner, 13 límites/causalidad, 7 journal/lock, 10 proyección).
- C#: 32 AggressiveGrowthTests en R20, incluidos 2 tests PostgreSQL.
- Hashes protegidos: **74/74** coinciden.

Evidencia y decisiones: `artifacts/aggressive-growth-r20-20261010/domain-journal/`
(`report.md`, `verification.json`, `python-final.log`, `r20-journal-final.trx`,
`postgres-roundtrip.json`, `protected-verification.json`). Fallos RED retenidos.
WinError5 inicial del test temporal de lock fue resuelto ejecutando las mismas
pruebas fuera del sandbox; no se desactivó ninguna comprobación.

## Estado heredado: no repetir auditorías

- Diseño: `docs/architecture/aggressive-growth-r20.md`.
- Proyección Dashboard/Sol anterior: 159 pruebas aprobadas; evidencia conservada
  en `artifacts/aggressive-growth-r20-20261010/verification.json`. Vue compilado,
  97 tests anteriores; no se reejecutó frontend en esta fase.
- No hay R20 operativo iniciado por esta fase. No se reinició Dashboard ni se
  detuvieron Shadow, Cost-Aware o Kronos. No se tocó Paper55433 ni sus migraciones.
- DB55432 estaba disponible al verificar Start; se deja disponible. Datos de
  integración son fixtures sintéticos identificados en postgres-roundtrip.json.
- HISTORICAL exige quote HISTORICAL_MODELED, tiempo no decreciente, rechaza
  señales caducadas y no entra al runner FORWARD. No existe un CLI de replay
  completo ni se ha ejecutado/validado un benchmark histórico R20.

## Pendientes para otra fase, solo con nueva instrucción

1. Comprobar procesos/puertos actuales, compatibilidad del engine_hash nuevo y
   preregistro; no reutilizar un experimento registrado con motor anterior.
2. Coordinar migración011 aditiva exclusivamente al clúster Paper y refresh único
   de Dashboard. No realizados ni autorizados por esta fase.
3. Verificar SignalR autenticado y Playwright; cerrar integración con suite global.
4. Preregistro/inicio Shadow únicamente tras los gates y nueva instrucción.
   Sigue sin existir adapter de ejecución Paper R20 ni autorización Live.

## Reproducir esta fase

DB explícita: TRADING_TEST_DB y TRADING_LAB_DB =
`Host=127.0.0.1;Port=55432;Username=trading_test;Database=postgres`.

`dotnet test tests/TradingAgent.Tests/TradingAgent.Tests.csproj -c R20 -m:1 --filter FullyQualifiedName~AggressiveGrowthTests`

Con PYTHONPATH=python;python/tests, desde raíz:
`.\.venv\Scripts\python.exe -m unittest test_aggressive_growth test_aggressive_growth_runner test_aggressive_growth_boundaries test_aggressive_growth_journal test_aggressive_growth_projection -v`

Usar R20 para compilar; Debug puede estar bloqueado por procesos operativos.
No detener observadores para compilar. No repetir la suite global en cambios pequeños.
