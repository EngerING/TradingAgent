# M03-A.5 — Independent Paper calendar scheduler / authentic history (DATA_ONLY)

Baseline: `develop` at `8e9a06b3c4f238e797ea6ace3bea651b13e9e628`.
This component does not place orders, enable Live, alter financial strategy, or
connect M03-B / Market Analyst to any execution path. All tests are offline.

## Prior defect and correction

M03-A.4 ran a historical collection only after the **continuous** market reader
reported `MARKET_CLOSED`. `RETRY_BUDGET`, a missing quote or a disconnected feed
could prevent that callback indefinitely. A feed-quality flag named
`MARKET_CLOSED_OR_CALENDAR_UNKNOWN` never proves a closed session.

M03-A.5 starts a **separate, bounded, account-validated TWS contract-calendar
preflight** for the Paper profile before each continuous capture. It sends only
Start API, managed accounts, current time and EUR/USD IDEALPRO contract details
and checks the explicit `tradingHours`/time zone from the returned contract.
Its `calendar_only` reader never requests historical bars or subscribes to live
quotes. Preflight failure returns `UNKNOWN`, never a guessed Friday close.

| Verified state | Action | Recheck | Market-data requests |
|---|---|---|---|
| `OPEN` | Existing bounded streaming and observation cycle | At next capture cycle | Existing streaming/history sampling under M03-A.3 |
| `CLOSED` | M03-A.2 historical backfill on Paper only | Every 300 s after attempt | Historical MIDPOINT, bounded and daily marker gated |
| `UNKNOWN` / disconnected | Hold `NO_TRADE`; no backfill attempt marker | Every 60 s | Calendar preflight only on reachable TWS |
| TWS unreachable | Existing WAITING_FOR_TWS | Every 15 s | None |

The historical reader **independently** checks the broker's contract calendar
again, and before **each** subsequent historical request. It refuses to dispatch
when status is OPEN or UNKNOWN, including during a session transition. The
generic M03-A.2 historical reader remains capable of deliberate OPEN backfills
when its new opt-in `require_market_closed` is false; the host always sets it
true. Closed preflight does not grant financial trading permissions.

The historical window still contains the prior six-to-seven calendar days
ending at the previous completed UTC 15-minute boundary, with 15-minute,
1-hour and 4-hour bar sets. Every published bar is authentic IBKR MIDPOINT
and subject to causal OHLC integrity rules, permissions, provenance, and pacing.
**One immutable attempt per UTC date** persists even if stopped or incomplete:
an existing `%LOCALAPPDATA%\TradingAgent\market-data-host\historical\paper\YYYYMMDD`
must not be deleted to force retries. The October 24 attempt from M03-A.4
remains protected. The scheduler may check calendar multiple times; it must not
send multiple backfills for the same UTC date.

## Existing Kronos history

The separate `verified_shadow_research_seed` adapter delegates to the existing
`kronos.persistence.source_request` SHA-256 / Shadow event verification. It
retains the authentic IBKR Paper source hash, event hash, original as-of,
timeframe and raw OHLC bars, labels them `RESEARCH_ONLY_NOT_MARKET_FEED`, and
does not write, extend, fill or relabel any older dataset. It is an explicit
M03-B **candidate input only**, not an automatic handoff into Market Analyst,
not a replacement for today's live quotes, and not evidence of recent data.
The prior audit mentioned 2,782/703/205 bars at 15m/1H/4H; **this PR does
not independently verify those files on the Windows host**.

## Operator evidence

`run-host.ps1 -Action watch -Environment PAPER` remains the operator interface.
`CALENDAR_STATUS` reports `calendarState`, `evidenceOrigin` and `brokerClosed`
without account credentials or market prices. `HISTORICAL_STATUS` reports
the resulting bounded backfill status; `HISTORICAL_ALREADY_ATTEMPTED_TODAY`
is an expected outcome after a previous daily marker. Neither means the data
have reached Kronos or Market Analyst. `CAPTURE_HEALTH` still distinguishes
quotes from calendar health. LIVE historical scheduling is not enabled.

## Proof boundaries

- Synthetic transcripts cover broker-open, broker-closed and calendar-unknown,
  including prevention of quote subscriptions and order opcodes on probe.
- The real off-hours reader requires an independent second calendar check.
- Fixtures never qualify as broker-verified closed evidence.
- Unknown calendar never consumes the daily historical budget; closed at
  startup no longer waits for a streaming supervisor or uses its archive.
- Previous M03-A.2/3/4, Core and Market Analyst invariants remain unchanged.
- Requires supervised Windows Paper validation with genuine TWS once reviewed.

`main`, Core V3.9, Market Analyst, PostgreSQL, UI, financial execution and
approved risk controls remain unchanged. No Live, merge, deployment or orders.
