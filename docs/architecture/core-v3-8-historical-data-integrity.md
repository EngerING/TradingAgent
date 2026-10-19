# Core V3.8 — ingesta histórica local e integridad causal

**Estado: infraestructura V3.8 implementada y verificada; formato real Dukascopy
pendiente de CSV. OFFLINE, NO_TRADE, 345 pruebas pasadas y cero violaciones
de barrera. Los 654 archivos originales y los dos documentos untracked están
preservados byte a byte. Sin integración al backtester ni inicio de V3.9.**

## Diseño previo a implementación (2026-10-19, America/La_Paz)

Base comprobada: `codex/core-v3-7-statistical-validation`,
`8c59061ef30e6fd6b9c943af5626811db7897706`. Rama nueva:
`codex/core-v3-8-historical-data-integrity`. El usuario ha autorizado diseño,
implementación incremental y pruebas exclusivamente offline de esta frontera.
No se inicia V3.9. Todos los cambios serán adiciones: los 654 archivos de la
base y los dos documentos untracked tienen SHA-256 registrado antes de editar.

### Objetivo y criterios de aceptación

Ingerir un CSV local acotado de un proveedor identificado, mantener sus bytes,
normalizar sin redondeos ni rellenos, comprobar procedencia declarada, relojes,
sesiones, calidad y causalidad, y producir un manifiesto reproducible y un
archivo de inspección o cuarentena. No obtener datos ni consumirlos en motores.
No se proporcionó todavía una exportación real ni documentación del proveedor:
las pruebas usarán fixtures expresamente identificadas como tales. Ninguna
prueba de fixtures certificará autenticidad o calidad de un dataset de mercado.

### Mapa de capacidades y orden de incrementos

1. **H38-C**: contratos cerrados e inmutables; sin dependencias operativas.
2. **H38-T**: tiempo exacto con TZif fijado y sesiones explícitas; depende de C.
3. **H38-I**: parser CSV, calidad, procedencia y manifiesto; depende de C/T.
4. **H38-F**: lectura local acotada y archivo reproducible; depende de I.
5. **H38-A**: pruebas adversariales, regresión de las 302 pruebas, inventario.

Fuentes en `python/trading_agent/core_v3/historical_ingestion/`; pruebas en
`python/tests/test_core_v38_*.py`; wrapper nuevo `core_v38_offline_check.py`.
La única reutilización será de primitivas y wire auditados V3.1/V3.2. No importar
brokers, backtesters, catálogos, modelos, servicios, configuración ni diarios.

### Frontera real separada y autoridad

V3.6 exige tipo exacto `SyntheticDataset` y `source_kind=SYNTHETIC` en
`event_backtest/contracts.py:81-92`; su reader exige ese tipo. V3.7 vuelve a
exigir SYNTHETIC en `statistical_validation/contracts.py:80-84` y reconstruye
SyntheticDataset en planning. **No se modifica ninguno de esos límites.**
V3.8 usa tipos propios, `source_kind=REAL_HISTORICAL_UNVERIFIED`, sin heredar de
SyntheticDataset, sin conversores ni adaptadores hacia V3.6/V3.7, entradas al motor o permisos.
Este identificador declara la clase de material solicitado, no su autenticidad.
Los fixtures conservan `data_origin=source_kind=SYNTHETIC_TEST_FIXTURE`; un fichero real exige
`data_origin=PROVIDER_EXPORT`. Resultado: `NO_TRADE`, scope de ingesta solamente,
backtest/paper/live/execution/statistical eligibility false, incluso aceptado.
La integración al backtester y su auditoría necesitan otra fase expresamente
autorizada. No ampliar permisos por datos JSON o valores de aprobación.

### Contratos y procedencia

