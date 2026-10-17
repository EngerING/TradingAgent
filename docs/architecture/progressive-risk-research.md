# Investigación progresiva de riesgo con US$100

Resultado: **NO_VIABLE_STRATEGY_FOUND**.

Simulación aislada. Exposición 1×, pérdidas acumuladas US$20 y políticas operativas intactas. Ninguna estrategia promovida ni orden enviada.

Dataset `bb95c4d5394704af60d7c4ccde15710f504daddf1463f3b9ac44c68f39e87c8c`; 2026-04-03T00:00:00+00:00–2026-10-03T00:00:00+00:00; validación desde 2026-08-03T00:00:00+00:00.

Costos por ciclo: BUY US$2.0 + SELL US$2.0; spread 0.0014; slippage .00045; reserva gap .00005 USD/EUR.

La comisión observada procede del diagnóstico Paper cerrado, no de resultados de estrategia. La extensión de esa tarifa a otras cantidades y el margen IBKR siguen desconocidos.

## Versiones exactas

- trend: `9860cd16f4f43d38ca7c29f161aea82e17dea100da48bb78259457cc31133211` (V1, parámetros sin cambios).
- pullback: `b622e9522da52b2aec358a4623d671b5398990d00e812a8fb81e2c71d155a9d3` (V1, parámetros sin cambios).
- mean_reversion: `fcd256a67a14d26c3e58cf73e0906713c09ed50aef69f67b99e92f52fcac80c2` (V1, parámetros sin cambios).

## Comprobación favorable independiente del spread de estrés

Incluso suponiendo spread, slippage y gap cero, sin redondeo de cantidad y sin aplicar el límite de riesgo, se reservan US$4 de comisión y se financia un notional máximo de US$96. Esta cota superior evalúa el mejor target entre todas las señales elegibles; no recomienda esos tamaños ni constituye un trade. Ningún target cubre las comisiones: no existe una primera entrada admisible por este criterio económico. Esto no calcula la probabilidad de un resultado positivo excepcional por gaps o por salida a la siguiente apertura.

| Estrategia | Señales elegibles | EUR en el mejor target | Notional USD | Target bruto máximo USD | Target neto máximo USD |
|---|---:|---:|---:|---:|---:|
| trend | 43 | 83.3536 | 96.00 | 0.22464 | -3.77536 |
| pullback | 762 | 81.8826 | 96.00 | 0.28610 | -3.71390 |
| mean_reversion | 23 | 83.1093 | 96.00 | 0.27230 | -3.72770 |

## Comparación por riesgo: cuenta continua de seis meses

| Riesgo % | Presupuesto inicial USD | Admitidas / rechazadas | Comisión supera riesgo | Geometría inválida | Target no cubre costos | Neto / comisiones USD | DD % / días detenidos |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1 | 0 / 828 | 635 | 193 | 0 | 0.00000 / 0.00000 | 0.00000 / 0 |
| 2 | 2 | 0 / 828 | 635 | 193 | 0 | 0.00000 / 0.00000 | 0.00000 / 0 |
| 3 | 3 | 0 / 828 | 635 | 193 | 0 | 0.00000 / 0.00000 | 0.00000 / 0 |
| 5 | 5 | 0 / 828 | 0 | 193 | 635 | 0.00000 / 0.00000 | 0.00000 / 0 |
| 7.5 | 7.5 | 0 / 828 | 0 | 193 | 635 | 0.00000 / 0.00000 | 0.00000 / 0 |
| 10 | 10 | 0 / 828 | 0 | 193 | 635 | 0.00000 / 0.00000 | 0.00000 / 0 |
| 12.5 | 12.5 | 0 / 828 | 0 | 193 | 635 | 0.00000 / 0.00000 | 0.00000 / 0 |
| 15 | 15 | 0 / 828 | 0 | 193 | 635 | 0.00000 / 0.00000 | 0.00000 / 0 |

Conteos agregados entre tres estrategias independientes, nunca una cartera ni la suma de beneficios de folds. Además se excluyen 751 candidatos NO_TRADE por riesgo (175 Trend, 576 Pullback), sin contarlos como operaciones. El win rate, PF y expectativa son n/a porque no hubo trades. Cero drawdown y cero días detenidos tampoco acreditan seguridad. La ejecución IBKR continúa UNKNOWN y las entradas están rechazadas económicamente.

## continuous_six_months

