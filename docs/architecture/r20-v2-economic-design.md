# R20 V2 — diseño económico configurable

12/oct/2026, revisión 3. **NÚCLEO MATEMÁTICO AISLADO IMPLEMENTADO; INTEGRACIÓN NO AUTORIZADA.** Alcance autorizado:
núcleo matemático y contratos V2 aislados. Este documento también describe
dependencias posteriores de persistencia/API/Dashboard, todavía no implementadas.
No crea perfiles activos, cohortes, permisos de trading ni migraciones.
El contrato implementado vigente es [r20-v2-core-contract.md](r20-v2-core-contract.md);
incorpora la aprobación del usuario y sustituye las alternativas anteriores
de día económico, baseline y cierre administrativo por apalancamiento.

## 1. Decisión y evidencia

Reutilizar `AGGRESSIVE_TREND_BREAKOUT_V1` y el reader IBKR de lectura. Añadir una
política económica V2 versionada, un estado multiposición y persistencia separados
del contrato V1. No construir otra estrategia ni clonar la pila IBKR. La economía
V2 calcula admisibilidad Shadow; nunca produce autorización de ejecución Paper.

Graphify fue consultado primero: el grafo disponible localiza RiskPolicy,
RiskEngine, ExecutionFeasibility y almacenamiento, pero no contiene R20. Se
completó mediante lectura dirigida, sin reconstruir el grafo ni repetir auditorías.

| Fuente inspeccionada | Restricción real / consecuencia |
|---|---|
| `python/trading_agent/aggressive_growth.py`, `configuration`, `signal`, `assess`, `mark`, `close`, `consume` | Configuración fija; señal reutilizable; sizing, costos, dos carteras y liquidación ligados a V1. No pasar perfiles V2 a `configuration()` ni reutilizar `assess()` como política V2. |
| `python/trading_agent/aggressive_growth_runner.py`, `Reader`, `Journal`, `engine_hashes` | Reader read-only reutilizable; journal y rutas limitados a V1. No editar el runner activo ni su build Debug. |
| `AggressiveGrowthInvariants.cs`, `AggressiveGrowthStore.cs`, migración `011_aggressive_growth.sql` | Exigen 100 USD, 20%, 10x, R20 + BASELINE_1X e identidad inmutable. V2 no cabe en 011. |
| `AggressiveGrowthCommand.cs` | Entrada CLI existente al almacenamiento; posible despacho explícito a V2 en un build futuro aislado, manteniendo la rama V1 idéntica. |
| `DashboardStore.cs`, `DashboardService.cs`, `DashboardRealtime.cs`, `aggressive_growth_projection.py` | Proyección desde journal mediante Python y publicación SignalR; reutilizar infraestructura, añadir una sección V2 tipada. |
| `frontend/src/modules/aggressive-growth/`, `stores/aggressiveGrowth.ts`, `types.ts`, `realtime.ts` | Contrato y textos V1 fijos, baseline obligatoria y posición única. Conservar vista V1; nuevo contrato V2, sin sustituir el existente. |
| `DashboardEndpoints.cs`, autenticación de `Program.cs` | Sesión Dashboard de lectura y bearer administrativo diferentes. Estar autenticado como lector no habilita configuración. |
| `r20-only-phase1-20261012/phase2-assessment.md` | RiskEngine y transporte no admiten íntegramente 20%/10x y SHORT; exclusión por cuenta incompleta. Siguen siendo bloqueos Paper. |

La [auditoría auténtica de V1](../../artifacts/aggressive-growth-r20-20261010/first-shadow-audit-20261012/report.md)
reconstruyó costos de 6.180091 USD y target bruto de aproximadamente 2.376931 USD
para 839.17 EUR. Target neto aproximado −3.803160 USD. El piso de spread era
140 veces el spread observado de esa entrada. No se encontró doble descuento.
El tamaño dejó el apalancamiento sobre equity neta prácticamente en 10x, por lo
que una mínima variación adversa podía disparar una salida antes del SL.
Estos hechos justifican revisar el contrato; no validan un nuevo piso de costos.

### Alternativas e impacto

