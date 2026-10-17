# TradingAgent — núcleo de investigación y simulación

Base funcional para investigación Forex. Preservación del capital primero. **No admite envío de órdenes y Live está bloqueado en código.** OpenAI, Telegram y el dashboard no están activados.

Estado actual: [entregas A/B: capital virtual y viabilidad](docs/architecture/virtual-capital-and-feasibility.md), [entrega C: primera lectura auténtica IBKR Paper](docs/architecture/paper-authentic-data-validation.md) y [entrega D: investigación automática EUR/USD](docs/architecture/eurusd-automatic-research.md). Base anterior: [informe de fase 2](docs/architecture/phase2-implementation.md). Riesgo en C#; indicadores en Python; backtest D con el motor de riesgo C# existente; persistencia PostgreSQL; API ASP.NET Core local autenticada. La lectura Paper real se verificó con autorización manual local; Live y órdenes permanecen bloqueados.

La asignación virtual es US$100, con presupuesto acumulado de pérdidas US$20, independiente del saldo IBKR. La política `research-capital-v3` conserva límites diarios/semanales/drawdown más estrictos. Las ganancias permiten composición, pero no reponen pérdidas netas acumuladas. La admisión exige evidencia de costos, comisión de cierre, margen y contrato; datos incompletos o congelados bloquean entradas. Todas las pruebas actuales son sintéticas, incluidas las de tarifas cero.

## Requisitos

- SDK .NET 9 (verificado con 9.0.316).
- Python 3.11 o posterior (verificado con 3.13.5). Para el calendario D instalar `python/requirements-research.txt` en `.venv` (`tzdata` para DST en Windows).
- PostgreSQL 17 para API y pruebas de persistencia. No se necesita Docker.
- Sin cuenta IBKR ni claves OpenAI para compilar, simular y ejecutar pruebas.

## Compilar y ejecutar demostraciones

Desde la raíz, en PowerShell:

```powershell
dotnet build TradingAgent.sln -m:1
dotnet run --project src/TradingAgent.Api --no-build -- --demo
$env:PYTHONPATH = Join-Path (Get-Location) 'python'
python -m trading_agent demo
```

La primera demo muestra la evolución de una misma asignación US$100 hacia US$110/98, rechazo por incompatibilidad económica del mínimo y suspensión por pérdida diaria. US$98 activa límites previos más estrictos. Los datos y costos son sintéticos. El resultado `ALLOW_SIMULATION` es una admisión de simulación; nunca es autorización ni envío al bróker.

## PostgreSQL de pruebas aislado

Si PostgreSQL está instalado en la ruta predeterminada de Windows:

```powershell
.\scripts\test-database.ps1 -Action Start
$env:TRADING_TEST_DB = 'Host=127.0.0.1;Port=55432;Username=trading_test;Database=postgres'
$env:TRADING_DB = $env:TRADING_TEST_DB
.\scripts\verify.ps1
.\scripts\smoke-api.ps1
```

El script crea `.local/postgres-test`, limitado a loopback, sin tocar otros clusters. Usa autenticación `trust` únicamente para datos sintéticos desechables; no guardar allí información de cuentas ni secretos. Para una instalación propia, usar una base vacía con credenciales seguras en `TRADING_DB` y un usuario de aplicación limitado; las migraciones requieren un usuario de migración separado en despliegues posteriores. Las pruebas de integración solo deben apuntar a una base desechable.

Sin `TRADING_TEST_DB`, las pruebas PostgreSQL se muestran como **omitidas**, no aprobadas. Los resultados C# se escriben en `artifacts/test-results/phase2.trx`.

## API local

```powershell
$env:TRADING_DB = 'Host=127.0.0.1;Port=55432;Username=trading_test;Database=postgres'
$env:TRADING_ADMIN_TOKEN = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
$env:TRADING_POLICY_PATH = Join-Path (Get-Location) 'config/research-policy.json'
dotnet run --project src/TradingAgent.Api --no-build
```

Escucha exclusivamente en `http://127.0.0.1:5080`. `/health` es público; el resto exige `Authorization: Bearer <TRADING_ADMIN_TOKEN>`. El token es para el operador local, jamás para un agente de IA. No exponer este servidor a Internet: la administración con OIDC/MFA y roles de producción aún no está implementada.

