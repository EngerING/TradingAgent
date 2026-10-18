# Core V3.3 — investigación simulada durable

Base: `77daf8e`, rama `codex/core-v3-3-research-orchestrator`.
Alcance autorizado: investigación offline sin modelos reales, brokers ni ejecución.

## Diseño previo

| Archivo nuevo | Responsabilidad |
|---|---|
| `core_v3/research_contracts.py` | Solicitudes, identidad/referencias, presupuesto, propuestas y estados cerrados e inmutables. |
| `core_v3/research_designer.py` | Puerto y diseñador simulado fijo; snapshots offline explícitos. |
| `core_v3/research_journal.py` | SQLite independiente, eventos inmutables encadenados, replay validado y presupuesto atómico. |
| `core_v3/research_runner.py` | Ciclo con gates V3.2, comprobaciones después del diseño y recuperación sin repetición. |
| `python/tests/test_core_v3_research_*.py` | Contratos, diario real temporal, concurrencia, fallos y ciclo offline. |

Se preservan fuentes, contratos y cálculos V3.1/V3.2. La única edición prevista
de una prueba anterior amplía su allowlist de imports offline, sin quitar
aserciones. No se modifican subsistemas históricos ni los dos documentos ajenos
sin seguimiento. No se lee `.local`.

El diario usa una ruta fija bajo un root explícito de composición, nunca paths
derivados de IDs. IDs y claves de idempotencia son acotados. SQLite es nuevo,
separado de Forex/R20, con transacciones `BEGIN IMMEDIATE`, timeout acotado,
eventos append-only y verificación de secuencia, hashes y máquina de estados.

Estados: RECEIVED, VALIDATION_REJECTED, ECONOMIC_BLOCKED, BUDGET_BLOCKED,
BUDGET_RESERVED, DESIGNING, DESIGN_RECEIVED, POSTFLIGHT_PENDING,
CANDIDATE_RECORDED, FAILED e INTERRUPTED. Repetir una solicitud devuelve su
estado durable. Una operación pendiente no invoca otra vez el diseñador.
La recuperación explícita interrumpe el trabajo, conservando reservas inciertas.

El presupuesto es de investigación: solicitudes, tokens e importe simulado USD.
No es equity, margen ni riesgo de posición. La reserva es atómica; una respuesta
simulada conocida consume una solicitud y cero tokens/costo real. Una llamada
sin resultado conocido conserva su reserva hasta revisión. Sin proveedor real,
no hay facturación. El estado financiero se mantiene en los inputs V3.2.

El resultado guarda identidades, hashes, evidencia económica y límites sin
autoridad operativa: NO_TRADE, sin Paper/Live, estadística ni ejecución.
El diseño produce una hipótesis ligada a un escenario, no una estrategia
ejecutable ni evidencia de backtest.

Riesgos a probar: doble reserva concurrente, crash entre commits, evidencia
caducada, salida inválida, alteración/truncamiento del diario y errores SQLite.
Los hashes detectan alteraciones respecto al historial disponible; no autentican
externamente al productor ni protegen frente a reescritura completa por quien
controle el archivo y sus anclas. El alcance de detección se documentará.

## Arquitectura entregada y contratos

`ResearchRequest` contiene ID, clave de idempotencia, `InstrumentIdentity`,
`ResearchInputs` y `ResearchAllowance`. Los inputs contienen los contratos
V3.2 originales, sin adaptarlos ni cambiar sus unidades. El presupuesto global
`BudgetPolicy` pertenece al diario y queda fijado en su evento génesis; reabrir
el mismo archivo con otra política produce conflicto.

Los contratos de wire tienen namespace `trading.core_v3.research.*`, versión 1,
dataclasses frozen/slots y el JSON estricto/canonicalización ya aprobados.
`DesignRequest`, `ResearchProposal`, `DesignReceipt`, `ResearchCharge`,
`BudgetStatus`, `ResearchReferences` y `ResearchResult` completan la frontera.
Se rechazan tipos incorrectos, versiones desconocidas, campos extra, duplicados,
IDs con rutas, saldos inconsistentes y permisos inyectados.

El resultado guarda hashes de solicitud, instrumento, política de presupuesto,
contexto, política económica, preflight, propuesta y postflight. El hash semántico
de propuesta es distinto del hash de los bytes recibidos. El ID de operación
incluye el namespace del motor, solicitud y presupuesto, evitando colisiones
entre asignaciones independientes. Dos ejecuciones aisladas con los mismos
inputs, presupuesto y reloj producen el mismo resultado y cadena de eventos.