| Estrategia | Riesgo % | Admitidas / rechazadas / NO_TRADE | Win neto % | Ganancia / pérdida media USD | Bruto / neto USD | Comisiones USD | PF neto | Expectativa USD | DD cerrado / intrabar % | Días primera pérdida / break-even | EUR media | Riesgo máx USD | Ejecución IBKR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| trend | 1 | 0 / 43 / 175 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.01: {"COMMISSION_EXCEEDS_RISK_BUDGET": 32, "INVALID_PRICE_GEOMETRY": 11} -->
| trend | 2 | 0 / 43 / 175 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.02: {"COMMISSION_EXCEEDS_RISK_BUDGET": 32, "INVALID_PRICE_GEOMETRY": 11} -->
| trend | 3 | 0 / 43 / 175 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.03: {"COMMISSION_EXCEEDS_RISK_BUDGET": 32, "INVALID_PRICE_GEOMETRY": 11} -->
| trend | 5 | 0 / 43 / 175 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.05: {"INVALID_PRICE_GEOMETRY": 11, "TARGET_DOES_NOT_COVER_COSTS": 32} -->
| trend | 7.5 | 0 / 43 / 175 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.075: {"INVALID_PRICE_GEOMETRY": 11, "TARGET_DOES_NOT_COVER_COSTS": 32} -->
| trend | 10 | 0 / 43 / 175 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.1: {"INVALID_PRICE_GEOMETRY": 11, "TARGET_DOES_NOT_COVER_COSTS": 32} -->
| trend | 12.5 | 0 / 43 / 175 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.125: {"INVALID_PRICE_GEOMETRY": 11, "TARGET_DOES_NOT_COVER_COSTS": 32} -->
| trend | 15 | 0 / 43 / 175 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.15: {"INVALID_PRICE_GEOMETRY": 11, "TARGET_DOES_NOT_COVER_COSTS": 32} -->
| pullback | 1 | 0 / 762 / 576 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.01: {"COMMISSION_EXCEEDS_RISK_BUDGET": 582, "INVALID_PRICE_GEOMETRY": 180} -->
| pullback | 2 | 0 / 762 / 576 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.02: {"COMMISSION_EXCEEDS_RISK_BUDGET": 582, "INVALID_PRICE_GEOMETRY": 180} -->
| pullback | 3 | 0 / 762 / 576 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.03: {"COMMISSION_EXCEEDS_RISK_BUDGET": 582, "INVALID_PRICE_GEOMETRY": 180} -->
| pullback | 5 | 0 / 762 / 576 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.05: {"INVALID_PRICE_GEOMETRY": 180, "TARGET_DOES_NOT_COVER_COSTS": 582} -->
| pullback | 7.5 | 0 / 762 / 576 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.075: {"INVALID_PRICE_GEOMETRY": 180, "TARGET_DOES_NOT_COVER_COSTS": 582} -->
| pullback | 10 | 0 / 762 / 576 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.1: {"INVALID_PRICE_GEOMETRY": 180, "TARGET_DOES_NOT_COVER_COSTS": 582} -->
| pullback | 12.5 | 0 / 762 / 576 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.125: {"INVALID_PRICE_GEOMETRY": 180, "TARGET_DOES_NOT_COVER_COSTS": 582} -->
| pullback | 15 | 0 / 762 / 576 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.15: {"INVALID_PRICE_GEOMETRY": 180, "TARGET_DOES_NOT_COVER_COSTS": 582} -->
| mean_reversion | 1 | 0 / 23 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.01: {"COMMISSION_EXCEEDS_RISK_BUDGET": 21, "INVALID_PRICE_GEOMETRY": 2} -->
| mean_reversion | 2 | 0 / 23 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.02: {"COMMISSION_EXCEEDS_RISK_BUDGET": 21, "INVALID_PRICE_GEOMETRY": 2} -->
| mean_reversion | 3 | 0 / 23 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.03: {"COMMISSION_EXCEEDS_RISK_BUDGET": 21, "INVALID_PRICE_GEOMETRY": 2} -->
| mean_reversion | 5 | 0 / 23 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.05: {"INVALID_PRICE_GEOMETRY": 2, "TARGET_DOES_NOT_COVER_COSTS": 21} -->
| mean_reversion | 7.5 | 0 / 23 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.075: {"INVALID_PRICE_GEOMETRY": 2, "TARGET_DOES_NOT_COVER_COSTS": 21} -->
| mean_reversion | 10 | 0 / 23 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.1: {"INVALID_PRICE_GEOMETRY": 2, "TARGET_DOES_NOT_COVER_COSTS": 21} -->
| mean_reversion | 12.5 | 0 / 23 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.125: {"INVALID_PRICE_GEOMETRY": 2, "TARGET_DOES_NOT_COVER_COSTS": 21} -->
| mean_reversion | 15 | 0 / 23 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.15: {"INVALID_PRICE_GEOMETRY": 2, "TARGET_DOES_NOT_COVER_COSTS": 21} -->

## development

