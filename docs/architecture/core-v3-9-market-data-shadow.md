# Core V3.9 — datos de mercado y Shadow observacional

Fecha de alcance: 2026-10-19, America/La_Paz. Base auditada por el usuario:
`542f250cd77c727832835d162596771430aa823a`, rama
`codex/core-v3-8-historical-data-integrity`, 345 pruebas aceptadas.
Rama nueva: `codex/core-v3-9-market-shadow`. Estado: **NO_TRADE**.
V3.9 requiere auditoría independiente; este documento no la aprueba.

## Diseño y amenazas expuestos antes de implementar

Paquete hermano `python/trading_agent/core_v3/market_observation/`.
Todos los cambios serán adiciones. Ningún dato real se convierte a
SyntheticDataset ni se conecta a V3.6/V3.7. No se modifica V3.1–V3.8.

| Componente nuevo | Frontera |
|---|---|
| contracts.py | Eventos originales acotados, identidad EUR/USD, quotes, calidad y políticas inmutables. |
| validation.py | Fold causal de identidad, tipo confirmado, secuencia, precios, recepción y lagunas. |
| journal.py | SQLite propia, eventos inmutables, hashchain/head y recuperación transaccional. |
| authorization.py | Verificación de aprobación externa de lectura ligada a endpoint, sesión, política y vigencia. |
| ibkr_protocol.py | Gramática estrecha de mensajes permitidos; sin SDK general. |
| ibkr_adapter.py | Perfil socket deshabilitado por defecto y transcript de pruebas identificado. |
| collector.py | Puerto simulado, persistir antes de exponer, límites y cancelación de suscripción. |
| shadow.py | Hipótesis declarativas de quotes, versión/hash, prefijos causales y observaciones posteriores. |

El transporte histórico `tws.py` hereda de EClient y bloquea mutadores. No se
importará: la nueva frontera no tendrá esa herencia ni dependencias de órdenes.
Perfil inicial de wire legacy negociado 157, comprobado contra el SDK local
10.50.2 por inspección, aún no recertificado contra TWS auténtico. Solo mensajes
START_API, hora, cuentas gestionadas para comparación opaca, detalles del
contrato, tipo de datos, suscripción de quotes y su cancelación. No hay método
genérico para enviar una operación por nombre ni acceso al SDK de órdenes.
Un perfil incompatible falla; no hace fallback al cliente histórico.

La aprobación de datos es independiente de cualquier permiso de trading.
Deshabilitado por defecto; el host confiable debe aportar evidencia externa de
sesión, modo Paper/Live, endpoint, TWS de solo lectura y permisos, ligada mediante
autenticación local a la aprobación. No hay autoridad real provisionada ni se
crea una aprobación auténtica en esta entrega. Un puerto o prefijo de cuenta no
prueba el entorno. Se comprueba además la sesión conectada y el contrato.

El perfil watchlist tickPrice no aporta timestamp de origen BID/ASK: queda null.
La recepción UTC y monotónica se conserva por lado. Callback marketDataType
confirma LIVE/FROZEN/DELAYED/DELAYED_FROZEN; solicitar LIVE no lo acredita.
UNKNOWN o ticks incompatibles nunca se presentan como LIVE. Los transcripts
y adaptadores simulados permanecen SYNTHETIC_TEST_FIXTURE, incluso al recorrer
el parser de conexión. No se inventan volúmenes, tamaños ni liquidez.

Cada evento de mercado se conserva antes de publicar una observación validada.
El journal tiene identidad de origen/entorno, clave de recepción, eventos
append-only, cadena/hash de bytes y head transaccional. Un hash no autentica
IBKR. Corrupción, conflicto y reordenamiento no se reparan silenciosamente.
Reinicio/desconexión exige laguna explícita y vacía las cachés de ambos lados.
Si falla persistencia se detiene el consumo y se cierra/cancela la suscripción.
No se promete recuperar ticks perdidos durante una desconexión ni secuencias
globales que IBKR no suministra.

Shadow usa hipótesis propias de quotes con identidad/versión y reglas cerradas;
no afirma ejecutar el AST OHLC histórico sin sus barras. Registra LONG/SHORT/
NO_TRADE hipotéticos, evento/prefijo disponible y condiciones posteriores.
Sin fills, P&L, cartera, simulación económica ni promoción. Shadow sobre datos
auténticos requiere habilitación independiente; también queda apagado.

