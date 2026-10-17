# Frozen Paper economic sweep

Dataset `bb95c4d5394704af60d7c4ccde15710f504daddf1463f3b9ac44c68f39e87c8c`; six months 2026-04-03T00:00:00+00:00 to 2026-10-03T00:00:00+00:00; validation starts 2026-08-03T00:00:00+00:00.

All sizes are conditional estimates. Actual margin, odd-lot execution and account commissions remain UNKNOWN. Active exposure stays 1x. No promotion is issued.

USD100 equity; risk min(10% equity, USD10, remaining cumulative loss allowance); cumulative losses USD20, profits never replenish consumed losses.

Costs: USD2 opening + USD2 closing; spread 0.00005; round-trip slippage 0.00045; adverse gap reserve 0.00005 USD/EUR. Original ATR stop/target and exits unchanged.

No-trade P&L/statistics are n/a. PF is n/a when there is no losing trade. Drawdown is a fraction of peak equity. Target-fail percentage screens structurally eligible signals at initial capital and includes sizes of zero.

Continuous samples stop permanently at the cumulative budget; partitions each start their own independent allocation, as in the original research protocol. Do not add their trade counts or P&L.

## Exact existing strategy versions

- trend: `9860cd16f4f43d38ca7c29f161aea82e17dea100da48bb78259457cc31133211` (V1).
- pullback: `b622e9522da52b2aec358a4623d671b5398990d00e812a8fb81e2c71d155a9d3` (V1).
- mean_reversion: `fcd256a67a14d26c3e58cf73e0906713c09ed50aef69f67b99e92f52fcac80c2` (V1).

## continuous_six_months

| Strategy | Cap x | Trades | Qty mean / median EUR | Risk mean / max USD | Costs USD | Gross USD | Net USD | Target <= costs % | Win % | Net PF | Expectancy USD | DD closed / intrabar bound % | First-loss days / zero days | Days entries / potential | Odd lots |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| trend | 1 | 0 | n/a / n/a | n/a / n/a | n/a | n/a | n/a | 100.0000 | n/a | n/a | n/a | n/a / n/a | 0 / 0 | 0 / 0 | 0 |
| trend | 5 | 0 | n/a / n/a | n/a / n/a | n/a | n/a | n/a | 100.0000 | n/a | n/a | n/a | n/a / n/a | 0 / 0 | 0 / 0 | 0 |
| trend | 10 | 0 | n/a / n/a | n/a / n/a | n/a | n/a | n/a | 100.0000 | n/a | n/a | n/a | n/a / n/a | 0 / 0 | 0 / 0 | 0 |
| trend | 20 | 0 | n/a / n/a | n/a / n/a | n/a | n/a | n/a | 100.0000 | n/a | n/a | n/a | n/a / n/a | 0 / 0 | 0 / 0 | 0 |
| trend | 30 | 2 | 2508.0500 / 2508.0500 | 9.3325 / 9.6333 | 10.5081 | -5.3796 | -15.8876 | 90.6977 | 0.0000 | 0.0000 | -7.9438 | 15.8876 / 15.8876 | 2 / 0 | 2 / 4 | 2 |
| trend | 50 | 3 | 2947.0867 / 2734.6100 | 9.7721 / 10.0000 | 16.4206 | 0.3980 | -16.0226 | 76.7442 | 33.3333 | 0.0206 | -5.3409 | 16.3043 / 16.3043 | 2 / 0 | 3 / 9 | 3 |
| pullback | 1 | 0 | n/a / n/a | n/a / n/a | n/a | n/a | n/a | 100.0000 | n/a | n/a | n/a | n/a / n/a | 0 / 0 | 0 / 0 | 0 |
| pullback | 5 | 0 | n/a / n/a | n/a / n/a | n/a | n/a | n/a | 100.0000 | n/a | n/a | n/a | n/a / n/a | 0 / 0 | 0 / 0 | 0 |
| pullback | 10 | 0 | n/a / n/a | n/a / n/a | n/a | n/a | n/a | 100.0000 | n/a | n/a | n/a | n/a / n/a | 0 / 0 | 0 / 0 | 0 |
| pullback | 20 | 2 | 1682.4550 / 1682.4550 | 8.3635 / 8.5162 | 9.6825 | 3.6253 | -6.0572 | 98.5564 | 50.0000 | 0.0185 | -3.0286 | 6.1715 / 11.8997 | 1 / 0 | 2 / 3 | 2 |
| pullback | 30 | 2 | 2326.6350 / 2326.6350 | 9.4457 / 10.0000 | 10.3266 | -5.3301 | -15.6568 | 89.3701 | 0.0000 | 0.0000 | -7.8284 | 15.6568 / 15.6568 | 2 / 0 | 2 / 26 | 2 |
| pullback | 50 | 2 | 2531.3400 / 2531.3400 | 9.5079 / 10.0000 | 10.5313 | -5.7218 | -16.2531 | 65.2231 | 0.0000 | 0.0000 | -8.1266 | 16.2531 / 18.5135 | 2 / 0 | 2 / 57 | 2 |
| mean_reversion | 1 | 0 | n/a / n/a | n/a / n/a | n/a | n/a | n/a | 100.0000 | n/a | n/a | n/a | n/a / n/a | 0 / 0 | 0 / 0 | 0 |
| mean_reversion | 5 | 0 | n/a / n/a | n/a / n/a | n/a | n/a | n/a | 100.0000 | n/a | n/a | n/a | n/a / n/a | 0 / 0 | 0 / 0 | 0 |
| mean_reversion | 10 | 0 | n/a / n/a | n/a / n/a | n/a | n/a | n/a | 100.0000 | n/a | n/a | n/a | n/a / n/a | 0 / 0 | 0 / 0 | 0 |
| mean_reversion | 20 | 1 | 1731.4000 / 1731.4000 | 8.7341 / 8.7341 | 4.8657 | -3.7818 | -8.6475 | 95.6522 | 0.0000 | 0.0000 | -8.6475 | 8.6475 / 8.6475 | 1 / 0 | 1 / 1 | 1 |
| mean_reversion | 30 | 3 | 2277.3933 / 2457.2400 | 9.0751 / 9.2094 | 15.4161 | -3.6666 | -19.0827 | 78.2609 | 0.0000 | 0.0000 | -6.3609 | 19.0827 / 19.0827 | 3 / 0 | 3 / 5 | 3 |
| mean_reversion | 50 | 2 | 2961.1800 / 2961.1800 | 9.6487 / 10.0000 | 10.9612 | -1.6091 | -12.5703 | 60.8696 | 0.0000 | 0.0000 | -6.2852 | 12.5703 / 13.0807 | 2 / 0 | 2 / 9 | 2 |

