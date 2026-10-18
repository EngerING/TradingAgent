# Core V3.2 — viabilidad económica offline

Base aprobada: `b01529f`, rama `codex/core-v3-2-economics`.
Alcance: búsqueda y validación económica deterministas, sin orquestadores,
persistencia, proveedores, autoridad operativa ni ejecución.

## Diseño previo a implementación

| Archivo nuevo | Responsabilidad |
|---|---|
| `core_v3/economic_contracts.py` | Entradas/resultados inmutables y versionados, costos, margen, FX, hipótesis, política y escenario. Reutiliza los tipos V3.1. |
| `core_v3/economic_scenarios.py` | Dominio discreto y acotado, geometrías LONG/SHORT y límites técnicos independientes del beneficio. |
| `core_v3/economic_calculation.py` | Desglose Decimal de costos, margen, exposición, pérdida y stress de un escenario. |
| `core_v3/economics.py` | Validación de evidencia, preflight, postflight, huellas de inputs y traza determinista. |
| `python/tests/test_core_v3_economic_contracts.py` | Contratos cerrados y fixtures sintéticos compartidos; permite verificar tipos independientemente del motor. |
| `python/tests/test_core_v3_economics.py` | Fixtures sintéticos, contratos, cálculo y búsqueda de los cuatro estados. |
| `python/tests/test_core_v3_economic_postflight.py` | Cambios de contexto/política/geometría, serialización e independencia de permisos/servicios. |

Una prueba V3.1 existente recorre todos los archivos de `core_v3` y tiene una
lista cerrada de imports. Se ampliará solo esa lista con los nuevos módulos puros
y sus dependencias estándar necesarias; se conserva la prohibición de módulos
operativos. Los contratos, importadores y otras pruebas históricas no se editan.

La API utiliza contexto, política y reloj explícitos. El capital de cuenta y la
asignación disponible se distinguen; el presupuesto y la exposición restantes
ya descuentan compromisos de cartera del productor. Este motor no reserva dinero.

La búsqueda enumera exclusivamente hipótesis documentadas (dirección, entrada,
distancias SL/TP, máximo movimiento favorable y horizonte), cruzadas con la
grilla del instrumento desde el mínimo hasta el máximo de la política. No
aumenta TP ni riesgo para pagar costos. La política limita además distancias,
desviación de entrada, horizonte, spread, pérdida por escenario y evaluaciones.

Estados: testigo válido → FEASIBLE; dominio íntegramente descartado → INFEASIBLE;
información/evidencia insuficiente → UNKNOWN; dominio no agotado o cálculo no
representable → UNRESOLVED. FEASIBLE demuestra existencia condicional, no una
expectativa positiva ni ejecución posible. Todos los resultados llevan NO_TRADE.

La procedencia autodeclarada no autentica datos. En este incremento, la ruta
resoluble es evidencia SYNTHETIC explícita, con hashes y fechas comprobables,
habilitada por una política de investigación. Otras fuentes dan UNKNOWN: no se
añade un autenticador real ni se declara verificada una captura por su etiqueta.
Una futura integración deberá aportar esa frontera confiable por separado.

Costos en moneda cotizada: comisión de apertura y cierre (cada una el máximo
entre mínimo y tarifa por unidad), spread completo una vez bajo geometría mid,
slippage por cada lado y financiación fija/por unidad y hora. Horizonte en horas
enteras; el costo horario debe incluir el carry/borrow aplicable a la dirección.
Para moneda de cuenta diferente se exige conversión quote→account explícita y
vigente. Margen inicial y mantenimiento son supuestos independientes y explícitos.

El postflight vuelve a comprobar inputs y evidencia y exige coincidencia exacta
de hashes de contexto/política, hipótesis y escenario. Recalcula costos y límites;
una aceptación importada Forex V1 no es un resultado V3.2 válido.

Se desarrollan pruebas antes de cada bloque y se ejecutan las 80 regresiones
aprobadas. No se editarán fuentes V3.1, R20, Forex, Kronos, esquemas históricos,
frontend, configuración, adaptadores, manifests ni contenido de `.local`.

## Contratos y frontera pública entregados

`EconomicContext` agrupa `MarketSnapshot`, `PortfolioSnapshot`, `CostSchedule`,
`MarginModel`, hipótesis técnicas y conversión FX opcional. `ResearchPolicy`
fija vigencia, revisión, cantidad máxima, límites técnicos/económicos, edad
máxima de evidencia, shocks y presupuesto de evaluaciones. Todos reutilizan
`Instrument`, `Money`, `Quantity`, `Price` y `EvidenceRef` de V3.1 sin editarlos.