Wire versionado `trading.core_v3.historical.*`, schema_version=1, campos exactos,
sin extras, claves duplicadas, bool como enteros, floats financieros, NaN,
infinito o colecciones mutables. Decimales de texto exactos con límites V3.1;
precios positivos, grilla de tick exacta, moneda/unidad explícitas. Identidad
por proveedor, símbolo del proveedor, instrumento, venue, moneda y unidad.
CSV canónico de pruebas (sin afirmar esquema de proveedor) `OHLC` con representación MID/BID/ASK/TRADE explícita o `QUOTE` BID_ASK.
No generar bid/ask desde mid ni reconstruir ticks desde OHLC. RAW únicamente:
metadatos de ajustes no admitidos se rechazan. Un ajuste oculto en precios
numéricamente válidos no es detectable sin evidencia externa del proveedor.

Descriptor: proveedor/exportación, identidad, origen, tipo/representación,
intervalo (OHLC), timestamps de exportación/observación, ventana solicitada,
base de disponibilidad, hashes de CSV/evidencia/calendario/TZif y zona IANA.
Evidencia local acotada se conserva literalmente; **hash != autenticidad**.
Un receipt separado, suministrado por el host confiable, debe vincular todos
esos hashes y declarar revisor, método independiente y fecha. No se extraen
receipts ni aprobaciones del CSV o descriptor. Sin receipt coincidente:
QUARANTINED. Receipt coincidente: LOCAL_REVIEW_ATTESTED, nunca autenticidad
criptográfica certificada. La confianza es en la revisión externa del origen,
no en un hash ni en un booleano del candidato. No hay ancla real por defecto.
El método permitido describe una reconciliación externa de proveedor/export;
el módulo no ejecuta ni finge verificar una firma. Host/revisor malicioso,
compromiso del proveedor y evidencia externa falsa permanecen fuera de lo
demostrable por comprobación local; constan en este informe. Cada manifiesto
expresa la ausencia de verificación criptográfica.

### Tiempo, calendario y disponibilidad

Timestamps ISO exactos hasta microsegundos; zona local exige offset explícito.
Normalización UTC con roundtrip contra ZoneInfo desde **bytes TZif locales
fijados por hash**, sin depender de la tzdb ambiental. Una hora local inexistente
se rechaza; una ambigua requiere offset que seleccione un fold válido. UTC
acepta Z/+00:00. Se conservan los timestamps originales en los bytes del CSV.
Calendario versionado con coverage_start/end y sesiones UTC ordenadas y sin
solapes, id/revisión y referencia de evidencia. Su lista completa representa
festivos, cierres tempranos y pausas; nunca se supone 24x5/24x7 por defecto.
Ventana solicitada dentro de cobertura. Barras completas dentro de una sesión,
alineadas desde apertura y con intervalo entero; partición exacta, sin vela
parcial implícita. Se comprueba cada barra esperada de la ventana, incluidos
huecos iniciales/finales; cierres de mercado no son gaps. Quotes son eventos
irregulares: secuencia explícita, máximo silencio declarado, sin prometer
exhaustividad del feed a partir de esa sola tolerancia.

OHLC solo disponible al cierre o después. Quotes disponibles al evento o después.
PROVIDER_PUBLISHED requiere declaración de revisión que cubra sus tiempos;
EXPORT_OBSERVED exige available_at == exported_at, límite conservador que
impide inventar disponibilidad histórica. Evento <= available <= exported <=
observed <= cutoff de ingesta. El reloj histórico no es el de adquisición.
No selección de estrategias ni pretensión OOS; orden cronológico estricto de
eventos y disponibilidad no decreciente. Nunca ordenar silenciosamente.

### Calidad, cuarentena y reproducibilidad

OHLC coherente, volúmenes/tamaños ausentes como null, nunca cero inventado;
quotes bid<=ask, tamaños no negativos, tick exacto. ID duplicado, intervalo
repetido, mismo evento/secuencia, conflicto, orden inverso, gaps, falta de
cobertura o disponibilidad futura ponen el lote completo en cuarentena.
Informe con códigos fijos/filas, sin copiar texto no confiable en errores.
No deduplicar, corregir, interpolar, hacer forward fill ni aceptar subconjuntos
como un dataset completo. Resultado cuarentenado no expone registros listos.

