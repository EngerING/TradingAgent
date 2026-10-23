# M03-A.2 — Historical backfill DATA_ONLY

Base: b7129313f216b24184c54f519fbc761c151bc101. OFFLINE / NO_TRADE.
Diseño registrado antes de implementar. Sin TWS auténtico, merge ni M03-B.

Paquete hermano market_data/backfill: contratos v1, planificación/wire estrecho,
lector histórico, persistencia/publicación y consumidor paginado. Observation v1,
los módulos M03-A, Core y los motores financieros se conservan.

El intervalo inicial es explícito: de uno a siete días UTC completos, [start,end),
sin fechas predeterminadas. 15m se segmenta por día, 1h hasta cuatro días y 4h
hasta siete días. Cada respuesta admite como máximo 128 barras/16384 bytes.
Una semana requiere diez solicitudes históricas, cuatro de preflight y reserva
de cancelación, dentro del máximo original de 16 solicitudes por conexión.
Una sola solicitud pendiente, separación conservadora de 20 s UTC y monotónica,
y reanudación con enfriamiento durable. Los límites de barras pequeñas documentados
por IBKR no se presentan como obligatorios para estas temporalidades: son una
política local conservadora adicional al throttling del proveedor.

El lector solo solicita START, cuentas para comparación opaca, hora y detalles,
históricos MIDPOINT y su cancelación. No pide quotes ni interpreta históricos como
LIVE. Un permiso nuevo firmado por el host liga el grant de captura, configuración,
intervalo y temporalidades; los permisos M03-A anteriores no habilitan este modo.
Paper/Live sigue dependiendo de la atestación y comparación exacta de identidad.

Archive se utiliza en un subdirectorio nuevo capture/, con su escritor exclusivo,
eventos originales y veredictos transaccionales. Los diagnósticos BACKFILL_* son
hermanos de HISTORY_* y no alteran la proyección existente. Solo registros aceptados
pueden contribuir a las barras. Los planes se confirman antes de enviar; el replay
reconstruye páginas terminadas y reintentos sin duplicar muestras. No se modifican
journals existentes ni se borran históricos automáticamente.

Las páginas son inmutables y direccionadas por hash. El manifest se publica al final
mediante reemplazo atómico después de COMMIT/verificación; puede seguir utilizándose
el prefijo publicado anterior durante una escritura. El consumidor solo abre JSON
acotado, nunca SQLite, y liga páginas/cursor al manifest, origen y entorno. Una
página contiene como máximo 64 barras; el escritor conserva como máximo 2048 muestras
y el presupuesto total propio es 16 MiB. No se amplía Observation ni sus 128 barras.

Completitud exige cobertura temporal explícita y continuidad de las sesiones del
calendario observado. No se infiere una semana Forex fija. tradingHours auténtico
puede carecer de cobertura histórica: en ese caso se conserva CALENDAR_UNKNOWN y
HISTORICAL_PARTIAL, aunque existan barras. Alineaciones nativas no verificadas,
respuestas parciales, precios conflictivos, futuros o fuera del intervalo no se
reparan con interpolación. Disponibilidad no se antedata a la hora del mercado.