| Decisión propuesta | Alternativa | Justificación, impacto y riesgo residual |
|---|---|---|
| Importar funciones puras de señal V1, con hash fijado, desde un adaptador V2 estrecho | Extraer ahora una librería común o copiar la estrategia | Importar evita modificar el archivo activo o duplicar la señal. El nombre del módulo sigue ligado a V1; fijar también dependencias transitivas y comprobar paridad. Una extracción futura requiere revisión separada. |
| Economía V2 independiente y pequeña | Hacer configurable `assess/mark/consume` V1 | Se necesita otro estado para perfiles y múltiples posiciones. Evita alterar el experimento; compartir primitivas puras comprobadas, no copiar el motor entero. |
| Journal V2 nuevo y proyección adicional | Ampliar 011 y relajar invariantes | Mantiene la interpretación histórica. Añade almacenamiento, pero evita compatibilidad ambigua. Migración solo futura y explícita. |
| Rechazar target neto estimado no positivo | Mantener admisión exploratoria V1 | Explicita el objetivo económico; puede producir cero operaciones. No demuestra expectativa positiva aunque el target sea neto positivo. Aprobado para entradas normales nuevas; ensayos separados requieren autorización específica. |
| Admisión con costos, reserva y estrés | Bajar un piso hasta que aparezcan fills | Conserva evidencia y puede rechazar todo tamaño. Costos y holguras deben calibrarse fuera de muestra; no hay valores nuevos aprobados. |
| Configuración administrativa separada del permiso de trading | Reutilizar una sesión de lectura o un permiso Paper | Reduce autoridad y evita que guardar un perfil abra órdenes. Exige pruebas de autorización en el endpoint, no solo ocultar botones. |

## 2. Arquitectura y capacidades

```text
IBKR Market Data → Reader read-only existente → evidencia causal e íntegra
                                              ↓
                        estrategia existente AGGRESSIVE_TREND_BREAKOUT_V1
                                              ↓
perfil diario + costos versionados + estado → assessment económico V2 puro
                                              ↓
               Shadow V2 (autorización futura) → journal V2
                                              ↓
               ASP.NET Core + proyección Python + SignalR → Vue R20 + Sol

assessment V2 → futura frontera Paper → RiskEngine + ExecutionGuard
             → autorización + coordinador durable + transporte → journal Paper
             [BLOQUEADO; no forma parte de esta implementación]
```

| Capacidad | Responsabilidad | Dependencias / criterio |
|---|---|---|
| C1 Perfiles | Validar, versionar, activar y resolver configuración | Identidad administrativa, reloj servidor, CAS; ninguna orden |
| C2 Assessment | Sizing, costos, margen, riesgo efectivo y motivos | Señal inalterada, perfil, políticas verificadas, snapshot de cartera |
| C3 Libro y día | Posiciones, reservas, pérdidas diarias y recuperación | Eventos inmutables; no reiniciar pérdidas al editar perfil |
| C4 Observador V2 | Consumir una señal una vez y gestionar inventario | C1–C3, reader existente, singleton y CAS propios |
| C5 Evidencia/UI | Preview, perfiles, posiciones y métricas con procedencia | Misma calculadora que C2; lectura nunca equivale a administración |
| C6 Validación | TDD, integración y replay causal aislado | Sin IBKR de ejecución y sin fixtures operativos |

La estrategia conserva instrumento EUR/USD, marcos 1H/4H, EMA20/50, ruptura de
20 barras, ATR14, stop 1.5 ATR y target 2 veces la distancia. El perfil económico
no expone parámetros de señal, dirección forzada ni precios de protección.
Importar `signal()` no sustituye los controles que hoy realiza `consume()`:
calidad explícita, gaps de todo el prefijo EMA/ATR, frescura, calendario,
partición y timestamps siguen siendo precondiciones verificables del adaptador.
Su paridad debe probarse antes de usar la señal importada en V2.
Sol interpreta evidencia; Kronos es opcional, RAW_ONLY/UNAVAILABLE no se convierte
en probabilidad calibrada y no tiene voto de ejecución.

## 3. Contrato inmutable del perfil

