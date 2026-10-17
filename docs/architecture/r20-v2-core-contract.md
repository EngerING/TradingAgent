# R20 V2 — contrato del núcleo aislado, revisión 3

12/oct/2026. Precisión autorizada para implementación matemática, sin integración
operativa. Este documento sustituye las fórmulas de equity y el techo obligatorio
de las revisiones anteriores; conserva su estrategia, zona y fronteras de seguridad.

## Equity que evoluciona

```text
cash = capital_inicial + PnL_bruto_realizado − costos_liquidados
equity_económica = cash + PnL_bruto_abierto
                  − costos_devengados_no_pagados − reservas_estimadas_abiertas
equity_disponible = equity_económica − reservas_de_entradas_pendientes
equity_operativa = max(0, equity_disponible)
si existe equity_cap_usd explícito: equity_operativa = min(equity_operativa, cap)
```

capital_base_usd es referencia/fondeo inicial, no techo ni aporte diario.
equity_cap_usd es opcional y null permite crecimiento compuesto. El perfil captura
el techo explícito si se configura; cambiarlo sólo afecta nuevas admisiones.
No modifica cash ni resetea pérdidas. Ejemplo abstracto: 100 inicial, +30 PnL
cerrado y 5 costos liquidados producen 125 operativos; cap explícito 110 limita
sizing a 110, sin borrar los otros 15 de equity económica.

Cada costo tiene ID único, importe no negativo, procedencia y exactamente un
estado: SETTLED (en cash), ACCRUED (obligación no pagada), RESERVED (estimación).
Confirmación o liquidación reemplaza el estado del mismo ID; no añade otra copia.
Si la estimación difiere del costo confirmado, sólo la diferencia altera equity.
MODELED no se presenta como BROKER_CONFIRMED. Un cierre traslada PnL abierto a
realizado y liquida/libera reservas; no vuelve a descontar costos ya liquidados.

## Perfil y decisiones

Perfil frozen versionado, cinco controles diarios, capital de referencia,
equity_cap_usd opcional, timestamps UTC, día America/Santo_Domingo, versiones/hash
de políticas y SHA256 de material canónico. Sin defaults económicos operativos.
Cada assessment conserva el hash de perfil; perfil expirado bloquea nueva entrada.
No existen mutaciones de posiciones, flags de excepción ni funciones de órdenes.

## Sizing, costos y margen

```text
B = equity_operativa × risk_per_trade_pct / 100
A = equity_operativa × capital_allocation_pct / 100
q_riesgo = B / D
q_asignación = A × L / P
q_final = max { q de rejilla válida : todas las restricciones se cumplen }
TP_neto = 2qD − C_target(q) > 0
SL_neto_estimado = qD + C_stop(q)
```

El primer núcleo usa costos por lado con mínimo y tarifa por unidad, spread
medio de entrada/salida, slippage por lado y financiación fija + por unidad para
el horizonte explícito de la política suministrada. No estima tasas ni tarifas
IBKR. Costos de estrés incluyen deterioros adicionales explícitos. Sin evidencia
identificada y parámetros válidos se rechaza. Son estimaciones, no fills.

Rejilla finita acotada: enumerar de mayor a menor para encontrar máximo admisible,
sin asumir monotonicidad del target neto con fees mínimos. Si la rejilla excede
el presupuesto de cálculo se rechaza SIZING_UNRESOLVED. No se aumenta leverage
para consumir B ni se redondea hacia arriba.

```text
E_post = equity_económica − costos_pendientes − C_entrada_total(q)
X_post = exposición_bruta_abierta_y_pendiente + qP
H = L E_post − X_post
E_j = E_post − pérdida_incremental_existente_j
      − max(0, −signo × q × movimiento_j) − deterioro_costos_j(q)
X_j = exposición_existente + cambio_exposición_existente_j
      + q(P + movimiento_j)
H_requerida = max(L E_post h_min,
                  max_j[(X_j−X_post) + L(E_post−E_j) + L b_equity_j])
```

Exigir H≥H_requerida, E_j>b_equity_j, margen mantenimiento_j+buffer_j≤E_j,
exposición dura, margen inicial libre, liquidez, cupo y presupuesto diario.
El margen libre es el menor entre capacidad lógica tras costos/margen comprometido
y disponibilidad suministrada/reconciliada; no confundirlo con apalancamiento.
Los escenarios deben cubrir stop y un gap adverso para el lado candidato; ambos
lados se prueban. h_min, buffers y escenarios tienen evidencia obligatoria y
ningún valor predeterminado. El núcleo valida coherencia matemática, no suficiencia
empírica del conjunto: calibración y aprobación operacional siguen pendientes.