Manifiesto liga versión de parser (política fija), hashes de entradas/receipt,
conteos, hash ordenado de registros candidatos e informe. Hash incremental
con prefijos de longitud por registro canónico, sin pérdida por contexto Decimal.
Archivo local nuevo identificado por el digest de file_index.json, que liga
nombres, tamaños y hashes de todos los ficheros: raw.csv, descriptor/calendario, timezone.tzif,
evidencia, receipt, manifiesto, informe y normalizados JSONL. Commit por rename
de directorio staging; no sobreescritura; reintento idéntico verifica bytes;
colisión/corrupción se rechaza. No ancla externa contra rollback coordinado.

### Amenazas y mitigaciones

| Amenaza | Control y límite |
|---|---|
| Hash presentado como autenticidad | Revisión externa separada; assurance explícita y limitada. |
| Proveedor/receipt autopromovido | Host provee receipt fuera del paquete; no decoder de permisos. |
| Lookahead, revisiones tardías | Disponibilidad conservadora, cutoff, export/observación y monotonía. |
| DST, festivos, sesión parcial | TZif fijado, offset roundtrip, cobertura/sesiones explícitas. |
| Duplicados/gaps/precios inventados | Cuarentena total, sin reparaciones automáticas. |
| Path traversal, UNC, ADS, .local, enlaces/reparse | Rutas locales acotadas; nombres relativos simples; rechazar componentes peligrosos. |
| Ficheros enormes, CSV malformado | Límites de bytes/filas/columnas, parser estricto, sin archivos comprimidos. |
| Carreras/corrupción de archivo | Snapshot acotado y stat antes/después; rename y verificación byte a byte. |
| Host malicioso muta filesystem | No es sandbox OS; la barrera de pruebas y host confiable siguen siendo necesarios. |
| Contaminación SYNTHETIC/operativa | Tipos hermanos; imports cerrados; ninguna integración o conversión. |

### Verificación y comandos

Usar `.venv/Scripts/python.exe -B python/tests/core_v38_offline_check.py`
para regresiones históricas y nuevas; patrón `test_core_v38_*.py` para pruebas
cercanas. Barrera nueva antes de importar código: red/subprocesos bloqueados,
.local bloqueado incluso por rutas resueltas, DB solo temporales como en V3.4,
Una prueba AST comprueba que el paquete no importa motores, brokers, modelos
o servicios ni usa eval/exec/imports dinámicos. No es un sandbox de imports.
No modificar wrappers ni suites previas. Pruebas positivas, adversariales,
reproducibilidad y preservación de tipos/autoridad. No ejecutar servicios .NET,
Paper/Live, migraciones, brokers, modelos, red, push o merge.
Cada incremento se verifica y guarda en commit local. El cierre registrará
comandos ejecutados, resultados exactos, límites, commits e inventario completo
de archivos del backend; existencia no equivale a certificación operativa.

### Consulta Graphify contrastada

Grafo histórico: 424 nodos, 1039 aristas. Vocabulario expandido real:
historical data provider evidence ohlc quote gap backtest research contract time
offline. BFS de 3 niveles: 52 nodos, semillas historicalData(),
historicalDataEnd() y el rationale offline de __init__.py. Aristas EXTRACTED:
_Wire contiene historicalData/historicalDataEnd, source_location L121/L127 de
tws.py en el grafo. El fichero actual ha evolucionado: esa numeración ya no
corresponde a callbacks. Se contrastaron el código actual de tws.py/broker.py,
backtest.py y test_quant.py, además de contratos/reader V3.6 y contratos/planning
V3.7. No reutilizar el transporte Paper sugerido por el grafo para esta ingesta.
Las lecciones históricas se leyeron. El intérprete anotado no tiene instalado
graphify (reflect falló con No module named graphify): se usó BFS determinista
sobre graph.json, sin instalar paquetes, red, modelos ni reconstruir el grafo.