| Estrategia | Riesgo % | Admitidas / rechazadas / NO_TRADE | Win neto % | Ganancia / pérdida media USD | Bruto / neto USD | Comisiones USD | PF neto | Expectativa USD | DD cerrado / intrabar % | Días primera pérdida / break-even | EUR media | Riesgo máx USD | Ejecución IBKR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| trend | 1 | 0 / 23 / 117 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.01: {"COMMISSION_EXCEEDS_RISK_BUDGET": 20, "INVALID_PRICE_GEOMETRY": 3} -->
| trend | 2 | 0 / 23 / 117 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.02: {"COMMISSION_EXCEEDS_RISK_BUDGET": 20, "INVALID_PRICE_GEOMETRY": 3} -->
| trend | 3 | 0 / 23 / 117 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.03: {"COMMISSION_EXCEEDS_RISK_BUDGET": 20, "INVALID_PRICE_GEOMETRY": 3} -->
| trend | 5 | 0 / 23 / 117 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.05: {"INVALID_PRICE_GEOMETRY": 3, "TARGET_DOES_NOT_COVER_COSTS": 20} -->
| trend | 7.5 | 0 / 23 / 117 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.075: {"INVALID_PRICE_GEOMETRY": 3, "TARGET_DOES_NOT_COVER_COSTS": 20} -->
| trend | 10 | 0 / 23 / 117 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.1: {"INVALID_PRICE_GEOMETRY": 3, "TARGET_DOES_NOT_COVER_COSTS": 20} -->
| trend | 12.5 | 0 / 23 / 117 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.125: {"INVALID_PRICE_GEOMETRY": 3, "TARGET_DOES_NOT_COVER_COSTS": 20} -->
| trend | 15 | 0 / 23 / 117 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.15: {"INVALID_PRICE_GEOMETRY": 3, "TARGET_DOES_NOT_COVER_COSTS": 20} -->
| pullback | 1 | 0 / 496 / 406 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.01: {"COMMISSION_EXCEEDS_RISK_BUDGET": 414, "INVALID_PRICE_GEOMETRY": 82} -->
| pullback | 2 | 0 / 496 / 406 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.02: {"COMMISSION_EXCEEDS_RISK_BUDGET": 414, "INVALID_PRICE_GEOMETRY": 82} -->
| pullback | 3 | 0 / 496 / 406 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.03: {"COMMISSION_EXCEEDS_RISK_BUDGET": 414, "INVALID_PRICE_GEOMETRY": 82} -->
| pullback | 5 | 0 / 496 / 406 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.05: {"INVALID_PRICE_GEOMETRY": 82, "TARGET_DOES_NOT_COVER_COSTS": 414} -->
| pullback | 7.5 | 0 / 496 / 406 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.075: {"INVALID_PRICE_GEOMETRY": 82, "TARGET_DOES_NOT_COVER_COSTS": 414} -->
| pullback | 10 | 0 / 496 / 406 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.1: {"INVALID_PRICE_GEOMETRY": 82, "TARGET_DOES_NOT_COVER_COSTS": 414} -->
| pullback | 12.5 | 0 / 496 / 406 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.125: {"INVALID_PRICE_GEOMETRY": 82, "TARGET_DOES_NOT_COVER_COSTS": 414} -->
| pullback | 15 | 0 / 496 / 406 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.15: {"INVALID_PRICE_GEOMETRY": 82, "TARGET_DOES_NOT_COVER_COSTS": 414} -->
| mean_reversion | 1 | 0 / 17 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.01: {"COMMISSION_EXCEEDS_RISK_BUDGET": 16, "INVALID_PRICE_GEOMETRY": 1} -->
| mean_reversion | 2 | 0 / 17 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.02: {"COMMISSION_EXCEEDS_RISK_BUDGET": 16, "INVALID_PRICE_GEOMETRY": 1} -->
| mean_reversion | 3 | 0 / 17 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.03: {"COMMISSION_EXCEEDS_RISK_BUDGET": 16, "INVALID_PRICE_GEOMETRY": 1} -->
| mean_reversion | 5 | 0 / 17 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.05: {"INVALID_PRICE_GEOMETRY": 1, "TARGET_DOES_NOT_COVER_COSTS": 16} -->
| mean_reversion | 7.5 | 0 / 17 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.075: {"INVALID_PRICE_GEOMETRY": 1, "TARGET_DOES_NOT_COVER_COSTS": 16} -->
| mean_reversion | 10 | 0 / 17 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.1: {"INVALID_PRICE_GEOMETRY": 1, "TARGET_DOES_NOT_COVER_COSTS": 16} -->
| mean_reversion | 12.5 | 0 / 17 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.125: {"INVALID_PRICE_GEOMETRY": 1, "TARGET_DOES_NOT_COVER_COSTS": 16} -->
| mean_reversion | 15 | 0 / 17 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.15: {"INVALID_PRICE_GEOMETRY": 1, "TARGET_DOES_NOT_COVER_COSTS": 16} -->

## validation

| Estrategia | Riesgo % | Admitidas / rechazadas / NO_TRADE | Win neto % | Ganancia / pérdida media USD | Bruto / neto USD | Comisiones USD | PF neto | Expectativa USD | DD cerrado / intrabar % | Días primera pérdida / break-even | EUR media | Riesgo máx USD | Ejecución IBKR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| trend | 1 | 0 / 20 / 58 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.01: {"COMMISSION_EXCEEDS_RISK_BUDGET": 12, "INVALID_PRICE_GEOMETRY": 8} -->
| trend | 2 | 0 / 20 / 58 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.02: {"COMMISSION_EXCEEDS_RISK_BUDGET": 12, "INVALID_PRICE_GEOMETRY": 8} -->
| trend | 3 | 0 / 20 / 58 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.03: {"COMMISSION_EXCEEDS_RISK_BUDGET": 12, "INVALID_PRICE_GEOMETRY": 8} -->
| trend | 5 | 0 / 20 / 58 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.05: {"INVALID_PRICE_GEOMETRY": 8, "TARGET_DOES_NOT_COVER_COSTS": 12} -->
| trend | 7.5 | 0 / 20 / 58 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.075: {"INVALID_PRICE_GEOMETRY": 8, "TARGET_DOES_NOT_COVER_COSTS": 12} -->
| trend | 10 | 0 / 20 / 58 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.1: {"INVALID_PRICE_GEOMETRY": 8, "TARGET_DOES_NOT_COVER_COSTS": 12} -->
| trend | 12.5 | 0 / 20 / 58 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.125: {"INVALID_PRICE_GEOMETRY": 8, "TARGET_DOES_NOT_COVER_COSTS": 12} -->
| trend | 15 | 0 / 20 / 58 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.15: {"INVALID_PRICE_GEOMETRY": 8, "TARGET_DOES_NOT_COVER_COSTS": 12} -->
| pullback | 1 | 0 / 266 / 170 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.01: {"COMMISSION_EXCEEDS_RISK_BUDGET": 168, "INVALID_PRICE_GEOMETRY": 98} -->
| pullback | 2 | 0 / 266 / 170 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.02: {"COMMISSION_EXCEEDS_RISK_BUDGET": 168, "INVALID_PRICE_GEOMETRY": 98} -->
| pullback | 3 | 0 / 266 / 170 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.03: {"COMMISSION_EXCEEDS_RISK_BUDGET": 168, "INVALID_PRICE_GEOMETRY": 98} -->
| pullback | 5 | 0 / 266 / 170 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.05: {"INVALID_PRICE_GEOMETRY": 98, "TARGET_DOES_NOT_COVER_COSTS": 168} -->
| pullback | 7.5 | 0 / 266 / 170 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.075: {"INVALID_PRICE_GEOMETRY": 98, "TARGET_DOES_NOT_COVER_COSTS": 168} -->
| pullback | 10 | 0 / 266 / 170 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.1: {"INVALID_PRICE_GEOMETRY": 98, "TARGET_DOES_NOT_COVER_COSTS": 168} -->
| pullback | 12.5 | 0 / 266 / 170 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.125: {"INVALID_PRICE_GEOMETRY": 98, "TARGET_DOES_NOT_COVER_COSTS": 168} -->
| pullback | 15 | 0 / 266 / 170 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.15: {"INVALID_PRICE_GEOMETRY": 98, "TARGET_DOES_NOT_COVER_COSTS": 168} -->
| mean_reversion | 1 | 0 / 6 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.01: {"COMMISSION_EXCEEDS_RISK_BUDGET": 5, "INVALID_PRICE_GEOMETRY": 1} -->
| mean_reversion | 2 | 0 / 6 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.02: {"COMMISSION_EXCEEDS_RISK_BUDGET": 5, "INVALID_PRICE_GEOMETRY": 1} -->
| mean_reversion | 3 | 0 / 6 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.03: {"COMMISSION_EXCEEDS_RISK_BUDGET": 5, "INVALID_PRICE_GEOMETRY": 1} -->
| mean_reversion | 5 | 0 / 6 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.05: {"INVALID_PRICE_GEOMETRY": 1, "TARGET_DOES_NOT_COVER_COSTS": 5} -->
| mean_reversion | 7.5 | 0 / 6 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.075: {"INVALID_PRICE_GEOMETRY": 1, "TARGET_DOES_NOT_COVER_COSTS": 5} -->
| mean_reversion | 10 | 0 / 6 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.1: {"INVALID_PRICE_GEOMETRY": 1, "TARGET_DOES_NOT_COVER_COSTS": 5} -->
| mean_reversion | 12.5 | 0 / 6 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.125: {"INVALID_PRICE_GEOMETRY": 1, "TARGET_DOES_NOT_COVER_COSTS": 5} -->
| mean_reversion | 15 | 0 / 6 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.15: {"INVALID_PRICE_GEOMETRY": 1, "TARGET_DOES_NOT_COVER_COSTS": 5} -->