`ResearchDesigner` describe el puerto, pero `run()` exige exactamente
`SimulatedDesigner`: no admite subclases, callables ni plugins. El adaptador no
tiene transporte ni código dinámico. Su respuesta por defecto es una hipótesis
determinista ligada al escenario del preflight. También admite un fixture JSON
acotado para comprobar rechazos. El ID de candidata, instrumento y geometría
deben coincidir con la propuesta determinista esperada; no se aceptan código,
reglas ejecutables ni una redefinición del riesgo.

`OfflineInputSource.capture()` devuelve un snapshot inmutable publicado por el
host. El runner lo consulta después del diseño. El host puede publicar inputs
de revisión nueva; cualquier cambio incompatible exige otra investigación.
Sin source explícito se vuelve a usar la copia inicial, declaradamente estática.
**Esto no captura ni autentica datos de mercado o saldos actuales.** V3.2 sigue
aceptando únicamente la ruta sintética explícita; una etiqueta real no la autentica.

Los errores estructurales anteriores a una solicitud válida producen un código
fijo y no archivan texto arbitrario sin identidad segura. Con una solicitud
válida, el diario conserva rechazos de identidad, bloqueos económicos y fallos.
Una salida inválida conserva su hash y diagnóstico; solo una propuesta validada
se conserva como datos tipados. No se guardan mensajes crudos de excepciones.

## Persistencia, presupuesto y máquina de estados

Ruta: `<root>/artifacts/research/core-v3-3/journal.sqlite3`. El root lo elige el
host confiable, no la solicitud. Se rechazan `.local`, symlinks/junctions y
redirecciones de la ruta fija. Los nombres cortos 8.3 de Windows se canonicalizan
sin confundirlos con un enlace. El host debe controlar permisos y estabilidad
del directorio: no se promete defensa frente a un atacante que controle todo
el filesystem durante una carrera de sustitución.

SQLite usa `synchronous=FULL`, conexión por worker, transacciones `BEGIN IMMEDIATE`
y timeout de bloqueo de 2 segundos. No hay conexiones compartidas entre threads.
Las tablas nuevas son `events` y `head`; no hay tablas mutables de candidatas o
contadores de presupuesto. Triggers impiden UPDATE/DELETE normal de eventos.

Cada evento contiene secuencia global, solicitud, estado, instante, payload
canónico, hash previo y hash propio. La cabecera se actualiza en la misma
transacción que el evento; permite detectar un sufijo borrado aunque la cadena
restante sea válida. Génesis contiene la política y un instante fijo de namespace
`1970-01-01`, que no representa la fecha real de creación ni evidencia financiera.

Toda operación pública comprueba bajo bloqueo la cadena, la cabecera, las
transiciones, la unicidad, los datos tipados, los vínculos y el presupuesto.
El replay verifica la admisión económica original y recalcula el postflight
antes de aceptar un registro terminal. Llamar directamente a persistencia no
permite registrar una candidata sin el gate ni falsificar un `allowed`.

| Estado anterior | Siguientes permitidos |
|---|---|
| RECEIVED | VALIDATION_REJECTED, ECONOMIC_BLOCKED, BUDGET_BLOCKED, BUDGET_RESERVED, INTERRUPTED |
| BUDGET_RESERVED | DESIGNING, FAILED por evidencia caducada antes de invocar, INTERRUPTED |
| DESIGNING | DESIGN_RECEIVED, FAILED, INTERRUPTED |
| DESIGN_RECEIVED | POSTFLIGHT_PENDING, FAILED, INTERRUPTED |
| POSTFLIGHT_PENDING | CANDIDATE_RECORDED, FAILED, INTERRUPTED |
| Cualquier terminal | Ninguna transición adicional |

Los instantes son explícitos y no retroceden dentro de una solicitud; la
secuencia global decide el orden entre solicitudes concurrentes. En cada fase
se valida el estado esperado. La clave y el ID deben referir la misma solicitud
completa; reutilizarlos con otro payload genera `IDEMPOTENCY_CONFLICT`.

El presupuesto global separa solicitudes, tokens e importe USD de investigación.
El capital, margen y pérdida de posición permanecen exclusivamente en V3.2.
Una reserva retiene una solicitud, el máximo de tokens de entrada+salida y el
importe máximo de la solicitud. Una respuesta conocida del simulador consume
una solicitud y cero tokens/importe API; libera los máximos reservados restantes.
El contrato ya representa estas dimensiones, pero no implementa facturación real.

