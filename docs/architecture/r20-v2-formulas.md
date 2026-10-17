# R20 V2 — contrato de fórmulas para revisión

12/oct/2026, revisión 3. El [contrato del núcleo](r20-v2-core-contract.md)
es la definición vigente implementada en aislamiento. Integra la aprobación
condicionada sobre equity que crece y costos excluyentes. Sin integración operativa.
Este documento concreta las secciones 4 y 6 del
[diseño](r20-v2-economic-design.md). No cambia V1 ni autoriza cohortes u órdenes.

## 1. Tiempo, controles y ámbito

Día económico: fecha local en `America/Santo_Domingo`, desde 00:00 inclusive
hasta 00:00 del día siguiente exclusive. Persistir instantes en UTC y la zona,
fecha económica y versión tzdb explícitas. Resolver ambas fronteras por calendario
local, no mediante un offset fijo ni sumando 24 horas UTC. El reloj local del
equipo no elige el día económico. Conservar las reglas de rechazo de horas
ambiguas/inexistentes y los tests temporales del contrato general.

Cinco controles diarios: riesgo `r`, asignación `a`, leverage `L`, pérdida diaria
`d` y cupo `n`. Porcentajes de API en puntos porcentuales; en estas ecuaciones
`r=pct_r/100`, `a=pct_a/100`, `d=pct_d/100`. `L` es multiplicador, `n` entero.
La estrategia conserva dirección LONG/SHORT, distancia `D=1.5×ATR14` y target `2D`.

`capital_base_usd` es referencia inicial, no limita crecimiento por ganancias.
`equity_cap_usd` es techo opcional explícito; null no limita crecimiento.
No es saldo del bróker ni aporte. Cambiar el techo sólo limita nuevas admisiones
y no cambia cash, equity económica ni presupuesto diario congelado.

Ámbito de capacidad y pérdidas: cartera lógica V2 completa, no perfil individual.
No sumar V1, BASELINE_1X, otras cohortes ni el saldo nominal de IBKR Paper. V2 no
incluye baseline operativa; datos y cálculo V1 permanecen íntegros.

## 2. Estado previo y costos, sin duplicación

Todo cálculo usa un snapshot coherente de cartera/perfil/mercado/políticas con
revisiones e instante de disponibilidad. Precios en USD/EUR, cantidades EUR,
exposición/margen/equity/costos en USD. Decimales exactos, no floats de interfaz.

```text
s_i = +1 LONG; −1 SHORT
cash = capital_inicial + PnL_realizado_bruto − costos_liquidados
V_i(t) = s_i q_i [P_i(t) − P_entry_i] − costos_no_liquidados_i(t)
E(t) = cash + Σ_abiertas V_i(t) − otros_devengos_no_pagados
C_pending = Σ_entradas_reservadas C_k(entrada)
E_available = E(t) − C_pending
E_eligible = max(E_available, 0)
si equity_cap_usd no es null: E_eligible = min(E_eligible, equity_cap_usd)
```

Cada costo tiene un ID y estado excluyente: liquidado en cash, devengado no
pagado o reservado estimado. Otros devengos excluyen los asignados a posiciones.
Confirmar/pagar reemplaza un estado, no agrega un segundo descuento. Entradas
pendientes no están en E(t); sus reservas se deducen sólo en E_available.
En la transacción de apertura la reserva pendiente se convierte en abierta,
sin descontar ambas. Reservar margen no es registrar un gasto en equity.

Costo total por escenario z:

```text
C_z(q) = fee_open_z(q) + fee_close_z(q)
       + q × [spread_entry_z + spread_exit_z]/2
       + q × [slippage_open_z + slippage_close_z]
       + financing_z(q, tiempo, dirección, calendario)
```

Referencia Shadow: midpoint para PnL y costos explícitos. No sumar otra vez la
diferencia bid/ask como si el midpoint fuera un fill ejecutado. Las funciones
incluyen mínimos/tramos, unidades, fuente, fecha, vigencia y hash. Separar
OBSERVED, ESTIMATED, BROKER_CONFIRMED y UNKNOWN. Tarifa publicada o quote observada
no son comisión/fill confirmados. UNKNOWN no significa cero. No sustituir el
piso por una única quote. Las políticas de costos requieren validación antes
de activar entradas; no se fija un piso nuevo en esta entrega.

