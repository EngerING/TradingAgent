# Core V3.5 — catálogo durable de investigación

Base verificada: `7d66d91`, rama `codex/core-v3-5-strategy-catalog`.
Alcance autorizado: OFFLINE. Todos los paths existentes se conservan sin editar.

## Diseño presentado antes de programar

Se añade el subpaquete optativo `core_v3/strategy_catalog/`, sin activación ni
ediciones en V3.1–V3.4. Las pruebas nuevas inspeccionarán su superficie de imports
y ejecución; no se amplía ni debilita ninguna prueba anterior.

| Archivo nuevo | Responsabilidad |
|---|---|
| `strategy_catalog/__init__.py` | Namespace sin efectos de arranque. |
| `strategy_catalog/contracts.py` | Comandos, versiones, vínculos, validaciones y deduplicación semántica acotada. |
| `strategy_catalog/research_link.py` | Lectura verificada V3.3; estado, presupuesto, prefijo durable y recálculo V3.4/V3.2. |
| `strategy_catalog/store.py` | Diario SQLite separado con cadena/cabecera, máquina de estados y CAS de versión. |
| `strategy_catalog/service.py` | Protocolo de registro/reconciliación, invalidación y diagnóstico causal V3.4. |
| `python/tests/test_core_v35_*.py` | Contratos, persistencia, fallos, concurrencia y seguridad offline. |
| `python/tests/core_v35_offline_check.py` | Ejecutor nuevo que reutiliza las barreras anteriores y añade V3.5. |

Dos SQLite independientes no proporcionan commit conjunto. El catálogo persiste
REQUESTED, PREPARED, RECORDED y VALIDATED por fases. Cada paso comprueba estado
esperado. El origen se liga a hashes de eventos y prefijo: nuevas investigaciones
pueden añadir eventos sin alterar ese prefijo. Una caída no repite proveedores;
la reconciliación es explícita y revalida vigencia, origen y economía. Un registro
RECORDED no es una validación vigente. Cambios incompatibles añaden INVALIDATED;
las versiones y los resultados previos no se borran.

La identidad de catálogo y el ordinal de versión son distintos de la identidad
V3.4. Una revisión debe señalar el hash del padre vigente. La deduplicación
normaliza únicamente equivalencias declaradas del vocabulario cerrado; conserva
instrumento, timeframe, dirección, cantidades, precios, horizonte e indicadores.
Una coincidencia semántica no traslada autorizaciones ni actualiza evidencia.

El catálogo solo lee el diario V3.3 suministrado por el host. No invoca diseñadores,
`run()`, reservas ni settlement. Conserva la solicitud, resultado, política y cargo
de investigación como evidencia vinculada. Los hashes no autentican productores.
No hay atomicidad frente a un atacante que reescriba ambos archivos y sus anclas.

Concurrencia: BEGIN IMMEDIATE, conexiones por worker, timeout acotado y control
del estado/versión dentro del commit. No se mantiene el lock del catálogo al
leer el origen. El root de composición es confiable; IDs nunca generan rutas.

Todas las salidas conservan NO_TRADE y autoridad, Paper, Live y estadística en
false. No hay transporte, backtest, datos reales, configuración ni frontend.
Los documentos previos ajenos y `.local` quedan fuera de este incremento.

## Entrega e interfaces

Implementado como biblioteca optativa. No se registra en la API ni se altera
ninguna entrada anterior. `CatalogRequest` fija operación, idempotencia, acción
REGISTER/REVALIDATE, identidad de catálogo, ordinal, padre, origen lógico,
solicitud V3.3, timeframe esperado y estrategia V3.4 completa.

`SourceProof` contiene la solicitud y resultado V3.3, política de presupuesto,
secuencias/hashes del evento recibido y terminal y el prefijo observado. Solo
un resultado CANDIDATE_RECORDED con una solicitud consumida y ninguna reservada
puede respaldar el registro. La historia V3.3 se obtiene mediante `history()`:
esa API valida la cadena, máquina de estados, cabecera, presupuesto y economía.
No se acepta un ResearchResult suministrado por el cliente como aprobación.

`CatalogVersion` conserva el comando inicial, estrategia, prueba de origen,
hash semántico e instante de registro. `record_sha256` identifica sus bytes
canónicos; `CatalogRef` liga identidad/ordinal a ese hash. La versión es inmutable.
`CatalogCheck` registra los inputs usados, corte, motivo y postflight recalculado.
`CatalogOutcome` describe el estado de una operación, referencia y comprobación.

