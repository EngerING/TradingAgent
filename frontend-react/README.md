# TradingAgent auth web — M01.4A

Use Node24.20.0/npm12.2.0. `npm ci --ignore-scripts`, then `npm run dev`.
Open http://localhost:3000. This is an explicitly simulated development application.
Use `demo@tradingagent.test`, an invented password of8+ characters, and fixture code
`123456`. Never enter real credentials. Recovery/invitation password demos use12+
characters. Nothing is sent, persisted or changed in a real account.

`npm run verify` runs strict types, lint,13 unit tests, production build and its
boundary scan. `npm run e2e` runs20 browser tests (install pinned Chromium first with
`npx --no-install playwright install chromium`). Evidence is written to ../artifacts/m014a/.
`node scripts/compare-reference.mjs` compares the supplied reference;
`node scripts/verify-results.mjs` requires exact test names and no skipped/retried cases.

`npm run preview` serves the build on localhost:3001. It contains no demo adapter and
disables authentication input. No real BFF transport has been implemented. Do not deploy.

Reference, contracts, limits, screenshots and Git strategy are described in
[the architecture record](../docs/architecture/m01-4a-react-auth.md).
The11 original financial migrations, Vue, backend and all843 baseline files are preserved.