## 3. Dimensionamiento por operación

```text
B_price = E_eligible × r
A = E_eligible × a
X_allocation = A × L
q_price = B_price / D
q_allocation = X_allocation / P

price_risk(q) = q × D
effective_price_risk_pct(q) = 100 × q × D / E_eligible
requested_price_risk_pct = 100 × r
stop_loss_net_est(q) = q × D + C_stop(q)
target_net_est(q) = 2 × q × D − C_target(q)
```

Para entradas normales: `target_net_est(q) > 0` obligatorio. La igualdad también
rechaza. Stop neto estimado no es pérdida máxima garantizada: gaps/deslizamiento
pueden superarlo. `r` es máximo, no objetivo de consumo. No cambiar D ni elevar L
para obtener tamaño o un fill.

Rejilla `G={q_min+k×q_step : k entero ≥0}`, conforme al contrato del instrumento.
Si sus reglas exigen múltiplos de un origen distinto, ese origen debe estar
declarado; no inventar mínimos o incrementos. Definición final:

```text
Q_admissible = {q ∈ G : q ≤ q_price, q ≤ q_allocation,
               y pasan simultáneamente las restricciones 4, 5 y 6,
               liquidez, cupo, target neto positivo y todos los guards}
q_final = max(Q_admissible) si no está vacío; en otro caso, REJECT
```

Límite de cantidad por liquidez `q_liquidity` y cupo
`N_open+N_pending+1 ≤ n` obligatorios. Quotes BBO solas no acreditan profundidad.
Exposición bruta: sumar `|q×P|` por posición y reserva; no compensar LONG/SHORT
para fabricar margen o capacidad. No aumentar cantidades al redondear. Comisiones
con mínimos pueden crear un límite inferior económico: no resumir el solver como
un min de techos si los tramos no son monotónicos. Revalidar todo q cuantizado;
si no se resuelve de forma comprobable, rechazar `SIZING_UNRESOLVED`.

## 4. Holgura verificable del apalancamiento administrativo

X_old incluye abiertas y entradas ya reservadas. Las reservas usan precios
conservadores acotados y su escenario de estrés, nunca un precio ilimitado.

```text
E_post(q) = E(t) − C_pending − C_entry_est(q)
X_post(q) = X_old + q × P
L_post(q) = X_post(q) / E_post(q)
H_0(q) = L × E_post(q) − X_post(q)
```

`C_entry_est` es el costo **total** de ida/vuelta reservado al abrir, no sólo fee
de apertura. E_post debe ser positivo. Sea `h_min` el mínimo relativo de holgura
y, para cada escenario aprobado j, `b_j` un colchón adicional de equity en USD:

```text
0 < h_min < 1; b_j ≥ 0
ΔE_j(q) = pérdida incremental conservadora desde E_post, sin costos duplicados
E_j(q) = E_post(q) − ΔE_j(q)
X_j(q) = exposición bruta conservadora bajo el escenario j
ΔX_j(q) = X_j(q) − X_post(q)   [puede ser negativa]

H_required(q) = max(L × E_post(q) × h_min,
                    max_j[ΔX_j(q) + L × ΔE_j(q) + L × b_j])

Aceptar sólo si H_0(q) ≥ H_required(q) y E_j(q) > b_j para todo j.
```

Equivalente verificable: `L_post ≤ L×(1−h_min)` y
`X_j ≤ L×(E_j−b_j)` para todos los escenarios. Mostrar H_0, H_required y su
diferencia en USD de exposición; mostrar también `1−L_post/L` como fracción
de holgura inicial. No confundir H con margen libre USD.

El conjunto de escenarios incluye stop, gap, deterioro de spread/slippage y
financiación, conjuntamente para posiciones existentes, pendientes y candidata.
ΔE se obtiene del deterioro del valor neto ya reservado: agregar sólo diferencias
de costo respecto al snapshot, no C completo otra vez. No acreditar ganancias
hipotéticas de otras posiciones como protección. Escenarios y buffers son
política operacional versionada, fuera de los cinco controles diarios.
**Sus valores numéricos requieren evidencia y aprobación; no hay defaults activos.**
La fórmula es definida, pero no puede dar un tamaño operativo sin esas entradas.