L es de admisión. Este núcleo no emite cierres; incumplimiento administrativo
bloquea entradas y se distingue de MARGIN/MAINTENANCE/HARD_EXPOSURE. Integración
futura debe mantener acciones defensivas de los guards ante condiciones reales.

## Día: términos mutuamente excluyentes

```text
E_day0 = equity económica al inicio del día, congelada
base_día = max(0,E_day0), limitada por cap explícito al abrir el día si existe
D_día = mínimo de base_día × porcentaje_día de los perfiles activados ese día
U = max(0, E_day0 − equity_económica_actual)
R_abierto = suma max(0, valor_neto_actual_i − valor_neto_estresado_i)
R_pendiente = pérdidas netas estresadas totales de entradas todavía no abiertas
R_candidata = pérdida bruta adversa + costos totales de candidata
Admisión: U + R_abierto + R_pendiente + R_candidata ≤ D_día
```

Los valores netos de cada posición deducen sólo costos todavía no liquidados;
los liquidados ya están en cash. R_abierto es deterioro desde el mark actual,
no pérdida desde entrada. Entradas pendientes/candidata aún no están en equity
económica; incluyen sus costos una vez. Los IDs de reservas y posiciones son
únicos. La contabilidad neta del día permite compensación de resultados realizados
y abiertos; no acredita ganancias hipotéticas en reservas futuras.

Latch = anterior OR U≥D_día. Perfil nuevo no amplía D_día ni elimina latch.
Estado inmutable serializable con hash, día, reloj monotónico, referencia,
presupuesto, reservas y bloqueos operacionales. Roundtrip prueba recuperación
en memoria; **no afirma durabilidad PostgreSQL**, que no se implementa aquí.
Nuevo día requiere referencia de frontera verificada, conserva bloqueos globales
(EmergencyStop, órdenes inciertas, reconciliación, recuperación). Reinicia sólo
el presupuesto/latch del nuevo día; el registro anterior permanece histórico.
Sin referencia verificada no se habilita un día nuevo para entradas.

## Alcance de la entrega

Python puro: perfiles, aritmética, ledger de costos, estado diario y sizing.
No reader, runner, journal operativo, migraciones, API, frontend, permisos ni
transporte. Señales y evaluaciones V1 no se alteran. Las comparaciones reproducen
supuestos explícitos y no acreditan rentabilidad ni ejecución Paper.

## Contratos implementados y límites precisos

- `r20_profiles.EconomicProfile`: frozen, validación decimal/UTC, cinco controles,
  `equity_cap_usd=None` sin techo, selección temporal, hash canónico y JSON estricto.
  No contiene activación administrativa, firma ni permiso. La versión tzdb usada
  se deberá fijar al integrar/desplegar; zona America/Santo_Domingo explícita.
- `r20_economics.Cost/Equity`: snapshots con IDs únicos y estados excluyentes;
  `equity()` y `eligible()` separan liquidados, devengos, reservas y pendientes.
  No se implementa un ledger persistente de cargos ni un motor de fills.
- `OpenRisk/PendingRisk/DailyState`: estado inmutable, términos por posición,
  presupuesto/latch y JSON con hash. Perfil intradía vencido conserva contabilidad
  de pérdidas pero no permite admisión. Día nuevo conserva inventario/bloqueos y
  exige revalorar antes de abrir. El caller suministra un snapshot reconciliado;
  el hash detecta corrupción, no sustituye autenticación, CAS ni cadena histórica.
- `r20_sizing.CostModel/Limits/Stress/Assessment`: cálculo puro, rejilla acotada,
  evidencia declarada obligatoria, hashes de políticas y de todos los inputs,
  incluidos escenarios/snapshot. Resultado con `cost_status=ESTIMATED`,
  `paper_execution_eligible=false` y `statistically_validated=false` no configurables.

Contexto Decimal local de 96 dígitos independiente del contexto global; validación
de finitud/tamaño de entradas. No es aritmética racional infinita. Rejilla y número
de escenarios acotados; SIZING_UNRESOLVED en vez de adivinar tamaño. Shocks estáticos
precomputados: no modelo estocástico, trayectoria intrabar ni correlación.
La evidencia es una referencia declarada, no certificación externa. Limits fija
límites y el hash del assessment fija también los escenarios concretos; calibrar
y autorizar conjuntos de escenarios queda pendiente de integración.

Este núcleo no emite cierres. La obligación de conservar acciones defensivas por
margen/emergencia debe probarse al conectar el ciclo de vida. No reemplaza
RiskEngine ni ExecutionGuard. No se afirma protección operativa V2 por aprobar
tests matemáticos ni durabilidad PostgreSQL por recuperar un objeto JSON.