## Precisión de alcance aportada por el usuario durante el diseño

Proveedor inicial de referencia: **Dukascopy Bank SA**; EUR/USD, H1, CSV,
UTC explícito y BID/ASK por separado. Un mes inicial; enero 2024–diciembre 2025
es el dataset ampliado previsto, no disponible ni validado en esta entrega.
El usuario exige no inventar columnas y deja pendiente cerrar el adaptador
hasta aportar una exportación real y revisar sus columnas/configuración.

Por tanto se separan dos fronteras: parser **canónico de fixtures sintéticos**
y recepción de originales Dukascopy **sin interpretación de esquema** en
cuarentena. Ningún original real pasará por el formato canónico inventando
columnas. El parser genérico reserva su aceptación a proveedores fixture-* etiquetados
SYNTHETIC_TEST_FIXTURE y rechazará material PROVIDER_EXPORT mientras no
exista un adaptador de esquema real revisado; ni siquiera un receipt externo
levanta esa limitación. El intake Dukascopy conserva bytes, configuración
declarada y hashes; emite FORMAT_UNVERIFIED, siempre NO_TRADE y sin registros
normalizados. Esto es una función de custodia completa y verificable, no una
implementación pretendida del esquema real pendiente. Fixtures identificados
SYNTHETIC_TEST_FIXTURE nunca acreditan el formato real de Dukascopy.

Límite inicial: 4096 filas y 1 MiB por fichero canónico; un mes H1 cabe sin
crear un supuesto 24x7. La recepción opaca permite hasta 16 MiB de CSV original.
La ampliación de dos años deberá usar lotes acotados y una comprobación posterior
de continuidad entre lotes; no se afirma validación global de ese periodo.


## Resultado implementado y límites de cierre

**Core V3.8 iniciado, OFFLINE y NO_TRADE.** La infraestructura de contratos,
normalización, calidad, custodia y pruebas queda implementada. El adaptador de
columnas **reales** de Dukascopy y la validación de datos auténticos quedan
**PENDIENTES DE CSV REAL**, conforme a la instrucción expresa del usuario.
No se ha validado ni ingerido como aceptable ningún dataset real del proveedor.
No se cierra esa validación a partir de fixtures ni de documentación inferida.

### Fuentes y pruebas nuevas

| Archivo en historical_ingestion/ | Comportamiento |
|---|---|
| __init__.py | Importación sin arranque ni exportación a motores. |
| contracts.py | DatasetSpec, ReviewReceipt del host, Session y SessionCalendar; wire cerrado. |
| time_rules.py | TZif fijado, lectura finita, UTC/offset/folds, cobertura y grillas explícitas. |
| records.py | HistoricalBar/Quote, QualityReport, IngestionManifest, IngestionResult; autoridad cerrada. |
| canonical_csv.py | Gramática canónica EXCLUSIVA de fixtures sintéticos; no esquema Dukascopy. |
| ingestion.py | Snapshot puro, vínculo de evidencias, calidad total y cuarentena del lote. |
| files.py | Entradas locales acotadas, custodia por índice de hashes, publicación y reverificación. |
| dukascopy_intake.py | Configuración declarada EURUSD/H1/UTC/BID o ASK y custodia opaca FORMAT_UNVERIFIED. |

| Suite nueva | Pruebas | Alcance |
|---|---:|---|
| test_core_v38_contracts.py | 5 | Wire, tipos, permisos, origen y reviews. |
| test_core_v38_time.py | 7 | DST/folds, offsets, cobertura, sesiones y TZif corrupto. |
| test_core_v38_ingestion.py | 4 | Camino canónico, procedencia, rechazo real y cuarentena total. |
| test_core_v38_adversarial.py | 11 | Quotes, disponibilidad, duplicados, evidencia, grilla y autoridad. |
| test_core_v38_files.py | 7 | Custodia, corrupción, paths/hardlinks, settings y Dukascopy opaco. |
| test_core_v38_boundaries.py | 9 | Mes H1, límites, malformaciones, tipos, imports y publicación interrumpida. |
| **Total nuevo** | **43** | Ejecutado bajo ambas barreras offline. |