Las entradas, escenarios y resultados son dataclasses frozen con slots y
colecciones tuple. Sus documentos tienen nombres `trading.core_v3.economic.*`
y `schema_version=1`; `.from_json()`/`.from_dict()` rechazan extras, versiones
desconocidas, tipos incorrectos y autoridad inyectada. Los contratos malformados
producen `ContractError` con código fijo. Las ausencias expresables como `None`
producen `UNKNOWN`; no se convierten en importes cero.

```python
from trading_agent.core_v3.economic_contracts import EconomicContext, ResearchPolicy
from trading_agent.core_v3.economics import preflight, postflight

context = EconomicContext.from_json(context_json)
policy = ResearchPolicy.from_json(policy_json)
result = preflight(context, policy, now=explicit_utc_datetime)
if result.witness is not None:
    checked = postflight(context, policy, result.witness, result, now=explicit_utc_datetime)
```

El resultado identifica `engine_version=CORE_V3_2_V1`, stage, instante, hashes
de contexto/política, tamaño del dominio, intentos, presupuesto, completitud,
contadores de rechazo y hash de traza. Un testigo incluye la geometría exacta;
su evaluación desglosa costos, pérdidas, nominal, margen y cada shock. Para
reproducirlo deben conservarse también los JSON de contexto/política: los hashes
no permiten reconstruirlos. El motor devuelve datos en memoria; no escribe un ledger.

Todos los resultados fijan `scope=ECONOMIC_RESEARCH_ONLY`,
`trading_decision=NO_TRADE`, `execution_authority=false`,
`paper_execution_eligible=false`, `live_enabled=false`,
`statistically_validated=false` y `broker_executability_verified=false`.
Deserializar un resultado no acredita quién lo produjo.

## Algoritmo y límites efectivos

1. Validar moneda/unidad, revisión, capital/asignación, costos completos,
   direcciones cubiertas por la tarifa, margen, FX y metadata. La asignación
   no puede superar el equity. Las capacidades restantes de cartera las aporta
   el productor; no se calculan ni se reservan desde este motor.
2. Exigir `observed_at <= now < valid_until`, edad dentro del máximo de política,
   hash del material coincidente y entorno RESEARCH/SIMULATION consistente.
   El hash de cada registro excluye solo su propio `EvidenceRef`; el hash global
   de contexto sí incluye las referencias. SYNTHETIC requiere `allow_synthetic=true`.
   La etiqueta AUTHENTIC_CAPTURE, por sí sola, sigue dando UNKNOWN.
3. Rechazar globalmente un spread superior al máximo. Para cada hipótesis,
   comprobar dirección, instrumento, horizonte, desviación de entrada, distancia
   máxima de stop y `target_distance <= min(plausible_move, max_target_distance)`.
   Generar `SL = entrada - signo * distancia_SL` y
   `TP = entrada + signo * distancia_TP`, con signo +1 LONG y -1 SHORT.
   Entrada, SL y TP deben ser positivos y múltiplos del tick.
4. Cruzar las geometrías admitidas con `cantidad = mínimo + n * paso`, desde
   `n=0` hasta `floor((máximo-mínimo)/paso)`. Si máximo < mínimo no hay cantidades.
   Mantener el orden de hipótesis del input y cantidades ascendentes. El resultado
   es el primer testigo válido, no un ranking ni el óptimo de rentabilidad.
5. Evaluar cada escenario y sus shocks. Terminar con FEASIBLE al encontrar un
   testigo; sin él, devolver INFEASIBLE solo si el dominio quedó resuelto por
   completo. Presupuesto agotado o precisión insuficiente producen UNRESOLVED.
   La ausencia/incompatibilidad de evidencia produce UNKNOWN antes de buscar.
6. Postflight repite validación temporal/material, compara hashes y testigo,
   rechaza un preflight futuro, vuelve a comprobar pertenencia al dominio y
   recalcula la evaluación. No confía en métricas previas. Un punto no alcanzado
   por el presupuesto tampoco se declara inviable. Cambiar snapshot, cartera,
   costos, FX o política requiere un preflight nuevo, incluso si el cambio parece favorable.

Límites: hasta 32 hipótesis, entre 1 y 16 shocks adicionales, 1–720 horas enteras
por hipótesis, 1–86400 segundos de edad máxima y 1–10000 evaluaciones por política.
El stop base se evalúa siempre y su ID `BASE_STOP` está reservado. El dominio
puede ser enorme, pero las cantidades se generan de forma perezosa: no se
materializa la grilla. El trabajo es proporcional a hipótesis más evaluaciones
por shocks; la memoria no crece con la cantidad total de puntos.

