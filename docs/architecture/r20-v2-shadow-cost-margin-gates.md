# EUR/USD — costos y margen antes de Shadow V2

Consultado13/oct/2026. Política propuesta existente:
`config/r20-v2-cost-policy.proposed.json`, hash
`00e6a902237f3769b64f5e1ddc5d6d9d45fc28cbc0a49865a8e130574adf6733`.
**No aprobada/activada operativamente; entradas normales BLOCKED.** No se redujo
ningún supuesto V1 ni se enviaron órdenes para calibrar.

| Componente | Evidencia de esta fase / anterior | Tratamiento y gate |
|---|---|---|
| Comisión | [Tarifa oficial spot](https://www.interactivebrokers.com/en/pricing/commissions-spot-currencies.php): tramo inicial0.20bp×valor, mínimo2USD por orden. No commissionReport R20. | Estimación, no cargo confirmado. Verificar plan, entidad, moneda y eventos facturables. Por evento: max(2,0.00002×notionalUSD); sumar eventos, no un mínimo global que oculte modificaciones/overnight. Condiciones de cuenta no acotadas bloquean. |
| Spread | Muestra V1 de3644 quotes: mediana0.00002, p95/p990.00003, max0.00004 USD/EUR. Quotes nuevas del13/oct:0.00001 y0.00002. | Entrada observada con timestamp de recepción; salida estimada. Ni máximo ni percentil observado son techo garantizado. Propuesta conserva piso legado0.0014 como supuesto, no como spread medido. Una estimación versionada exige ventana/sesión/cobertura y bound justificable. |
| Slippage | Ningún fill IBKR R20. El supuesto0.00045 por lado no es calibración empírica. | UNBOUNDED; bloquea nuevas entradas normales. Cambios entre quotes no demuestran slippage de ejecución ni profundidad. No bajar valor hasta producir target positivo. |
| Financiación | [Cálculo y benchmarks oficiales](https://www.interactivebrokers.com/en/trading/margin-benchmarks.php): devengo diario y contabilización mensual. [Tasas de financiación](https://www.interactivebrokers.com/en/trading/pricing-margin-rates.php) dependen de moneda/tramo. | UNKNOWN; faltan saldos por moneda/settlement, plazo máximo, calendario, tasas y condiciones aplicables.0.25 fijo V1 es reserva del modelo, no devengo por duración. Sin horizonte/cota no hay entradas normales. |
| Inicial/mantenimiento | ContractDetails y AccountBinding no acreditan margen incremental. [Requisitos oficiales](https://www.interactivebrokers.com/en/trading/margin-requirements.php) dependen de residencia/producto/mercado. | UNKNOWN para esta cuenta/tamaño.10%/5% del ensayo sólo MODEL/SYNTHETIC. Una cuenta Paper grande no prueba capacidad del capital lógico100USD. Mantener gate; no deducir porcentajes por puerto o símbolo. |
| Holgura | Solver verifica pérdida, nominal repriciado y mantenimiento bajo shocks LONG/SHORT. | No porcentaje elegido para conseguir admisión. Deben aprobarse cobertura/bounds de shocks y buffers junto al modelo de margen. Un estrés de fixture prueba ecuaciones, no liquidez futura. |

La estimación puede sustituir un cargo aún no realizado **cuando exista evidencia
del tarifario aplicable, estructura de eventos y un límite conservador explícito**.
UNKNOWN no significa cero. Identidad, datos actuales, cobertura de escenarios,
margen, financiación y slippage sin cota suficiente bloquean operación normal.
No existe una excepción implícita por ser Shadow, por activar perfil o por usar
Kronos. Los ensayos técnicos están separados y etiquetados como laboratorio.

Tarifa y comisión son distintas de ejecución: incluso [Paper tiene limitaciones
de simulación](https://www.interactivebrokers.com/campus/trading-lessons/paper-trading-vs-live-trading-whats-the-difference/).
Sus fills futuros no demostrarán slippage real. Un target neto positivo tampoco
demuestra ventaja estadística o expectativa positiva.

## Evidencia auténtica sin activación

client193 verificó exactamente managedAccounts frente a AccountBinding***3784 y
quote06:15:16.942244UTC, bid1.11760/ask1.11761. client194 obtuvo calendario y
históricos nativos MIDPOINT:705 originales1H y205 originales4H. La normalización
existente seleccionó675/146 barras completas, excluyendo parciales/de sesión sin
relleno ni remuestreo. Cero missing_expected_openings en ambos prefijos.
Últimos cierres06:00UTC/04:00UTC; ambas señales NO_BREAKOUT.

Quote del segundo corte06:21:22.828671UTC, bid1.11753/ask1.11755, LIVE/OPEN,
recibida/local, source_timestamp=null. No es timestamp del exchange ni ejecución.
Ambos clientes fueron read_only/Research y se desconectaron en finally. Fuentes,
request traces, normalización y SHA256 están en los artefactos de esta fase.
No se insertaron en un ledger de posiciones ni se presentaron como feed activo.

Los resultados INVALID_MARKET_DATA del primer cálculo directo sobre históricos
crudos se conservaron: incluían barras parciales/de sesión. La normalización
existente resolvió su selección para el diagnóstico; no se cambió el motor ni
se ignoraron gaps. La señal actual tampoco entra fuera de la ventana180s.

## Desbloqueo futuro, sin autorización implícita

Necesarios: política versionada aprobada, estructura facturable y plan exacto;
slippage/shocks defendibles; duración máxima y reserva financiada con tasas y
saldos apropiados; modelo de margen y protección de recuperación revisados.
Hasta entonces sólo diagnósticos/cálculos, sin posiciones económicas auténticas.
La aprobación del perfil diario no sustituye permiso Shadow ni consentimiento
Paper. Ningún probe de esta fase envía what-if/placeOrder o cancelOrder.