| Situación | Recursos y recuperación |
|---|---|
| Preflight bloqueado o presupuesto insuficiente | Cero reserva; terminal durable. |
| Interrupción antes de invocar, aún BUDGET_RESERVED | `recover()` interrumpe y libera la reserva no usada. El CAS impide que el worker continúe desde ese estado. |
| DESIGNING sin respuesta conocida, o excepción del diseñador | Reserva retenida, incluso si el fallo es terminal. No hay repetición automática ni liberación por timeout. |
| DESIGN_RECEIVED o POSTFLIGHT_PENDING | Uso simulado conocido: una solicitud consumida. Repetir `run()` devuelve el estado; no vuelve a diseñar. |
| Fallo al guardar la candidata final | Rollback deja POSTFLIGHT_PENDING. `finish()` explícito puede repetir el postflight y commit, sin llamar al diseñador. Si la evidencia venció, registra fallo. |
| Solicitud terminal | Reintento devuelve el resultado durable idéntico; no vuelve a consumir. |

El replay de un terminal es histórico: no refresca datos ni emite una aprobación
vigente. Una investigación nueva requiere otra identidad y evidencia actual.

`recover()` es una acción explícita del host tras detener/revisar el worker;
no detecta por sí solo si un proceso está vivo. Puede invalidar a un worker
todavía activo, que después fallará su transición y no registrará candidata.
No hay resolución automática de reservas inciertas ni permisos para aumentar
el presupuesto. Un cambio de política del mismo diario se rechaza.

Límites: 256 solicitudes distintas por diario, política de hasta 256 llamadas,
máximo 2049 eventos, payload JSON de hasta 131072 bytes y respuesta de diseñador
de hasta 32768 bytes. La reserva por solicitud limita cada lado a un millón de
tokens; el presupuesto global tiene un máximo de mil millones. Los límites
económicos siguen siendo los de V3.2. El replay usa memoria y trabajo acotados
pero crece con el historial y sus evaluaciones: este slice es para experimentos
pequeños, no un store operativo de alta frecuencia.

La cadena y cabecera detectan contenido alterado, secuencias incorrectas,
transiciones inválidas, eventos incompletos y pérdida de sufijos respecto a la
cabecera disponible. No detectan rollback del archivo completo a una copia
anterior válida ni reescritura coordinada de eventos y anclas por su propietario.
Un anclaje externo confiable sería otra capacidad. Las pruebas inyectan errores
SQLite; no certifican un corte físico de energía ni la durabilidad del hardware.

## Ejemplos reproducibles

Desde la raíz, definir `PYTHONPATH=python` y ejecutar con
`.venv/Scripts/python.exe -B`. Los helpers siguientes son fixtures sintéticos
de pruebas, no configuración operativa:

```python
import sys, tempfile
sys.path.insert(0, 'python/tests')
from dataclasses import replace
from decimal import Decimal
from test_core_v3_research_contracts import AT, budget, request
from test_core_v3_economic_contracts import sealed
from trading_agent.core_v3.contracts import Money
from trading_agent.core_v3.research_designer import SimulatedDesigner
from trading_agent.core_v3.research_journal import ResearchJournal
from trading_agent.core_v3.research_runner import run

req = request()
with tempfile.TemporaryDirectory() as root, ResearchJournal(root, budget(requests=1)) as journal:
    result = run(journal, req, SimulatedDesigner(), clock=lambda: AT)
    print(result.state.value, result.receipt.proposal.scenario.quantity.amount,
          result.postflight.evaluation.net_target.amount)
    # CANDIDATE_RECORDED 26 0.0322; una solicitud consumida, cero costo API.

costs = sealed(replace(req.inputs.context.costs, opening_minimum=Money(Decimal('100'), 'USD')))
expensive = replace(req, inputs=replace(req.inputs, context=replace(req.inputs.context, costs=costs)))
with tempfile.TemporaryDirectory() as root, ResearchJournal(root, budget(requests=1)) as journal:
    rejected = run(journal, expensive, SimulatedDesigner(), clock=lambda: AT)
    print(rejected.state.value, rejected.preflight.status.value)
    # ECONOMIC_BLOCKED INFEASIBLE; cero reserva y cero consumo.

with tempfile.TemporaryDirectory() as root:
    with ResearchJournal(root, budget(requests=1)) as journal:
        journal.receive(req, now=AT)
        journal.admit(req.request_id, now=AT)
        journal.start(req.request_id, now=AT)
        # Cierre en DESIGNING: no podemos afirmar si hubo respuesta.
    with ResearchJournal(root, budget(requests=1)) as journal:
        pending = run(journal, req, SimulatedDesigner(), clock=lambda: AT)
        interrupted = journal.recover(req.request_id, now=AT)
        print(pending.state.value, interrupted.state.value,
              interrupted.charge.reserved_requests, journal.budget_status().remaining_requests)
        # DESIGNING INTERRUPTED 1 0; no se repite el diseñador.
```

