# Core V3.3 — investigación simulada durable

Base: `77daf8e`, rama `codex/core-v3-3-research-orchestrator`.
Alcance autorizado: investigación offline sin modelos reales, brokers ni ejecución.

## Diseño previo

| Archivo nuevo | Responsabilidad |
|---|---|
| `core_v3/research_contracts.py` | Solicitudes, identidad/referencias, presupuesto, propuestas y estados cerrados e inmutables. |
| `core_v3/research_designer.py` | Puerto y diseñador simulado fijo; snapshots offline explícitos. |
| `core_v3/research_journal.py` | SQLite independiente, eventos inmutables encadenados, replay validado y presupuesto atómico. |
| `core_v3/research_runner.py` | Ciclo con gates V3.2, comprobaciones después del diseño y recuperación sin repetición. |
| `python/tests/test_core_v3_research_*.py` | Contratos, diario real temporal, concurrencia, fallos y ciclo offline. |

Se preservan fuentes, contratos y cálculos V3.1/V3.2. La única edición prevista
de una prueba anterior amplía su allowlist de imports offline, sin quitar
aserciones. No se modifican subsistemas históricos ni los dos documentos ajenos
sin seguimiento. No se lee `.local`.

El diario usa una ruta fija bajo un root explícito de composición, nunca paths
derivados de IDs. IDs y claves de idempotencia son acotados. SQLite es nuevo,
separado de Forex/R20, con transacciones `BEGIN IMMEDIATE`, timeout acotado,
eventos append-only y verificación de secuencia, hashes y máquina de estados.

Estados: RECEIVED, VALIDATION_REJECTED, ECONOMIC_BLOCKED, BUDGET_BLOCKED,
BUDGET_RESERVED, DESIGNING, DESIGN_RECEIVED, POSTFLIGHT_PENDING,
CANDIDATE_RECORDED, FAILED e INTERRUPTED. Repetir una solicitud devuelve su
estado durable. Una operación pendiente no invoca otra vez el diseñador.
La recuperación explícita interrumpe el trabajo, conservando reservas inciertas.

El presupuesto es de investigación: solicitudes, tokens e importe simulado USD.
No es equity, margen ni riesgo de posición. La reserva es atómica; una respuesta
simulada conocida consume una solicitud y cero tokens/costo real. Una llamada
sin resultado conocido conserva su reserva hasta revisión. Sin proveedor real,
no hay facturación. El estado financiero se mantiene en los inputs V3.2.

El resultado guarda identidades, hashes, evidencia económica y límites sin
autoridad operativa: NO_TRADE, sin Paper/Live, estadística ni ejecución.
El diseño produce una hipótesis ligada a un escenario, no una estrategia
ejecutable ni evidencia de backtest.

Riesgos a probar: doble reserva concurrente, crash entre commits, evidencia
caducada, salida inválida, alteración/truncamiento del diario y errores SQLite.
Los hashes detectan alteraciones respecto al historial disponible; no autentican
externamente al productor ni protegen frente a reescritura completa por quien
controle el archivo y sus anclas. El alcance de detección se documentará.