| Amenaza | Decisión y límite |
|---|---|
| Cliente SDK expone mutadores | No importarlo; encoder con lista permitida y pruebas de cada opcode. |
| Booleano/JSON se convierte en autorización | Firma local del host, ámbito DATA_ONLY, binding, política y expiración. Host comprometido queda fuera del aislamiento Python. |
| Cuenta/puerto confundido con Paper/Live | Atestación externa separada y comparación exacta de identidad conectada. |
| Delayed/frozen o precio viejo como LIVE | Tipo confirmado por solicitud, épocas y frescura por lado. |
| Lookahead/reloj inventado | Dos relojes, source_at opcional, cutoff explícito y prefijo causal. |
| Disconexión o fallo de escritura | Commit antes de publicar; detener, reabrir y registrar GAP. |
| Duplicados/reordenamiento | Claves idempotentes, conflictos explícitos y secuencia verificada. |
| Disco/memoria ilimitados | Límites por eventos, bytes, páginas SQLite, solicitudes, duración y reconexiones. |
| Secretos en errores | Códigos fijos; identidad opaca; mensajes sensibles redactados con digest. |
| Datos reales reetiquetados como sintéticos | Tipos hermanos y ninguna dependencia/conversión hacia motores sintéticos. |

Se aplican senior-software-engineer, Graphify, TDD incremental y revisión
adversarial interna. El usuario solicitó preparar también un artefacto para
revisión externa manual. No se ejecutarán CLIs externas para ello.

Pruebas previstas: cotizaciones y relojes adversos, tipo de feed, identidad,
reconexión, duplicados/orden, fallos de commit, recuperación, cuotas, comandos
denegados, Paper/Live, causalidad Shadow, replay sin red y separación de tipos.
Wrapper nuevo sobre las barreras anteriores intactas. Las 345 regresiones
anteriores se ejecutarán junto a las nuevas. Ninguna prueba abrirá TWS/IBKR.

La conexión auténtica, las autorizaciones operativas, Paper/Live, migraciones,
servicios, frontend, modelos, V3.10, push y merge quedan fuera de esta entrega.

## Contratos entregados y procedencia

Los tipos wire usan `trading.core_v3.observation.*`, schema_version=1, JSON
cerrado y dataclasses frozen/slots. Se reutilizan serialización y decimales
V3.1 y Record V3.8 sin editarlos. Se rechazan extras, versiones desconocidas,
duplicados JSON, floats/bool financieros y valores no representables.

| Tipo | Contenido y límite |
|---|---|
| CapturePolicy | Límites de recepción, spread, salto, frames, disco, eventos, solicitudes y reconexiones; no política de trading. |
| ContractIdentity | conId positivo, EUR/CASH/USD/IDEALPRO, minTick y hash del frame de detalles. No inventa mínimos de negociación. |
| RawEvent | Origen declarado, sesión, conexión, solicitud lógica, solicitud wire original cuando existe, secuencia local, UTC y monotónico, datos crudos y referencias de atestación/aprobación de captura. |
| Quote | BID/ASK Decimal, spread USD por EUR, referencias de ambos lados, recepciones, timestamps fuente opcionales y tipo confirmado. No incorpora tamaño/liquidez. |
| ValidatedEvent | Original, cutoff explícito, aceptación, motivos y quote opcional. Aceptar una observación no autoriza trading. |
| ShadowSpec | Hipótesis quote-only con ID/versión/hash, BID_GT o ASK_LT y dirección hipotética. No representa una versión aprobada del catálogo V3.5. |
| ShadowSignal | Fecha de generación, prefijo/hash causal, índices de los dos lados disponibles, dirección hipotética e incertidumbre. |
| SubsequentCondition | BID/ASK posteriores, instante, referencia de señal y prefijo propio; edad fuente puede seguir desconocida. |
| ShadowResult | Señales y condiciones acotadas, cutoff y prefijo disponible; NO_TRADE, execution_authorized=false, statistically_validated=false, economically_approved=false. |

Un frame de mercado se conserva en base64 con su SHA-256 y longitud verificados.
Los callbacks de cuentas, errores y mensajes no reconocidos potencialmente
sensibles se redactan explícitamente: quedan tipo/motivo, digest, longitud y
redacted=true. No se conserva el texto de cuenta ni de error. Los precios
inválidos y frames de mercado rechazados sí conservan sus bytes acotados.
Un frame anunciado por encima del límite se corta antes de recibir el cuerpo;
se registra el fallo de conexión, sin afirmar que se conservó un cuerpo ausente.