## walk_forward_1

| Estrategia | Riesgo % | Admitidas / rechazadas / NO_TRADE | Win neto % | Ganancia / pérdida media USD | Bruto / neto USD | Comisiones USD | PF neto | Expectativa USD | DD cerrado / intrabar % | Días primera pérdida / break-even | EUR media | Riesgo máx USD | Ejecución IBKR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| trend | 1 | 0 / 3 / 24 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.01: {"COMMISSION_EXCEEDS_RISK_BUDGET": 1, "INVALID_PRICE_GEOMETRY": 2} -->
| trend | 2 | 0 / 3 / 24 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.02: {"COMMISSION_EXCEEDS_RISK_BUDGET": 1, "INVALID_PRICE_GEOMETRY": 2} -->
| trend | 3 | 0 / 3 / 24 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.03: {"COMMISSION_EXCEEDS_RISK_BUDGET": 1, "INVALID_PRICE_GEOMETRY": 2} -->
| trend | 5 | 0 / 3 / 24 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.05: {"INVALID_PRICE_GEOMETRY": 2, "TARGET_DOES_NOT_COVER_COSTS": 1} -->
| trend | 7.5 | 0 / 3 / 24 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.075: {"INVALID_PRICE_GEOMETRY": 2, "TARGET_DOES_NOT_COVER_COSTS": 1} -->
| trend | 10 | 0 / 3 / 24 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.1: {"INVALID_PRICE_GEOMETRY": 2, "TARGET_DOES_NOT_COVER_COSTS": 1} -->
| trend | 12.5 | 0 / 3 / 24 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.125: {"INVALID_PRICE_GEOMETRY": 2, "TARGET_DOES_NOT_COVER_COSTS": 1} -->
| trend | 15 | 0 / 3 / 24 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.15: {"INVALID_PRICE_GEOMETRY": 2, "TARGET_DOES_NOT_COVER_COSTS": 1} -->
| pullback | 1 | 0 / 97 / 75 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.01: {"COMMISSION_EXCEEDS_RISK_BUDGET": 59, "INVALID_PRICE_GEOMETRY": 38} -->
| pullback | 2 | 0 / 97 / 75 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.02: {"COMMISSION_EXCEEDS_RISK_BUDGET": 59, "INVALID_PRICE_GEOMETRY": 38} -->
| pullback | 3 | 0 / 97 / 75 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.03: {"COMMISSION_EXCEEDS_RISK_BUDGET": 59, "INVALID_PRICE_GEOMETRY": 38} -->
| pullback | 5 | 0 / 97 / 75 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.05: {"INVALID_PRICE_GEOMETRY": 38, "TARGET_DOES_NOT_COVER_COSTS": 59} -->
| pullback | 7.5 | 0 / 97 / 75 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.075: {"INVALID_PRICE_GEOMETRY": 38, "TARGET_DOES_NOT_COVER_COSTS": 59} -->
| pullback | 10 | 0 / 97 / 75 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.1: {"INVALID_PRICE_GEOMETRY": 38, "TARGET_DOES_NOT_COVER_COSTS": 59} -->
| pullback | 12.5 | 0 / 97 / 75 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.125: {"INVALID_PRICE_GEOMETRY": 38, "TARGET_DOES_NOT_COVER_COSTS": 59} -->
| pullback | 15 | 0 / 97 / 75 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.15: {"INVALID_PRICE_GEOMETRY": 38, "TARGET_DOES_NOT_COVER_COSTS": 59} -->
| mean_reversion | 1 | 0 / 0 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.01: {} -->
| mean_reversion | 2 | 0 / 0 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.02: {} -->
| mean_reversion | 3 | 0 / 0 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.03: {} -->
| mean_reversion | 5 | 0 / 0 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.05: {} -->
| mean_reversion | 7.5 | 0 / 0 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.075: {} -->
| mean_reversion | 10 | 0 / 0 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.1: {} -->
| mean_reversion | 12.5 | 0 / 0 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.125: {} -->
| mean_reversion | 15 | 0 / 0 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.15: {} -->