## 5. Margen, exposición dura y posiciones existentes

Además de la holgura administrativa, exigir, en el estado inmediato y cada estrés:

```text
F_initial = E_available − M_initial_existing_and_pending − B_initial
M_initial_candidate(q) + C_entry_est(q) ≤ F_initial
M_maintenance_j(q) + B_maintenance_j ≤ E_j(q)
X_j(q) ≤ X_hard_j
```

`B_initial`, `B_maintenance_j`, `X_hard_j` y funciones de margen proceden de
políticas operacionales vigentes y condiciones del instrumento; conocidas,
versionadas y con procedencia. El primer renglón usa capacidad lógica modelada;
en Paper futuro también debe cumplirse la disponibilidad real reconciliada
del bróker, que puede ser menor. No derivar margen IBKR de L ni heredar sin
validación los porcentajes modelados de V1. Recursos no disponibles o condiciones
desconocidas bloquean entrada. La referencia de capital no convierte ganancias no utilizables en efectivo.

L diario es **sólo un límite de admisión**, también aplicado a los escenarios de
esa nueva admisión. No es un trigger independiente de liquidación. Reglas:

| Situación | Gestión de existentes | Nuevas entradas |
|---|---|---|
| Pequeño movimiento de equity lleva L observado por encima de L diario | Conservar SL/TP, perfil y gestión; registrar `ADMIN_LEVERAGE_EXCEEDED`, no cierre por ese motivo | Bloquear hasta que snapshot y candidata cumplan todas las restricciones |
| Usuario reduce L o n por debajo del inventario actual | No redimensionar ni cerrar para adaptar el perfil; contratos anteriores intactos | Aplicar nuevo límite al total, incluidos inventario/reservas anteriores; no sólo a la candidata |
| Riesgo/porcentaje asignado nuevo menor | Riesgo y tamaño históricos no se reescriben | Aplicar presupuesto nuevo y riesgo abierto agregado |
| Insuficiencia de margen real, emergencia, mantenimiento o exposición dura | Ejecutar la gestión defensiva que exija el contrato/guard aplicable, independiente de L administrativo | Bloqueadas; no ocultar el incumplimiento como una simple alerta administrativa |
| Datos obsoletos/desconexión | Conservar inventario; marcar valoración obsoleta, recuperar/conciliar; no fabricar fills | Bloqueadas |

Una reducción de perfil no puede reducir artificialmente el riesgo contabilizado
de posiciones anteriores. Sus reservas se recalculan desde precio actual y
contrato congelado. Congelar el perfil no congela requisitos reales del bróker.
En Shadow sólo hay gestión simulada con datos válidos; en Paper futuro cierres,
protecciones, cancelaciones y recuperación seguirán sus guards y permisos propios.
Esta especificación no autoriza ninguna acción IBKR.

## 6. Pérdida diaria, reservas y bloqueo durable

`E_day0` es equity neta de referencia congelada al comienzo del día económico.
`E_day_eligible=max(E_day0,0)`, limitado sólo por cap opcional explícito
al abrir el día. Para cada perfil k activado durante el día:

```text
D_k = E_day_eligible × d_k
D_budget(t) = min(D_k de todos los perfiles activados en ese día hasta t)
U_day(t) = max(0, E_day0 − E(t))
V_i_stress = valor neto de salida estresada de la posición i
R_open(t) = Σ_abiertas max(0, V_i(t) − V_i_stress)
R_pending(t) = Σ_pendientes Loss_k_stress_total
Loss_new(q) = max_j(max(0, −s q [P_exit_j−P_entry]) + C_j(q))

Admisión diaria: U_day + R_open + R_pending + Loss_new(q) ≤ D_budget
```

R_open es pérdida **adicional** desde el valor neto actual, no pérdida desde la
entrada: costos y pérdidas ya reflejados en E(t) no se añaden otra vez. Pendientes
y candidata no están en E(t): R_pending y Loss_new incluyen su pérdida y costos
completos exactamente una vez. Se usa la suma conservadora de peores pérdidas
individuales sin compensación hipotética entre posiciones. Puede reservar más
que una trayectoria conjunta plausible; es intencional y se muestra como tal.
Los escenarios empleados aquí cubren al menos los de la sección 4.