Nombre propuesto: `R20EconomicProfileV2`. Sin valores económicos por defecto.
Decimales como cadenas canónicas en JSON y `Decimal`/`decimal` en cálculo y
validación; porcentajes en **puntos porcentuales**: `"20"` significa 20%, no 0.20.
Prohibir floats no finitos, campos desconocidos, booleanos como enteros y
conversión silenciosa de unidades. Redondeo visual nunca alimenta el cálculo.

| Campo | Regla propuesta |
|---|---|
| `schema_version` | Discriminante fijo del contrato V2, distinto de V1 |
| `profile_id`, `configuration_version` | UUID y secuencia creciente por ámbito; asignados por servidor |
| `configuration_hash` | SHA256 del documento canónico, excluyendo solo el propio hash |
| `capital_base_usd` | Decimal > 0; referencia inicial, no limita crecimiento ni repone pérdidas |
| `equity_cap_usd` | null o Decimal > 0; sólo limita sizing si el usuario configura explícitamente el techo |
| `risk_per_trade_pct` | 0 < valor ≤ 100 y dentro del techo operativo aprobado; riesgo por precio |
| `capital_allocation_pct` | 0 < valor ≤ 100; asignación por entrada, sujeta a reservas agregadas |
| `max_leverage` | ≥ 1 y ≤ techo de política operacional; no cambia condiciones del bróker |
| `daily_loss_limit_pct` | 0 < valor ≤ 100 y dentro de política; semántica de día en sección 6 |
| `max_open_positions` | Entero positivo dentro de límite operativo; cuenta también entradas reservadas |
| `effective_from`, `effective_until` | Instantes UTC con offset, intervalo [inicio, fin), inicio < fin |
| `created_at`, `created_by` | Reloj servidor e identidad administrativa auditable, no campos confiados al cliente |
| `trading_day_id`, `timezone`, `day_start_local`, `tzdb_version` | Día civil y reglas temporales congeladas; límites UTC resueltos explícitamente |
| `scope_id` | Cartera lógica V2; entorno y estrategia explícitos, nunca V1 ni cuenta Live |
| `cost_policy_hash`, `operational_policy_hash` | Referencias obligatorias a políticas inmutables; desconocidas/vencidas bloquean aperturas |
| `supersedes_profile_id` | Referencia opcional; no modifica ni borra la versión anterior |

Los rangos anteriores son validación estructural, **no un permiso para riesgo de
100% ni apalancamiento arbitrario**. Sin techo operacional aprobado no hay perfil
activable. No se importan R1/R5/R10 ni excepciones históricas para rellenarlo.

Día aprobado: 00:00–00:00 del día siguiente en `America/Santo_Domingo`.
Registros persistidos en UTC con zona económica explícita; no hay despliegue.
Resolver cada frontera desde la fecha local y zona IANA; no sumar 24 horas UTC.
Persistir también los dos instantes UTC y la versión de reglas temporales. Para
zonas con cambios de hora, cubrir días de 23/25 horas; si la hora límite resulta
ambigua o inexistente, rechazar programación hasta resolución explícita. Un cambio
de zona no se permite dentro de la cohorte: requiere nuevo protocolo.

Un perfil abarca como máximo un día. Puede comenzar a mitad del día; no se
retrodata. Guardar una versión no la activa. Una activación es otro evento
administrativo con revisión esperada, visible sólo tras commit y con vigencia
solicitada no anterior a la recepción validada del servidor. El consumidor registra
cuándo conoció esa revisión y nunca la aplica a observaciones anteriores. El
timestamp de escritura no se presenta como hora exacta de commit PostgreSQL.
Activaciones concurrentes sobre el mismo head: gana una; la otra recibe conflicto.
En cada instante existe una sola versión resuelta por ámbito. Una sustitución
append-only termina lógicamente la selección anterior sin editar sus fechas.
Replay resuelve tanto tiempo de vigencia como tiempo de disponibilidad/commit;
un perfil publicado después de una señal no puede aplicarse hacia atrás.

Cada posición conserva perfil completo o referencia + hash verificable, estrategia,
engine, políticas de costos/margen, señal, assessment y reservas de apertura.
Si vence, se revoca o falta el perfil de nuevas entradas, se continúa la gestión
con el contrato congelado de cada posición. Reducir el nuevo límite de posiciones
no cierra las existentes; impide nuevas entradas mientras se exceda el límite.

