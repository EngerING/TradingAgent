# Kronos local — observation EUR/USD

Auditoría de recuperación, causas verificadas y límites actuales: [kronos-recovery-20261008.md](kronos-recovery-20261008.md).

Integration zero-shot, exclusively `KRONOS_OBSERVATION_ONLY / SHADOW_FEATURE`.
No broker transport, authorization, strategy promotion or OpenAI inference exists in this module.
`paperEligible=false`, `liveEnabled=false`, `executionAuthority=false` remain explicit in the persisted evidence and UI.
Original Shadow, its cost-aware sidecar, Forex V1, H40, AccountBinding, EmergencyStop, RiskEngine and execution profiles are preserved.

## Audited sources and reproducibility

- Official repository: https://github.com/shiyu-coder/Kronos
- Commit: `67b630e67f6a18c9e9be918d9b4337c960db1e9a`.
- Code license MIT, copyright 2025 ShiYu; full notice preserved in `KRONOS_LICENSE.txt` and the isolated checkout.
- Model `NeoQuasar/Kronos-base`, revision `2b554741eca47781b64468546e77fef3e85130e6`.
- Tokenizer `NeoQuasar/Kronos-Tokenizer-base`, revision `0e0117387f39004a9016484a186a908917e22426`.
- Both public model cards declare MIT; cards are retained beside the weights.
- `config/kronos/upstream-lock.json` records SHA256 of every executed upstream source and every downloaded config/weight/card.
- `config/kronos/requirements.lock.txt` fixes the complete installed dependency set.

Upstream recommends Python 3.10+ and torch >=2.0.0; it does not pin one Python version.
This machine uses isolated Python 3.13, PyTorch 2.8.0+cu128, float32, numpy 2.2.6, pandas 2.2.3,
einops 0.8.1, huggingface_hub 0.33.1, safetensors 0.6.2 and tqdm 4.67.1.
Pandas 2.2.3 replaces the upstream 2.2.2 requirement to use a Python 3.13 wheel.
Matplotlib, Qlib, Comet and training dependencies are not installed for inference.

The executed upstream files are `model/__init__.py`, `model/kronos.py`, `model/module.py`, inspected before import.
No repository demo, web UI, training script, shell script or setup hook is executed.
Model instances are constructed from audited classes and locally hashed `config.json`; weights load with safetensors, not pickle or `torch.load`.
No `trust_remote_code`, Hub Python downloads or private Hugging Face token is used.
Downloads use official public Hub repositories with fixed revisions and allowlisted filenames.
The dependency wheels are executable software from PyPI / the official PyTorch CUDA index; versions are pinned, not a claim of a full supply-chain security certification.
The main TradingAgent `.venv` has no added Torch dependencies.

## Runtime boundary

```
Existing IBKR read-only Shadow → authentic archive + PostgreSQL event
  → dedicated Python Kronos observer → local weights
  → PostgreSQL research_kronos → ASP.NET read model / SignalR → Vue / Sol
```

The observer never connects to IBKR. It verifies the original source event hash and content-addressed archive before using OHLC.
It consumes the same incumbent Shadow study, without changing or restarting that collector.
The process entry script removes OpenAI, private HF and IBKR environment variables.
This is capability isolation in code and process configuration, not an OS security sandbox against an administrator.
The model receives OHLC and UTC calendar timestamp features only; no account identity, broker credentials or order tools.
Frontend requests read stored predictions; they cannot submit arbitrary inference code or load weights.
The .NET main thread does not run inference. A dedicated single-thread inference queue bounds pending work and caches the last 128 windows.
Worker polling is 30s; model stays loaded once when an uncached hourly window arrives.
An OS byte lock prevents a second observer, releases on crash, and does not lock Shadow.

## Initial configuration and data quality

`config/kronos/observation.json` is the only initial experimental configuration:

- EUR/USD, 1H, lookback 64, maximum supported context 512.
- 12 projected hourly bars, 32 independent paths, batches of 8.
- temperature 0.8, top_p 0.9, seed 47291.
- CUDA if available and >=2048 MiB free VRAM; CPU fallback on absence/low VRAM/OOM.
- float32; one CPU fallback, no retry loop on continued failure.
- a first short warm-up is timed separately.
- maximum input/prediction age 3900s, heartbeat 120s.
- reject gaps >7200s or more than three missing hourly bars in the lookback.
- reject nonfinite/corrupt OHLC, duplicates, unordered timestamps, incomplete/future bars, unverified volume and wrong symbol/timeframe.

IBKR session-opening partial bars (for example 21:15 UTC) are excluded, counted in provenance, and never re-labelled as full hourly bars.
Missing bars stay missing; no interpolation, zero price, future repair or synthetic central Forex volume.
Limited gaps are recorded (`missing_candles`); excessive weekend/unexplained gaps block inference.
Calendar timestamps projected into the future do not assert that the instrument will be tradable at those times.
15m and 4H are accepted as separate configured streams; their statistics/config hashes are not pooled with 1H.