Ejemplos ejecutados con cutoff fijo `2026-10-18T12:00:00Z`. Hash del resultado
exitoso: `dc99d368c22470b9a34758c5cafa11cfd631206588aa2c859e6c5747e5b9f03c`.
Hash final de su cadena: `629901ce0ecb5230377a4cf89f6b8ae51ca2c5fc105968ed47f8401246fe8d78`.
El neto positivo corresponde al escenario y supuestos; no es expectativa
estadística ni P&L observado. En todos los casos se conserva NO_TRADE.

## Verificación, cambios Git y límites

Se aplicaron Senior Software Engineer y Graphify antes de editar. Se consultó
el grafo existente de 424 nodos/1039 aristas, con vocabulario
`research strategy capital`, presupuesto 1100. La consulta inicial incluyó
`journal`; se retiró al comprobar que no existe en el vocabulario. La consulta
corregida encontró 94 nodos y mostró 37. El grafo es anterior
a V3: se contrastaron sus referencias a capital y
estrategias con las fuentes actuales, y se examinó el patrón de diario/runner
Forex sin importarlo ni reutilizar su persistencia. No se reconstruyó el grafo.
El costo de extracción declarado en ese grafo no mide tokens de esta sesión.

| Grupo | Pruebas finales |
|---|---:|
| Contratos y diseñador V3.3 | 4 |
| Diario, concurrencia y recuperación SQLite V3.3 | 10 |
| Orquestador y fallos V3.3 | 15 |
| Aislamiento y ciclos concurrentes V3.3 | 3 |
| **Nuevas V3.3** | **32** |
| V3.2 | 38 |
| V3.1 | 36 |
| Forex Fase 1 | 28 |
| Contratos AI históricos | 16 |
| **Total** | **150** |

La verificación final instala un audit hook que deniega conexiones/resolución
de sockets, bind, subprocesos y apertura/listado de la `.local` real. Una prueba
adicional permite conexiones SQLite únicamente dentro de su directorio temporal.
Se comprueban ambos instrumentos y direcciones, bloqueos económicos, presupuestos,
dos workers, reinicios, fallos antes/después de reserva, datos falsificados,
mutaciones de geometría/permisos, caducidad, revisiones de contexto/política,
alteración de eventos, bloqueo de DB y rollback de persistencia.

La revisión interna comprobó límites de confianza, binds, transiciones, errores
fijos y dependencias. Invertir temporalmente la guardia del tipo de diseñador
hizo fallar la prueba contra subclases/plugins; se restauraron los bytes originales
antes de la ejecución final. Esto es sensibilidad puntual, no mutation testing
exhaustivo ni auditoría independiente. Se verificó con Python 3.13 en Windows;
`Path.is_junction()` requiere Python 3.12 o posterior. No se ejecutaron .NET,
API, TWS, modelos, backtests, broker ni facturación.

Comparación de alcance: cuatro módulos nuevos, cuatro archivos de pruebas y este
informe. Solo cambia una prueba anterior, `test_core_v3_legacy_import.py`, para
añadir a su allowlist `research_contracts`, `research_designer`, `research_journal`,
`economics`, `contextlib`, `pathlib` y `sqlite3`; conserva todas sus aserciones.
Los módulos V3.1/V3.2, Forex, R20, Kronos, frontend, transportes, configuración y
.NET permanecen intactos. No se incorporan el informe Fase 0 ni el PDF ajenos.
La comparación reproducible es `git diff --name-status 77daf8e..HEAD`.
No hay push, merge, migraciones operativas ni lectura de secretos.

Para rollback de código se pueden revertir los commits específicos tras revisar
el árbol. El diario creado por el host se conserva como evidencia y no se borra
al revertir; tampoco se habilita un consumidor antiguo sobre esos datos. Este
incremento solo creó diarios en directorios temporales de prueba.

La propuesta es una hipótesis de escenario fija, sin AST de estrategia, biblioteca
de reglas, selección de régimen, backtest ni calibración. Las fuentes y capacidades
de cartera siguen siendo supuestos del productor. El proceso Python del host es
confiable: las barreras de tipos no son un sandbox frente a quien pueda modificar
el código o monkeypatchar clases. Los hooks de prueba tampoco certifican un
aislamiento de producción. Una futura integración real exige nuevos puertos,
presupuestos de usage verificado y su autorización separada; no se retira la
barrera del simulador de este runner.

## Propuesta para V3.4

Definir un contrato declarativo cerrado de estrategia y un diseñador simulado
que produzca reglas ligadas de forma demostrable a la geometría económica, con
fixtures multiinstrumento y validación causal de las entradas. Mantener separados
el registro de hipótesis y la evidencia de resultados. El backtest y cualquier
transporte real requerirán sus incrementos y aceptación propios.
**V3.4 no se implementó ni se habilitaron Paper/Live.**