`capital_base_usd` no reescribe capital inicial, cash, PnL ni pérdidas. El fondeo
inicial de una futura cohorte es un evento distinto, autorizado al crearla.
V2 inicial no admite aportes/retiros durante la cohorte. El equity evoluciona
con PnL/costos; un techo opcional explícito sólo limita nuevas admisiones.
Ni modificar el techo ni el perfil altera cash o reinicia pérdidas diarias.

### Hashes y trazabilidad

Canonicalización definida por esquema: claves ordenadas ASCII, UTF-8 sin BOM,
sin espacios, decimales en notación fija sin ceros redundantes (`0`, nunca `-0`),
timestamps UTC `Z` con precisión fijada común de microsegundos. Sin normalización
implícita de texto libre: usar identificadores validados. Pruebas de vectores
idénticos C#/Python; almacenar el material exacto junto al hash.
El `engine_hash_v2` fija estrategia importada, economía, ciclo de vida, reader y
dependencias efectivas; el hash de perfil puede cambiar sin cambiar el motor.
El protocolo preregistra reglas de versionado y admisión, no perfiles futuros
conocidos retrospectivamente. La cadena incluye revisiones y hashes previos.

## 4. Sizing y holgura: contrato definido para revisión

Las [fórmulas definitivas de esta revisión](r20-v2-formulas.md) definen un único
snapshot para costos, pendientes, equity elegible y capacidad. Riesgo, asignación,
apalancamiento, pérdida diaria y cupo son los cinco controles diarios. Porcentajes
API se convierten una vez a fracción matemática.

```text
E_available = E_net − costos totales reservados de entradas pendientes
E_eligible = max(E_available, 0), limitado sólo por equity_cap_usd si no es null
B_price = E_eligible × r
A = E_eligible × a
q_price = B_price / distancia_stop
q_allocation = A × L / midpoint
q_final = mayor cantidad válida de la rejilla que satisface todos los límites
```

La admisión exige riesgo, asignación, exposición bruta agregada, margen inicial
libre, mantenimiento bajo estrés, liquidez, cupo, riesgo diario reservado, target
neto positivo y guards. Un mínimo/incremento no permite redondear hacia arriba;
comisiones no lineales obligan a resolver el conjunto admisible, no sólo un min.
No se modifica la señal ni se aumenta L para alcanzar el presupuesto de riesgo.

Holgura: calcular después de costos completos de abiertas, pendientes y candidata,
exactamente una vez. H_0=L×E_post−X_post debe cubrir un mínimo relativo y el
peor requerimiento de exposición/equity estresadas. El documento de fórmulas
especifica H_required, la equivalencia algebraica por escenario, margen libre
y qué valores quedan por calibrar. Sin políticas validadas no se activa un perfil.

**Decisión aprobada:** L diario limita admisiones, no dispara cierres por pequeñas
fluctuaciones de equity. Reducir L/n conserva contratos y posiciones anteriores;
la nueva admisión se evalúa contra el total actual y el límite nuevo. Si no cabe,
se bloquea y muestra el exceso administrativo. Las protecciones duras de margen,
solvencia, emergencia, exposición y recuperación siguen siendo independientes y
obligatorias. Un exceso de margen real nunca se trata como exceso administrativo
inofensivo. Quotes obsoletas no producen fills.

Señales simultáneas se ordenan por timestamp de cierre, timeframe e ID estable;
cada reserva consume capacidad antes de la siguiente. CAS de cartera y perfil
impide gastar dos veces un recurso. Preview caducado o activación concurrente
obliga a recalcular. Una señal rechazada no se resucita al cambiar el perfil.

## 5. Costos y contabilidad

Cada componente registra `OBSERVED`, `ESTIMATED`, `BROKER_CONFIRMED` o `UNKNOWN`,
unidad, fuente/hash, instante observado, disponibilidad causal, vigencia y
versión. En Shadow no hay comisión ni fill confirmado por IBKR. Una tarifa
publicada tampoco acredita la comisión de una ejecución individual.