Volume evidence is `WITHOUT_VOLUME` by default. The official predictor's documented omission route supplies zeros internally
to the volume channels; those zeros are an input mask, not observed zero market volume. Reliable volume/amount requires both fields and VERIFIED provenance.

## Forecasts, barriers and calibration

Upstream `sample_count>1` averages trajectories. This adapter instead uses official `predict_batch` with independent series and `sample_count=1` per series,
preserving 32 complete paths. Invalid generated OHLC is not repaired; it is counted and causes degraded calibration.
Forecast median, mean, return distribution, projected high/low, population dispersion and 5/25/75/95 percentiles use valid trajectories.
Percentile bands are model sample dispersion, not calibrated confidence intervals.
Samples are gzip artifacts addressed by hash, outside the main table.

When a genuine existing 1H candidate signal is present, every path is classified:
adverse opening gap → SL_FIRST; both barriers in one bar → SL_FIRST; TP alone → TP_FIRST;
none within the forecast horizon → NEITHER; corrupt trajectory → INVALID.
Frequency denominator includes all requested samples, including invalid paths. Without a genuine signal, raw barrier frequency is null;
no artificial barrier or fake trade is invented to fill dashboard fields.

Calibration binds symbol, timeframe, model/tokenizer revisions, configuration hash, regime, exact candidate and geometry bucket.
Only completed CALIBRATION outcomes known before the new prediction may train the mapping; overlapping windows are embargoed.
VALIDATION and FORWARD never become training rows automatically. Minimum 100 independent comparable outcomes and 30 in the probability bucket;
error <=0.15 and no invalid forecast paths are required. Otherwise calibrated probability stays null.
Brier, clipped log loss, ECE, reliability buckets and Wilson intervals are reported.
NEITHER is a non-TP outcome for the binary TP-before-SL event, never removed to increase apparent accuracy.
`tp_first_accuracy` measures correctness of the fixed 0.5 binary TP threshold; `observed_tp_rate` is the actual TP event rate.
Neither metric is a net trading win rate.

Consensus explicitly records technical/Kronos contradictions. The shared forecast reaches R1/R5/R10 once, with independent cost-aware sizing.
EV = p × net win − (1−p) × net loss. Lower Wilson-bound EV must exceed US$0.25 of uncertainty.
US$100, 1× exposure, costs and gaps stay inside each profile's risk budget; no automatic leverage or risk increase.
Forward assessment reads each profile's actual virtual equity, consumed losses, pending inventory/reservation and daily stop
from the hash-verified incumbent Shadow event. Missing state is UNKNOWN → NO_TRADE, never an assumed US$100 balance.
The budget is min(current equity × fixed fraction, initial US$100 × fraction, remaining US$20 loss budget);
profits never replenish consumed losses. Available exposure subtracts reservations. Pending inventory and a stopped local day block admission.
These are independent observation calculations, not changes to the protected RiskEngine or original simulator.
Changed profile state creates an immutable new assessment of the same cached forecast, including after restart from verified gzip samples.
Only valid historical forecast trajectories may train calibration; validation/forward remain excluded.
An unavailable/stale required predictor produces `KRONOS_REQUIRED_BUT_UNAVAILABLE → NO_TRADE`; optional prediction logs degraded mode.
Even a positive calibrated Shadow decision has zero execution authority and still needs independent RiskEngine/ExecutionGuard and protected Paper authorization.

## Persistence and restart

Migration `009_kronos.sql` adds schema `research_kronos` without changing existing journal migrations.
Append-only `events` holds PREDICTION, OUTCOME, STATUS and EVALUATION; a view exposes prediction fields.
IDs are SHA256-derived, payload hashes are checked on writes/reads, exact retries are idempotent, changed retries fail.
UPDATE/DELETE triggers reject mutation; Paper app role has SELECT/INSERT only.
Predictions store model/version/config, source hashes, UTC windows, sampling, raw/calibrated values, quantiles, consensus and artifact reference.
Separate outcome events retain actual barriers, Brier component, MAE and source. Missing outcome candles become DATA_QUALITY_BLOCKED, never a win.
Restart checks PostgreSQL before inference, reuses an existing identical forecast, and resolves outstanding observed outcomes without sending orders.
Read limits reserve independent quotas per event kind so heartbeats cannot evict all forecasts from the read model.

## Reproducible historical experiment