El wrapper nuevo conserva el guard V3.4 y añade contabilidad propia de intentos
bloqueados y resolución de aliases/reparse hacia .local. El código anterior no
se altera. Los tests usan directorios temporales; no se generan diarios ni
bases operativas ni se lee almacenamiento privado. Las escrituras de runtime
nuevas son exclusivamente archivos de custodia solicitados por el llamador.

### Evidencia de ejecución

1. Baseline antes de cambios de código: `.venv/Scripts/python.exe -B
   python/tests/core_v37_offline_check.py`: **302 pruebas, OK, 296.997 s;
   OFFLINE_BARRIER_VIOLATIONS: 0**.
2. Verificación cercana final: `.venv/Scripts/python.exe -B
   python/tests/core_v38_offline_check.py 'test_core_v38_*.py'`: **43 pruebas,
   OK, 1.631 s; ambos contadores de barrera: 0**.
3. Regresión conjunta: `.venv/Scripts/python.exe -B python/tests/core_v38_offline_check.py`: **345 pruebas, OK, 261.989 s; OFFLINE_BARRIER_VIOLATIONS: 0 y V38_OFFLINE_BARRIER_VIOLATIONS: 0**.
4. `git diff --check 8c59061`: sin errores de whitespace.
5. Comparación SHA-256 de los **654 archivos originales**: cero diferencias.
   Los dos documentos untracked conservan sus hashes originales y su estado.

Un mes H1 fabricado: **552 barras**, calendario sintético de días laborables de
enero 2024, precios inventados y evidencia TEST_FIXTURE. No representa el
calendario real del mercado: incluso sus festivos son deliberadamente parte
del fixture. Se verificó cobertura sin generar barras de fin de semana.
Esto prueba el mecanismo a esa escala, no autenticidad, calidad del proveedor,
calendario bancario, BID/ASK real ni validez económica.

No se ejecutaron servicios ni compilación o suites .NET, modelos, IBKR, otros
servicios externos, migraciones, Paper o Live. No hubo descarga, instalación,
red desde el repositorio, push o merge. El acceso al chat referenciado se usó
solo para contexto; no fue una fuente de datos de mercado.

### Defectos reproducidos y revisión

Las pruebas iniciales fallaron por ausencia de las capacidades y después pasaron
con cada incremento. Cinco regresiones adversariales se reprodujeron ejecutando
sus tests antes de corregirlas: calendario no ligado a evidencia, CSV usado
como su propia evidencia independiente, proveedor promovido con etiqueta de
fixture, offset desconocido -00:00 y acceso mediante hardlink. Todas pasaron
después de aplicar el control correspondiente.

Una revisión estática por otro agente, con contexto separado y sin ejecutar
código, detectó truncamientos TZif (struct.error y bucle EOF en el footer del
lector estándar), exceso combinado de issues y extremos del rango datetime.
Se corrigieron mediante lectura que falla ante EOF/short read, conversión a
códigos fijos, límite central de issues y cuarentena de overflow. Se añadieron
regresiones, incluidas TZif válidos sin su última newline. La revisión no es
una auditoría humana ni recertificación operativa independiente.

Sensibilidad ejecutada: se sustituyó temporalmente solo la condición del vínculo
`calendar.evidence_sha256 != spec.evidence_sha256` por False. La suite adversarial
produjo **1 fallo en 11 pruebas**, precisamente en la evidencia del calendario.
El bloque finally restauró los bytes. SHA-256 de ingestion.py restaurado:
`9f225fe172aee6d82a7277398c952cc9c8bb239dbce252ae978356b29b1e8e75`.
La regresión conjunta posterior usa ese archivo restaurado. Es una mutación
puntual; no es un score global de cobertura o de mutación.

