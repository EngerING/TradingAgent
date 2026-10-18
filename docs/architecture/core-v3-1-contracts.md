# Core V3.1 — contratos e importación histórica

Alcance autorizado el 2026-10-18. Base: `48f318a`, rama de trabajo
`codex/core-v3-1-contracts`. El informe de Fase 0 y el PDF previamente sin
seguimiento se conservan fuera de este cambio.

## Alcance antes de implementar

Este incremento crea `core_v3` como paquete hermano. No edita fuentes ni
manifiestos históricos. Implementa tipos comunes inmutables, `Instrument` y
registros de importación de bundles Forex V2 y assessments Forex fase 1.
Los registros importados son evidencia de investigación; todavía no son una
`StrategyVersion` ejecutable ni una evaluación del futuro gate V3.2.

Archivos previstos:

| Archivo nuevo | Función e impacto |
|---|---|
| `python/trading_agent/core_v3/contracts.py` | Tipos, validadores cerrados, precisión/unidades, vigencia, JSON y hashes. Sin I/O. |
| `python/trading_agent/core_v3/legacy_import.py` | Recibe JSON en memoria; verifica contratos/hashes originales mediante validadores puros existentes. No abre archivos ni actualiza almacenes. |
| `python/trading_agent/core_v3/__init__.py` | Identifica el paquete; no activa módulos/servicios. |
| `contracts/core-v3/v1/core.schema.json` | Esquema versionado de los contratos consumidos aquí y tipos comunes. |
| `python/tests/test_core_v3_contracts.py` | Contratos, dos clases de activo, roundtrip, errores, inmutabilidad y canonicalización. |
| `python/tests/test_core_v3_legacy_import.py` | Importaciones, preservación, ausencia de promociones y dependencias operativas. |

No se crean los trece contratos completos. Régimen, snapshots de mercado/cartera,
backtest, ranking, políticas de riesgo, autorizaciones, intenciones y reportes de
ejecución quedan para sus consumidores futuros. No hay filtro económico nuevo,
generación de estrategias, ledger, .NET, transporte, procesos ni endpoints.

## Decisiones del contrato

- `Instrument` exige ID estable, versión de especificaciones, clase de activo,
  símbolo, monedas, unidad de cantidad, unidad de precio, multiplicador, tick,
  mínimo, paso y calendario. No deduce USD ni convierte monedas/unidades.
- `Money`, `Quantity` y `Price` almacenan `Decimal` finito; el wire usa cadenas
  decimales. Los límites y la canonicalización se fijan con pruebas reproducibles.
  Las operaciones de compatibilidad comparan moneda y unidad explícitamente.
- `Environment` distingue RESEARCH, SIMULATION, PAPER y LIVE como procedencia.
  Etiquetar evidencia Paper/Live no concede autoridad. Los registros importados
  tienen alcance de investigación, autoridades falsas y `NO_TRADE`.
- `EvidenceRef` admite fechas desconocidas de forma explícita. Usarla como actual
  exige comprobar reloj, inicio y caducidad. Una importación histórica puede estar
  vencida y conservarse; no se presenta como actual.
- La importación recibe el `Instrument` completo del llamador: no inventa tick,
  mínimo, calendario ni contrato IBKR. Para Forex V2 comprueba EUR/USD, EUR por
  cantidad y USD por precio. Preserva una sola dirección y timeframe originales.
- El assessment económico se importa con su contexto, plan e instante original
  explícitos. Se contrasta contra el evaluador puro existente en ese instante;
  esto verifica consistencia histórica, no implementa V3.2 ni refresca evidencia.
  Sin esos datos se rechaza. No se vincula automáticamente a una estrategia.
- Se preservan JSON original, hash de bytes y hashes históricos declarados. El
  hash nuevo V3 tiene namespace/semántica propios y nunca sustituye al original.
- La validación estadística ausente en un bundle se conserva como desconocida;
  la fase 1 declara false y se preserva. Una aceptación económica antigua sigue
  siendo `ECONOMIC_SCENARIO_ONLY`, sin aprobación económica V3.
