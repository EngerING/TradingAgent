# Core V3.4 — estrategias declarativas y señales causales offline

Fecha: 2026-10-18. Base comprobada: `1f20567c2ad4b85ca99bf625a8045f1767505973`,
rama original `codex/core-v3-3-research-orchestrator`. Rama de entrega:
`codex/core-v3-4-declarative-strategies`. Alcance autorizado: solo investigación
sintética offline, sin backtest completo, proveedores ni órdenes.

## Diseño presentado antes de editar

Crear un subpaquete independiente `python/trading_agent/core_v3/strategy_v34/`,
un esquema cerrado, pruebas nuevas y este informe. Mantener sin cambios todos
los archivos presentes en la base, incluidas las pruebas anteriores. Se eligió
el subpaquete porque la prueba V3.1 de imports inspecciona los módulos directos
de `core_v3/`; no se amplió su allowlist. La nueva prueba de seguridad inspecciona
todos los módulos del subpaquete V3.4.

Skills aplicadas: `senior-software-engineer`, `graphify`, flujo Git, cambios
mínimos, pruebas primero, implementación incremental, depuración, revisión de
código y seguridad. Se leyó la referencia local de sistemas de trading.

El grafo existente tenía 424 nodos y no incluía Core V3. Se consultaron sus
lecciones y el vocabulario real `research economic strategy signal instrument
timeframes scenario validator offline test`, con BFS y presupuesto 2500.
La consulta encontró 162 nodos, mostrando 85: orientación histórica, no evidencia
de implementación V3.4. Se corroboraron contratos, economía, diseñador, pruebas
y arquitectura V3.1/V3.2/V3.3 directamente en sus fuentes. No se reconstruyó
el grafo ni se ejecutaron modelos para extraerlo. Su costo de extracción no
mide el consumo de esta sesión.

## Archivos y efectos

| Archivo nuevo | Función |
|---|---|
| `strategy_v34/__init__.py` | Paquete optativo sin activación de servicios. |
| `strategy_v34/contracts.py` | Timeframes, indicadores, operandos, reglas y estrategia inmutables. |
| `strategy_v34/designer.py` | Diseñador simulado fijo y comparación exacta de su salida. |
| `strategy_v34/validation.py` | Identidad, escenario y recálculo de preflight/postflight V3.2. |
| `strategy_v34/signals.py` | Velas sintéticas cerradas y diagnóstico de reglas al corte. |
| `contracts/core-v3/strategy-v34/v1/strategy.schema.json` | JSON Schema Draft 2020-12 cerrado, tres raíces y diez definiciones. |
| `python/tests/test_core_v34_contracts.py` | Vocabulario, números, versiones, inmutabilidad y JSON hostil. |
| `python/tests/test_core_v34_design.py` | Diseñador, vínculos económicos y variantes multiinstrumento. |
| `python/tests/test_core_v34_signals.py` | Causalidad, cruces, disponibilidad, límites y pureza. |
| `python/tests/test_core_v34_security.py` | Abuso de fronteras, imports y correspondencia de wire/esquema. |
| `python/tests/core_v34_offline_check.py` | Ejecutor reproducible con barreras offline. |
| Este informe | Contratos, verificación, límites e inventario de backend. |

V3.4 importa tipos y funciones puras anteriores, sin modificar V3.1/V3.2/V3.3.
No escribe en el diario V3.3, no registra automáticamente candidatas ni añade
persistencia. No hay cambios en legados, Forex, frontend, R20, .NET, Kronos,
adaptadores IBKR/OpenAI o configuración. Los dos documentos ajenos permanecen
sin seguimiento y no se incluyen en ningún commit. Las pruebas no usan `.local`.
No hay dependencias nuevas, migraciones, push, merge ni despliegue.

## Contrato declarativo cerrado

Namespace de wire: `trading.core_v3.strategy_v34.*`, `schema_version=1`.
Las raíces del esquema son `Strategy`, `CandleSeries` y `SignalResult`.
Se reutilizan `InstrumentIdentity`, `Scenario`, `Price` y `Quantity` originales.
Todos los registros son dataclasses frozen/slots; las colecciones son tuplas.
El JSON estricto y la canonicalización V3.1 rechazan duplicados, Unicode inválido,
no finitos, campos extra, versiones desconocidas, profundidad superior a 32 y
documentos superiores a 131072 bytes. Los errores de contrato son códigos fijos.

Vocabulario admitido:

- Timeframes: `M1` (60 s), `M5` (300 s), `H1` (3600 s).
- `CLOSE`: período exactamente 1. `SMA`: período entre 2 y 200.
- Retardo de cada operando: entero entre 0 y 32; nunca negativo.
- Operadores: `GT`, `LT`, `CROSS_ABOVE`, `CROSS_BELOW`.
- Entre 1 y 8 reglas distintas por conjunto de entrada/salida; conjunción `ALL`.

No existen campos de código, expresiones libres, funciones, importaciones,
plugins, paths, prompts o nombres de proveedor. Los tipos primitivos son exactos:
un booleano no sustituye un entero. Los identificadores están acotados.
El validador Python aplica además invariantes entre campos y comprobaciones
económicas que JSON Schema no expresa. Aceptar JSON Schema nunca es aprobación.

`Strategy` fija el hash completo de `ResearchRequest`, la identidad y hash de
especificación del instrumento, timeframe y el `Scenario` completo. La identidad
incluye versión, no solo símbolo. Cantidad/unidad, dirección LONG/SHORT, entrada,
SL, TP, horizonte y hashes de contexto/política deben coincidir exactamente con
el testigo que se vuelve a calcular. Se comprueban ticks, mínimos y pasos.
`max_holding_bars * segundos_timeframe == horizon_hours * 3600`; máximo 43200 barras.

`validate()` recalcula el preflight y postflight V3.2 al instante explícito.
Un contexto o política nuevos, evidencia vencida, economía desconocida o geometría
alterada bloquean el proceso. Una supuesta aprobación previa no evita ese recálculo.
El retorno es un `EconomicResult` POSTFLIGHT existente, con autoridad deshabilitada.

## Diseñador y procedencia

`design(request, timeframe, SimulatedStrategyDesigner(), now=...)` produce una
estrategia fija y reproducible: CLOSE cruza SMA(3) a favor de la dirección para
entrada, y en sentido inverso para salida. La geometría se copia del testigo
económico recalculado; no se inventa ni redimensiona. La identidad determinista
incluye solicitud, timeframe y versión `SIMULATED_V34_V1` del diseñador.

Solo se acepta el tipo exacto `SimulatedStrategyDesigner`, sin subclases ni
callables. Su fixture opcional se limita a 32768 bytes, se parsea como datos y
debe coincidir con toda la propuesta esperada. Esto permite probar ataques sin
añadir un transporte ni ejecutar texto. El diseñador no tiene uso API, tokens
facturados ni costo real. V3.4 no cambia el presupuesto ni el diario V3.3.

Una estrategia construida explícitamente por el host puede tener otras reglas
del vocabulario y pasar `validate()` si conserva todos los vínculos. Esa validación
no acredita que proceda del diseñador simulado ni que sea estadísticamente buena.

## Causalidad y semántica de señales

Cada `Candle` contiene OHLC tipado, `closed_at` y `available_at`, con disponibilidad
igual o posterior al cierre. La serie solo acepta `SYNTHETIC`; una etiqueta de
captura real se rechaza. Entre 1 y 256 barras consecutivas, alineadas a UTC,
sin duplicados ni huecos y con disponibilidad no decreciente. Esto es una ventana
de prueba, no una representación de sesiones reales o calendarios de mercado.
También rige el límite global de bytes al serializar o calcular hashes.

Al evaluar un corte, se usan únicamente barras cerradas Y disponibles hasta ese
instante. El prefijo debe terminar a menos de un timeframe del corte. Una barra
reciente todavía no publicada no se sustituye con datos futuros. Las barras
futuras estructuralmente válidas no participan en indicadores, diagnóstico ni
hash de prefijo; su adición no modifica el resultado anterior. Un documento
estructuralmente malformado sigue siendo rechazado en la frontera.

SMA usa la media simple de cierres de una ventana completa que termina en
`índice_actual - lag`. Para evitar redondeos de medias periódicas, se comparan
numeradores/denominadores mediante productos cruzados bajo precisión local 160,
independientemente de la precisión decimal ambiental. Un cruce ascendente exige
comparación previa <= 0 y actual > 0; el descendente exige previa >= 0 y actual
< 0. La igualdad actual no es cruce. No hay ventanas centradas, desplazamientos
negativos ni indicadores que dependan de observaciones posteriores.

El calentamiento se valida para TODAS las reglas antes de evaluar la conjunción:
`max(period + lag)`, más una barra si hay cruce. Evita que un primer `False`
oculte historia insuficiente en otra regla. El máximo necesario es 233 barras,
compatible con el límite 256. Entrada y salida simultáneas se rechazan.

