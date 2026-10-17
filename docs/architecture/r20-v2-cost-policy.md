# EUR/USD V2 â€” propuesta de costos versionada

Estado: **PROPOSED_NOT_ACTIVATED**. Identificador EURUSD_COST_PROPOSAL_V1,
versiÃ³n1, hash `00e6a902237f3769b64f5e1ddc5d6d9d45fc28cbc0a49865a8e130574adf6733`.
Contrato y datos: `python/trading_agent/r20_cost_policy.py` y
`config/r20-v2-cost-policy.proposed.json`. No son una configuraciÃ³n diaria activada.
La propuesta conserva incertidumbres; no concede permiso de operaciÃ³n.

## Costos diferenciados

| Componente | PolÃ­tica propuesta | Procedencia y condiciÃ³n |
|---|---|---|
| ComisiÃ³n | Por tramo: n_eventosÃ—max(2,0,00002Ã—qÃ—precio_USD/EUR), si falta desglose por evento. Entrada y salida se estiman por separado. | PUBLISHED_ESTIMATE. Confirmar cuenta/entidad/plan, moneda base y nÃºmero de mÃ­nimos aplicables. No existe commissionReport R20. |
| Spread | Precio al midpoint; costo de ida/vuelta qÃ—(spread_entrada+spread_salida_estimado)/2. Usar quote vÃ¡lida en entrada; conservar piso de investigaciÃ³n0,0014USD/EUR en esta propuesta, sin sustituirlo por percentiles. | OBSERVED_WITH_ASSUMPTION. El piso no es una mediciÃ³n ni garantiza spread futuro. El de salida requiere horizonte/sesiÃ³n y aprobaciÃ³n del supuesto. |
| Slippage | Conservar0,00045USD/EUR por lado como supuesto de investigaciÃ³n identificado. | UNBOUNDED_ASSUMPTION. No hay fills ni cota empÃ­rica. Impide entradas normales; no convertir a cero ni llamarlo calibrado. |
| FinanciaciÃ³n | UNKNOWN. Conservar la referencia histÃ³rica0,25USD en documentaciÃ³n, sin convertirla en curva ni lÃ­mite por duraciÃ³n. | Faltan saldos por moneda, tipos, plazo y condiciones. Impide entradas normales. Intraday previsto no demuestra costo cero si hay desconexiÃ³n/overnight. |

El tarifario oficial reconsultado en esta fase publica nivel I0,20 puntos bÃ¡sicos
y mÃ­nimoUSD2 por orden. TambiÃ©n contempla mÃ­nimos adicionales para ciertas
modificaciones y Ã³rdenes overnight; acuerdos/introducciÃ³n pueden alterar tarifas.
Se separa explÃ­citamente la conversiÃ³n automÃ¡tica de una orden spot FX.
[Tarifario IBKR](https://www.interactivebrokers.com/en/pricing/commissions-spot-currencies.php).

La estimaciÃ³n anterior cobra conservadoramente el notional completo en cada
evento. Con desglose fiable debe usarse Î£max(2,0,00002Ã—notional_evento). No usar
max(2n,0,00002Ã—notional_total) para una distribuciÃ³n desigual: puede subestimar
mÃ­nimos. La multiplicidad debe ser explÃ­cita; no se supone una sola orden por
tramo si modificaciones, fragmentaciÃ³n o overnight la vuelven incierta.

Los futuros fills Paper seguirÃ­an siendo simulados y no demostrarÃ­an slippage
de ejecuciÃ³n real. [Limitaciones Paper de IBKR](https://www.interactivebrokers.com/campus/trading-lessons/paper-trading-vs-live-trading-whats-the-difference/).

## QuÃ© puede estimarse y quÃ© bloquea

Un cargo confirmado desconocido no obliga a bloquear por sÃ­ solo: la comisiÃ³n
puede estimarse con un tarifario aplicable y fuente/versionado; el spread de
salida puede modelarse con un supuesto explÃ­cito sustentado por muestras y estrÃ©s.
Estas estimaciones deben reservarse, revisarse con datos nuevos y mantener su
etiqueta ESTIMATED. No implican aceptaciÃ³n del brÃ³ker ni ventaja estadÃ­stica.

SÃ­ bloquean: falta de quote fresca/bid-ask vÃ¡lido; identidad o tarifa aplicable
inciertas cuando no existe una cota aceptada; costos materiales sin modelo acotado;
slippage/financiaciÃ³n de esta propuesta; horizonte de carry desconocido; polÃ­ticas
de margen/estrÃ©s no verificadas; o propuesta sin aprobaciÃ³n de adopciÃ³n.
La clase devuelve COST_POLICY_NOT_APPROVED, SLIPPAGE_COST_UNBOUNDED y
FINANCING_COST_UNBOUNDED. No hay fallback operativo ni transformaciÃ³n automÃ¡tica
de esa propuesta al CostModel del solver.

La muestra anterior permanece intacta:3644 quotes, mediana0,00002,
p95/p990,00003, mÃ¡ximo0,00004USD/EUR, con recepciÃ³n local y discontinuidades.
Describe el corte V1, no una cota garantizada. Ver mÃ©todo y hashes en
`r20-v2-eurusd-cost-evidence.md` y su evidencia original. No se recortaron costos
para hacer admisibles las cuatro operaciones V1; siguen rechazadas segÃºn la
comparaciÃ³n anterior, incluso en su escenario optimista de comisiÃ³n solamente.

## Contabilidad sin doble cargo

SETTLED se descuenta de cash una vez; ACCRUED y RESERVED se descuentan de equity
econÃ³mica mientras estÃ©n pendientes. El mismo cost_id no puede figurar dos veces.
Un precio basado en midpoint incorpora el spread estimado; cuando exista un
precio efectivo bid/ask/fill, debe retirarse la parte ya incorporada al PnL en
vez de sumar otro spread completo. ComisiÃ³n realizada debe sustituir/reclasificar
la reserva de su mismo concepto, nunca aÃ±adirse como un segundo cargo.

En las reservas de admisiÃ³n del laboratorio, costoC se aÃ±ade una sola vez a
RESERVED y reduce equity. Si pÃ©rdida estresada total esW, PendingRisk recibe
Wâˆ’C. PÃ©rdida consumida incorporaC, y el riesgo pendiente incorpora sÃ³lo el
incremento futuro: C+(Wâˆ’C)=W. Se prueba con dos reservas simultÃ¡neas/sucesivas,
recuperaciÃ³n e idempotencia. No se confirma ni realiza un cargo IBKR al reservar.

No se activÃ³ esta propuesta. Los valores pequeÃ±os y financiaciÃ³n cero del
fixture de UI pertenecen al ensayo matemÃ¡tico anterior SYNTHETIC_TEST_ONLY;
no se reutilizan como polÃ­tica EUR/USD ni como evidencia de costos.