Las referencias de atestación y grant son hashes de evidencia del host. No son
firmas de IBKR. Origin.IBKR_SOCKET_OBSERVED describe el camino de captura local,
no autenticación criptográfica del proveedor. TranscriptAdapter y FixtureAdapter
siempre declaran SYNTHETIC_TEST_FIXTURE. Los dobles de socket de las pruebas
verifican el camino del lector, sin producir archivos ni muestras de mercado real.

## Validador causal y relojes

Cada conexión vuelve a verificar contrato y tipo y recibe una secuencia local
nueva; IBKR no aporta una secuencia global de quotes en este perfil. Se conserva
el orden de recepción incluso al detectar saltos o retrocesos. No se ordenan ni
fusionan ticks para ocultar el problema. Duplicados exactos se resuelven en el
journal; mismo ID con otro contenido es conflicto.

El precio debe ser positivo, finito y alineado al minTick observado. Se rechazan
crosses, spread superior al límite y saltos configurados. El tipo se confirma
mediante callback58; ticks1/2 corresponden al grupo normal, 66/67 al retrasado.
Solicitar tipo1 no cambia UNKNOWN a LIVE. Cambiar tipo borra ambos lados.

Se comprueban UTC contra cutoff y monotónico contra UTC. La edad por lado se
comprueba tanto por UTC como por monotónico, evitando que pequeñas derivas
acumuladas mantengan vivo un BID antiguo. El reloj monotónico se reinicia como
referencia al cambiar de conexión. El timestamp fuente futuro se rechaza.

Con timestamp fuente ausente, source_age_us=null y SOURCE_TIME_NOT_PROVIDED.
No se publica una latencia de mercado calculada desde la recepción. La ausencia
queda visible incluso si un investigador permite explícitamente esa incertidumbre
en una hipótesis Shadow. Fuente vieja, recepción vieja y tipo retrasado son
dimensiones distintas; ninguno se reetiqueta como dato actual auténtico.

## Journal, publicación y recuperación

Journal recibe RawEvent, recalcula el validador y registra original/veredicto
dentro de BEGIN IMMEDIATE. La cadena incluye secuencia durable, hash anterior y
documento canónico. Head se actualiza en la misma transacción; SQLite usa DELETE,
synchronous=FULL y temp_store=MEMORY. Triggers deniegan UPDATE/DELETE de eventos
y metadatos. Las consultas verifican triggers, quick_check, contenido, hashchain,
head y recalculan todos los veredictos. No se aceptan aprobaciones del llamador.

Un archivo existente se identifica primero por cabecera SQLite, modo DELETE y
application_id V391. Después se verifica con un authorizer que solo permite
lecturas antes de habilitar escritura. No se cambia el journal_mode de una base
ajena para después rechazarla. La creación usa O_EXCL. Se comprueban directorio,
identidad de archivo, rutas locales, reparse points, hardlinks y sidecars. WAL/SHM
se rechazan; el rollback journal de esta base puede recuperarse bajo el presupuesto.
El authorizer limita SQL, no convierte Python en un sandbox de un propietario
malicioso del proceso/directorio. Recuperación SQLite de un hot journal propio
puede escribir antes de las consultas; no se aplica a un archivo sin esa identidad.

Append exacto repetido devuelve el evento ya confirmado sin duplicarlo; distinto
payload produce OBS_DUPLICATE_CONFLICT. Un fallo antes de COMMIT revierte todo.
Si el COMMIT ocurrió y se perdió la respuesta, reintentar el mismo evento recupera
su registro. Si falla almacenamiento, collect cierra el iterador y el adaptador;
no devuelve eventos sin confirmar. No hay cola en memoria de reintentos indefinidos.

Al reanudar, collect exige otra conexión y añade COLLECTOR_RESTART_GAP a la anterior.
La clave del GAP usa un ordinal libre superior al máximo de esa conexión, incluso
si los últimos eventos llegaron fuera de orden. Desconexión, error de conectividad,
permiso retirado o feed perdido vacían la caché. No se pueden recuperar ticks que
el proceso no recibió. Un journal lleno bloquea nuevas capturas; el host debe
archivarlo y crear una captura nueva mediante un procedimiento posterior.