- Se rechazan extras/versiones desconocidas, claves duplicadas, permisos
  inyectados, números no finitos, unidades/monedas incompatibles e identificadores
  inválidos. Errores públicos contienen códigos fijos, sin copiar contenido crudo.

## Verificación y cierre previstos

TDD por incrementos: tipos comunes/instrumento, serialización y después
importadores. Ejecutar pruebas V3.1 y regresiones offline, incluidas las 28 Forex.
Revisar límites, esquemas y dependencia transitiva; comprobar que las fuentes
históricas no cambiaron. Pruebas sin red, procesos ni acceso a `.local` real.
No iniciar V3.2; queda pendiente de auditoría independiente y aprobación.

## Contratos entregados y uso

El esquema tiene tres raíces: `trading.core_v3.instrument`,
`trading.core_v3.imported_strategy` y
`trading.core_v3.imported_economic_assessment`, todas con `schema_version=1`.
Los tipos comunes implementados son `Money`, `Quantity`, `Price`, `EvidenceRef`
y los enums `AssetClass`, `SourceKind`, `Environment`. Instancias y componentes
anidados son dataclasses frozen con slots; los diccionarios devueltos son copias.

```python
from trading_agent.core_v3.contracts import Instrument
from trading_agent.core_v3.legacy_import import import_forex_bundle, import_forex_assessment

instrument = Instrument.from_json(instrument_metadata_json)
strategy_record = import_forex_bundle(original_bundle_json, instrument=instrument)
assessment_record = import_forex_assessment(
    original_assessment_json,
    context_json=original_context_json,
    plan_json=original_plan_json,
    assessed_at=original_assessment_datetime,  # datetime con zona; no el reloj actual
    instrument=instrument,
)
serialized = strategy_record.to_json()
# La procedencia histórica conserva su vigencia. Esto solo comprueba el tiempo:
assessment_record.provenance.require_current(explicit_current_datetime)
```

El importador recibe texto/bytes UTF-8 en memoria y no abre archivos. Las fuentes
se limitan a 32768 bytes cada una; un documento V3 a 131072 bytes y profundidad
32. Los originales conservan espacios, orden de claves, BOM UTF-8 si existe y saltos de línea;
`original_sha256` corresponde a sus bytes UTF-8 exactos. Los hashes declarados
V2/input V1 se guardan por separado, sin reemplazarlos por el hash nuevo.
Los blobs fuente se conservan como texto, no como reglas V3 ya compiladas.

`source_admitted` reproduce exclusivamente la decisión del evaluador histórico;
el sobre siempre declara `HISTORICAL_RESEARCH_ONLY`, `economically_approved=false`
y autoridades falsas. No hay vinculación automática entre el registro de
estrategia y el de assessment. Cadenas de datos no confiables siguen siendo
datos: no se evalúan como código ni se envían a un modelo.

## Canonicalización y validación

- Dinero: `Decimal` finito, hasta 18 dígitos enteros, 12 posiciones decimales y
  28 dígitos significativos. No se redondea para aceptar un valor. Se eliminan
  ceros decimales finales y el cero negativo se representa como `"0"`, sin usar
  `Decimal.normalize()` dependiente de la precisión ambiental.
- El wire financiero exige cadenas decimales sin exponente; no convierte floats,
  booleanos o valores ausentes. Las constantes numéricas de reglas V2 permanecen
  dentro del JSON original bajo su contrato histórico.
- Canonicalización de contratos validados: claves ordenadas, sin espacios,
  `ensure_ascii=True`, UTF-8 y SHA-256; arrays mantienen orden. No se normaliza
  Unicode: se conserva su secuencia de puntos de código y se escapa en JSON.
  No se aceptan surrogates aislados. Fechas normalizadas a UTC con seis posiciones
  de microsegundos y sufijo Z. Un hash no autentica una fuente ni concede permisos.
