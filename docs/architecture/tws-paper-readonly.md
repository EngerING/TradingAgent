# TWS Paper: integración de datos de solo lectura

Informe histórico de la integración inicial. Para el estado actual, autorización y recuentos reales, véase [primera lectura auténtica de IBKR Paper](paper-authentic-data-validation.md).

Fecha: 2026-10-04 (America/La_Paz). **Entrega implementada con diagnóstico real; demostración operativa pendiente. LIVE_TRADING deshabilitado y ninguna orden enviada.** Las entregas A/B, su capital virtual de US$100 y su presupuesto de pérdidas acumuladas de US$20 se conservan.

## Evidencia y estado de la entrega

| Elemento solicitado | Resultado verificable |
| --- | --- |
| 1. Conexión | TWS ejecutándose; TCP 7497 abierto; handshake oficial y managedAccounts recibidos. Sesión de diagnóstico cerrada ordenadamente. Colector operativo deshabilitado. |
| 2. SDK | `ibapi 10.50.2`, Python 3.13, `protobuf 5.29.5`, instalados en `.venv`. Imports EClient/Contract ejecutados. Fuente descargada de IBKR; no se instaló ibapi desde PyPI. |
| 3. Puerto | Exclusivamente `127.0.0.1:7497`; clientId 73. No fallback a Live/Gateway. |
| 4. Identidad Paper | API devolvió una identidad enmascarada `***3784`, identificador interno `PAPER-a5d83c14f37c1e49`. **Descubierta, no autorizada**: falta la cuenta completa configurada por el propietario y confirmar Paper/Read-Only. |
| 5. EUR/USD | Contrato y lectura implementados; disponibilidad real de datos y permisos **no comprobada**. |
| 6. Temporalidades | 15m, 1h y 4h implementadas y probadas con dobles de prueba; ninguna serie real recuperada todavía. |
| 7. Registros | Base Paper segura: cero observaciones/velas IBKR reales. PostgreSQL desechable: persistencia, deduplicación, conflicto, snapshots y tres series sintéticas comprobadas. |
| 8. Pruebas | Compilación sin errores/advertencias; suite C# completa y suite Python ejecutadas. Detalle y recuento final abajo. |
| 9. Errores | Extracción MSI 1603: se usó el mismo código Python de la distribución ZIP oficial. El sandbox impidió arrancar PostgreSQL de pruebas y terminar un árbol de procesos de prueba; se ejecutaron esas acciones con permiso revisado. Arranque con rol limitado falló por CREATE en public: corregido con verificación de migraciones sin DDL. |
| 10. Configuración pendiente | Identidad Paper exacta autorizada; atestaciones de Paper/Read-Only; activar colector; ejecutar demostración real y verificar permisos de datos. No hacen falta credenciales IBKR en código. |
| 11. Cuenta real | Aislada: no conexión a puerto Live, rechazo de identidades adicionales/desconocidas, sin ejecutor ni ruta de órdenes. No se ha validado viabilidad real de EUR/USD con US$100. |
| 12. Siguiente entrega | Completar la demostración Paper de datos y validar calendario de sesiones, permisos, incrementos de mercado y costos reales antes de considerar estrategias ejecutables. |

Diagnóstico reproducible guardado en `artifacts/ibkr/diagnostic.json`. Registró handshake true, servidor API 226, SDK 10.50.2 y eventos informativos 2104. La instalación TWS contiene `jts4launch-1051-windows-x64...`; esto es evidencia del build instalado, no prueba exhaustiva de compatibilidad. El handshake acredita negociación para esa sesión; la decodificación de saldos/mercado queda pendiente.

Distribución Python oficial: `https://interactivebrokers.github.io/downloads/twsapi_macunix.1050.02.zip`. SHA256 del archivo descargado: `673129e5cba58c4d77bc40647265f84ea42f605eccf88fa4c1221d62d12454f3`. Este hash registra el artefacto usado, no representa una firma del proveedor. Se extrajo únicamente `IBJts/source/pythonclient` en `.local/sdk/source` y se instaló su `setup.py` en `.venv`; dicho archivo exige protobuf 5.29.5. El código Python es portable; no se instalaron componentes Java/C++ de Mac/Linux en Windows.

