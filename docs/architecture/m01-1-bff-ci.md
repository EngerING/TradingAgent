# M01.1 — comprobación CI para auditoría

2026-10-20, America/La_Paz. **OFFLINE / NO_TRADE**.
Entrega auditada: `2979fa42e3c75e093f191fc5fe4c4507a425645e`, árbol
`b6a51b83770c08ac9039b71b616c293af34a19e9`.
Rama única: `codex/m01-1-bff-foundations`.

Se añaden únicamente este documento y
[m01-1-bff-ci.yml](../../.github/workflows/m01-1-bff-ci.yml).
No se modifica `build/web/check.ps1`, el producto, las pruebas originales ni
la evidencia histórica. El campo not_executed de esa evidencia describe su
entrega original; los resultados nuevos pertenecen a cada ejecución de Actions.

## Ejecución y permisos

El workflow arranca por push de esta rama, sin workflow_dispatch, PR ni
pull_request_target. Usa GitHub-hosted windows-2025, pwsh y timeout de15 minutos.
GITHUB_TOKEN dispone solamente de contents:read; checkout no persiste credenciales.
No se solicitan secrets ni variables operativas. No hay servicios auxiliares,
runners propios, environments, despliegue ni pasos de escritura en GitHub.

| Acción oficial | Versión revisada | SHA fijado |
|---|---|---|
| checkout | [v7.0.1](https://github.com/actions/checkout/releases/tag/v7.0.1) | `3d3c42e5aac5ba805825da76410c181273ba90b1` |
| setup-dotnet | [v6.0.0](https://github.com/actions/setup-dotnet/releases/tag/v6.0.0) | `a98b56852c35b8e3190ac28c8c2271da59106c68` |
| upload-artifact | [v7.0.2](https://github.com/actions/upload-artifact/releases/tag/v7.0.2) | `cf430e030ddbb5b0abf93d22962f4752f3646cd9` |

Se contrastaron releases, tags y action.yml oficiales: Node24, entradas de
credenciales, caché, SDK y artefactos. No es una auditoría completa del bundle JS
o de todas sus dependencias. La imagen del [runner windows-2025](https://github.com/actions/runner-images/blob/main/images/windows/Windows2025-Readme.md)
es mantenida por GitHub y puede cambiar entre ejecuciones.

Setup instala SDK exacto10.0.402 con cache:false. NuGet utiliza carpetas nuevas
bajo runner.temp; no hay actions/cache ni caché persistente entre jobs.
`dotnet --version` se comprueba en build/web para aplicar su global.json existente;
no se añade uno en la raíz. Desde la raíz se ejecuta exactamente:

```powershell
./build/web/check.ps1 -Dotnet dotnet
```

El script original realiza restore --locked-mode --force --no-http-cache,
NuGet Audit all/low, build Release --warnaserror, xUnit/VSTest y reporte vulnerable
directo/transitivo en JSON. La CI verifica resultados independientemente del exit0.

## Condiciones de éxito y evidencia

Antes de compilar se exige que el SHA del evento coincida con checkout, que el
commit auditado sea ancestro y que todo el diff desde él sean exclusivamente
las dos adiciones CI/documentación. Se registran SHA del commit, árbol, ref,
evento, run_id y objetos Git protegidos. No se ejecuta código del host histórico.

Después del script, el lector XML sin DTD exige contadores presentes y coherentes,
total=ejecutadas=aprobadas>=21, cero fallidas/omitidas y cero estados inconclusos,
abortados, pendientes o errores. Comprueba los nombres de los **21 casos originales**,
incluidas las nueve variantes parametrizadas, resultados únicos y Passed.
Una suite vacía o una prueba original sustituida falla, aunque el comando devuelva0.

Cada resultado debe tener una definición única con ensamblado
`tests/TradingAgent.Web.Tests/bin/Release/net10.0/TradingAgent.Web.Tests.dll`.
Se registra su SHA-256, duración total del TRX y suma de duraciones individuales.
Se comprueban SDK, build con0 advertencias/errores, ausencia de avisos NU1900–1905,
JSON de auditoría de dos proyectos net10.0 sin vulnerabilidades reportadas y árbol
de trabajo/index sin cambios tras la ejecución.

Los pasos de validación y upload usan always(). El artefacto
`m011-bff-<commit>-<attempt>` conserva exclusivamente estos siete archivos, durante
**14 días**, cuando existan:

- restore.log y build.log.
- m011.trx y dependencies.json.
- identity.json, sdk-version.txt y summary.json.

No se suben directorios completos, SDK, cachés, binarios, configs ni archivos
ocultos. summary.json distingue FAIL/NOT_VERIFIED y contadores desconocidos de
un resultado exitoso; la falta de evidencia produce fallo. Un runner cancelado,
timeout global o caída del servicio de artefactos puede impedir su publicación.
Las descargas de artefactos requieren autenticación de GitHub.

## Comprobaciones locales y preservación

Se validaron YAML, las restricciones del workflow y la sintaxis PowerShell.
Se ejercitó el bloque real de validación con el TRX original y17 copias adversas:
TRX ausente, suite vacía, prueba original sustituida, omitida, fallida, contadores
incoherentes/ausentes, ensamblado distinto, duración inválida, vulnerabilidad,
auditoría ausente, SDK distinto, paso omitido, warning de build/audit, duplicados
e identidad incorrecta. Resultado:18/18 comportamientos esperados. El caso de
contador ausente reprodujo una aceptación indebida en el workflow en desarrollo;
se corrigió sin tocar check.ps1 y se repitieron todos los fixtures.
Estas verificaciones locales del validador no son una ejecución remota ni otras
pruebas xUnit del producto. No se atribuyen resultados de Actions antes de leerlos.

| Componente preservado | Objeto Git de referencia |
|---|---|
| Core V3 completo, incluido V3.9 | `0c6a3c211249151582556862d610ffe29ae221a0` |
| Market Analyst V1 | `1cdcffba113842977a881b57912be1e101eae688` |
| Infrastructure/PostgreSQL/migraciones | `c9322ebfb7e813c71ba6098eedabf5ba8b6970dd` |
| Frontend Vue | `8b2101aeb2c3cd8661e95ee8ae13511e5dff09e2` |

identity.json registra también API, Core .NET, ConfigurationLab, ResearchLab,
tests históricos, Web, tests Web, Directory.Build.props, solución y check.ps1.
El diff cerrado preserva los727 archivos rastreados del commit auditado. Los
dos documentos locales untracked siguen fuera de Git. main permanece en
`f67fa92086d10b9562df214f4e869344bf0753d8` y no recibe push ni merge.

Graphify: consulta `test dotnet build`, presupuesto700, grafo histórico424 nodos,
92 encontrados/26 mostrados/66 truncados; no cubre Web/CI. Fuentes actuales
contrastadas; sin reconstrucción del grafo ni extracción remota.

## Límites

Solo se autorizan conexiones de infraestructura CI, acciones oficiales, SDK y
NuGet. Los tests originales usan TestServer en memoria y verifican aislamiento;
el workflow no llama IBKR, PostgreSQL, API histórica, PaperFeed, OpenAI, Kronos o
Supabase, ni crea usuarios, cambia permisos/estrategias o modifica journals.
No ejecuta migraciones, Paper/Live, backtests ni suites financieras históricas.
Esto es evidencia de los caminos probados, no un firewall o sandbox del runner.

Una CI verde no reemplaza la auditoría independiente ni concede autoridad de
autenticación o trading. Si Actions está deshabilitado o falta autorización,
se informa sin ampliar permisos. **M01.2 no se inicia.**