## walk_forward_2

| Estrategia | Riesgo % | Admitidas / rechazadas / NO_TRADE | Win neto % | Ganancia / pérdida media USD | Bruto / neto USD | Comisiones USD | PF neto | Expectativa USD | DD cerrado / intrabar % | Días primera pérdida / break-even | EUR media | Riesgo máx USD | Ejecución IBKR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| trend | 1 | 0 / 4 / 18 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.01: {"COMMISSION_EXCEEDS_RISK_BUDGET": 1, "INVALID_PRICE_GEOMETRY": 3} -->
| trend | 2 | 0 / 4 / 18 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.02: {"COMMISSION_EXCEEDS_RISK_BUDGET": 1, "INVALID_PRICE_GEOMETRY": 3} -->
| trend | 3 | 0 / 4 / 18 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.03: {"COMMISSION_EXCEEDS_RISK_BUDGET": 1, "INVALID_PRICE_GEOMETRY": 3} -->
| trend | 5 | 0 / 4 / 18 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.05: {"INVALID_PRICE_GEOMETRY": 3, "TARGET_DOES_NOT_COVER_COSTS": 1} -->
| trend | 7.5 | 0 / 4 / 18 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.075: {"INVALID_PRICE_GEOMETRY": 3, "TARGET_DOES_NOT_COVER_COSTS": 1} -->
| trend | 10 | 0 / 4 / 18 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.1: {"INVALID_PRICE_GEOMETRY": 3, "TARGET_DOES_NOT_COVER_COSTS": 1} -->
| trend | 12.5 | 0 / 4 / 18 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.125: {"INVALID_PRICE_GEOMETRY": 3, "TARGET_DOES_NOT_COVER_COSTS": 1} -->
| trend | 15 | 0 / 4 / 18 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.15: {"INVALID_PRICE_GEOMETRY": 3, "TARGET_DOES_NOT_COVER_COSTS": 1} -->
| pullback | 1 | 0 / 86 / 75 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.01: {"COMMISSION_EXCEEDS_RISK_BUDGET": 39, "INVALID_PRICE_GEOMETRY": 47} -->
| pullback | 2 | 0 / 86 / 75 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.02: {"COMMISSION_EXCEEDS_RISK_BUDGET": 39, "INVALID_PRICE_GEOMETRY": 47} -->
| pullback | 3 | 0 / 86 / 75 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.03: {"COMMISSION_EXCEEDS_RISK_BUDGET": 39, "INVALID_PRICE_GEOMETRY": 47} -->
| pullback | 5 | 0 / 86 / 75 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.05: {"INVALID_PRICE_GEOMETRY": 47, "TARGET_DOES_NOT_COVER_COSTS": 39} -->
| pullback | 7.5 | 0 / 86 / 75 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.075: {"INVALID_PRICE_GEOMETRY": 47, "TARGET_DOES_NOT_COVER_COSTS": 39} -->
| pullback | 10 | 0 / 86 / 75 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.1: {"INVALID_PRICE_GEOMETRY": 47, "TARGET_DOES_NOT_COVER_COSTS": 39} -->
| pullback | 12.5 | 0 / 86 / 75 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.125: {"INVALID_PRICE_GEOMETRY": 47, "TARGET_DOES_NOT_COVER_COSTS": 39} -->
| pullback | 15 | 0 / 86 / 75 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.15: {"INVALID_PRICE_GEOMETRY": 47, "TARGET_DOES_NOT_COVER_COSTS": 39} -->
| mean_reversion | 1 | 0 / 3 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.01: {"COMMISSION_EXCEEDS_RISK_BUDGET": 2, "INVALID_PRICE_GEOMETRY": 1} -->
| mean_reversion | 2 | 0 / 3 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.02: {"COMMISSION_EXCEEDS_RISK_BUDGET": 2, "INVALID_PRICE_GEOMETRY": 1} -->
| mean_reversion | 3 | 0 / 3 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.03: {"COMMISSION_EXCEEDS_RISK_BUDGET": 2, "INVALID_PRICE_GEOMETRY": 1} -->
| mean_reversion | 5 | 0 / 3 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.05: {"INVALID_PRICE_GEOMETRY": 1, "TARGET_DOES_NOT_COVER_COSTS": 2} -->
| mean_reversion | 7.5 | 0 / 3 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.075: {"INVALID_PRICE_GEOMETRY": 1, "TARGET_DOES_NOT_COVER_COSTS": 2} -->
| mean_reversion | 10 | 0 / 3 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.1: {"INVALID_PRICE_GEOMETRY": 1, "TARGET_DOES_NOT_COVER_COSTS": 2} -->
| mean_reversion | 12.5 | 0 / 3 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.125: {"INVALID_PRICE_GEOMETRY": 1, "TARGET_DOES_NOT_COVER_COSTS": 2} -->
| mean_reversion | 15 | 0 / 3 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.15: {"INVALID_PRICE_GEOMETRY": 1, "TARGET_DOES_NOT_COVER_COSTS": 2} -->

## walk_forward_3

