# R20 → IBKR Paper: diagnóstico y mapa propuesto

2026-10-11, America/La_Paz. Estado: **PROPUESTA PARA REVISIÓN; NO IMPLEMENTADO**.
Solicitud: adjunto `f551f8ae-24d0-4198-b274-b363fdbb15d4/Texto pegado.txt`.
Este documento no concede consentimiento, no autoriza órdenes y no cambia Shadow.

## Punto de partida comprobado

Lectura actual del journal: cohorte `aggressive-r20-b6675940304348228168514f1409c173`,
revisión 132 a las 21:17:42 locales; SHADOW_RUNNING, tres velas evaluadas,
NO_BREAKOUT, cero trades, equity R20 100 USD. Quote recibida a las 21:17:40,
bid 1.12154 / ask 1.12156, IBKR_PAPER, LIVE/OPEN; source_timestamp=null.
LIVE aquí designa el tipo de datos, no el entorno de cuenta.

TWS 7497/PID20708, PostgreSQL Paper55433/PID15432 y Dashboard5080/PID13216
están escuchando. Los 74 hashes protegidos coinciden. Dashboard autenticado:
PostgreSQL VERIFIED, EmergencyStop ACTIVE, Live BLOCKED_BY_BACKEND,
ordersSupported=false, Sol LOCAL_EVIDENCE_ONLY con presupuesto 0.
La cabecera general sigue mostrando el estudio antiguo sin datos; la sección R20
entrega su propia observación reciente. Kronos UNAVAILABLE/RAW_ONLY, calibrada null.
No se abrió otra conexión IBKR en este diagnóstico: identidad exacta y condiciones
se describen según la evidencia existente, no como una nueva inspección independiente.

Graphify consultado primero mediante recorrido del JSON existente: no contiene
nodos R20. Sus referencias a ExecutionFeasibilityTests y broker.py orientaron las
lecturas; no acreditan compatibilidad de los módulos incorporados después.
NetworkX no está instalado en el venv: se hizo BFS equivalente con biblioteca estándar,
sin instalar dependencias ni reconstruir el grafo.

## Qué falta y qué se puede reutilizar

| Frontera | Evidencia actual | Consecuencia |
|---|---|---|
| Estrategia Shadow | Dominio/runner preregistrados y activos | Consumir evidencia causal; no editar ni recalcular señales históricas para forzar entradas |
| Journal R20 | 011 exige SHADOW_SIMULATED, broker_orders=0 | No puede alojar fills Paper sin violar su contrato; necesita stream separado con el mismo experiment_id |
| Persistencia | ShadowHead/ShadowEvent, hash, CAS y SQL parametrizado existentes | Reutilizar contratos y patrón de commit; añadir invariantes específicas Paper, no relajar las de Shadow |
| Identidad | AccountBinding, SessionConfiguration, IbkrSessionGuard existentes | Reutilizables sin editar; identidad no equivale a consentimiento |
| Transporte Forex | PaperOrderBuilder, guard y close_owned fijan BUY/SELL | No soporta SHORT directamente; el archivo está protegido |
| Autorización exploratoria | Cohorte eurusd-explore, perfiles previos, client82 y límites propios | No reutilizar el grant ni adaptar R20 haciéndolo pasar por R10 |
| Protección/recovery | Historial de ACK perdido, fill tardío y cancelación de hijos | Reutilizar evidencia, normalizadores compatibles y casos de regresión; no asumir que la máquina LONG es simétrica |
| Observación | DashboardStore → proyección → API/SignalR/Vue y AggressiveGrowthChat | Extender el contrato de lectura existente; Sol nunca entrega permisos |

Archivos inspeccionados: `aggressive_growth.py` y su contrato de arquitectura;
`paper_execution_wire.py`, `ibkr_session.py`, `eurusd_exploratory_runner.py`,
`eurusd_exploratory.py`, `eurusd_exploratory_wire.py`, `stock_paper_forward_wire.py`;
`AggressiveGrowthStore.cs`, `ExploratoryStore.cs`, `PaperLabJournal.cs`, migración011;
`DashboardStore.cs`, `DashboardService.cs`, `DashboardRealtime.cs`, `AggressiveGrowthChat.cs`.
Las referencias son puntos de integración, no una lista de archivos autorizados a editar.

Shadow calcula fills virtuales con midpoint/costos modelados. Paper requiere
precios y cantidades negociables, reservas reales, ACK, execId, comisiones reportadas
y reconciliación. Un fill Shadow nunca demuestra una ejecución IBKR ni propiedad de
inventario. Paper tendrá su propio capital lógico inicial de 100 USD, actualizado
por sus propios resultados; no tomará el equity Shadow, baseline o saldo del bróker.