Los contratos usan namespace `trading.core_v3.catalog.*`, schema_version=1,
dataclasses frozen/slots y los validadores JSON/canonicalización V3 anteriores.
No se añaden dependencias ni se modifica el JSON Schema V3.4. Los validadores
Python cerrados y el replay semántico son obligatorios: un hash o deserialización
aislada nunca acreditan al productor ni autorizan un registro.

API de composición:

```python
with Catalog(root_controlado_por_el_host) as catalog:
    outcome = catalog.register(command, research_journal, current_inputs, now=cutoff)
    pending = catalog.outcome(command.operation_id)       # resultado histórico
    version = catalog.version(command.catalog_id, 1)      # contenido histórico
    recovered = catalog.reconcile(command.operation_id, research_journal,
                                  current_inputs, now=new_cutoff)
```

`research_journal` debe ser exactamente el tipo V3.3 auditado. El catálogo no
abre un origen indicado en JSON: el host proporciona el objeto y su source_id
lógico. Una réplica con idéntico contenido no se distingue por un path privado;
el vínculo es de contenido y origen declarado, no autenticación física de archivo.

El root es una decisión confiable de composición. La ruta es fija:
`<root>/artifacts/research/core-v3-5/strategy-catalog.sqlite3`. Se rechazan rutas
hacia `.local`, symlinks/junctions y redirecciones detectables, admitiendo aliases
8.3 de Windows. No se promete eliminar carreras de sustitución si un atacante
controla el filesystem. Se verificó con Python 3.13; is_junction requiere 3.12+.

## Protocolo de dos diarios y recuperación

El catálogo solo tiene `events` y `head`. INSERT y avance de cabecera son
atómicos en su SQLite, con synchronous=FULL y BEGIN IMMEDIATE. UPDATE/DELETE
normal de eventos se bloquean mediante triggers. Los eventos incluyen secuencia,
operación, estado, corte, payload canónico, hash previo y hash propio. El génesis
usa un marcador fijo 1970-01-01, no una fecha de observación financiera.

Cada lectura reproduce la historia y comprueba hashes, cabecera, estados,
vínculos, decisiones de deduplicación/versionado y economía al corte registrado.
La cabecera detecta pérdida de sufijos respecto al ancla disponible. No hay
tablas mutables que puedan aprobar una versión eludiendo los eventos.

| Fase | Commit y significado |
|---|---|
| REQUESTED | Intento durable e identidad fijada antes de consultar el origen. |
| PREPARED | Prueba V3.3 fijada y comprobación económica/de vínculos registrada. Todavía no hay versión nueva. |
| RECORDED | Versión inmutable o referencia de revalidación guardada; sigue pendiente de reconciliación. |
| VALIDATED | Origen leído nuevamente después del commit independiente y economía comprobada para esos inputs/corte. |
| RECOVERY_REQUIRED | Origen ausente, pendiente o no verificable. Conserva la fase alcanzada y bloquea la validación. |
| INVALIDATED | Contexto, vigencia, geometría, metadata o prefijo incompatible. Conserva registros anteriores. |
| REJECTED | Conflicto de identidad/versión, padre, familia o investigación terminal no apta. |
| DUPLICATE | Referencia al contenido ya conservado; no crea versión ni renueva su vigencia. |

Una operación terminal no cambia. REVALIDATE utiliza una operación y clave
nuevas para añadir validación o invalidación, ligadas a la versión existente.
Una revalidación no puede predatar el registro referenciado; una revisión no
puede predatar al padre. Dentro de cada operación los cortes tampoco retroceden.

`register()` repetido devuelve el estado durable; si hay una prueba fijada,
verifica nuevamente su prefijo antes de responder. No continúa un pendiente
automáticamente. `reconcile()` explícito reanuda desde la fase durable, con
inputs y corte explícitos. Ninguno de estos caminos llama diseñadores o muta
presupuesto. Un terminal en caché es histórico, no una aprobación para el reloj
actual; una comprobación nueva exige un nuevo comando REVALIDATE.

Puntos de recuperación probados: caída tras REQUESTED/PREPARED, fallo SQLite
antes del primer evento o al validar, commit confirmado con respuesta perdida,
origen no disponible después de RECORDED y caducidad durante la interrupción.
Un sufijo faltante o una fuente sustituida bloquean el vínculo; una fuente
corrupta queda no verificable. No hay fallback a otra fuente ni aprobación previa.

Concurrencia: conexión por worker y timeout SQLite de 2 segundos. La versión,
padre y decisión semántica se resuelven bajo el lock del catálogo. Cada avance
comprueba la secuencia previa de su propia operación, sin invalidarse por un
append legítimo de otra operación. Dos revisiones incompatibles del mismo
ordinal tienen un único ganador. Un conflicto de worker puede devolver el
estado durable o un error acotado; nunca produce repetición de proveedores.