`domain_size` incluye las geometrías no representables pendientes de resolución
y excluye las descartadas de forma concluyente. `evaluated` cuenta intentos,
incluidos fallos numéricos. `search_complete=false` si quedan puntos o cálculos
sin resolver; `SEARCH_LIMIT_REACHED` identifica específicamente el presupuesto
agotado. Cada intento añade hipótesis, índice, escenario, desglose y motivos
a una cadena SHA-256 determinista. No hay reloj de pared interno ni aleatoriedad.

## Modelo económico explícito

Con cantidad `q`, multiplicador `m`, spread `s`, slippage por lado `l`, horizonte
`h`, distancias `dTP`/`dSL` y tasa quote→account `r`:

```text
apertura = max(mínimo_apertura, q * tarifa_apertura)
cierre = max(mínimo_cierre, q * tarifa_cierre)
spread = q * m * s
slippage = 2 * q * m * l
financiación = fijo + q * tarifa_horaria * h
costos = apertura + cierre + spread + slippage + financiación
TP_neto = (q * m * dTP - costos) * r
pérdida_stop = (q * m * dSL + costos) * r
nominal = q * m * entrada * r
margen_inicial = (q * m * entrada * tasa_inicial + costos) * r
```

`r=1` solo cuando moneda cotizada y de cuenta coinciden. Las comisiones se cobran
por unidad de cantidad, sin aplicarles el multiplicador; spread/slippage y P&L
sí lo incluyen. Apertura y cierre aparecen una vez cada uno. Las hipótesis usan
precios de referencia mid; se carga un spread completo por round trip, sin
sumarlo de nuevo mediante fills bid/ask ficticios.

El TP neto debe ser estrictamente positivo y alcanzar el mínimo de política.
El nominal respeta exposición restante; margen más costos respeta equity,
asignación y margen libre. Stop y shocks respetan el mínimo entre riesgo
restante y pérdida máxima de política. Las tasas de margen son no negativas
(inicial estrictamente positiva) y pueden superar 1; no son probabilidades.

Cada shock añade gap adverso y slippage adicional por ambos lados a la pérdida.
Comprueba exposición en el precio adverso y mantenimiento sobre ese nominal.
La capacidad de margen después de pérdida es
`min(equity, asignación, margen_libre) - pérdida`; debe ser positiva y cubrir
mantenimiento. El resultado distingue esta capacidad del equity de la asignación
después de pérdida. Se trata de un stress conservador antes de liquidación, no
de una simulación de fills o una fórmula certificada del broker.

Los cálculos usan un contexto Decimal local independiente del ambiente, con
precisión 160 y detección de redondeo inexacto en la evaluación. Los productos
acotados de estos contratos caben en ese contexto; las salidas conservan los
límites V3.1: 18 dígitos enteros, 12 decimales y 28 significativos. Una salida
no representable produce UNRESOLVED, sin redondearla para obtener aceptación.

## Cuatro ejemplos reproducibles

Desde la raíz del repositorio, con `PYTHONPATH=python`, ejecutar el siguiente
Python con `.venv/Scripts/python.exe -B`. Usa fixtures de pruebas explícitamente
sintéticos y el cutoff fijo `2026-10-18T12:00:00Z`; no captura mercado ni cuenta:

```python
import sys
sys.path.insert(0, 'python/tests')
from dataclasses import replace
from test_core_v3_economic_contracts import AT, D, fixture, sealed
from trading_agent.core_v3.contracts import Money
from trading_agent.core_v3.economics import preflight

context, policy = fixture()
expensive = replace(context, costs=sealed(replace(
    context.costs, opening_minimum=Money(D('100'), 'USD'))))
cases = [
    (context, policy),
    (expensive, policy),
    (replace(context, costs=None), policy),
    (context, replace(policy, max_evaluations=1)),
]
for inputs, limits in cases:
    result = preflight(inputs, limits, now=AT)
    print(result.status.value, result.evaluated, result.domain_size, result.search_complete)
```

Salida ejecutada:

| Estado | Intentos/dominio | Completo | Interpretación |
|---|---|---|---|
| FEASIBLE | 26/50 | false | Primer testigo: 26 EUR, costos USD1.0078 y TP neto USD0.0322 bajo los supuestos. |
| INFEASIBLE | 50/50 | true | Comisiones, riesgo y margen descartan todo el dominio declarado. |
| UNKNOWN | 0/0 | false | Falta el esquema de costos; `COSTS_UNKNOWN`. El dominio todavía no se construye. |
| UNRESOLVED | 1/50 | false | Un intento no basta; no demuestra inviabilidad del resto. |

Traza del primer caso:
`fc7e86248093e512d9a706d5e49632f6e63b7d694145a522c730632c4948f6d0`.
Cambiar inputs, cutoff u orden de hipótesis cambia la identidad de la ejecución.

## Evidencia de verificación y revisión