## Alternativas

1. Modificar RiskEngine, las autorizaciones R10 o el transporte protegido: descartado
   por restricciones expresas y por mezclar políticas históricas.
2. Reutilizar íntegramente el runner exploratorio: descartado; límites, perfiles,
   dirección y consentimiento no representan R20.
3. Copiar un segundo sistema completo: descartado; duplica identidad, sesiones,
   transporte y fallos ya resueltos.
4. Adaptación R20 acotada, con composición de componentes compatibles y estado Paper
   separado: propuesta preferida. La viabilidad del transporte bidireccional debe
   probarse primero con SDK falso; no se da por demostrada por esta revisión.

Limitar silenciosamente Paper a LONG tampoco completa el objetivo. Si la adaptación
bidireccional exige modificar un protegido o duplicar sustancialmente el transporte,
se presentará ese conflicto antes de implementar tal cambio; no se sustituirán guards
en ejecución ni se llamará al SDK para eludirlos.

## Mapa de capacidades para revisión humana

| ID estable | Responsabilidad y frontera | Depende de |
|---|---|---|
| r20-paper-journal | Stream Paper append-only, CAS, deduplicación, consentimiento consumido e intención durable; vinculado a la cohorte existente | Contratos de persistencia existentes |
| r20-paper-assessment | Señal auténtica elegible, identidad y condiciones con origen/edad; sizing y costos; Inspect/Assess sin canal de órdenes | Journal Shadow de lectura, lectores existentes |
| r20-paper-execution | Consentimiento específico, reserva, exclusión por cuenta, adaptación LONG/SHORT, ACK/parciales/protección, Stop y recuperación como una misma frontera de autoridad | r20-paper-journal, r20-paper-assessment |
| r20-paper-observation | Proyección del journal Paper, API/SignalR/Vue y Sol local con estados, métricas y bloqueos explícitos | r20-paper-journal, contratos de r20-paper-assessment y r20-paper-execution |

Orden propuesto: validar primero la extensión de transporte en aislamiento;
journal y assessment → execution → observation. No hay nueva cohorte Shadow,
ni modificación del engine_hash. Las especificaciones por módulo se escribirán
después de revisar este mapa, siguiendo la skill solicitada.

La revisión adversarial independiente identificó seis puntos que deben resolverse
antes de aceptar el diseño de ejecución: exclusión entre perfiles por cuenta,
frontera de transporte compatible, intento durable por pata, propiedad del equity,
cliente/callbacks y versión propia del stream/adapter. Véase
[revisión](../../artifacts/aggressive-growth-r20-20261010/paper-adapter-design-20261011/adversarial-review.md).
El mapa define responsabilidades propuestas; no acredita que esas garantías ya existan.

## Restricciones que deberán resolver las especificaciones

- 100 USD lógicos Paper; riesgo por precio ≤20% de su equity actualizado;
  exposición ≤10x; tamaño redondeado hacia abajo. Costos, spread, slippage,
  financiación y margen separados, sin doble conteo. Revalidar tras redondear
  precio/stop/target y antes de cada transmisión. No prometer pérdida máxima.
- Señal del journal FORWARD, versión y hash del motor comprobados; cierre causal,
  edad máxima de señal 180s y quote 30s. Caducidad durante revisión humana bloquea;
  no renovar señal ni extender ventanas para facilitar consentimiento.
- Autorización AGGRESSIVE_GROWTH_R20_PAPER específica, revocable, una apertura,
  máximo 30 minutos, ligada a todos los campos solicitados, hash de evidencia y
  nonce. Sesión UI de lectura, payload externo, R10 o Sol no pueden emitirla.
- Reserva/consumo durable antes del envío, referencias estables y bloqueo por
  cuenta compartido con otros ejecutores. Una transacción y un singleton por
  experimento solos no protegen de otro perfil operando en la misma cuenta.
- Resultado de envío incierto exige conciliación; nunca retry ciego. Deduplicar
  callbacks por identidad de ejecución, sin convertir orderStatus en un fill.
- Protección pendiente antes del envío es distinta de aceptación posterior.
  La aceptación específica del bracket solo puede verificarse tras el futuro envío;
  no se inventará ni se usará una dependencia circular para declarar READY.
  Permiso/capacidad previos y evidencia de protección posterior requieren contratos
  distintos. Una condición crítica previa UNKNOWN mantiene BLOCKED.