## Arquitectura y límites

Graphify se consultó antes de editar. El grafo existente señaló `PaperDataBroker`, `official_wire`, `PostgresStore`, `RiskPolicy`, `AccountState` y `VirtualCapital`; su consulta amplia truncó resultados, por lo que se verificaron selectivamente esos archivos. El índice anterior no describe automáticamente los nuevos componentes.

`python/trading_agent/broker.py` conserva el gate de Paper: cuenta exacta, puerto confirmado, entorno Paper y atestación del propietario. Ahora también exige solo lectura y prohíbe el puerto 7496 incluso si se configura como confirmado. La validación del prefijo DU es un filtro adicional; la autorización depende de la coincidencia completa y las atestaciones, nunca del prefijo, la terminación o el puerto.

`python/trading_agent/tws.py` amplía el transporte existente: negociación y callbacks con timeout, clientId, managedAccounts, saldos y Currency textual separados de montos, posiciones, contractDetails y errores por código sin texto sensible. Una nueva identidad o pérdida de conectividad invalida inmediatamente las lecturas. Los métodos SDK de envío/cancelación de órdenes, cancelación global, ejercicio, what-if vía placeOrder y sus variantes protobuf están bloqueados antes de serializar. El adaptador público no expone esos métodos.

`paper_feed.py` mantiene una conexión, publica observaciones NDJSON en stdout y recibe únicamente shutdown por stdin. Reconecta con espera creciente y detiene la sesión ante rechazo de cuenta/permisos. No recibe credenciales de base de datos ni token administrativo. No hay fallback a cotizaciones simuladas. El modo diagnóstico solamente descubre identidades enmascaradas; no habilita lecturas de saldo ni mercado.

`PaperFeedService` arranca ese proceso desde una ruta local configurada por el operador, controla su vida útil, valida cuenta interna y esquemas con `PaperData`, y persiste mediante `PostgresStore`. Rechaza campos desconocidos, OHLC inválido, timestamps futuros, datos no finitos/incompletos y cualquier capacidad Live/orden. Los fallos invalidan el estado conectado; una fila histórica CONNECTED nunca prueba que una nueva instancia esté conectada. Hay watchdog de 90s, cierre por stdin con límite de 20s y terminación del proceso como último recurso.

La migración aditiva `003_paper_observations.sql` añade snapshots de estado, cuenta, posiciones, contrato, cotización y eventos. Reutiliza `market_candles`, su índice único y la identidad interna `PAPER-*`. Las velas tienen clave determinista; repetirlas no duplica registros. Una versión diferente de la misma vela provoca conflicto y rollback, nunca overwrite silencioso. No se alteran migraciones previas ni estados de capital virtual.

El clúster `.local/postgres-paper` usa loopback:55433 y SCRAM. Los dos secretos locales quedan cifrados con DPAPI en archivos ignorados por control de versiones. `paper_migration` se usa solamente para migrar/crear el rol; `paper_data` puede SELECT/INSERT en observaciones/velas y SELECT en schema_migrations. Se comprobó que carece de UPDATE en paper_observations y account_states. `TRADING_DB_AUTO_MIGRATE=false` hace que el backend compruebe checksums sin intentar CREATE. No usar el clúster sintético con trust para datos de bróker.

Las rutas GET internas heredan Bearer auth y se vinculan explícitamente a loopback:5080. Configuración externa de endpoints Kestrel se rechaza y el middleware rechaza direcciones remotas. No existe un endpoint de envío de órdenes. El rol limitado de la base Paper no puede usar rutas de escritura de simulación; las entregas A/B siguen disponibles al ejecutar la API contra su base de simulación con sus permisos habituales.