## development

| Strategy | Cap x | Trades | Qty mean / median EUR | Risk mean / max USD | Costs USD | Gross USD | Net USD | Target <= costs % | Win % | Net PF | Expectancy USD | DD closed / intrabar bound % | First-loss days / zero days | Days entries / potential | Odd lots |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| trend | 1 | 0 | n/a / n/a | n/a / n/a | n/a | n/a | n/a | 100.0000 | n/a | n/a | n/a | n/a / n/a | 0 / 0 | 0 / 0 | 0 |
| trend | 5 | 0 | n/a / n/a | n/a / n/a | n/a | n/a | n/a | 100.0000 | n/a | n/a | n/a | n/a / n/a | 0 / 0 | 0 / 0 | 0 |
| trend | 10 | 0 | n/a / n/a | n/a / n/a | n/a | n/a | n/a | 100.0000 | n/a | n/a | n/a | n/a / n/a | 0 / 0 | 0 / 0 | 0 |
| trend | 20 | 0 | n/a / n/a | n/a / n/a | n/a | n/a | n/a | 100.0000 | n/a | n/a | n/a | n/a / n/a | 0 / 0 | 0 / 0 | 0 |
| trend | 30 | 2 | 2508.0500 / 2508.0500 | 9.3325 / 9.6333 | 10.5081 | -5.3796 | -15.8876 | 86.9565 | 0.0000 | 0.0000 | -7.9438 | 15.8876 / 15.8876 | 2 / 0 | 2 / 3 | 2 |
| trend | 50 | 3 | 2947.0867 / 2734.6100 | 9.7721 / 10.0000 | 16.4206 | 0.3980 | -16.0226 | 69.5652 | 33.3333 | 0.0206 | -5.3409 | 16.3043 / 16.3043 | 2 / 0 | 3 / 6 | 3 |
| pullback | 1 | 0 | n/a / n/a | n/a / n/a | n/a | n/a | n/a | 100.0000 | n/a | n/a | n/a | n/a / n/a | 0 / 0 | 0 / 0 | 0 |
| pullback | 5 | 0 | n/a / n/a | n/a / n/a | n/a | n/a | n/a | 100.0000 | n/a | n/a | n/a | n/a / n/a | 0 / 0 | 0 / 0 | 0 |
| pullback | 10 | 0 | n/a / n/a | n/a / n/a | n/a | n/a | n/a | 100.0000 | n/a | n/a | n/a | n/a / n/a | 0 / 0 | 0 / 0 | 0 |
| pullback | 20 | 1 | 1703.1200 / 1703.1200 | 8.5162 / 8.5162 | 4.8516 | -1.3199 | -6.1715 | 98.5887 | 0.0000 | 0.0000 | -6.1715 | 6.1715 / 8.2067 | 1 / 0 | 1 / 2 | 1 |
| pullback | 30 | 2 | 2326.6350 / 2326.6350 | 9.4457 / 10.0000 | 10.3266 | -5.3301 | -15.6568 | 87.2984 | 0.0000 | 0.0000 | -7.8284 | 15.6568 / 15.6568 | 2 / 0 | 2 / 20 | 2 |
| pullback | 50 | 2 | 2531.3400 / 2531.3400 | 9.5079 / 10.0000 | 10.5313 | -5.7218 | -16.2531 | 58.2661 | 0.0000 | 0.0000 | -8.1266 | 16.2531 / 18.5135 | 2 / 0 | 2 / 38 | 2 |
| mean_reversion | 1 | 0 | n/a / n/a | n/a / n/a | n/a | n/a | n/a | 100.0000 | n/a | n/a | n/a | n/a / n/a | 0 / 0 | 0 / 0 | 0 |
| mean_reversion | 5 | 0 | n/a / n/a | n/a / n/a | n/a | n/a | n/a | 100.0000 | n/a | n/a | n/a | n/a / n/a | 0 / 0 | 0 / 0 | 0 |
| mean_reversion | 10 | 0 | n/a / n/a | n/a / n/a | n/a | n/a | n/a | 100.0000 | n/a | n/a | n/a | n/a / n/a | 0 / 0 | 0 / 0 | 0 |
| mean_reversion | 20 | 1 | 1731.4000 / 1731.4000 | 8.7341 / 8.7341 | 4.8657 | -3.7818 | -8.6475 | 94.1176 | 0.0000 | 0.0000 | -8.6475 | 8.6475 / 8.6475 | 1 / 0 | 1 / 1 | 1 |
| mean_reversion | 30 | 3 | 2277.3933 / 2457.2400 | 9.0751 / 9.2094 | 15.4161 | -3.6666 | -19.0827 | 76.4706 | 0.0000 | 0.0000 | -6.3609 | 19.0827 / 19.0827 | 3 / 0 | 3 / 4 | 3 |
| mean_reversion | 50 | 2 | 2961.1800 / 2961.1800 | 9.6487 / 10.0000 | 10.9612 | -1.6091 | -12.5703 | 58.8235 | 0.0000 | 0.0000 | -6.2852 | 12.5703 / 13.0807 | 2 / 0 | 2 / 7 | 2 |