Se aplicaron las skills Senior Software Engineer y Graphify antes de editar.
Se consultó el grafo existente (424 nodos, 1039 aristas, informe 2026-10-03),
sin reconstruirlo. Tras `graphify reflect --if-stale`, se usó su vocabulario
`execution risk capital` con presupuesto 1500: encontró 130 nodos y mostró 44.
La consulta orientó la revisión de `ExecutionFeasibility.cs` y contratos V3.1;
las dependencias nuevas se verificaron en fuentes actuales, no en ese grafo viejo.
El costo de extracción declarado por el grafo no mide el consumo de esta sesión.

| Grupo ejecutado | Resultado final |
|---|---|
| Contratos económicos V3.2 | 3 pasadas |
| Búsqueda/cálculos V3.2 | 16 pasadas |
| Evidencia, postflight, límites y aislamiento V3.2 | 19 pasadas |
| Contratos/importadores V3.1 | 36 pasadas |
| Forex Fase 1 | 28 pasadas |
| Contratos AI históricos | 16 pasadas |
| Total | **118 pasadas, cero fallos** |

La ejecución final instaló audit hooks que deniegan `socket.connect`,
`socket.getaddrinfo`, `socket.bind`, `subprocess.Popen` y apertura/listado de la
`.local` real. Las bases SQLite de regresión fueron temporales nuevas; se usó
permiso fuera del sandbox Windows. Las llamadas al motor también se probaron
con apertura de archivos prohibida. No se hicieron llamadas de modelos ni broker.

Casos relevantes: ambos instrumentos y direcciones, capital/asignación variable,
multiplier y FX explícitos, neto cero, fees/carry, datos desconocidos, fuentes
autodeclaradas, caducidad/futuro, tick/grilla, stress, evidencia alterada,
postflight falsificado y una grilla de más de un billón de puntos con límite
de tres intentos. También se comprobó independencia de precisión, redondeo,
traps y límites de exponente Decimal ambientales.

La revisión de corrección, arquitectura, seguridad y límites corrigió temporalidad,
representabilidad numérica, capacidad de margen bajo stress y ausencia de prueba
por presupuesto agotado. Una inversión temporal de `net <= 0` hizo fallar la
prueba de neto cero; se restauraron los bytes originales antes de verificar todo.
Es una comprobación puntual de sensibilidad, no mutation testing exhaustivo ni
una auditoría independiente. No se ejecutaron .NET, servicios ni pruebas operativas.

## Comparación Git y alcance conservado

Base verificada: `codex/core-v3-1-contracts` en `b01529f`. Rama creada:
`codex/core-v3-2-economics`. La entrega añade cuatro módulos, tres archivos de
pruebas y este documento. Solo cambia un archivo previo:
`test_core_v3_legacy_import.py`, ampliando su allowlist con `types`, `typing`,
`economic_contracts`, `economic_scenarios` y `economic_calculation`, conservando
todas sus aserciones y prohibiciones operativas.

Los contratos/importadores V3.1, fuentes Forex/R20/Kronos, frontend, configuración,
schemas históricos, manifests, migraciones y adaptadores conservan sus bytes
versionados. Los documentos ajenos sin seguimiento
`core-v3-phase0-audit.md` y `TradingAgent_Manual_Tecnico_Integral.pdf` se conservan
sin incorporarlos a los commits. No hay push, merge, servicios ni datos operativos.
La comparación reproducible es `git diff --stat b01529f..HEAD` y
`git diff --name-status b01529f..HEAD`.

## Limitaciones y siguiente incremento propuesto

La plausibilidad técnica viene declarada por cada hipótesis: no se obtiene de
un clasificador causal ni de Sol/Kronos. Las tarifas son mínimos o cargos por
unidad y financiación lineal/fija; no modelan escalones, rebates, horarios de
rollover ni todos los costos de un broker. El multiplicador es constante y
todos los costos parten de la moneda cotizada. No hay liquidez, fills parciales,
órdenes, cartera multiinstrumento reservada ni actualización autenticada de saldos.
Un entorno real, captura autodeclarada o FX sin evidencia admitida queda UNKNOWN.

El modelo supone costos/FX/margen constantes durante cada escenario; los shocks
son acotados y no garantizan pérdida máxima ni disponibilidad de préstamo. No
calcula probabilidad TP, expectativa estadística, backtest o rentabilidad futura.
INFEASIBLE solo habla del dominio/política provistos; FEASIBLE solo demuestra
un testigo bajo esos supuestos. US$100 es un fixture, nunca capital fijo del motor.

El siguiente incremento propuesto sería un ciclo de investigación exclusivamente
simulado, con presupuesto durable, idempotencia y ledger propio que consuma este
gate antes de invocar un diseñador simulado. Requiere auditoría y aprobación
separadas. **V3.3 no se inició.**