No se toman ambos locks a la vez. La fuente puede añadir eventos sin alterar
el prefijo fijado. Entre dos archivos siempre existe una ventana de observación;
no se promete commit distribuido ni protección ante reescritura coordinada por
quien controle ambos. Las validaciones son de investigación al corte explícito,
no capturas autenticadas de mercado ni permisos operativos instantáneos.

## Versiones y deduplicación

La identidad del catálogo es distinta de strategy_id V3.4. El primer ordinal
es 1, sin padre; cada revisión señala el hash exacto del último ordinal. La
familia conserva instrumento/especificación, timeframe y dirección. Otra
familia requiere otra identidad. Reutilizar el mismo ordinal con otros bytes
produce VERSION_CONTENT_CONFLICT; la misma clave de idempotencia con otro
comando produce CATALOG_IDEMPOTENCY_CONFLICT.

La huella semántica mantiene instrumento/especificación, timeframe, dirección,
cantidad/unidad, entrada/SL/TP/monedas, horizonte, máximo de barras e indicadores.
Excluye strategy_id, request_sha256, hypothesis_id y hashes de contexto/política,
que permanecen íntegros en la procedencia. Ordena y elimina condiciones ALL
equivalentes; LT(A,B) se normaliza como GT(B,A), y CROSS_BELOW(A,B) como
CROSS_ABOVE(B,A). No aplica álgebra general ni afirma equivalencia estadística.

Un clon bajo otra identidad devuelve DUPLICATE con referencia al original.
Una revisión nominal sin cambio de comportamiento ni procedencia también se
detecta como duplicada. Una revisión explícita de la misma familia puede
conservar comportamiento y renovar su vínculo a una investigación nueva y
completa; conserva el hash semántico y una nueva versión de contenido. No
traslada automáticamente la validación del padre ni consume presupuesto adicional.

Los límites son 128 operaciones distintas por archivo, 2049 eventos, ordinales
1–1024 y documentos canónicos de hasta 131072 bytes. Los payloads combinados
también deben caber en ese límite. El agotamiento o un documento excesivo falla
cerrado, sin descartar historia. El replay incluye validaciones económicas y
su costo crece con el historial: no se certifica rendimiento de alta frecuencia.

## Señales causales y ausencia de autoridad

`diagnose()` requiere un comando REVALIDATE nuevo o verificado al mismo corte,
comprueba el origen y llama al evaluador causal V3.4 existente. Devuelve su
SignalResult; no almacena velas, no es un backtest ni un journal de señales.
La validación del catálogo describe identidad y economía, no que las reglas
sean verdaderas. Un fallo del diagnóstico no transforma una señal en orden.

CatalogOutcome fija NO_TRADE y execution_authority, paper_execution_eligible,
live_enabled y statistically_validated en false. Las estrategias conservan sus
flags V3.4; los postflights conservan los V3.2. No existe ruta a RiskEngine,
ExecutionGuard, cuentas, sesiones, credenciales o transportes. La única ruta
económica resoluble sigue siendo la sintética explícita.

## Ejemplos ejecutados

Con PYTHONPATH=python, los helpers de pruebas `command`, `complete` y `budget`
permiten reproducir los casos en un TemporaryDirectory. Son fixtures sintéticos,
no configuración operativa. El corte fijo es 2026-10-18T12:00:00Z.

```python
import sys, tempfile
sys.path.insert(0, 'python/tests')
from dataclasses import replace
from test_core_v35_contracts import AT, budget, command
from test_core_v35_catalog import complete
from trading_agent.core_v3.research_journal import ResearchJournal
from trading_agent.core_v3.strategy_catalog.service import Catalog

with tempfile.TemporaryDirectory() as root, ResearchJournal(root, budget()) as source:
    req = complete(source)  # investigación V3.3 explícita, anterior al registro
    before = source.history()
    with Catalog(root) as catalog:
        cmd = command(req=req)
        registered = catalog.register(cmd, source, req.inputs, now=AT)
        clone = command(name='clone', catalog_id='clone-id', req=req,
                        strategy=replace(cmd.strategy, strategy_id='renamed'))
        duplicate = catalog.register(clone, source, req.inputs, now=AT)
        print(registered.state.value, duplicate.state.value)
        assert before == source.history()
```