| Ruta | Función |
| --- | --- |
| `GET /health`, `GET /policy` | Estado de capacidades y política de lectura |
| `POST /simulation/accounts` | Crear cuenta `SIM-*` con US$100 virtuales; repetir no reinicia resultados |
| `GET /simulation/accounts/{id}` | Recuperar equity, reserva y suspensiones |
| `POST /simulation/strategies` | Registrar versión inmutable candidata |
| `POST /simulation/decisions` | Evaluar, registrar experiencia y reservar un slot simulado si se acepta |
| `GET /simulation/decisions/{id}` | Recuperar decisión idempotente |
| `POST /simulation/settle` | Cerrar simulación con P&L **neto ya incluido el costo observado**; no se vuelve a restar el costo |
| `POST /simulation/mark` | Actualizar equity sintética cuando no hay una reserva abierta |
| `POST /simulation/valuation` | Valorar P&L/costos flotantes y riesgo residual de una posición sintética conservando su reserva |
| `POST /safety/stop/{id}` | Suspender nuevas entradas; conserva reservas y no toca protecciones |
| `GET /experiences/{id}` | Recuperar experiencias aceptadas/rechazadas y observaciones disponibles |
| `POST /experiences/{id}/similar` | Distancia normalizada a episodios anteriores a la fecha de corte |
| `POST /experiences/rejected-observation` | Añadir evolución posterior de señal rechazada sin inventar P&L |
| `POST /research/backtests` | Archivar reporte Python y operaciones como evidencia de investigación, no aprobada |

`scripts/smoke-api.ps1` contiene ejemplos completos, incluido `request.execution`, y comprueba el flujo con reinicio de proceso. Omitir esa evidencia o desconocer la comisión de cierre produce rechazo. La API es para un operador de simulación: las marcas de fiabilidad no certifican datos del bróker. No ejecutarlo mientras otra API ocupe el puerto 5080. Las valoraciones/cotizaciones caducan a los 30 segundos en la política de ejemplo; refrescar mediante `/simulation/mark` o `/simulation/valuation` únicamente con datos sintéticos en este alcance. Cuentas antiguas sin asignación requieren revisión explícita; no se les reinicia el presupuesto.