| Componente | Política propuesta |
|---|---|
| Comisión | Función por lado, instrumento, cantidad, moneda y mínimos; fuente y fecha. Sin tarifa verificada, no simular costo cero. Estimación y confirmación futura separadas. |
| Spread | Costo de ida/vuelta `q × (S_entry + S_exit)/2` sobre midpoint. En preview, entrada observada y salida estimada; usar pisos/distribuciones segmentados por sesión y liquidez, validados con muestra suficiente. Registrar spread observado y aplicado. |
| Slippage | Costo adicional por lado sobre la convención de referencia, condicionado por tamaño/liquidez. Nunca volver a sumar el spread dentro de slippage sin descomposición. |
| Financiación | Devengo modelado según tiempo, dirección y calendario de rollover documentado, más reserva del horizonte futuro aprobado. Si no existe evidencia para la tasa, UNKNOWN bloquea admisión; no presentar 0.25 fijo como cargo real. |
| Conversión | EUR/USD usa USD directamente. Otras monedas/instrumentos quedan fuera; no expandir universo implícitamente. |

No reemplazar el piso 0.0014 por 0.00001 a partir de una quote. Construir dataset
auténtico con sesiones, tamaños disponibles, timestamps, calidad y hashes;
documentar suficiencia de muestra, selección, percentil/reserva y validación fuera
de muestra. Sin datos de ejecución auténtica, slippage sigue siendo hipótesis
conservadora con sensibilidad. Parámetros no validados impiden activar la política.
El costo de target y de stop puede diferir: el último incorpora condiciones
adversas; el estrés agrega gaps por separado. La política es inmutable por posición,
pero sus fórmulas evalúan las nuevas observaciones y el tiempo transcurrido.

**Convención contable implementada en el núcleo aislado:** el
[contrato de revisión 3](r20-v2-core-contract.md) separa costos liquidados,
devengados no pagados y reservas estimadas por ID. Cash descuenta los liquidados;
equity deduce únicamente lo que todavía no está en cash. Confirmación/pago
reemplazan un estado; cierre traslada PnL abierto a realizado. Cada USD se cuenta
una vez. No se cambió la convención del motor V1. No hay ledger persistente V2.

Paper necesitará contabilidad por fills/comisiones/devengos confirmados y ajustes
append-only, con reservas sólo para lo pendiente. No copiar ciegamente esta
convención Shadow ni convertir fills virtuales en fills Paper.
Congelar una política no congela el mundo exterior: cambios reales de margen,
restricciones del instrumento o emergencia siguen siendo entradas de los guards.
Datos de costos ausentes bloquean aperturas; no eliminan inventario ni impiden
gestión defensiva. Un costo desconocido se registra como tal, nunca como cargo
confirmado ni como cero fabricado para cerrar la contabilidad.

## 6. Pérdidas diarias y bloqueo persistente

Contrato aprobado: contabilidad neta, reservas y bloqueo durable por cartera/día.
Las [ecuaciones de día](r20-v2-formulas.md) fijan el denominador E_day0, el mínimo
histórico del presupuesto intradía y la identidad de reservas sin doble descuento.

```text
D_budget = mínimo de E_day_eligible × d de los perfiles activados ese día
U_day = max(0, E_day0 − E_net_actual)
U_day + riesgo adicional abierto + pérdida neta reservada pendiente
      + pérdida neta estresada candidata ≤ D_budget
loss_blocked = loss_blocked_previo OR (U_day ≥ D_budget)
```

La pérdida abierta ya contenida en E_net no vuelve a incluirse en el riesgo
adicional; pendientes y candidata todavía no incluidos en E_net reservan costos
y pérdida completos. Las ganancias reales compensan pérdidas netas, pero no
amplían el presupuesto inicial ni limpian un latch disparado.

Cambiar, revocar o recrear un perfil no reinicia pérdidas ni desbloquea un latch.
Reducir el presupuesto puede bloquear entradas; no altera stops ni posiciones.
Reinicio recupera día, referencia, presupuestos, reservas y latch desde journal.
Incoherencia de recuperación bloquea nuevas entradas, conservando gestión.
Agotar capacidad por reservas es distinto de alcanzar pérdidas: no se registran
reservas como pérdidas realizadas. Liberación verificada de capacidad no borra
un bloqueo por pérdida ya disparado.