checkpoint() devuelve metadata/hash y prefijo. El host puede conservarlo fuera de
la base y exigirlo al abrir para detectar pérdida de un prefijo conocido. Sin
ancla externa no se detecta restaurar una copia histórica íntegra de la base.
export() devuelve una tupla de documentos individuales; abrir la misma base y
recalcular history() permite replay sin broker. No se instala un servicio de
backup ni se promete recuperación de archivos perdidos.

## Lectura IBKR aislada y apagada

Approval exige un Grant tipado, HMAC válido con clave aportada por el host,
enabled=true, scope DATA_CAPTURE_ONLY, sesión/entorno/política exactos y vigencia.
El grant liga endpoint loopback, clientId, HMAC del conjunto de cuentas y hash de
una atestación externa de modo, read-only y permisos. No se emite ni provisiona
una aprobación auténtica. Las claves de tests son fixtures públicos sin autoridad.

El modo de sesión y el ajuste read-only de TWS dependen de la atestación externa
del host; este protocolo no ofrece una prueba automática de esos ajustes.
La comparación exacta de managedAccounts verifica identidad, no deduce Paper/Live
del prefijo. Callback de datos y entitlement no sustituyen ese preflight externo.

Antes de crear el socket y antes de cada solicitud/conexión se revalida la
aprobación. Se repite mientras se recibe y después de completar un recv bloqueante.
Un frame que llega tras caducidad/deadline queda como GAP rechazado con digest y
longitud; no se publica como quote. Revocar una aprobación detiene nuevas lecturas.
La limpieza solo cancela la suscripción de datos propia, incluso si ya expiró el
permiso, y cierra el socket. Cerrar el generador también ejecuta esa limpieza.

Negociación exacta157, sin fallback. Preflight: START, cuentas, hora de servidor y
detalles de contrato. Debe recibirse una única respuesta EUR/USD compatible y su
fin antes de solicitar LIVE y suscribirse. Hora de servidor no se usa como hora
fuente de los ticks. Cambios de cuenta, errores1100/1101/1102/1300/2103/2108 y
errores de permisos354/10167/10168/10186 invalidan aunque TCP siga conectado.
La reconexión repite preflight completo con identidad de conexión nueva.

| Opcode de salida permitido | Uso |
|---:|---|
| 71 | START_API, versión2. |
| 17 | Managed accounts, comparación opaca sin almacenar cuentas. |
| 49 | Reloj de servidor, no timestamp fuente. |
| 9 | Detalles EUR/CASH/USD/IDEALPRO. |
| 59 | Solicitar LIVE, sin afirmar que fue concedido. |
| 1 | Suscripción BID/ASK de datos de mercado. |
| 2 | Cancelar esa suscripción de datos. |

La gramática se implementó independientemente; el producto no importa ibapi,
tws.py, broker.py ni laboratorios. Una prueba usa el SDK oficial local10.50.2
como oráculo offline de los siete mensajes; intercepta sendMsg sin connect/run.
El perfil de solicitud declara strike=0.0 para CASH; el SDK actual tiene un
default UNSET_DOUBLE distinto, por lo que la comparación lo fija explícitamente.
Otros tests usan vectores literales, framing fragmentado y callbacks de detalles.
No hay certificación contra TWS real ni afirmación de compatibilidad con otra
versión. El proveedor, su host y sus permisos no se comprobaron en esta entrega.