Las ganancias reales del día compensan pérdidas en U_day, pero no amplían
D_budget. El consumo disponible y la reserva se muestran por separado. Sin
perfil válido no hay apertura, aunque todavía haya presupuesto.

```text
loss_blocked_day(t) = loss_blocked_day(t−1)
                     OR [U_day(t) ≥ D_budget(t)]
can_enter = NOT loss_blocked_day
            AND perfil_vigente AND datos_válidos
            AND presupuesto_con_reservas_suficiente AND demás_guards
```

La actualización del latch y del estado diario se persiste por CAS antes de
cualquier admisión. También evaluar el latch al reducir D_budget. Reinicio
recupera `day_id`, E_day0, historial de presupuestos, reservas y latch; no los
recrea desde configuración. Si falta coherencia, bloquear entradas y recuperar.
Editar/revocar/recrear un perfil o recuperar equity no limpia el latch. Un aumento
del porcentaje no amplía presupuesto intradía porque rige el mínimo histórico.
No acumular deuda de límites negativos ni convertir rechazo en orden de cierre.

Agotar capacidad por reservas sin alcanzar pérdida observada es otro motivo:
`DAILY_CAPACITY_RESERVED`. Puede liberar capacidad un cierre o una reducción de
riesgo verificada, pero nunca desaparece un latch de pérdida ya disparado. No
persistir como pérdida realizada una reserva aún no consumida.

Al día siguiente se crea un registro diario nuevo, conservando el anterior,
posiciones, costos y riesgo pendiente. El latch del día anterior no se borra; el
nuevo día tiene su propio latch y presupuesto, sujetos a datos válidos. No
reiniciar EmergencyStop ni otras paradas globales. La gestión continúa incluso
con perfil vencido o pérdida diaria bloqueada. El límite diario por sí solo no
fuerza cierres; los guards de protección duros mantienen su autoridad.

Si no hay mark válido en frontera, `DAY_BOUNDARY_UNVALUED` bloquea admisión:
conservar el último mark íntegro previo como referencia provisional, atribuir
conservadoramente al nuevo día el gap hasta recuperación y registrar el intervalo
real. No tomar el primer precio recuperado como base para borrar pérdidas.
Sin referencia íntegra, seguir bloqueado. La primera cohorte sin posiciones usa
el fondeo autorizado como referencia. El cambio de día es idempotente.

## 7. Ensayos técnicos y decisiones económicas

Rechazo de target neto ≤0 rige entradas normales nuevas V2. No reevalúa admisión
histórica de V1 ni obliga a cerrar posiciones antiguas. Un ensayo técnico distinto
puede estudiar ese caso sólo con identidad, finalidad, alcance y autorización
explícitos, registro separado y resultados excluidos de estadísticas operativas.
No existe checkbox `ignore_costs`, perfil diario de excepción ni fallback desde
un rechazo normal. Autorizar el diseño no autoriza ese ensayo; si involucra IBKR
necesita su autorización específica y todos sus guards. En esta fase no se crea
ningún mecanismo de ensayo ni permisos.

## 8. Pruebas algebraicas propuestas y criterios de revisión

- Demostrar la equivalencia de H_required con las desigualdades de leverage
  inicial y de cada escenario, incluidos ΔX negativos y costo no lineal.
- Costo reservado una vez al pasar pendiente→abierta→cerrada: identidad de equity
  y conciliación de pérdidas; margen no se contabiliza como comisión.
- Bajar L no produce cierre administrativo; no exime déficit de margen real ni
  exposición dura. No modificar SL/TP/tamaño por cambio diario.
- Perfil intradía más permisivo no aumenta D_budget ni elimina latch. Reinicio,
  cambio de zona del equipo y día nuevo no borran el registro previo.
- Neto TP cero/negativo rechaza normal; ensayo no autorizado tampoco abre.
  Ninguna alteración de V1, baseline ni sus hashes.

No se ha elegido una calibración de h_min, buffers, gaps o costos. Las ecuaciones
son el contrato presentado para revisión; su integración espera aprobación; el núcleo aislado está implementado.
