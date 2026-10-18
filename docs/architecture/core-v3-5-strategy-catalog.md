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