Fuentes primarias consultadas, contrastadas con client.py, decoder.py,
server_versions.py, comm.py y message.py del SDK instalado:
[documentación oficial](https://www.interactivebrokers.com/docs/tws-api/doc/introduction),
[ticks en vivo](https://www.interactivebrokers.com/docs/tws-api/doc/md/live-ticks),
[recepción watchlist](https://interactivebrokers.github.io/tws-api/md_receive.html)
y [datos retrasados](https://interactivebrokers.github.io/tws-api/delayed_data.html).
La consulta documental no fue una conexión al broker ni captura de mercado.

## Shadow y disponibilidad

observe verifica el journal completo, consume solamente el prefijo cuyo recibido
y as_of ya están disponibles al cutoff, y comprueba de nuevo ese prefijo al final.
No salta filas futuras para usar después filas con UTC menor. generated_at es el
máximo de recepción, validación y generación previa; no se antedata una señal al
instante de recepción si solo se validó después. Recalcula edad de ambos lados y
fuentes en ese instante efectivo antes de decidir la dirección hipotética.

Sin pareja válida o con FROZEN/DELAYED/DELAYED_FROZEN/UNKNOWN devuelve NO_TRADE.
Por defecto tampoco acepta ausencia de timestamp fuente. Permitirla explícitamente
conserva SOURCE_AGE_UNKNOWN, sin cambiar la calidad de origen. Las condiciones
posteriores se registran aparte, con secuencia e instante estrictamente posteriores
a la señal y horizonte acotado. No se insertan hechos posteriores dentro de una señal
antigua. La misma historia/spec/cutoff produce los mismos bytes.

Para Origin.SOCKET se exige otra aprobación scope OBSERVATIONAL_SHADOW_ONLY,
ligada al hash de ShadowSpec y metadatos del journal. Estar autorizado a capturar
no autoriza Shadow. El host aporta el reloj de verificación explícito. No existe
conversión a SyntheticDataset, integración con el catálogo ni aprobación económica.

API reproducible de fixtures: los eventos y su cutoff se construyen explícitamente
como en test_core_v39_validation.py, sin importar fuentes operativas.

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from trading_agent.core_v3.market_observation.contracts import Origin, SessionKind
from trading_agent.core_v3.market_observation.collector import FixtureAdapter, collect
from trading_agent.core_v3.market_observation.journal import Journal
from trading_agent.core_v3.market_observation.shadow import observe

# events: tuple[RawEvent, ...] de fixture; policy, spec y cutoff explícitos.
with TemporaryDirectory() as directory:
    with Journal(Path(directory) / 'fixture.sqlite', policy, 'session-1',
                 Origin.FIXTURE, SessionKind.PAPER) as journal:
        receipt = collect(FixtureAdapter(events), journal, now=lambda: cutoff)
        result = observe(journal, spec, cutoff=cutoff)
        serialized = result.to_json()
        checkpoint = journal.checkpoint()
```

Los fixtures, los tests de transporte y el wrapper completo son los ejemplos
ejecutados. Este fragmento muestra las firmas; no aporta eventos ni autorización
de conexión real. No se registró un launcher de captura.

## Recursos

Defaults: 512 eventos, 16MiB de almacenamiento, 60s de captura, 16 solicitudes,
2 reconexiones máximas y 16384 bytes por frame. Máximos duros: 4096 eventos,
64MiB, 300s, 16 solicitudes y2 reconexiones. Cada documento sigue limitado a
131072 bytes. Shadow permite hasta64 señales y64 condiciones posteriores;
alcanzar límites marca incomplete o produce rechazo controlado por tamaño.

Se reserva una solicitud para cancelar datos antes de suscribir. El presupuesto
de solicitudes se comparte entre reconexiones; tener2 reconexiones permitidas
no garantiza capacidad para todas si se agota ese presupuesto. Timeout de socket2s
y deadline se comprueban durante la recepción. No hay threads ni colas externas.
La persistencia síncrona puede añadir latencia; no se afirma capacidad HFT.

SQLite limita páginas principales a floor((presupuesto−65536)/(3×4096)), dejando
reserva para rollback. Se suma tamaño de base/sidecars antes y después de operar.
Son bytes lógicos y límites de estructuras, no cuotas del sistema de archivos,
RSS portable ni defensa frente a modificar el directorio desde otro proceso.
La verificación completa por append tiene costo creciente y está destinada a
capturas acotadas. La rotación/streaming de producción sigue pendiente.

## Graphify y contraste

Se consultó primero graphify-out/graph.json:424 nodos/1039 links, grafo histórico
sin V3.x. Vocabulario real seleccionado: broker paper quote market data tws.
La consulta BFSdepth2 encontró136 nodos, mostró61 y truncó75 con presupuesto1800.
Se contrastaron PaperDataBroker, quote() y official_wire con las fuentes actuales;
las ubicaciones antiguas no se usan como evidencia de líneas actuales.
La búsqueda del grafo no prueba ausencia de dependencias.

reflect --if-stale fue no-op y se leyeron lecciones existentes. No se reconstruyó
el grafo ni se instaló Graphify; se usó su CLI porque el intérprete de
.graphify_python no tiene ese módulo. No se atribuye costo de extracción histórica
al consumo de esta implementación.

## Revisión y verificación

Se aplicaron senior-software-engineer, Graphify, TDD, implementación incremental
y revisión adversarial con otro agente de contexto separado. Esa revisión es
interna de Codex; no equivale a auditoría independiente del usuario.
El paquete de [revisión externa manual](core-v3-9-external-review.md) no se envió
a terceros ni ejecutó herramientas externas de revisión.

Los primeros tests de cada capacidad fallaron por módulo ausente antes de
implementarla. La revisión interna produjo seis correcciones reproducidas:
deriva acumulada UTC/monotónico, conservación de frames rechazados, identificación
de SQLite ajeno antes de mutarlo, permiso vencido durante recv, reinicio tras7,6
y frescura recalculada al generated_at. Sus regresiones quedaron en los tests nuevos.

Un intento de abrir SQLite por URI fue bloqueado por el guard histórico; se
cambió solo el nuevo journal a rutas canónicas, cabecera y authorizer de lecturas.
No se debilitó ninguna barrera para obtener verde. Otra incidencia de desarrollo
fue un handle del fixture SQLite sin cerrar; el test nuevo ahora lo cierra con
contextlib.closing. No se alteraron pruebas antiguas.

Sensibilidad: cambiar temporalmente el control de tipo LIVE de Shadow por False
provocó1 fallo en6 pruebas, porque FROZEN generaba LONG. Finalmente se restauraron
los bytes y se comprobó el mismo SHA-256 antes/después de la mutación. Es un
experimento puntual, no una puntuación global de mutation testing.

Ejecución final desde la raíz, con el código de64720cb:

```powershell
.venv/Scripts/python.exe -B python/tests/core_v39_offline_check.py
```

**394 pruebas pasadas en266.313s, exit_code=0**.
OFFLINE_BARRIER_VIOLATIONS:0; V39_OFFLINE_BARRIER_VIOLATIONS:0.

| Grupo | Pasadas |
|---|---:|
| V3.9 validación de quotes/relojes | 6 |
| V3.9 journal/transacciones/recuperación | 7 |
| V3.9 protocolo y aprobación externa | 6 |
| V3.9 colección simulada/transcripts | 6 |
| V3.9 Shadow | 6 |
| V3.9 seguridad y regresiones adversariales | 13 |
| V3.9 transporte con dobles de bytes | 5 |
| Total nuevo V3.9 | **49** |
| Regresiones V3.1–V3.8, Forex e AI anteriores | **345** |
| Total conjunto final | **394** |

Una pasada conjunta intermedia anterior ejecutó391 pruebas en268.590s con OK y
ambos contadores0. Después se añadieron tres regresiones y se repitió la suite
completa sobre el código final, no solamente los tests nuevos. El wrapper conserva
las selecciones previas y añade test_core_v39_*.py, sin editar los guards antiguos.
Se bloquean eventos socket, subprocesos/os.system/os.startfile, acceso a.local y
SQLite fuera del temporal canónico. No se afirman suites ajenas al wrapper.
La barrera es evidencia del proceso de prueba, no un sandbox de producción.
Ninguna prueba autoriza activar el lector.

## Inventario actualizado del backend

[core-v3-9-backend-inventory.json](core-v3-9-backend-inventory.json) enumera473
archivos:456 de la base y17 adiciones backend/tests. Incluye ruta, grupo, estado,
bytes, líneas, SHA-256 e imports/declaraciones Python. Se contrastaron los456
hashes base: cero diferencias. Incluye los seis proyectos .NET, sus referencias
y propiedades heredadas net9.0; no son evidencia de compilación o disponibilidad.
Excluye frontend/docs/.local/entornos/artefactos ignorados y documentos untracked.

| Grupo | Archivos | Estado al entregar |
|---|---:|---|
| Core V3.1–V3.3 | 11 | Base auditada por usuario; contratos, economía y orquestación preservados. |
| Core V3.4 | 5 | Declarativo causal, preservado. |
| Core V3.5 | 5 | Catálogo durable de investigación, preservado. |
| Core V3.6 | 6 | Backtester exclusivamente sintético, preservado. |
| Core V3.7 | 8 | Estadística exclusivamente sintética, preservada. |
| Core V3.8 | 8 | Custodia/calidad; esquema de proveedor real todavía pendiente. |
| Core V3.9 | 9 | Implementado y probado offline; auditoría independiente pendiente; lector real deshabilitado. |
| Python histórico | 95 | Datos, broker, Kronos, R20, equity, laboratorios; no recertificados operativamente. |
| AI strategy researcher | 29 | Proveedores, Sol, memoria y simulación históricos; no integrados ni ejecutados. |
| Forex research histórico | 4 | Preservado;28 regresiones incluidas. |
| Tests/wrappers Python | 130 | Selección base intacta más8 archivos V3.9. No se afirma haber ejecutado todas las suites ajenas al wrapper. |
| Soporte/dependencias Python | 1 | Sin editar ni instalar dependencias. SDK existente usado solo como oráculo test. |
| TradingAgent.Api | 23 | Endpoints/servicios existentes; no iniciados. |
| TradingAgent.Core | 19 | Riesgo/dominio históricos; no recertificados. |
| TradingAgent.Infrastructure | 25 | Stores/PostgreSQL y11 migraciones SQL; ninguna ejecutada. |
| ConfigurationLab / ResearchLab | 2 /4 | Históricos; no ejecutados. |
| Tests .NET | 35 | Intactos; no ejecutados. |
| Schemas / configuración | 3 /22 | Intactos; no activados. |
| Scripts históricos | 27 | Intactos; no ejecutados. |
| Solución/build | 2 | Intactos; no build .NET. |

| Pendiente para completar backend | Condición |
|---|---|
| Activación de lectura IBKR | Autorización específica futura, host confiable, evidencia externa de sesión/read-only/permisos y recertificación real del protocolo. |
| Shadow auténtico | Aprobación separada ligada a hipótesis/journal; revisión de fuente y límites. |
| Dukascopy/datos históricos reales | Muestra original, esquema/calendario y evidencia; V3.8 no admite aún el formato auténtico. |
| Dataset enero2024–diciembre2025 | No aportado ni validado; continuidad y procesamiento por lotes pendientes. |
| Backtest/estadística con datos reales | Fase y auditoría específicas; no hay puente desde V3.9 ni se salta SyntheticDataset. |
| Régimen, ranking y selección | Evaluación causal/versionada y comparabilidad pendientes. |
| Sol/Kronos controlados | Proveedores autorizados, presupuesto durable, fallos inciertos e integración V3 pendientes. |
| Cartera y riesgo agregado | Capital compartido, reservas y única autoridad operativa pendientes. |
| Python/.NET | Contratos entre procesos y separación de roles/autoridad V3 pendientes. |
| Operación IBKR | Intenciones, SDK falso, conciliación y guardias operativas pendientes. |
| Persistencia/observabilidad | Rotación, archivo durable, anclas externas, métricas, backup y recuperación integral pendientes. |
| Paper/Live/despliegue | Validaciones y autorizaciones propias; ninguna concedida aquí. |

## Git y límites de entrega

Commits locales:90b9dd4 contratos/validador/journal y diseño previo;
8bc7ef1 lector aislado/Shadow;64720cb recuperación/frescura/procedencia.
Un commit de documentación registra el cierre y se informa al entregar.
Todo el diff frente a542f250 es aditivo. No se tocaron las671 rutas tracked de
la base ni se añadieron los dos documentos preexistentes sin seguimiento.
No hubo reset/clean/stash, push, merge ni despliegue. Revertir commits específicos
permite retirar código después de revisar el árbol; no borrar journals ni datos
del usuario. Esta entrega no creó bases persistentes dentro del proyecto.
Resultado:20 rutas añadidas (9 módulos,8 archivos de tests/wrapper y3 documentos),
sin modificaciones/eliminaciones/renombres de la base. git diff --check pasó.

SHA-256 finales de los dos documentos que permanecen untracked:

- docs/architecture/core-v3-phase0-audit.md:
  419d1e97b7f7017bddebd3074b1433d48702a59a274194f017129933e4314537.
- docs/manual/TradingAgent_Manual_Tecnico_Integral.pdf:
  1f31321892f532b3d5de1bc3d574bd5f66c3af38ae634d7173b6b173c49b3944.

No hubo captura auténtica, acceso a secretos/.local, inferencia, orden Paper/Live,
servicio/API/.NET o migración. No se acredita latencia de mercado, autenticidad
criptográfica del proveedor, seguridad frente a dueño del host ni restauración
total sin anclas/backup externos. **V3.9 queda NO_TRADE y pendiente de auditoría
independiente. V3.10 no se inicia.**