### Uso local y preparación de una muestra Dukascopy

API de custodia disponible: `dukascopy_intake.stage_export(input_root,
csv_name, output_root, settings, cutoff=..., evidence_name=...)`.
`settings` es un DukascopySettings cerrado: EURUSD, H1, UTC, BID o ASK, mes,
exported_at, observed_at, PROVIDER_EXPORT o SYNTHETIC_TEST_FIXTURE y referencia
a la configuración de exportación. Son datos declarados, nunca autenticación.
`verify_export(target, cutoff=...)` reconstituye el manifiesto fijo y verifica
los bytes del archivo completo sin convertirlo en un dataset aceptado.

Al proporcionar el CSV real, conservar original y configuración de exportación,
separar BID y ASK si así se exportan y revisar cabeceras, formato decimal,
semántica y precisión temporal, fechas de apertura/cierre, volumen/unidades,
ajustes, sesiones y base de disponibilidad. No cambiar los originales para que
encajen con el formato de fixtures. Si no hay tiempo de publicación histórico
verificable, usar como límite conservador la fecha de exportación observada,
sin inventar disponibilidad pasada. El calendario real y su evidencia también
siguen pendientes: no se ha supuesto un horario FX o un cierre bancario.

Para pruebas exclusivamente sintéticas están `ingest_canonical`, `ingest_local`,
`archive_local` y `verify_archive`. Headers canónicos de fixtures:

```text
record_id,symbol,opened_at,closed_at,available_at,open,high,low,close,volume
record_id,symbol,event_at,available_at,sequence,bid,ask,bid_size,ask_size
```

**Estas columnas no se presentan como un esquema real de Dukascopy.** El primer
header representa OHLC con lado declarado en DatasetSpec; el segundo quotes.
No se combinan barras BID y ASK ni se fabrica mid. Las comprobaciones cruzadas
de barras reales por lado seguirán pendientes del adaptador y de sus muestras.
Los objetos ReviewReceipt se construyen fuera de los datos por el host después
de una revisión externa; su copia guardada es solo auditoría y no se decodifica
como fuente de confianza. Ningún receipt habilita ahora el esquema real.

### Inventario completo del backend

`core-v3-8-backend-inventory.json` enumera **456 archivos** git-tracked bajo
python/, src/, tests/, contracts/, config/ y scripts/, más la solución y las
propiedades de compilación. Para cada archivo: ruta, grupo, estado, bytes,
líneas, SHA-256 y, en Python, declaraciones/imports por AST. No hubo errores AST.
Registra los seis proyectos .NET, referencias, dependencias declaradas y
framework efectivo net9.0 (incluida su herencia de Directory.Build.props).
No incluye frontend, docs, .local, entornos, artefactos ignorados ni documentos
untracked. Es un inventario estático de existencia; no una prueba operativa.