- Reconciliar inventario propio firmado por fills, posiciones, órdenes y reservas;
  parciales, fills tardíos, comisiones desconocidas y desconexión mantienen obligaciones.
  Recuperación reduce únicamente inventario propio con autoridad independiente
  y conciliación fresca; no convierte emergencia o expiración en permiso de entrada.
- Nuevo stream Paper requeriría cambio de esquema estrictamente aditivo, primero
  en 55432 aislado. No reaplicar 011 ni modificar su CHECK. No aplicar nada al
  clúster operativo durante la preparación de este mapa.
- Estados solicitados de UI conservados; UNKNOWN permanece null, P&L neto no
  cerrado mientras falten comisiones, Shadow/Paper/Live inequívocos. Sin rediseño.
- Kronos carece de autoridad; RAW_ONLY/UNAVAILABLE conserva probabilidad calibrada
  null. Sol consulta solo evidencia estructurada, LOCAL_EVIDENCE y US$0.

## Condiciones operativas y EmergencyStop

La evidencia actual de R20 informa identidad/reconciliación verificadas por su reader,
pero permisos Forex efectivos UNKNOWN, margen incremental UNKNOWN, mínimo/paso
declarados, costos estimados a partir de un único ciclo histórico y protección efectiva
UNKNOWN. No son suficientes para READY; no se ejecutó What-If.

El informe histórico `paper-pending-bracket-recovery.md` documenta intención sin ACK
persistido, ApiCancelled local que no acreditaba cancelación del servidor, fill tardío
y pérdida de protección tras cancelar hijos. El informe supervisado posterior registra
el cierre independiente. No se presenta el inventario histórico de 100 EUR como actual.

Existe ReviewEmergency en el runner exploratorio: exige consentimiento propio,
inspección completa/plana, ausencia de reservas/comisiones pendientes y confirmación
local; registra revisión y modifica el journal/marcador. Su scope no es R20. No invocarlo
ni reutilizar un grant antiguo. El futuro procedimiento R20 necesitará una revisión
humana específica y auditable; no habrá excepción que ignore EmergencyStop ni cambio
de Live. Esta fase preserva tanto el marcador protegido como el estado persistido.

IBKR documenta que `transmit=false` crea una orden en TWS aunque no la envíe al
servidor: tampoco es una prueba de lectura autorizada para esta fase.
[Documentación oficial de envío](https://www.interactivebrokers.com/docs/tws-api/doc/orders/place-order/introduction).
What-If utiliza placeOrder y devuelve estimaciones; quedará fuera del canal Inspect.
[Documentación oficial de margen](https://interactivebrokers.github.io/tws-api/margin.html).

## Pruebas necesarias, todavía no ejecutadas para el adapter

- SDK falso sin conexión: LONG/SHORT, geometría, límites, cada mutación y variantes
  protobuf, autorización ausente/expirada/revocada, ámbito R10/Live incorrecto,
  EmergencyStop y cambio de identidad/proceso entre evaluación y envío.
- Journal en DB55432: CAS concurrente, cuenta compartida, nonce usado, ACK perdido,
  restart, una apertura, reserva retenida, no borrado de fills/consentimientos.
- Eventos: ACK/rechazo/parciales duplicados/desordenados, hijos rechazados,
  protección con precios/cantidades/referencias correctos, fill tardío, desconexión,
  cierre simultáneo y comisiones ausentes/corregidas con procedencia.
- API/SignalR/Sol: autenticación vigente, proyección desde journal, no autoridad por
  chat, costo cero y ausencia de inferencias fabricadas.
- Vitest/Playwright desktop/móvil: estados Paper y separación, bloqueos/control
  deshabilitado, UNKNOWN, reconexión y falta de overflow. Fixtures solo aislados.
- Al cierre de implementación: suites globales pertinentes y hashes 74/74 más los
  archivos del motor activo; evidencia de continuidad del singleton Shadow.

No se reejecutan suites cerradas para una entrega exclusivamente documental.

## Comandos existentes y futuros

Los únicos comandos R20 aquí comprobados/existentes son los de Shadow:

```powershell
$experiment = 'aggressive-r20-b6675940304348228168514f1409c173'
.\scripts\aggressive-growth.ps1 -Action Status -Experiment $experiment
# Solo si se solicita detener Shadow; no se ejecutó:
.\scripts\aggressive-growth.ps1 -Action Stop -Experiment $experiment
```

Inspect, Assess, Stop y Recovery **Paper R20 todavía no están implementados**.
No proporcionar un comando antiguo de otra cohorte como sustituto. Su contrato
deberá distinguir inspección, evaluación, parada de entradas y recuperación autorizada.

Evidencia de esta revisión: `artifacts/aggressive-growth-r20-20261010/paper-adapter-design-20261011/`.