## Datos de mercado

EUR/USD se consulta como EUR, USD, CASH, IDEALPRO. contractDetails valida conId, divisas, tipo, mercados e incremento mínimo y conserva horarios, zona, marketRuleIds y tamaños cuando el SDK proporciona valores válidos. `restrictions_verified=false` impide presentar esos metadatos como prueba de viabilidad o permiso de operar con US$100. La descarga de market rules y una evaluación comercial completa quedan pendientes.

Se permite observar datos REALTIME, DELAYED, FROZEN y UNAVAILABLE. marketDataType 4 conserva su código y se etiqueta FROZEN (delayed-frozen). Bid/ask/last se validan; se calcula spread y se guardan tiempos UTC de recepción por lado. Cambiar el tipo descarta ticks previos. **La recepción local no acredita hora de origen**: `source_timestamp=null` y `executable=false` en toda cotización de esta entrega. Las respuestas indican desconexión/antigüedad (`stale`) y nunca autorizan señales u órdenes.

Históricos: MIDPOINT, formatDate=2, UTC, 15 mins/1 hour/4 hours, páginas de siete días hasta treinta días en el transporte. El colector carga siete días y refresca cada quince minutos, en serie con al menos dieciséis segundos entre solicitudes históricas por sesión. Los errores de pacing no crean un bucle de reintentos de históricos. Se guardan únicamente velas cerradas, con OHLC válido, sin inventar volumen ni llenar huecos. Se retiene la apertura nativa de IBKR; no se realinea una sesión 4H a UTC generando barras sintéticas. El analizador previo exige alineación y continuidad; no se le conectan automáticamente estas series hasta validar el calendario Forex.

## Verificación ejecutada

- `scripts/verify.ps1`: **76 pruebas C# aprobadas, cero omitidas**, con `TRADING_TEST_DB` al clúster desechable 55432; regresiones de capital, viabilidad, idempotencia y PostgreSQL incluidas. Después se añadió una prueba del SDK real sin conexión; la suite Python final contiene **43 pruebas aprobadas**.
- `scripts/smoke-api.ps1`: aprobado; incluye autenticación, simulación, capital, parada de emergencia y reinicio del proceso.
- `scripts/smoke-paper-api.ps1`: aprobado con **TEST_DOUBLE**, PostgreSQL real y proceso Python separado; cuenta/saldos/posiciones/contrato/cotización congelada, una vela por timeframe tras solicitudes repetidas, endpoints, rechazo 401 y ausencia 404 de ruta de órdenes; conserva velas tras reinicio abrupto del backend.
- `PaperFeedTests`: inicio, desconexión ordenada y nuevo inicio del servicio con proceso Python y PostgreSQL reales; transporte de IBKR sustituido explícitamente por fixture sintético.
- Base Paper con rol limitado: migraciones aplicadas, arranque de API con colector deshabilitado y permisos SQL comprobados; cero datos reales guardados.
- Diagnóstico TWS real: imports, socket, handshake, serverVersion y managedAccounts; ninguna lectura operativa ni orden.