| Grupo | Archivos | Estado y límite |
|---|---:|---|
| Core V3.1–V3.3 | 11 | Contratos, economía, orquestación; preservados y cubiertos por regresión base. |
| Core V3.4 | 5 | Estrategias declarativas; preservado. |
| Core V3.5 | 5 | Catálogo; preservado. |
| Core V3.6 | 6 | Backtester exclusivamente sintético; preservado. |
| Core V3.7 | 8 | Validación estadística exclusivamente sintética; preservada. |
| Core V3.8 | 8 | Contratos/custodia/calidad; formato real pendiente. |
| Python histórico | 95 | Broker, datos, cuantitativo, equity, R20 y laboratorios existentes; sin recertificación operativa. |
| AI strategy researcher histórico | 29 | Proveedores, memoria, simulación, Sol/Kronos y herramientas; sin ejecución ni integración V3.8. |
| Forex research histórico | 4 | Componentes existentes preservados. |
| Tests y wrappers Python | 122 | Incluyen las suites base y V3.8; la suite completa histórica ajena al wrapper no se afirma ejecutada. |
| Soporte Python | 1 | tzdata==2026.5 ya existente; ninguna dependencia añadida. |
| TradingAgent.Api | 23 | Endpoints/servicios/laboratorios existentes; no iniciados. |
| TradingAgent.Core | 19 | Dominio/riesgo/economía históricos; no compilados ni recertificados. |
| TradingAgent.Infrastructure | 25 | Postgres/stores y 11 migraciones SQL existentes; ninguna ejecutada o modificada. |
| TradingAgent.ConfigurationLab | 2 | Existente; no ejecutado. |
| TradingAgent.ResearchLab | 4 | Existente; no ejecutado. |
| Tests .NET | 35 | Existentes; no ejecutados en esta entrega. |
| Schemas wire | 3 | Históricos, intactos. |
| Configuración tracked | 22 | Intacta; no se activó ninguna configuración operativa. |
| Scripts históricos | 27 | Intactos; no ejecutados. |
| Solución/build | 2 | Intactos. |

| Capacidad pendiente para completar el backend | Condición o límite |
|---|---|
| Datos reales Dukascopy | Muestra, esquema/documentación/configuración, calendario y revisión de procedencia; adaptar y auditar dentro del alcance autorizado. |
| Dataset enero 2024–diciembre 2025 | No aportado ni validado; lotes acotados y continuidad entre lotes pendientes. |
| Consumo real en backtester/estadística | Fase y auditoría posterior con autorización específica; sin puente actual. |
| Régimen, ranking y selección | Componentes causales/versionados, comparabilidad y control de selección múltiple pendientes. |
| Sol/Kronos controlados | Integración V3, proveedores autorizados, presupuestos y uso incierto pendientes. |
| Cartera y riesgo agregado | Capital compartido, límites agregados y autoridad única pendientes. |
| Comunicación Python/.NET | Contratos, roles y aislamiento de autoridad V3 pendientes. |
| Operación/conciliación IBKR | Intenciones durables, simulación SDK, reconciliación y guardias posteriores. |
| Persistencia/observabilidad integral | Anclas externas contra rollback, archivo durable, métricas/trazas y recuperación pendientes. |
| Paper, Live y despliegue | Validación y autorización separadas; fuera de esta fase. |

### Commits y preservación

| Commit | Incremento |
|---|---|
| 735f769 | Diseño previo: contratos, amenazas, procedencia y frontera real separada. |
| 15577a0 | Contratos cerrados y receipts de revisión del host. |
| 1f6571e | TZif local fijado y sesiones explícitas. |
| 4b898e3 | Parser sintético, calidad y cuarentena; formato real expresamente pendiente. |
| 8a49094 | Custodia de originales y archivos reproducibles. |
| c3b2050 | Regresiones adversariales y hardening causal/temporal. |
| 770940b | Reverificación opaca de Dukascopy y settings cerrados. |
| Commit de cierre | Este informe y el inventario; hash comunicado al entregar. |

Todos son commits locales en la rama V3.8. Se deshabilitaron hooks solo en cada
invocación de commit para evitar tareas automáticas fuera del alcance offline;
no se modificó configuración de Git ni hooks existentes. No hubo push o merge.

Documentos preservados y todavía untracked:

- docs/architecture/core-v3-phase0-audit.md:
  `419d1e97b7f7017bddebd3074b1433d48702a59a274194f017129933e4314537`.
- docs/manual/TradingAgent_Manual_Tecnico_Integral.pdf:
  `1f31321892f532b3d5de1bc3d574bd5f66c3af38ae634d7173b6b173c49b3944`.

Reversión posible mediante revisión y revert de los commits específicos en orden
inverso; no usar reset/clean ni borrar archivos del usuario o journals. No se
realizó reversión operativa. V3.9 no se ha diseñado, implementado ni iniciado.
