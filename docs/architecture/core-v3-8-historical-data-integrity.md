# Core V3.8 — ingesta histórica local e integridad causal

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
V3.8 usa tipos propios, `source_kind=REAL_HISTORICAL`, sin heredar de
SyntheticDataset, sin conversores, adaptadores, entradas al motor ni permisos.
Este identificador declara la clase de material solicitado, no su autenticidad.
Los fixtures conservan `data_origin=TEST_FIXTURE`; un fichero real exige
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
CSV `OHLC` con representación MID/BID/ASK/TRADE explícita o `QUOTE` BID_ASK.
No generar bid/ask desde mid ni reconstruir ticks desde OHLC. RAW únicamente:
ajustes, splits, dividendos y revisiones no documentados se rechazan.

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
probable por comprobación local; constarán en todo manifiesto.

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

Manifiesto liga versión de parser, hashes de entradas/política/receipt,
conteos, hash ordenado de registros candidatos e informe. Hash incremental
con prefijos de longitud por registro canónico, sin pérdida por contexto Decimal.
Archivo local nuevo por digest: raw.csv, descriptor/calendario, timezone.tzif,
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
imports de broker/modelos/servicios bloqueados para las pruebas nuevas.
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