- La suma de Money y la comprobación de grillas usan un contexto Decimal local
  de precisión 60; la validación final mantiene los límites del contrato. No hay
  conversión de monedas ni cálculo de riesgo, margen o rentabilidad V3.
  La grilla de cantidad es `mínimo + n * paso`; los precios se alinean a múltiplos
  del tick. Son convenciones explícitas del contrato, no restricciones IBKR verificadas.
- `core.schema.json` describe la estructura del wire con referencias locales.
  Las invariantes entre campos, el límite de precisión y la consistencia de los
  originales exigen usar los validadores Python: validar solo el JSON Schema no
  basta. Las pruebas verifican referencias y paridad de campos del esquema; no se
  añadió un motor JSON Schema externo ni una dependencia de runtime nueva.
- Las fechas históricas pueden conservarse vencidas. `require_current` rechaza
  tiempo desconocido, futuro o vencido, pero comprueba únicamente vigencia temporal;
  no afirma autenticidad del productor ni disponibilidad actual de mercado.

No existe consumidor .NET en este incremento. Hay vectores dorados reproducibles
de bytes/hashes en las pruebas Python; los vectores compartidos y DTOs .NET se
posponen hasta tener ese consumidor.

## Evidencia de verificación

Graphify se consultó sobre el grafo existente de 424 nodos/1039 aristas. Se usó
el vocabulario `strategy research risk account`; la salida encontró 181 nodos,
limitada a 1400 tokens. Se contrastó con los validadores puros actuales de bundles
V2 y economía V1 antes de reutilizarlos. No se reconstruyó el grafo ni se dedujo
autoridad operativa de sus relaciones.

Verificación final del incremento:

| Grupo | Resultado |
|---|---|
| Contratos/serialización V3.1 | 17 pruebas pasadas |
| Importación/esquemas/aislamiento V3.1 | 19 pruebas pasadas |
| Forex fase 1 | 28 pruebas pasadas |
| Contratos AI históricos | 16 pruebas pasadas |
| Total | **80 pruebas pasadas** |

Se instalaron audit hooks en el proceso de verificación que deniegan red,
subprocesos y apertura/listado de la `.local` real del proyecto. Los importadores
también se probaron con apertura de archivos prohibida durante sus llamadas.
Las bases SQLite de regresión se crean en directorios temporales nuevos;
se usó permiso fuera del sandbox por sus restricciones conocidas en Windows.
No hubo conexiones a servicios, lectura de secretos ni operaciones de broker.

Se comprobó que una inversión temporal de la condición de autoridad hace fallar
la prueba de importación válida; la condición se restauró antes de la ejecución
final. Esto verifica sensibilidad de esa prueba, no un puntaje de mutation testing
de toda la suite. No se ejecutaron pruebas .NET ni servicios operativos.

## Límites y decisiones para la auditoría independiente

- Las restricciones del instrumento proporcionadas por el llamador no están
  verificadas contra IBKR. Los fixtures Forex y equity son ilustrativos;
  el segundo instrumento es sintético y cotiza en EUR, con otro calendario,
  unidad SHARE y mínimo/paso diferentes. Ninguno habilita operar.
- La importación económica requiere contexto, plan y cutoff originales. Es una
  comprobación de consistencia contra el evaluador puro preservado, no una prueba
  de que el productor era auténtico o el escenario se ejecutó. Una incompatibilidad
  de precisión, grilla, metadatos o versión produce error controlado.
- El bundle no contiene estadística verificable; se representa con null. La fase 1
  declara false y se conserva. No se añaden resultados ni se completa un bracket
  ausente. Las métricas históricas permanecen en el original bajo sus unidades y
  semántica V1; no se renombran como métricas aprobadas por V3.
- Ajuste explícito frente al diseño amplio de Fase 0: se incluye RESEARCH en
  `Environment` según V3.1 y se crean sobres de importación con nombres propios,
  sin presentar como completos `StrategyVersion` o `EconomicAssessment` V3.
- No se modificaron fuentes históricas, manifests, frontend, configuración,
  adaptadores, bases ni permisos. No se creó ledger ni se inició V3.2.