The initial benchmark uses the already frozen cost-aware `trend / 60m / swing` candidate, not a new strategy and not the active Trend V1 execution baseline.
Its EMA/RSI/MACD/ATR, regime/session, stop, target and original five-day hold semantics remain fixed.
Only the calibrated Kronos consensus/EV filter differs between comparator arms.
The existing six-month IBKR archive loader checks receipts, dataset/config hashes and the original development/validation split.
Candidates/windows are preregistered before inference, at most 60 forecasts, nonoverlapping forecast windows.
Only context available at the historical timestamp reaches the model. Future market data is attached only after inference to score outcomes.
Trade replay uses actual future opens, conservative stop ambiguity/gaps, one position and Santo Domingo FIRST_LOSS_STOPS_DAY;
pending positions retain explicit unrealized valuation and risk, not realized wins.
Walk-forward evaluates chronological validation blocks without fitting on those blocks.
The final holdout stays SEALED. Model pretraining overlap with these dates is UNKNOWN, a separate limitation of zero-shot evaluation.

Current bounded run: 9 preregistered opportunities; 4 blocked by missing-candle input; 5 actual forecasts (3 calibration, 2 validation).
Two validation forecasts have no TP event; Brier/ECE zero on n=2 is insufficient evidence, not skill or profitability.
R1 admits zero trades because US$4 estimated round-trip commissions exceed US$1 risk. R5/R10 admit zero because the target does not cover conservative friction at 1× exposure.
Both comparators therefore have 0 realized P&L/trades, and expectancy, PF, win-rate CI and delta expectancy are null.
NO_VIABLE_STRATEGY_FOUND remains the strategy decision; Kronos evaluation is INSUFFICIENT_EVIDENCE.
The US$2+US$2 fees were observed once in a previous 100 EUR Paper diagnostic; their applicability to other sizes, effective margin and odd-lot permissions remain UNKNOWN.

## UI and Sol

Dashboard and Mercado show status, model/timeframe, inference time, input/horizon/samples, raw frequency, calibrated probability, uncertainty and device.
Historical candlesticks are labelled REAL MARKET DATA; dashed median and band are labelled KRONOS FORECAST after a visible boundary.
SignalCard shows direction/consensus/disagreements/EV. Research → Kronos Evaluation shows counts, quality, reliability, regimes and the benchmark report.
Authenticated `GET /api/ui/kronos` returns the same read model. SignalR `kronos.updated` refreshes it.
Sol's Kronos questions produce deterministic evidence tables/metrics/reliability chart and comparator results.
With chat budget zero there is no OpenAI request. An explicitly budgeted future chat may pass only a compact structured consensus to the existing interpreter;
its text cannot replace probability, EV or order gates. The numerical visuals remain deterministic.

## Commands from the repository root

The observer is already running in observation mode. Do not start a second instance.

```powershell
.\scripts\kronos.ps1 -Action Status
.\scripts\kronos.ps1 -Action Once
.\scripts\kronos.ps1 -Action Stop
.\scripts\kronos.ps1 -Action Resume
.\scripts\kronos.ps1 -Action Observe
```

`Once` is one forecast diagnostic, never a broker order; when the observer is running it rejects a duplicate observer instance.
`Stop` sets only Kronos's own stop latch; `Resume` removes only that latch, never EmergencyStop.
Status is safe alongside the running observer.

```powershell
.\scripts\kronos.ps1 -Action Replay
.\scripts\start-dashboard.ps1 -SolBudget 0 -CopyAccessCode
```

Replay creates a new immutable preregistration/report directory and reuses identical persisted predictions where available.
Do not start a second dashboard if port 5080 is occupied. Current dashboard is http://127.0.0.1:5080.

Reinstall on a fresh machine requires the audited exact Git checkout, isolated venv, locked wheels, then `Install`:

```powershell
git clone --no-checkout https://github.com/shiyu-coder/Kronos.git .local/kronos/upstream
git -C .local/kronos/upstream checkout --detach 67b630e67f6a18c9e9be918d9b4337c960db1e9a
py -3.13 -m venv .local/kronos/venv
.\scripts\kronos.ps1 -Action Install
```

Build Debug/Release and apply the existing Paper migration procedure before using the journal bridge; the worker uses the Release command executable.
No secret is entered into the frontend or committed. Public model cache is `.local/kronos`; artifacts/report are `artifacts/research/kronos`.

## Further research and fine-tuning boundary

Kronos cannot become PAPER_ELIGIBLE through installation or calibration alone.
Required: enough independent chronological calibration and fresh OOS/forward evidence, cost sensitivity, positive net economic utility,
robustness by regime, no selection of repeated favorable tests, and verified Paper account/margin/cost/protection/reconciliation prerequisites.
No evidence currently authorizes Paper or Live.
Future `KRONOS_EURUSD_FINETUNE_V1` needs explicit authorization and a separately preregistered TRAIN/CALIBRATION/VALIDATION/FORWARD split,
audited training code/dependencies, no pickle from untrusted sources, no validation/test training, frozen model versions and new independent validation.
No fine-tuning, optimizer search, Kronos-large or billable OpenAI request was executed here.

Verification results, measured telemetry, protected hashes and complete changed-file inventory are recorded in
`artifacts/research/kronos/verification/verification.json` and `artifacts/research/kronos/report.json`.