Fuentes oficiales consultadas: [barras históricas TWS](https://www.interactivebrokers.com/docs/tws-api/doc/md/historical-bars)
y [límites y step sizes legacy](https://interactivebrokers.github.io/tws-api/historical_limitations.html).
El wire 157 se contrasta offline con el SDK local como oráculo; no certifica TWS real.

La CI conserva los 507 casos y añade pruebas de contratos, semana abierta/cerrada,
segmentación, cuotas, calidad, cierres, recuperación, publicación y consumo Windows.
Un guard nuevo compara todos los objetos de la base salvo su dispatcher de CI;
no se debilitan las barreras históricas. Los resultados locales se detallan abajo;
la ejecución remota se conserva en los artefactos y en el PR Draft.

## Contratos y consumo

BackfillSpec, Window, HistoricalPermit, HistoricalBar, Page, PageRef, Dataset y
PageCursor usan schema_version=1, JSON cerrado, dataclasses frozen/slots y Decimal.
La identidad del almacén liga configuración de captura, sesión, origen y entorno;
cada ejecución añade BACKFILL_AUTH_CONTEXT con spec y hash del permiso. No guarda
su clave ni cuentas. El fold propio coteja el plan wire con su contexto autorizado,
su ventana y conId. Los planes rechazados no autorizan batches posteriores.

HistoricalBar conserva Bar (timestamp original, OHLC, recepción disponible, calidad
y hash del frame), contrato, origen/entorno, ventana/requestId, conexión, recepción
y hash de su registro durable. No incluye volumen inventado, P&L ni indicadores.
Dataset declara instrumento/fuente, intervalo/temporalidades, última disponibilidad,
estado, incertidumbre, referencias a páginas y head del journal. feed_type=UNKNOWN,
indicators_evaluated=false y execution_authorized=false permanecen explícitos.

Los requestId de conexión no son identidad durable de un período. El fold mantiene
cobertura por (temporalidad,día UTC) acreditada por respuestas aceptadas y las
sesiones observadas. Un spec posterior compatible en el mismo directorio conserva
los originales y pide solo los días incompletos, agrupándolos según step size.
Cambiar rango exige otro HistoricalPermit ligado al nuevo spec; no amplía el viejo.
Una respuesta parcial puede reconsultar su día, con comparación OHLC y exclusión
permanente de conflictos. Treinta planes como máximo en todo el almacén, tres
intentos por ventana, máximo dieciséis segmentos y límites heredados adicionales.
El host debe coordinar otros clientes IBKR; Python no aísla al dueño del host.

El plazo mínimo configurado se valida contra el plan y pacing; una semana completa
usa CapturePolicy.max_duration_seconds=300. Un grant conserva cuatro solicitudes
de preflight y una reserva de cancelación por conexión, incluso tras caída. La
reanudación exige 600 s UTC desde el último plan durable y no reusa grants agotados.
La aprobación se revisa antes de socket, solicitudes y tras recv bloqueante.
El enfriamiento y los presupuestos no son compartidos con programas ajenos al host.

Ejemplo de lectura sin red, sobre un directorio de fixtures ya generado:

```python
import hashlib
from trading_agent.market_data.backfill.store import HistoricalConsumer

# spec, directory, cutoff y entorno son explícitos y coinciden con la captura.
consumer = HistoricalConsumer(directory, spec, 'session-1', origin, environment)
page = consumer.read(15, spec.start, spec.end, as_of=cutoff, minimum_bars=200)
snapshot = hashlib.sha256(page.dataset.to_json().encode()).hexdigest()
cursor = page.next_cursor
# La suficiencia es solo recuento solicitado y completitud, nunca aprobación de RSI/EMA.
while cursor:
    page = consumer.read(15, spec.start, spec.end, as_of=cutoff,
                         minimum_bars=200, cursor=cursor, snapshot=snapshot)
    cursor = page.next_cursor
```

El cursor liga SHA del manifest, consulta completa/cutoff y posición. Los snapshots
inmutables se conservan; se rechaza una generación posterior a as_of. Consultar el
snapshot anterior es explícito, sin ocultar hechos futuros dentro de señales viejas.
El consumidor carga como máximo una página de trabajo y la página devuelta; recorre
las referencias para contar barras en el rango. Un cambio de manifest durante lectura
produce rechazo controlado. El manifest actual debe coincidir con su copia inmutable.
Un hash no autentica IBKR. Sin ancla externa no se detecta restaurar una copia antigua
íntegra; conservar un cursor/snapshot externamente permite exigir ese prefijo conocido.

## Windows y validación supervisada posterior

Desde la raíz, sin contactos con TWS:

```powershell
./build/historical-backfill/run-approved.ps1
.venv/Scripts/python.exe -B python/tests/m03a2_offline_check.py
.venv/Scripts/python.exe -B build/historical-backfill/concurrency-check.py
```

El primer comando es DISABLED/OFFLINE por defecto. Solo después de una aprobación
operativa futura y recertificación del wire, el host confiable podrá preparar fuera
del repositorio spec.json, capture-grant.json, historical-permit.json, signatures.json
y verification.key, con ACL de propietario/SYSTEM/Administradores. No se provee una
autoridad auténtica ni se firma un permiso operativo aquí. El script revisa ACL;
Python revisa rutas, contratos, firmas, ámbito, endpoint/sesión y vigencia.

Comando futuro supervisado, **no ejecutado en esta entrega**:

```powershell
./build/historical-backfill/run-approved.ps1 `
  -ApprovalDirectory 'C:\TradingAgentHost\history-approval' `
  -DatasetDirectory 'C:\TradingAgentHost\history-capture' `
  -ApprovedHistoryOnly
```

Antes de ese comando: verificar externamente Paper/Live, read-only, permisos de datos,
cuentas exactas, clientId y sesión. Confirmar TWS/SDK y perfil157 mediante prueba de
lectura aprobada; comprobar volumen/layout de respuestas y alineación nativa de barras.
tradingHours puede no cubrir el pasado: no suplirlo con una semana supuesta. Comparar
una muestra con una fuente del proveedor y conservar evidencia de calendario. Detener
con Ctrl+C; se cierra el socket y solo se cancela la petición histórica propia pendiente.
No borrar páginas/journals al detener. Un almacén lleno requiere archivo por el host
y una captura nueva; esta fase no implementa rotación/borrado ni backup automático.

## Revisión y límites

La revisión interna con un agente separado reprodujo dos errores de calendario/grid;
otra regresión detectó un manifest alterado sin contraste con su generación inmutable.
Sus pruebas fallaron antes de la corrección y pasan tras ella. La sensibilidad puntual
deshabilitando el vínculo de manifest fue detectada y se restauraron los bytes exactos.
No representa un mutation score global ni una auditoría independiente.

Graphify: grafo histórico 424 nodos/1039 enlaces, consulta broker paper quote market
data tws, presupuesto700, 136 encontrados/24 mostrados/112 truncados. No contiene
M03-A.2; se contrastaron fuentes actuales. reflect --if-stale fue no-op; sin reconstruir.

Limitaciones: intervalos iniciales de días UTC completos (1–7), perfil legacy157,
una solicitud pendiente, fase de barras verificada contra inicio de sesión declarado,
límites estrictos de frames y capturas locales pequeñas. Mayor respuesta del proveedor
o alineación no certificada falla cerrada; no se fragmenta ni rellena inventando barras.
Las medidas de fixture no son latencia de mercado, HFT ni límites portables de RSS.
Los procesos Windows de prueba no son un sandbox frente a un host malicioso.

Si la apertura falla antes del primer CONNECTED, se publica únicamente un estado
local HISTORICAL_UNAVAILABLE con BACKFILL_CONNECTION_OR_VALIDATION y cero eventos
durables. No se fabrica una conexión ni se afirma conservar un frame no recibido.

## Verificación y preservación de entrega

Código y tests: commit 10e0a5b; la documentación/evidencia se añade en un commit
posterior. Ejecuciones locales Windows, sin conexión TWS, fallos ni omisiones:

| Grupo distinto | Aprobadas |
|---|---:|
| Core V3.9 y regresiones previas | 394 |
| Market Analyst | 38 |
| M03-A / M03-A.1 | 72 |
| Procesos Windows anteriores | 3 |
| Nuevas unidades M03-A.2 | 42 |
| Nuevos procesos Windows M03-A.2 | 2 |
| Total | **551** |

Los 507 casos anteriores se ejecutaron de nuevo. El wrapper nuevo ejecutó los 42
casos en 134.828 s; después de reforzar dos aserciones de entorno/lectura sin
escritura, se repitieron esos dos casos y pasaron. La CI ejecuta el conjunto exacto
del commit publicado y exige también sus identificadores distintos y cero skips.
Los contadores de las barreras de red, subprocesos no autorizados, rutas privadas
y SQLite ajeno quedaron en cero en los caminos comprobados.

Reproducción de la verificación conjunta: ejecutar los tres wrappers históricos,
build/market-data/concurrency-check.py, los dos comandos nuevos de pruebas indicados
arriba y, finalmente, build/historical-backfill/verify-results.py. El workflow
.github/workflows/m03a2-historical-backfill-ci.yml ejecuta esa secuencia en
windows-2025 con Python 3.13.5 y oráculo SDK 10.50.2 offline, dependencias con hashes,
acciones oficiales fijadas por SHA, contents:read y credenciales checkout desactivadas.
La retención de artefactos es 14 días; no contiene aprobaciones ni muestras reales.

[Evidencia de entrega](m03a2-evidence.json) registra hashes, resultados y límites.
Los 984 archivos de la base se compararon por SHA-256 local: 983 idénticos y solo
build/market-data/preservation.py modificado para delegar al guard de esta fase.
El guard compara todos los blobs y modos Git de esos 983 archivos con b7129313,
además de los objetos protegidos de Core, Market Analyst, M03-A, frontend y backend.
Los tres documentos/scripts preexistentes sin seguimiento conservan sus hashes y
no se incluyen en los commits. main y develop no se modifican en esta entrega.
El diff autorizado contiene 19 adiciones y ese único cambio de infraestructura.

El módulo permanece apagado. No hay muestra auténtica ni certificación TWS real;
CI acredita fixtures, integridad y aislamiento de los caminos probados. La revisión
adversarial fue interna; la auditoría independiente del PR sigue pendiente. Por
elección del usuario no se prepara paquete de revisión externa ni se envía código.

Para iniciar M03-B se requiere auditoría independiente de este PR, aprobación propia
y contratos de investigación causal que consuman estados/procedencia/suficiencia. Esta
entrega no inicia M03-B ni conecta datos reales a motores sintéticos o financieros.