| Caso obligatorio | Evidencia ejecutada | TWS real |
| --- | --- | --- |
| 1. TWS disponible | Diagnóstico SDK con handshake | Sí, diagnóstico |
| 2. Puerto incorrecto | Gate unitario rechaza 7496 sin conexión | No se conecta a Live para probarlo |
| 3. TWS desconectado | Wire desconectado/fallos de conexión con mocks | No se detuvo el TWS del propietario |
| 4. Handshake incompleto | Negociación/callback ausente con mocks y timeout | No inducido en TWS |
| 5. Paper autorizado | Coincidencia exacta con mock | Pendiente autorización completa |
| 6. Cuenta desconocida | Unitario; se invalida conexión | Pendiente operativo |
| 7. Cuenta Live | Unitario; rechazo de U/additional accounts | No conexión Live |
| 8. Saldos | Mock de callback, esquema C#, pipeline/API | Pendiente |
| 9. Persistencia velas | PostgreSQL real con fixture | Pendiente velas reales |
| 10. Duplicados | PostgreSQL, replay y conflicto | Pendiente dataset real |
| 11. Frozen | Callbacks y endpoint con fixture; executable=false | Pendiente |
| 12. Datos incompletos | Unitarios de saldos, quote, OHLC/timestamps | Pendiente |
| 13. Reconexión | Backoff y caída con mocks; nuevo proceso | No inducida en TWS |
| 14. Reinicio backend | API/proceso real con PostgreSQL y fixture | Pendiente colector real |
| 15. Límite pérdidas | Regresiones PostgreSQL A/B y smoke API | Independiente de IBKR |
| 16. Toda orden bloqueada | Guards unitarios, SDK instalado sin socket y ruta API inexistente | Cero órdenes enviadas |

## Completar la demostración real

En TWS, el propietario debe verificar modo Paper y cuenta completa, Enable ActiveX and Socket Clients, puerto 7497 y Read-Only API marcado. No desmarcar Read-Only ni configurar credenciales de inicio de sesión dentro del proyecto. Véase [configuración oficial de IBKR](https://interactivebrokers.github.io/tws-api/initial_setup.html).

Desde la raíz del proyecto, después de la confirmación del propietario:

```powershell
.\scripts\paper-database.ps1 -Action Start
$env:PYTHONPATH = Join-Path (Get-Location) 'python'
# Introducir la identidad completa autorizada, no la terminación ni un valor descubierto automáticamente.
$env:IBKR_PAPER_ACCOUNT = Read-Host 'Cuenta Paper completa autorizada'
$env:IBKR_PAPER_ATTESTED = 'true'
$env:IBKR_READ_ONLY_ATTESTED = 'true'
$env:IBKR_PORT = '7497'
$env:IBKR_VERIFIED_TWS_PORT = '7497'
$env:IBKR_CLIENT_ID = '73'
$env:LIVE_TRADING = 'false'
.\scripts\smoke-paper-api.ps1 -RealTws
```

El script realiza consultas, verifica persistencia a través de los GET y cierra su API/colector al terminar. No modifica TWS ni transmite órdenes. Una cotización UNAVAILABLE debe registrarse como limitación; no se sustituye. La prueba solo demuestra las fases que realmente obtengan respuestas y datos guardados. Para mantener la API después de verificarla, configurar `IBKR_DATA_ENABLED=true` y un `TRADING_ADMIN_TOKEN` aleatorio de al menos 32 caracteres y ejecutar el backend; terminarlo con Ctrl+C para desconexión ordenada.

Para tests sintéticos, usar únicamente `TRADING_TEST_DB` al clúster de pruebas y omitir `-RealTws`. Los tests no autorizan cuentas Paper reales. Cerrar los clústeres iniciados por esta tarea con `paper-database.ps1 -Action Stop` y `test-database.ps1 -Action Stop`; los archivos se conservan.

Documentación primaria utilizada: [SDK oficial](https://interactivebrokers.github.io/), [negociación de conexión](https://www.interactivebrokers.com/docs/tws-api/doc/connectivity/verify-api-connection), [Account Summary](https://www.interactivebrokers.com/docs/tws-api/doc/account-portfolio-data/account-summary/requesting-account-summary), [tipos de mercado](https://www.interactivebrokers.com/docs/tws-api/doc/market-data-delayed/market-data-type-behavior) y [históricos EUR/USD](https://www.interactivebrokers.com/campus/ibkr-quant-news/how-to-retrieve-equity-data-through-the-python-api/).

**La fase no se declara completada.** Falta evidencia de la cuenta exacta autorizada, saldos, posiciones, contrato EUR/USD, quotes/históricos reales, almacenamiento y recuperación desde la API interna. El diagnóstico y los dobles de prueba no sustituyen esa demostración.