El día siguiente crea otro registro, no elimina el anterior. Conserva inventario
y riesgos, y no limpia EmergencyStop ni otras paradas. Si falta valoración válida
en frontera, DAY_BOUNDARY_UNVALUED bloquea admisión; preservar último mark previo
íntegro y atribuir conservadoramente su gap, con intervalo real identificado. No
usar primer mark recuperado para perdonar pérdidas. Sin referencia íntegra, seguir
bloqueado. La gestión no depende de tener un perfil diario vigente y el límite
diario por sí solo no fuerza cierres. Reglas completas en el contrato de fórmulas.

## 7. Persistencia, API y Vue (diseño, sin SQL ejecutable)

### PostgreSQL

Namespace propuesto `aggressive_growth_v2`, con registro de perfiles inmutables,
eventos de activación/revocación y journal de cartera. Identidad distinta
`aggressive-r20-v2-<uuidhex>`, `protocol_version=2`, `SHADOW_SIMULATED` y partición
FORWARD/HISTORICAL explícita. Sin mezcla con journal 011 ni registro Paper futuro.

Perfiles: unicidad scope/version e ID; FK a políticas; hash/material verificado.
Eventos de cartera: PK cohorte/revisión, CAS, previous_hash y eventos inmutables,
referencias de posición al perfil, al día y a evidencia de señal/mercado.
Unicidad de evaluación por cohorte/strategy_version/instrumento/timeframe/cierre;
una entrada por señal admitida. Índices de cabecera, no scans de todos los payloads.

Activar perfil, reservar entrada y añadir evento de cartera deben serializarse
con la misma revisión de ámbito: bloquear el head de perfiles, comprobarlo y
confirmar el append de cartera en una transacción; después, liberar. Así un
cambio administrativo no se intercala entre validación y commit. El runtime puede
leer perfiles y anexar estado, pero no crear/activar perfiles. El componente
administrativo no recibe permisos de órdenes. Diseñar roles mínimos en pruebas;
no otorgarlos al clúster operativo en esta fase.

Reutilizar patrones existentes CAS/inmutabilidad/validación, sin modificar el
Store V1. Snapshots/materializaciones son derivables; UPDATE/DELETE del ledger
se rechazan. ACK perdido: recargar y conciliar IDs antes de reintentar; nunca
duplicar una apertura. Singleton por cartera complementa CAS, no lo sustituye.

Nueva migración aditiva, con número asignado al implementar (012 era el siguiente
libre al inspeccionar). Validar destino exacto, backup y esquema previo antes de
aplicación autorizada futura. Recuperación posterior al commit conserva tablas y
journal; desactivar nuevas entradas V2, continuar gestión, nunca DROP como rollback.

### API y autorización

API propuesta bajo `/api/ui/r20-v2/config` para conectar con el host existente:
`GET profiles`, `GET profiles/{id}`, `POST profiles`, `POST activations`,
`POST revocations`, `POST preview`. Consultar historial completo de perfiles y
mutarlos requiere autorización administrativa de configuración; lectores ven
únicamente la proyección de sus parámetros y procedencia en el Dashboard.
Sin PUT/DELETE de una versión. Guardar y activar son acciones distintas.

No basta el middleware global: `/api/ui` admite la cookie de lectura. Los nuevos
endpoints deben aplicar autorización adicional específica. Propuesta para Vue:
intercambiar el bearer administrativo existente por una sesión corta de
configuración, con scope `r20-config-admin`, sin authority de trading. Validar
bearer explícitamente al crear esa sesión; no inferirlo de `IsAuthenticated`.
Mantener la sesión de lectura separada para atravesar el middleware actual.
El segundo esquema de cookie no sustituye el esquema Dashboard ni concede acceso
a otros endpoints administrativos. Logout/expiración/revocación invalidan esa
sesión de configuración; proteger POST con token antiforgery y Origin estricto.

El bearer se presenta sólo durante el desbloqueo administrativo, no se persiste
en localStorage, logs, URL ni SignalR. Cookie HttpOnly/SameSite, conexión limitada
al loopback actual; no ampliar bind/CORS/CSP. Registro de actor, acción, hash,
revisión y resultado sin secretos. Si no puede añadirse esta frontera desde
`AddDashboard/MapDashboard` sin tocar archivos hash-bound, detener esa parte y
presentar alternativa; no modificar `Program.cs` para sortear el límite.

