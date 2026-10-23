# M02 / PR #13 — Read-only dashboard shell

## Scope

Implement the first TradingAgent dashboard shell using React + strict TypeScript
and the existing visual tokens. The route remains `/preview` under the
isolated `HOSTED_PASSWORD_ONLY_PREVIEW` Auth Dev HTTPS pilot. No financial
dashboard access is implied by a valid password-only AAL1 preview session.

The screen includes:

- Persistent navigation for Overview and Session & security, with future
  modules visibly disabled.
- Capital, net P&L, open positions, strategies and alerts shown as unavailable,
  **not as invented zeroes or broker-sourced metrics**.
- An illustration that is explicitly labelled as decorative, never a market
  price feed.
- Paper, Shadow and Forecast represented as three separate disconnected
  sources, without blending evidence or outcomes.
- Display-only `OFFLINE / NO_TRADE` state and absence of financial permissions.
- Accessible responsive layout and the established warm-white, navy, muted
  blue and restrained gold design language.

## Authentication and boundaries

- Auth Dev / BFF controls the session: explicit activity only, 30-minute idle
  limit, 8-hour absolute limit, secure server-side token rotation. The dashboard
  waits for a successful `auth.session()` before rendering any workspace state.
- Polling, chart drawings and route navigation do not independently confer
  financial authorization. Failed/expired session reads still navigate to
  existing closed error states.
- The existing `auth.logout()` is reused; failures remain explicit and
  unconfirmed. No tokens, credentials, auth grants or browser storage are added.
- The real protected AAL2 security model and future operational dashboard are
  **not** implemented by this UI milestone.
- No BFF endpoints, SQL, Python, Core, Market Analyst, IBKR, order execution,
  strategy promotion, financial services, Vue, `main` or existing design
  tokens/assets are changed. **OFFLINE / NO_TRADE**.

## Verification

- React unit cases cover confirmed access, strict separation of absent data,
  session detail navigation, expiration, fail-closed loading and logout.
- Baseline 29 React tests are retained and five new dashboard tests are
  inventoried. Exact expected count: 34, zero failures/skips.
- Original Playwright login screens and screenshot reference tests remain
  unchanged (20 scenarios).
- The M01.4A/M01.4B preservation checker permits only these exact additions:
  `ReadOnlyDashboard.tsx`, `ReadOnlyDashboard.test.tsx`, `dashboard.css`
  and this document, along with necessary explicitly allowlisted integration,
  test inventory and shared auth-layout edits. Financial paths remain byte
  identical to the established baselines.

## Handoff and constraints

This is a reviewable Module 2 shell, not a connection to financial streams.
Separate read-only BFF data contracts and AAL2-protected financial dashboards
require a later approved milestone. The current PR must target `develop`,
run CI and receive explicit review/merge authorization. Green tests alone do
not authorize merging or enabling trading.