`SignalResult` guarda hashes de estrategia, prefijo causal y postflight, instante,
último cierre, número de barras y resultados booleanos de reglas. Siempre conserva
`NO_TRADE`, autoridad/Paper/Live/validación estadística en `False`. El instante
describe cuándo se conoce el diagnóstico: cualquier acción hipotética tendría
que ocurrir después, con nueva validación. No se simula un fill al cierre usado
para calcular la señal. No hay estado de posición, activación de SL/TP ni evaluación
del tiempo transcurrido en una posición; el horizonte es un contrato verificado.
Tampoco se certifica que el precio actual permita obtener la entrada fija del
escenario. Una regla verdadera no equivale a una orden ni a una oportunidad rentable.

## Ejecución reproducible y resultados

Desde la raíz del repositorio Windows:

```powershell
.venv/Scripts/python.exe -B python/tests/core_v34_offline_check.py
```

El ejecutor descubre exactamente las suites aceptadas V3.1/V3.2/V3.3, Forex Fase 1,
contratos AI históricos y V3.4. No ejecuta las suites operativas de broker/Kronos.
Su audit hook deniega eventos de sockets, subprocesos y apertura/listado de la
`.local` real. SQLite se permite únicamente bajo el directorio temporal resuelto
del sistema; otra prueba anterior lo restringe al temporal concreto del caso.
Se corrigió el verificador inicial por los nombres corto 8.3/largo de Windows;
no se cambió código anterior para resolver ese falso bloqueo. Una prueba V3.4
adicional deniega toda apertura de archivos y SQLite durante la evaluación pura.
Las barreras son evidencia de pruebas en este proceso, no un sandbox de producción.

| Suite | Pruebas pasadas |
|---|---:|
| V3.4 contratos | 6 |
| V3.4 diseño y vínculos | 8 |
| V3.4 causalidad y series | 16 |
| V3.4 seguridad y esquema | 7 |
| **Nuevas V3.4** | **37** |
| V3.3 | 32 |
| V3.2 | 38 |
| V3.1 | 36 |
| Forex Fase 1 | 28 |
| Contratos AI históricos | 16 |
| **Total** | **187/187** |

Ejecución conjunta final: 17.092 s, cero fallos, cero infracciones de la barrera.
Los tests nacieron en rojo antes de cada capacidad. La prueba de seguridad
reprodujo y corrigió una excepción genérica ante solicitud ausente: ahora la
frontera rechaza el tipo antes de acceder a atributos. No se debilitaron tests,
umbrales ni validaciones anteriores. `git diff --check` sin errores.

Se validaron además tres documentos sintéticos con `Test-Json -SchemaFile` de
PowerShell: Strategy, CandleSeries y SignalResult. Los nueve casos negativos
(versión, autoridad y campo de código para cada raíz) fueron rechazados.
La prueba Python de esquema verifica que todas las definiciones cierren campos
y correspondan recursivamente con ejemplos serializados; el validador de esquema
de Windows aporta una comprobación distinta. No se instaló ninguna librería.

Ejemplo de uso con fixtures de pruebas ya disponibles:

```python
from test_core_v34_signals import AT, case
from trading_agent.core_v3.strategy_v34.signals import evaluate

request, strategy, candles = case()  # EUR/USD sintético, LONG, M1
result = evaluate(strategy, request, candles, as_of=AT)
assert result.entry_rules_met and not result.exit_rules_met
assert result.trading_decision == 'NO_TRADE'
```

Para este ejemplo con corte `2026-10-18T12:00:00Z`:

- Hash de estrategia: `8f4fcc10e35c4d16b65dd3cc3cc68216edac63d7162eb8d6cf76f2b41e60175a`.
- Hash de serie: `1541a8a203383915fcabebbfc13e0256c3b53eec2e24cda9df160bc66e0e6479`.
- Hash de resultado: `aee2fa0c9d0e512279a4d8f1d0ca44a93a27554ecee4749257547102f33e2051`.

## Revisión, diff y limitaciones

Revisión interna por cinco ejes: corrección, claridad, arquitectura, seguridad y
trabajo acotado. Las entradas son datos cerrados; no hay imports de transporte,
almacenamiento ni ejecución dinámica. La prueba de AST recorre el subpaquete
completo. Los hashes detectan cambios de contenido, no autentican al productor.
El host Python es confiable: frozen/slots y tipos exactos no protegen contra
quien pueda modificar código o monkeypatchar clases. No fue auditoría externa.

Commits de implementación:

- `3c63177`: contratos, diseñador y validación económica.
- `740d7a1`: series sintéticas y evaluación causal.
- `872f435`: esquema versionado, barreras y pruebas de seguridad.
- El commit posterior de documentación contiene este cierre.

Comparación reproducible: `git diff --name-status 1f20567..HEAD` y
`git diff --stat 1f20567..HEAD`. Todos los paths de la base se conservan;
el diff final solo añade los doce archivos enumerados. No se incorporan
`docs/architecture/core-v3-phase0-audit.md` ni
`docs/manual/TradingAgent_Manual_Tecnico_Integral.pdf`.

No ejecutado ni certificado: datos reales, backtest completo, rentabilidad,
calibración, integración de estrategias con el diario V3.3, API/.NET/frontend,
Sol/OpenAI/Kronos, IBKR, Paper/Live, conciliación o ejecución. Los controles de
parada de emergencia, credenciales y autorización Live existentes no se auditaron
en este alcance; V3.4 no tiene ruta a ellos. No hay promoción automática.

El rollback consiste en revertir los commits de esta rama tras revisar el árbol;
V3.4 no crea persistencia que migrar. No se debe borrar el trabajo ajeno al revertir.

## Inventario obligatorio al cierre de auditoría

Regla persistente del usuario: **al FINAL de CADA auditoría futura, presentar
lo implementado y lo pendiente para completar el backend, ANTES de solicitar
aprobación de la siguiente fase**. No sustituir el inventario por un porcentaje
ni considerar la existencia de código como validación operativa.

### Implementado en Core V3 y verificado en las suites de esta entrega

| Componente | Lo que tenemos | Límite |
|---|---|---|
| V3.1 | Instrumentos versionados, dinero/precios/cantidades tipados, evidencia, hashes, importación histórica cerrada. | Metadatos/importación; no autentica mercado ni concede permisos. |
| V3.2 | Preflight/postflight económico determinista, costos/margen/FX/stress, búsqueda finita y geometría LONG/SHORT. | Ruta sintética; no expectativa estadística ni ejecución de broker. |
| V3.3 | Orquestación simulada, presupuestos, idempotencia, diario SQLite, recuperación y replay. | Hipótesis de escenario; sin proveedores reales ni promoción. |
| V3.4 | Estrategias declarativas cerradas, reglas/indicadores acotados, vínculo económico y diagnóstico causal multiinstrumento. | Sin backtest, posiciones, persistencia de estrategias o ejecución. |

También existen componentes históricos de backend Python/.NET, riesgo,
persistencia y flujos Paper/R20/Forex/Kronos según el grafo y documentación
corroborada. En esta entrega solo se ejecutaron las regresiones históricas
enumeradas; la integración y seguridad operativa del resto siguen sin
recertificarse. No se los presenta como backend V3 completo.

### Pendiente para completar un backend Core V3 integrado

1. Catálogo durable de estrategias declarativas, versiones, revisiones e
   integración explícita con el diario/orquestador V3.3 y sus presupuestos.
2. Ingesta y datasets versionados/autenticados; calidad, calendarios, datos
   faltantes y timestamps de disponibilidad con procedencia comprobable.
3. Backtest por eventos con fills/costos/slippage/gaps/SL/TP/horizonte y contratos
   compatibles; impedir ambigüedad intrabar y fuga temporal.
4. Protocolo estadístico definido antes de evaluar: splits temporales, holdout,
   walk-forward, sensibilidad, stress/Monte Carlo y comparación reproducible.
5. Proveedores de diseño/forecast reales solo en una fase autorizada, con puertos
   acotados, validación, presupuestos, usage verificado, timeout y recuperación.
6. Gobierno de candidatas y evidencia: revisión humana, aprobaciones ligadas a
   hashes/política/cuenta, revocación y promoción explícita; nunca automática.
7. Integración de cartera/riesgo y contratos entre Python/.NET: capital, sizing,
   reservas concurrentes, exposición y suspensiones persistentes coherentes.
8. Adaptación IBKR de lectura, identidad/capacidades, conciliación y simulación
   de fallos; después ejecución Paper separada, idempotente y recuperable.
9. API y persistencia integradas, auditoría y observabilidad operativa, permisos,
   gestión de secretos, pruebas de recuperación y despliegue/rollback.
10. Habilitación Live únicamente tras evidencia suficiente, verificación de
    todos los controles y autorización humana independiente para esa fase.

Este inventario define capacidades pendientes de integración/verificación, no
afirma que todos sus componentes históricos deban reescribirse. La siguiente
fase requiere su alcance propio; esta entrega no la inicia.