| Estrategia | Riesgo % | Admitidas / rechazadas / NO_TRADE | Win neto % | Ganancia / pérdida media USD | Bruto / neto USD | Comisiones USD | PF neto | Expectativa USD | DD cerrado / intrabar % | Días primera pérdida / break-even | EUR media | Riesgo máx USD | Ejecución IBKR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| trend | 1 | 0 / 13 / 16 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.01: {"COMMISSION_EXCEEDS_RISK_BUDGET": 10, "INVALID_PRICE_GEOMETRY": 3} -->
| trend | 2 | 0 / 13 / 16 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.02: {"COMMISSION_EXCEEDS_RISK_BUDGET": 10, "INVALID_PRICE_GEOMETRY": 3} -->
| trend | 3 | 0 / 13 / 16 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.03: {"COMMISSION_EXCEEDS_RISK_BUDGET": 10, "INVALID_PRICE_GEOMETRY": 3} -->
| trend | 5 | 0 / 13 / 16 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.05: {"INVALID_PRICE_GEOMETRY": 3, "TARGET_DOES_NOT_COVER_COSTS": 10} -->
| trend | 7.5 | 0 / 13 / 16 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.075: {"INVALID_PRICE_GEOMETRY": 3, "TARGET_DOES_NOT_COVER_COSTS": 10} -->
| trend | 10 | 0 / 13 / 16 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.1: {"INVALID_PRICE_GEOMETRY": 3, "TARGET_DOES_NOT_COVER_COSTS": 10} -->
| trend | 12.5 | 0 / 13 / 16 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.125: {"INVALID_PRICE_GEOMETRY": 3, "TARGET_DOES_NOT_COVER_COSTS": 10} -->
| trend | 15 | 0 / 13 / 16 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- trend 0.15: {"INVALID_PRICE_GEOMETRY": 3, "TARGET_DOES_NOT_COVER_COSTS": 10} -->
| pullback | 1 | 0 / 83 / 20 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.01: {"COMMISSION_EXCEEDS_RISK_BUDGET": 70, "INVALID_PRICE_GEOMETRY": 13} -->
| pullback | 2 | 0 / 83 / 20 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.02: {"COMMISSION_EXCEEDS_RISK_BUDGET": 70, "INVALID_PRICE_GEOMETRY": 13} -->
| pullback | 3 | 0 / 83 / 20 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.03: {"COMMISSION_EXCEEDS_RISK_BUDGET": 70, "INVALID_PRICE_GEOMETRY": 13} -->
| pullback | 5 | 0 / 83 / 20 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.05: {"INVALID_PRICE_GEOMETRY": 13, "TARGET_DOES_NOT_COVER_COSTS": 70} -->
| pullback | 7.5 | 0 / 83 / 20 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.075: {"INVALID_PRICE_GEOMETRY": 13, "TARGET_DOES_NOT_COVER_COSTS": 70} -->
| pullback | 10 | 0 / 83 / 20 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.1: {"INVALID_PRICE_GEOMETRY": 13, "TARGET_DOES_NOT_COVER_COSTS": 70} -->
| pullback | 12.5 | 0 / 83 / 20 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.125: {"INVALID_PRICE_GEOMETRY": 13, "TARGET_DOES_NOT_COVER_COSTS": 70} -->
| pullback | 15 | 0 / 83 / 20 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- pullback 0.15: {"INVALID_PRICE_GEOMETRY": 13, "TARGET_DOES_NOT_COVER_COSTS": 70} -->
| mean_reversion | 1 | 0 / 3 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.01: {"COMMISSION_EXCEEDS_RISK_BUDGET": 3} -->
| mean_reversion | 2 | 0 / 3 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.02: {"COMMISSION_EXCEEDS_RISK_BUDGET": 3} -->
| mean_reversion | 3 | 0 / 3 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.03: {"COMMISSION_EXCEEDS_RISK_BUDGET": 3} -->
| mean_reversion | 5 | 0 / 3 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.05: {"TARGET_DOES_NOT_COVER_COSTS": 3} -->
| mean_reversion | 7.5 | 0 / 3 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.075: {"TARGET_DOES_NOT_COVER_COSTS": 3} -->
| mean_reversion | 10 | 0 / 3 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.1: {"TARGET_DOES_NOT_COVER_COSTS": 3} -->
| mean_reversion | 12.5 | 0 / 3 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.125: {"TARGET_DOES_NOT_COVER_COSTS": 3} -->
| mean_reversion | 15 | 0 / 3 / 0 | n/a | n/a / n/a | 0.00000 / 0.00000 | 0.00000 | n/a | n/a | 0.00000 / 0.00000 | 0 / 0 | n/a | n/a | UNKNOWN |
<!-- mean_reversion 0.15: {"TARGET_DOES_NOT_COVER_COSTS": 3} -->

## Rechazos y tamaño de muestra fuera de muestra