## Análisis/backtest de archivos

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'python'
python -m trading_agent analyze --input datos.json
python -m trading_agent backtest --input datos.json
```

Formato: `{"candles":[{"opened_at":"2026-01-05T00:00:00+00:00","minutes":15,"open":1.1,"high":1.101,"low":1.099,"close":1.1005,"volume":null,"spread":null}],"as_of":"2026-01-06T00:00:00+00:00"}`. Se necesitan al menos 51 velas para análisis completo. Backtesting acepta `config` con campos de `python/trading_agent/backtest.py` y `dataset_role` (`development` o `validation`). Valores monetarios/configuración de backtest se expresan como cadenas decimales. Salida JSON por stdout, para guardar o importar mediante `/research/backtests`.

El comando histórico `analyze` rechaza gaps por defecto y analiza los marcos por separado. La entrega D añade un calendario versionado y un contrato multitemporal causal para la investigación sobre datos auténticos, sin rellenar huecos ni crear volúmenes ausentes.

## Investigación automática sobre PostgreSQL

La [ampliación histórica y de costos](docs/architecture/eurusd-history-and-costs.md) recuperó seis meses auténticos: 12.423 velas 15M, 3.009 de 1H y 655 de 4H completas, con calendarios IBKR, BID_ASK y una muestra de ticks. Desarrollo/validación se separan cronológicamente. Ninguna de las 1.579 señales fue admitida; los costos de cuenta siguen incompletos y el escenario estimado de US$2 por orden excede el presupuesto. Para descargar/reanudar usar `scripts/collect-research-history.ps1`; para evaluar el archivo completo y persistirlo, `scripts/run-extended-research.ps1`. Live, órdenes y OpenAI permanecen bloqueados.

```powershell
.\.venv\Scripts\python.exe -m pip install -r python/requirements-research.txt
dotnet build TradingAgent.sln -m:1
.\scripts\run-market-research.ps1
```

Usa el dataset Paper ya almacenado y la autorización local vigente para seleccionarlo; no conecta con TWS. Conserva originales y normalizados por separado, calcula indicadores/clasificación, versiona tres hipótesis y evalúa sus señales mediante el riesgo existente. Guarda resultados en PostgreSQL y JSON local en `artifacts/research`, incluido un contexto preparado para Sol sin llamadas a OpenAI. La captura inicial produjo 615 barras normalizadas y 39 señales rechazadas; costos desconocidos y contexto 4H insuficiente impiden evaluar rentabilidad. Consulte el [informe D](docs/architecture/eurusd-automatic-research.md) para cifras por indicador y limitaciones.

## Viabilidad económica E.0

`scripts/run-economic-study.ps1` ejecuta un estudio offline por cantidad con evidencia de comisiones, costos, margen y punto de equilibrio; no usa TWS, PostgreSQL ni secretos. Con US$100, la apertura manual estimada de US$2 para 100 EUR supera el riesgo máximo US$0.50. Costos/restricciones pendientes dejan las comparaciones `UNVERIFIED`; los contratos de preparación Paper mantienen bloqueada toda transmisión. Véase el [informe E.0](docs/architecture/paper-economic-feasibility.md), incluido el diseño de conciliación/protección y la comprobación manual pendiente. No cambia EUR/USD ni la política activa.

## TWS Paper, solo lectura

La [entrega E.1](docs/architecture/paper-execution-laboratory.md) añade un laboratorio de ejecución Paper separado, con autorización DPAPI independiente, journal PostgreSQL y modos StrategyPaper/ExecutionDiagnostics. Se verificaron 320 pruebas. La autorización actual venció; no se enviaron órdenes IBKR y la emergencia sigue activa. Diagnose distingue EUR_ZERO_CONFIRMED, EUR_ROW_ABSENT y EUR_BALANCE_UNKNOWN y contrasta saldos/cartera/posiciones/órdenes. Se preparó una excepción DPAPI inicial de uso único y vigencia máxima 30 minutos, exclusiva del diagnóstico Paper, que acepta incertidumbre sin establecer EUR=0. No está registrada ni activa: requiere aceptación, revisión protegida y autorización de ejecución vigente independientes, y conserva conciliación estricta posterior. StrategyPaper mantiene US$100/20 y su bloqueo económico; diagnóstico US$10 intacto, transporte de lectura bloqueado y Live deshabilitado.

El SDK oficial `ibapi 10.50.2` está instalado en `.venv`; se verificó TWS en `127.0.0.1:7497`, servidor API `226`, y la coincidencia exacta con la cuenta autorizada terminada en `3784`. Se leyeron saldos, posiciones y contrato EUR/USD; se almacenaron 475 velas 15m, 115 de 1h y 26 de 4h. La cotización fue UNAVAILABLE. Véase el [informe actual de lectura real](docs/architecture/paper-authentic-data-validation.md). El puerto y el prefijo por sí solos no demuestran Paper. La autorización DPAPI vigente se carga mediante `scripts/paper-identity.ps1 -Action Load`, sin activar automáticamente el colector.

Para una sesión autorizada, configurar `IBKR_PAPER_ACCOUNT` con la cuenta Paper exacta, `IBKR_PORT=7497`, `IBKR_VERIFIED_TWS_PORT=7497`, `IBKR_PAPER_ATTESTED=true` e `IBKR_READ_ONLY_ATTESTED=true` después de verificarlos en TWS. Usar `.venv/Scripts/python.exe -m trading_agent.tws status`, `balance`, `positions`, `contract_details`, `quote` o `history --minutes 15`, con `PYTHONPATH=python`. `diagnose` descubre identidades enmascaradas y comprueba el handshake sin autorizar lecturas operativas. Se exige coincidencia exacta con las cuentas del handshake y se rechaza cualquier cuenta adicional. La API no aporta una atestación criptográfica de Paper ni del checkbox Read-Only.

Con `IBKR_DATA_ENABLED=true`, el backend inicia un colector Python de solo lectura, valida sus observaciones, las persiste en PostgreSQL y expone `GET /api/broker/status`, `/api/broker/account`, `/api/broker/positions`, `/api/market/eurusd/contract`, `/api/market/eurusd/quote` y `/api/market/eurusd/candles?timeframe=15m|1h|4h`, con el token de operador existente. No hay rutas de órdenes. Todas las cotizaciones tienen `executable=false`. El simulador y el capital virtual permanecen separados de los saldos Paper.

`scripts/paper-database.ps1 -Action Start` prepara un clúster Paper separado en loopback:55433 con SCRAM y contraseñas cifradas por Windows. Migra con un usuario separado y configura un usuario de aplicación limitado a leer/insertar observaciones y velas. `-Action Load` vuelve a cargar la conexión; `-Action Stop` detiene ese clúster. El PostgreSQL existente en 5432 y el clúster sintético 55432 quedan separados.

`scripts/smoke-paper-api.ps1` exige `TRADING_TEST_DB` y usa explícitamente un colector sintético para probar endpoints y reinicio sin conectar a TWS. `-RealTws` exige configuración Paper autorizada y consulta exclusivamente datos reales. La demostración real completó las tres series y los endpoints de lectura; sus procesos se detuvieron al finalizar. Los informes distinguen pruebas sintéticas de observaciones auténticas.

## Cerrar servicios

Detener la API con `Ctrl+C` y después:

```powershell
.\scripts\test-database.ps1 -Action Stop
Remove-Item Env:TRADING_ADMIN_TOKEN -ErrorAction SilentlyContinue
```

Los archivos del cluster de pruebas se conservan para inspección; no se borran automáticamente.

El [perfil PAPER_EXPERIMENTAL_10_PERCENT](docs/architecture/paper-experimental-risk.md) está preparado para evaluación offline exclusiva de IBKR StrategyPaper, sin activación. Conserva capital US$100, pérdidas acumuladas US$20 y exposición 1×. Techo nominal US$10 a equity US$100; el límite diario conservado reduce el presupuesto efectivo inicial a US$1. Última verificación: 339 pruebas aprobadas, cero omitidas. Live y activación del perfil permanecen bloqueados.