| Caso ejecutado | Resultado |
|---|---|
| Alta EUR/USD LONG | VALIDATED, ordinal 1. |
| Renombrado bajo otra identidad | DUPLICATE / SEMANTIC_DUPLICATE, referencia a catalog-1. |
| Mismo ordinal con reglas distintas | REJECTED / VERSION_CONTENT_CONFLICT. |
| Interrupción inyectada antes de record | PREPARED durable; reinicio y reconcile explícito → VALIDATED, sin repetir investigación. |

En los cuatro casos se conservó exactamente el historial V3.3 y solo una
solicitud previamente consumida. La recuperación de la variante con reglas
nuevas dejó dos identidades versionadas, sin duplicar ninguna.

Hash de la primera versión:
`6d0cbee0af321e342a6e11470b454de7d9889c322c45c998be56212c7265fc49`.
Huella semántica:
`42d3f6c0662be92ce4b4746fe93691ff6a7be5e483f0b512605e9afd35d5faa5`.
Los casos de rechazo e interrupción completos están en las pruebas nuevas
test_core_v35_catalog.py y test_core_v35_recovery.py. La inyección usa únicamente
SQLite temporal o mocks de los nuevos componentes; no altera diarios privados.

## Verificación y revisión

Skills obligatorias aplicadas: Senior Software Engineer y Graphify, incluyendo
la referencia de sistemas de trading. El grafo histórico tenía 424 nodos y
1039 aristas. Se consultó vocabulario real `strategy research store`, presupuesto
1200: 98 nodos encontrados, 41 mostrados. No incluía V3: se contrastaron fuentes
actuales V3.3/V3.4 y las pruebas de aislamiento. No se reconstruyó el grafo;
su costo de extracción no representa el uso de tokens de esta sesión.

Ejecutor reproducible, sin modificar el anterior:

```powershell
.venv/Scripts/python.exe -B python/tests/core_v35_offline_check.py
```

| Suite | Pruebas pasadas |
|---|---:|
| V3.5 contratos/semántica | 2 |
| V3.5 vínculo y catálogo | 11 |
| V3.5 recuperación/integridad/concurrencia | 10 |
| V3.5 seguridad y permisos | 6 |
| **Nuevas V3.5** | **29** |
| V3.4 | 37 |
| V3.3 | 32 |
| V3.2 | 38 |
| V3.1 | 36 |
| Forex Fase 1 | 28 |
| Contratos AI históricos | 16 |
| **Total final** | **216/216** |

Ejecución final: 129.643 s, cero fallos y OFFLINE_BARRIER_VIOLATIONS: 0.
La barrera anterior deniega sockets, procesos externos, apertura/listado de
`.local` y conexiones SQLite fuera del temporal del sistema canonicalizado.
Las pruebas nuevas inspeccionan recursivamente todo el subpaquete con allowlist
cerrada y prohíben ejecución/imports dinámicos. También bloquean en runtime
los diseñadores y métodos V3.3 de reserva/consumo durante el registro.

La primera ejecución conjunta pasó 215 pruebas. La revisión temporal posterior
reprodujo en rojo una validación anterior al alta referenciada; se corrigió
únicamente en V3.5 y se volvió a ejecutar toda la suite. Se comprobó sensibilidad
invirtiendo temporalmente la normalización de comparaciones: la prueba semántica
falló y se restauraron los bytes originales antes de verificar todo. Es revisión
interna y una mutación puntual, no auditoría independiente ni certificación de
durabilidad del hardware. No se ejecutaron API, .NET, modelos, broker ni backtest.

## Git y preservación

Commits funcionales: 931fd63 (contratos/semántica), 0660a9c (persistencia y
protocolo), 45184c0 (seguridad, recuperación y corrección temporal). El commit
posterior de documentación contiene este cierre. Rama: codex/core-v3-5-strategy-catalog.

`git diff --name-status 7d66d91..HEAD` al cierre solo contiene adiciones:

```text
A docs/architecture/core-v3-5-strategy-catalog.md
A python/tests/core_v35_offline_check.py
A python/tests/test_core_v35_catalog.py
A python/tests/test_core_v35_contracts.py
A python/tests/test_core_v35_recovery.py
A python/tests/test_core_v35_security.py
A python/trading_agent/core_v3/strategy_catalog/__init__.py
A python/trading_agent/core_v3/strategy_catalog/contracts.py
A python/trading_agent/core_v3/strategy_catalog/research_link.py
A python/trading_agent/core_v3/strategy_catalog/service.py
A python/trading_agent/core_v3/strategy_catalog/store.py
```

`git status --short` al cierre conserva exclusivamente los dos documentos ajenos:

```text
?? docs/architecture/core-v3-phase0-audit.md
?? docs/manual/TradingAgent_Manual_Tecnico_Integral.pdf
```