| Estrategia | Riesgo % | Rechazos | n / días | Wilson 95% | Wilson familia 95% (24 comparaciones) | CI bootstrap win / expectativa |
|---|---:|---|---:|---|---|---|
| trend | 1 | {"COMMISSION_EXCEEDS_RISK_BUDGET": 12, "INVALID_PRICE_GEOMETRY": 8} | 0 / 0 | n/a | n/a | n/a / n/a |
| trend | 2 | {"COMMISSION_EXCEEDS_RISK_BUDGET": 12, "INVALID_PRICE_GEOMETRY": 8} | 0 / 0 | n/a | n/a | n/a / n/a |
| trend | 3 | {"COMMISSION_EXCEEDS_RISK_BUDGET": 12, "INVALID_PRICE_GEOMETRY": 8} | 0 / 0 | n/a | n/a | n/a / n/a |
| trend | 5 | {"INVALID_PRICE_GEOMETRY": 8, "TARGET_DOES_NOT_COVER_COSTS": 12} | 0 / 0 | n/a | n/a | n/a / n/a |
| trend | 7.5 | {"INVALID_PRICE_GEOMETRY": 8, "TARGET_DOES_NOT_COVER_COSTS": 12} | 0 / 0 | n/a | n/a | n/a / n/a |
| trend | 10 | {"INVALID_PRICE_GEOMETRY": 8, "TARGET_DOES_NOT_COVER_COSTS": 12} | 0 / 0 | n/a | n/a | n/a / n/a |
| trend | 12.5 | {"INVALID_PRICE_GEOMETRY": 8, "TARGET_DOES_NOT_COVER_COSTS": 12} | 0 / 0 | n/a | n/a | n/a / n/a |
| trend | 15 | {"INVALID_PRICE_GEOMETRY": 8, "TARGET_DOES_NOT_COVER_COSTS": 12} | 0 / 0 | n/a | n/a | n/a / n/a |
| pullback | 1 | {"COMMISSION_EXCEEDS_RISK_BUDGET": 168, "INVALID_PRICE_GEOMETRY": 98} | 0 / 0 | n/a | n/a | n/a / n/a |
| pullback | 2 | {"COMMISSION_EXCEEDS_RISK_BUDGET": 168, "INVALID_PRICE_GEOMETRY": 98} | 0 / 0 | n/a | n/a | n/a / n/a |
| pullback | 3 | {"COMMISSION_EXCEEDS_RISK_BUDGET": 168, "INVALID_PRICE_GEOMETRY": 98} | 0 / 0 | n/a | n/a | n/a / n/a |
| pullback | 5 | {"INVALID_PRICE_GEOMETRY": 98, "TARGET_DOES_NOT_COVER_COSTS": 168} | 0 / 0 | n/a | n/a | n/a / n/a |
| pullback | 7.5 | {"INVALID_PRICE_GEOMETRY": 98, "TARGET_DOES_NOT_COVER_COSTS": 168} | 0 / 0 | n/a | n/a | n/a / n/a |
| pullback | 10 | {"INVALID_PRICE_GEOMETRY": 98, "TARGET_DOES_NOT_COVER_COSTS": 168} | 0 / 0 | n/a | n/a | n/a / n/a |
| pullback | 12.5 | {"INVALID_PRICE_GEOMETRY": 98, "TARGET_DOES_NOT_COVER_COSTS": 168} | 0 / 0 | n/a | n/a | n/a / n/a |
| pullback | 15 | {"INVALID_PRICE_GEOMETRY": 98, "TARGET_DOES_NOT_COVER_COSTS": 168} | 0 / 0 | n/a | n/a | n/a / n/a |
| mean_reversion | 1 | {"COMMISSION_EXCEEDS_RISK_BUDGET": 5, "INVALID_PRICE_GEOMETRY": 1} | 0 / 0 | n/a | n/a | n/a / n/a |
| mean_reversion | 2 | {"COMMISSION_EXCEEDS_RISK_BUDGET": 5, "INVALID_PRICE_GEOMETRY": 1} | 0 / 0 | n/a | n/a | n/a / n/a |
| mean_reversion | 3 | {"COMMISSION_EXCEEDS_RISK_BUDGET": 5, "INVALID_PRICE_GEOMETRY": 1} | 0 / 0 | n/a | n/a | n/a / n/a |
| mean_reversion | 5 | {"INVALID_PRICE_GEOMETRY": 1, "TARGET_DOES_NOT_COVER_COSTS": 5} | 0 / 0 | n/a | n/a | n/a / n/a |
| mean_reversion | 7.5 | {"INVALID_PRICE_GEOMETRY": 1, "TARGET_DOES_NOT_COVER_COSTS": 5} | 0 / 0 | n/a | n/a | n/a / n/a |
| mean_reversion | 10 | {"INVALID_PRICE_GEOMETRY": 1, "TARGET_DOES_NOT_COVER_COSTS": 5} | 0 / 0 | n/a | n/a | n/a / n/a |
| mean_reversion | 12.5 | {"INVALID_PRICE_GEOMETRY": 1, "TARGET_DOES_NOT_COVER_COSTS": 5} | 0 / 0 | n/a | n/a | n/a / n/a |
| mean_reversion | 15 | {"INVALID_PRICE_GEOMETRY": 1, "TARGET_DOES_NOT_COVER_COSTS": 5} | 0 / 0 | n/a | n/a | n/a / n/a |

## Protocolo estadístico y selección

Se fijaron previamente los ocho riesgos y tres estrategias, sin optimización. Walk-forward expansivo: cuatro meses iniciales de desarrollo y tres bloques contiguos de validación; separación de 15 minutos entre entrenamiento y prueba. Los indicadores solo usan contexto pasado. No se suman los resultados de asignaciones independientes.

Mínimos de investigación: 100 trades OOS y 30 días con trades; tres folds con beneficio neto positivo; win rate neto estrictamente >80%; límites inferiores de Wilson ajustado y bootstrap >80%; expectativa neta y su límite inferior >0; PF >1; drawdown intrabar ≤20%; restricciones IBKR comprobadas y una nueva muestra jamás examinada. Son criterios de investigación, no garantías ni autorización.

El dataset de validación ya fue usado en investigaciones anteriores: sus resultados no constituyen confirmación nueva. Un intervalo n/a con n=0 no equivale a 0% ni 100% de acierto. El bootstrap usa bloques de cinco días de trades y semilla reproducible; es aproximado y puede omitir dependencia más larga.