POST requiere clave idempotente y revisión esperada. Mismo cuerpo/clave retorna
el mismo resultado; clave repetida con otro cuerpo: conflicto. 401 sin sesión,
403 scope insuficiente, 409 head cambiado, 422 contrato inválido, 503 datos/política
no disponibles. Ningún error reintenta activación automáticamente.

Preview usa la misma calculadora Python pura que el runner, siguiendo el patrón
existente de proceso acotado con JSON tipado, timeout y argumentos permitidos,
sin shell ni reader/red/transporte. Regresa versiones de perfil/estado/políticas,
timestamps de datos, cantidades, restricciones vinculantes y caducidad. No reserva
capital, no consume señales y no es autorización. Recalcular siempre al consumir.
Los cinco controles y el capital lógico visible bastan para preview de asignación/exposición; riesgo efectivo,
SL/TP y target neto requieren una señal real y quote válida. Si faltan, mostrar
“pendiente de señal”, no inventar un stop para completar cifras.

### Vue y SignalR

Sección “CONFIGURACIÓN DIARIA R20” con cinco controles y capital lógico de sólo lectura, zona/intervalo, historial,
versión/hash y panel de preview. Lectura y edición administrativa distinguibles;
guardar muestra “no autoriza órdenes”. Con inventario abierto, identificar por
posición su versión y avisar “nueva configuración: sólo futuras entradas”.
Posiciones listadas por ID; no asumir `active` único como V1. Mostrar riesgo por
precio vs pérdida neta/estrés, margen modelado, costos por procedencia y holgura.
No sumar el capital de baseline con R20 ni reutilizar tarjetas V1 con datos V2.

Nuevo slice `aggressiveGrowthV2` y evento `aggressiveGrowthV2.updated` con revisión
monotónica; V1 `aggressiveGrowth.updated` conserva su contrato. Los eventos no
portan secretos ni conceden permisos. Hueco de revisiones/reconexión obliga a
snapshot; validación fallida mantiene última vista marcada obsoleta. Formularios
no se sobrescriben silenciosamente por SignalR: conflicto visible y nueva revisión.
Reutilizar componentes Vue/Pinia/Zod y estilos responsive actuales. Sol puede
explicar rechazos, no guardar/activar perfiles ni alterar cantidades.

## 8. Archivos y entregas futuras

Nombres propuestos; no creados como código en esta fase. Antes de editar se
verificará pertenencia a manifiestos protegidos y dependencias hash-bound.

| Bloque | Nuevos | Modificaciones futuras acotadas |
|---|---|---|
| Economía/perfiles | `python/trading_agent/r20_economics.py`, `r20_profiles.py`, `r20_v2_state.py` | Ninguna a `aggressive_growth.py`/config V1; imports estrechos de funciones puras |
| Observación | `r20_v2_runner.py`, `scripts/aggressive-growth-v2.ps1` | Reutilizar Reader y utilidades existentes sin editar el runner V1; singleton/rutas propias |
| Persistencia | `R20EconomicProfiles.cs`, `R20V2Store.cs`, `R20V2Invariants.cs` en Infrastructure; migración nueva posterior | Posible despacho versionado en `AggressiveGrowthCommand.cs`; no tocar 011 |
| API | `R20ConfigurationEndpoints.cs`, `R20ConfigurationSession.cs`, DTOs y servicio de preview | `DashboardEndpoints.cs` registro; `DashboardStore.cs`, `DashboardService.cs`, `DashboardRealtime.cs` para slice V2 |
| Proyección | `python/trading_agent/r20_v2_projection.py` | `dashboard_projection.py` incorpora slice V2; proyección V1 intacta |
| Frontend | `modules/aggressive-growth-v2/` contratos/configuración/posiciones, store V2 | `types.ts`, `realtime.ts`, navegación o página contenedora existente; conservar vista V1 |
| Tests | Python perfiles/economía/estado/runner/replay; C# perfiles/CAS/auth; Vitest y Playwright V2 | Tests actuales se conservan; agregar paridad y separación |