No se modificaron paths versionados de la base, ni siquiera pruebas anteriores.
No hubo autorización adicional necesaria por ediciones fuera de alcance. No se
leyeron secretos ni `.local`, ni se hizo push, merge o despliegue. Los diarios
V3.5 de verificación fueron temporales; no se creó uno persistente en el proyecto.

Rollback: revertir commits concretos tras revisar el árbol. Conservar cualquier
diario creado después por el host para inspección; no borrarlo ni conectarlo a
un consumidor anterior para ocultar cambios. Los hashes/cabeceras no detectan
rollback completo a copias válidas o reescritura coordinada de ambas bases por
su propietario. Faltan anclas externas, backup operativo y pruebas de disaster
recovery. Python es un host confiable: no se promete sandbox frente a monkeypatch
o código modificado, ni autenticidad de fuentes autodeclaradas.

## Propuesta siguiente, sin implementación

V3.6 podría especificar e implementar un backtest por eventos acotado y
exclusivamente sintético: posiciones, fills, costos, gaps, precedencia SL/TP y
horizonte, consumiendo una versión inmutable del catálogo. No implicaría todavía
ventaja estadística, datos reales ni ejecución. Requiere alcance y aprobación
independientes. **V3.6 no se inició; Paper/Live no se habilitaron.**

## Inventario obligatorio del backend

### IMPLEMENTADO Y VERIFICADO — alcance offline de estas suites

| Componente | Capacidad comprobada | Límite |
|---|---|---|
| Core V3.1 | Contratos financieros multiinstrumento, hashes e importación histórica. | No autentica mercado ni concede autoridad. |
| Core V3.2 | Búsqueda económica, costos, FX, margen, riesgo y postflight LONG/SHORT. | Supuestos sintéticos; no expectativa ni ejecución. |
| Core V3.3 | Investigación simulada, presupuesto, diario, idempotencia y recuperación. | Sin modelos reales ni cartera operativa. |
| Core V3.4 | Estrategias declarativas y diagnóstico causal de señales. | Sin simulación de posiciones o backtest completo. |
| Core V3.5 | Catálogo durable, revisiones, deduplicación, vínculo V3.3, invalidación y reconciliación. | Investigación al corte explícito; no habilita estrategias. |

### EXISTENTE PERO PENDIENTE DE INTEGRACIÓN O RECERTIFICACIÓN

| Componentes | Estado y alcance verificado aquí |
|---|---|
| Python histórico, Forex Fase 1 e investigador AI | Se preservan; 28 pruebas Forex y 16 contratos AI pasaron. Esto no certifica sus transports o flujos operativos. |
| .NET, riesgo/stores/API e IBKR histórico | Existen según arquitectura y fuentes previas. Sin integración operacional V3 ni recertificación en esta entrega. |
| R20 y Kronos históricos | Se conservan. No se ejecutaron bases, inferencias, observadores ni permisos; su existencia no implica capacidad V3 activa. |

### PENDIENTE PARA COMPLETAR EL BACKEND INTEGRADO

| Capacidad | Qué falta |
|---|---|
| Datos reales y procedencia autenticada | Ingesta, datasets versionados, calidad/calendarios y productor confiable. |
| Backtesting por eventos | Posiciones/fills, costos, gaps, SL/TP/horizonte y reproducción causal. |
| Validación estadística | OOS/holdout, incertidumbre, selección múltiple y criterios fijados antes de medir. |
| Régimen de mercado | Clasificación causal versionada y evidencia de calidad. |
| Selección/clasificación de estrategias | Biblioteca comparable, ranking y NO_TRADE; deduplicar no equivale a seleccionar. |
| Integración controlada de IA | Puertos autorizados, uso/costos verificados, presupuestos y recuperación de respuestas inciertas. |
| Cartera y riesgo agregado | Autoridad única, capital compartido, reservas atómicas y exposición multiinstrumento. |
| Integración operacional Python/.NET | Contratos comunes, persistencia/roles y límites de autoridad verificados entre procesos. |
| Paper Trading | Conciliación, SDK simulado, guardias y aprobación posterior específica. |
| Live Trading | Evidencia y autorización humana independientes; ningún avance offline la concede. |
| Observabilidad, recuperación y despliegue | Operación end-to-end, métricas, backups/anclas, recuperación del broker, permisos y rollout/rollback. La recuperación local de catálogo ya probada no completa esta capacidad. |

Este inventario describe límites y trabajo de integración/verificación; no
ordena reescribir componentes históricos ni declara completo el backend operativo.