Referencias metodológicas: [Wilson/NIST](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm), [intervalos simultáneos Bonferroni/NIST](https://www.itl.nist.gov/div898/handbook/prc/section4/prc473.htm), [validación temporal/scikit-learn](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html).

## Perfil experimental recomendado

Ninguno para activación. Aumentar el porcentaje de riesgo sin aumentar exposición no elimina la comisión fija ni crea una expectativa positiva. Se conserva PAPER_EXPERIMENTAL_10_PERCENT operativo protegido y sin activar. El perfil mínimo viable no se pudo identificar.

## Restricciones de ejecución IBKR

El contrato informa mínimo 0.01 EUR e incremento 0.01 EUR; esa metadata no certifica permisos de cuenta, margen ni ejecución de todos los tamaños. Solo consta un diagnóstico Paper de 100 EUR. Todos los tamaños financiables aquí son inferiores al [mínimo estándar IDEALPRO de 20,000 EUR publicado por IBKR](https://investors.interactivebrokers.com/en/?f=5479) y se etiquetan odd lot; su tratamiento efectivo sigue pendiente.

La [tarifa pública de spot currencies IBKR](https://www.interactivebrokers.com/en/pricing/commissions-spot-currencies.php) incluye mínimos por orden, pero no sustituye la tarifa de esta cuenta. El modelo utiliza los US$2 observados en cada lado de un único diagnóstico; no asume margen disponible ni apalancamiento adicional.

## Limitaciones

- Existing validation has already been examined; this is retrospective OOS replay, not fresh untouched confirmation.
- 24 risk/strategy comparisons are disclosed; Wilson and block-bootstrap intervals use Bonferroni family correction.
- No parameters are refitted; expanding chronological training windows only establish past-only context.
- Each partition/fold starts independent USD100/USD20. Never add their P&L or compare them as one persistent account.
- Six-month replay carries consumed losses continuously, including across the development/validation boundary.
- Model includes BUY and SELL; protected Paper strategy adapter supports long entries only.
- Original research exit semantics shared; actual broker execution equivalence is not certified.
- OHLC cannot identify intrabar fill times; exit timestamps follow original close/next-open model.
- Pending/uncertain outcomes retain one-position lock across local midnight; replay assumes estimated fees finalized at exit.
- Gap reserve is a sizing buffer. Actual modeled gaps enter gross P&L and may exceed the budget.
- Maximum archived average/tick spread is a stress scenario, not reconstructed historical executable BID/ASK.
- Current Paper fees and archive-wide spread stress are applied counterfactually to past signals; they are not an ex-ante historical cost forecast.
- The commission-only upper bound ignores risk and all variable costs to test whether any first target can cover fixed fees at 1x.
- Full notional plus round-trip costs funded from own equity; margin, actual tariff and odd-lot eligibility remain unknown.
- No-trade win rate, expectancy, average win/loss and PF are undefined. Zero P&L/drawdown does not establish viability.

## Alternativas de investigación

- Obtain authoritative small-size Paper tariff, margin and odd-lot evidence through a separately authorized diagnostic.
- Collect fresh untouched data and historical executable BID/ASK/slippage observations.
- Investigate fee-compatible instruments or a different virtual capital in a separately approved research scope.
- Do not raise leverage or operative risk to compensate for fixed commissions.

## Condiciones pendientes antes de considerar PaperAuto

- Evidencia económica nueva y suficiente, resultado neto positivo y tasas/intervalos exigidos.
- Tarifas, cantidades, margen y semántica de ejecución verificadas; no eliminar STRATEGY_PAPER_EVIDENCE_REQUIRED para hacer pasar el laboratorio.
- Identidad Paper y reconciliación frescas; revisión explícita del operador para emergencia y permiso PaperAuto nuevo.
- Cualquier riesgo operativo diferente requiere decisión expresa y un cambio separado; este laboratorio jamás lo autoriza.
- Live permanece absolutamente bloqueado.

## Reproducción del laboratorio sin broker

```powershell
dotnet build TradingAgent.sln -m:1
$env:PYTHONPATH = "python"
.venv/Scripts/python.exe -m trading_agent.progressive_risk_research --root .
```

Salida completa: `artifacts/research/progressive-risk/report.json` y `comparison.csv`. El proceso solo lee el archivo auténtico y escribe evidencia de simulación; no consulta TWS ni registra permisos.

## Regresiones y archivos de esta entrega

Verificación 2026-10-06T07:33:52.375998+00:00: **665 pruebas aprobadas** (439 Python + 226 C#), 0 fallidas y 0 omitidas. Build sin warnings/errores, compileall Python correcto; PostgreSQL de pruebas iniciado y detenido, sin utilizar la base Paper.

Se preservaron las 623 pruebas anteriores y se agregaron 42 (18 Python, 24 C#). Cubren costos, ocho riesgos, exposición aislada, resultados inciertos, pérdida/break-even diario, America/Santo_Domingo, reinicios, pérdida acumulada, salidas originales, cronología, intervalos y selección conservadora.

Los 19 controles/archivos protegidos comparados permanecieron idénticos; emergencia activa, permiso PaperAuto ausente y cero órdenes de esta investigación. Logs y hashes en `artifacts/test-results/progressive-risk/`.

Archivos de código/documentación agregados o modificados:

- `TradingAgent.sln`
- `src/TradingAgent.ResearchLab/TradingAgent.ResearchLab.csproj`
- `src/TradingAgent.ResearchLab/ProgressiveRisk.cs`
- `src/TradingAgent.ResearchLab/Program.cs`
- `python/trading_agent/progressive_risk_research.py`
- `python/tests/test_progressive_risk_research.py`
- `tests/TradingAgent.Tests/TradingAgent.Tests.csproj`
- `tests/TradingAgent.Tests/ProgressiveRiskResearchTests.cs`
- `docs/architecture/progressive-risk-research.md`
- `docs/architecture/paper-execution-laboratory.md`

Evidencia generada: `report.json`, `comparison.csv`, informe Markdown y logs/hashes de verificación. No se alteraron parámetros ni versiones de estrategia.