Build futuro aislado para V2; no sobrescribir DLLs Debug/R20Only en uso. El
despliegue del Dashboard requiere ventana propia y comprobación de compatibilidad,
no reiniciar Shadow para liberar un archivo. No crear servicio ni autorrestart
implícito. Tener código construido no autoriza iniciar cohorte V2.

Orden propuesto tras aprobación: (a) contrato/canonicalización y calculadora pura,
(b) ledger/día/recuperación y persistencia sólo en test, (c) API administrativa y
preview, (d) Vue/SignalR, (e) replay aislado y revisión económica. Cada entrega
requiere sus pruebas RED→GREEN y revisión de hashes. Migración operativa y primer
arranque V2 son decisiones posteriores separadas. Complejidad: media para perfil,
alta para sizing/costos/día y concurrencia, media para API/UI; Paper continúa alta
y fuera de esta fase. No estimar días antes de aprobar políticas y evidencia.

## 9. Compatibilidad, pendientes y gates

V1 conserva cohorte `aggressive-r20-b6675940304348228168514f1409c173`, motor
`e20ab2563683ec5dce55f842fde7abe131b21d0007e682dd032ec28042e2adbd`, protocolo
`92ee393739a2eba323ca6c7d68389443b27b04b71f04096e4e87631794f976d9` y BASELINE_1X.
Validar estas identidades contra el manifiesto original. V2 tiene
identificador/protocolo/engine propios.

BASELINE_1X forma parte de las invariantes y protocolo V1: no puede ocultarse del
ledger ni retirarse del cálculo vivo. Decisión aprobada: una sola cartera R20
operativa en V2. Un comparador 1x podría existir en replay separado, con capital
y contrato propios; no se crea ahora ni es una opción del perfil diario.

Decisiones incorporadas: America/Santo_Domingo, target neto estrictamente positivo
para entradas normales, L como límite de nuevas admisiones, pérdida neta con
reservas/latch durable, cinco controles diarios sobre equity lógico y sin baseline
V2. Los ensayos técnicos separados no se prohíben por un target no positivo, pero
requieren identidad y autorización explícitas, sin bypass en perfiles normales ni
mezcla de estadísticas. No se altera historia ni se autoriza ensayo alguno.

Pendientes antes de implementar:

1. Revisión del usuario de las ecuaciones de sizing, holgura, margen y día de
   [r20-v2-formulas.md](r20-v2-formulas.md).
2. Valores y evidencia de costos, escenarios, liquidez, buffers y límites duros;
   no se introducen defaults activos ni se deducen de una única quote.
3. Autorización explícita de integración posterior al núcleo aislado. Despliegue, migración, cohorte V2
   y cualquier ensayo técnico u operación IBKR tendrán sus gates separados.

Paper conserva los bloqueos de la evaluación previa: RiskEngine actual no admite
íntegramente 20%/10x; modificar un perfil no cambia ese rechazo. Transporte actual
no es simétrico LONG/SHORT; un adapter debe reutilizar SDK/callbacks y conservar
guards, sin convertir el reader. Exclusión durable debe abarcar todos los emisores
heredados o probar su inhabilitación; lease/CAS por cohorte no excluyen la cuenta.
Registro Paper separado, reservas previas a envío, conciliación ante ACK incierto,
protecciones y consentimiento futuros siguen obligatorios. No ampliar permisos
por aprobar la economía V2. R20-Only fase 1 sigue parcial.

## 10. Verificación y límites de esta entrega

Plan detallado: [r20-v2-test-plan.md](r20-v2-test-plan.md). La matriz de integración sigue propuesta; resultados del núcleo y regresiones
se registran en el informe r20-v2-core-20261012, sin acreditar integración. La auditoría previa es evidencia de V1, no prueba de V2.
No se ha consultado el journal operativo ni el estado vivo en esta fase de diseño;
su último corte citado sigue siendo 07:44:43 local, revisión 2262 del 12/oct.
No se afirma que esas posiciones permanezcan abiertas ahora. No se llamó Run,
Stop, reader IBKR, API de trading ni migraciones; no se modificó seguridad.

**Detención después del núcleo aislado. Integración, activación V2 y ejecución
Paper requieren sus autorizaciones correspondientes; ninguna se infiere aquí.**