## validation

| Strategy | Cap x | Trades | Qty mean / median EUR | Risk mean / max USD | Costs USD | Gross USD | Net USD | Target <= costs % | Win % | Net PF | Expectancy USD | DD closed / intrabar bound % | First-loss days / zero days | Days entries / potential | Odd lots |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| trend | 1 | 0 | n/a / n/a | n/a / n/a | n/a | n/a | n/a | 100.0000 | n/a | n/a | n/a | n/a / n/a | 0 / 0 | 0 / 0 | 0 |
| trend | 5 | 0 | n/a / n/a | n/a / n/a | n/a | n/a | n/a | 100.0000 | n/a | n/a | n/a | n/a / n/a | 0 / 0 | 0 / 0 | 0 |
| trend | 10 | 0 | n/a / n/a | n/a / n/a | n/a | n/a | n/a | 100.0000 | n/a | n/a | n/a | n/a / n/a | 0 / 0 | 0 / 0 | 0 |
| trend | 20 | 0 | n/a / n/a | n/a / n/a | n/a | n/a | n/a | 100.0000 | n/a | n/a | n/a | n/a / n/a | 0 / 0 | 0 / 0 | 0 |
| trend | 30 | 1 | 2645.5900 / 2645.5900 | 9.4910 / 9.4910 | 5.3228 | 6.0538 | 0.7310 | 95.0000 | 100.0000 | n/a | 0.7310 | 0.0000 / 5.7196 | 0 / 0 | 1 / 1 | 1 |
| trend | 50 | 3 | 3210.9300 / 3272.6600 | 10.0000 / 10.0000 | 16.8164 | 19.0529 | 2.2365 | 85.0000 | 100.0000 | n/a | 0.7455 | 0.0000 / 6.3062 | 0 / 0 | 3 / 3 | 3 |
| pullback | 1 | 0 | n/a / n/a | n/a / n/a | n/a | n/a | n/a | 100.0000 | n/a | n/a | n/a | n/a / n/a | 0 / 0 | 0 / 0 | 0 |
| pullback | 5 | 0 | n/a / n/a | n/a / n/a | n/a | n/a | n/a | 100.0000 | n/a | n/a | n/a | n/a / n/a | 0 / 0 | 0 / 0 | 0 |
| pullback | 10 | 0 | n/a / n/a | n/a / n/a | n/a | n/a | n/a | 100.0000 | n/a | n/a | n/a | n/a / n/a | 0 / 0 | 0 / 0 | 0 |
| pullback | 20 | 2 | 1778.6200 / 1778.6200 | 8.4064 / 8.4877 | 9.7786 | 1.9277 | -7.8509 | 98.4962 | 50.0000 | 0.0467 | -3.9255 | 8.2042 / 8.2042 | 1 / 0 | 1 / 1 | 2 |
| pullback | 30 | 3 | 2404.7833 / 2400.5800 | 9.2290 / 9.4938 | 15.6072 | 0.8022 | -14.8049 | 93.2331 | 33.3333 | 0.0426 | -4.9350 | 14.8049 / 16.0292 | 2 / 0 | 2 / 6 | 3 |
| pullback | 50 | 5 | 2494.4660 / 2468.0500 | 9.2463 / 10.0000 | 26.2362 | 11.3549 | -14.8812 | 78.1955 | 60.0000 | 0.0673 | -2.9762 | 14.8812 / 17.8070 | 2 / 0 | 4 / 19 | 5 |
| mean_reversion | 1 | 0 | n/a / n/a | n/a / n/a | n/a | n/a | n/a | 100.0000 | n/a | n/a | n/a | n/a / n/a | 0 / 0 | 0 / 0 | 0 |
| mean_reversion | 5 | 0 | n/a / n/a | n/a / n/a | n/a | n/a | n/a | 100.0000 | n/a | n/a | n/a | n/a / n/a | 0 / 0 | 0 / 0 | 0 |
| mean_reversion | 10 | 0 | n/a / n/a | n/a / n/a | n/a | n/a | n/a | 100.0000 | n/a | n/a | n/a | n/a / n/a | 0 / 0 | 0 / 0 | 0 |
| mean_reversion | 20 | 0 | n/a / n/a | n/a / n/a | n/a | n/a | n/a | 100.0000 | n/a | n/a | n/a | n/a / n/a | 0 / 0 | 0 / 0 | 0 |
| mean_reversion | 30 | 1 | 2646.3600 / 2646.3600 | 9.1357 / 9.1357 | 5.3232 | 0.4499 | -4.8733 | 83.3333 | 0.0000 | 0.0000 | -4.8733 | 4.8733 / 5.4820 | 1 / 0 | 1 / 1 | 1 |
| mean_reversion | 50 | 2 | 3017.2150 / 3017.2150 | 9.6780 / 10.0000 | 11.0172 | -0.3331 | -11.3503 | 66.6667 | 0.0000 | 0.0000 | -5.6752 | 11.3503 / 11.9851 | 2 / 0 | 2 / 2 | 2 |

