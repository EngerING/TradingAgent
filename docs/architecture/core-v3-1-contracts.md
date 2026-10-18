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