## Minimum sizes with strictly positive conservative target

This selects the smallest historical eligible opportunity satisfying the USD10 risk cap, not a size for today. Net at this boundary is almost zero. Every signal minimum and exact daily first-loss timestamp is in economic-sweep.json.

| Strategy | Signal UTC / side | EUR | USD notional | Exposure x | Stop USD | Costs USD | Gap reserve USD | Total risk USD | Gross target USD | Net target USD |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| trend | 2026-07-31T17:00:00+00:00 / BUY | 1864.8200 | 2147.7971 | 21.4780 | 3.3504 | 4.9324 | 0.0932 | 8.3761 | 5.0257 | 0.00001293 |
| pullback | 2026-04-21T19:45:00+00:00 / SELL | 1358.7000 | 1592.9874 | 15.9299 | 3.1649 | 4.6794 | 0.0679 | 7.9121 | 4.7473 | 0.00000478 |
| mean_reversion | 2026-06-11T18:00:00+00:00 / SELL | 1467.1500 | 1694.7490 | 16.9475 | 3.2046 | 4.7336 | 0.0734 | 8.0116 | 4.8069 | 0.00001132 |

## Limitations

- Hypothetical BUY and SELL research; current protected Paper transport supports BUY entries only.
- Constant conservative spread/slippage estimates, not historical executable quote reconstruction.
- Gap reserve is included in sizing and potential target screening; actual model stop gaps change gross P&L.
- Gaps can exceed the reserved amount; USD10/USD20 are entry budgets, not guarantees on fills.
- Costs assume USD2 each side and no percentage surcharge in this size range; this account tariff remains unverified.
- Potential net >0 is a strict mathematical threshold, not a reasonable profit or positive expectancy.
- Positions one at a time; fees finalized synchronously only in offline replay; runtime remains pending until actual fees reconcile.
- MarginRate=1 is an unused serialization placeholder, not evidence of actual margin; no candidate called viable.
- No parameter optimization, no active leverage or authorization changes, no broker order or what-if request.
