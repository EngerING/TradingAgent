# M01.4A — React authentication and develop integration

2026-10-21, America/La_Paz. OFFLINE / NO_TRADE. This delivery implements the
supplied reference and simulated flows. M01.3B hosted Auth remains incomplete;
no real login, recovery, invitation, MFA or trading capability is approved here.

## Git identity and integration

After fetch, local and remote main matched
`f67fa92086d10b9562df214f4e869344bf0753d8`. The audited pilot matched
`cd25a103b177d43a59f9d99c8047c0db3d20abbb`, tree
`c8193bf17437e0c7987231a62b7adf46182c0d88`. Main is its ancestor, with25 commits
ahead and none behind. The previous266-test CI archive was checked again.

Develop did not exist. It was initialized and published directly at that commit,
without a merge commit. Fetch/pull --ff-only confirmed it, then
`feature/m01-4a-react-auth` was created from its published HEAD. Develop includes
experimental work and is **not approved for deployment or real trading**.

The permanent branch rules are recorded in root AGENTS.md. Feature/fix branches
start from updated develop; reviewed PRs target develop. Release promotion to main
needs its own approval. No automatic merge, force push, branch deletion, default
branch change or deployment was performed. This feature must not be merged yet.

Branch protection is **prepared, not activated or certified**: the available GitHub
connector exposes PR operations but no authenticated branch-administration operation.
No credential extraction or permission expansion was attempted. An administrator can
apply [the exact template](../../build/react-auth/branch-protection.template.json)
to main and develop using GitHub's branch-protection API/UI: required PR, one approval,
stale-review dismissal, both M01.4A checks, current base, conversation resolution,
admin enforcement, no force push and no deletion. Verify plan/support and read back
the effective rules before claiming enforcement. CI green alone never authorizes merge.

## Application and visual system

`frontend-react/` is an independent npm boundary; Vue and root build files remain
untouched. React19, strict TypeScript6, Vite8, React Router declarative mode,
Vitest4, RTL, Playwright and axe are exact-pinned in package.json/package-lock.json.
Node24.20.0 and npm12.2.0 are pinned. Dependencies install with scripts disabled.
Native optional prebuilt tooling was sufficient; no lifecycle scripts were approved.

The mandatory1536×1024 image is stored under frontend-react/reference/ with SHA-256
`773d40b3f46888d736d8cda69d0cfaa7f2b1474805f7e9c209bc445cd1a9c8a5`.
The card is1212×848 at(162,88). Local Inter/Libre Baskerville fonts, warm ground,
blue controls, muted gold, borders, radii and motion roles are defined in tokens.
The logo is an editable reconstruction; no official vector was found in tracked
frontend assets. The SVG candle/curve scene contains fixed decorative values and
an explicit illustrative-data caption. It is not a feed or economic chart.

The10 requested skills were found and consulted: design-taste-frontend, impeccable,
emil-design-eng, tradingagent-product-design, trading-data-visualization,
frontend-ui-engineering, api-and-interface-design, security-and-hardening,
senior-software-engineer and graphify. The supplied design overrides conflicting
generic style rules; no alternate art direction or raster mock was invented.
Graphify's frontend query found no matching nodes; a narrowed historical query
found168/shown15/truncated153, budget500. Its424-node graph predates these modules;
sources and contracts were inspected directly. No graph rebuild was performed.

Finite entry/candle/curve animations,180ms interactions and240ms route transitions
use restrained easing. No perpetual price changes or ambient loops. Reduced motion
cancels animations. Responsive checks cover1536×1024,1440×900,1366×768,1024×768,
768×1024,390×844 and360×800. Mobile prioritizes the form and preserves the mark.

Two visual inspection rounds compared desktop/mobile with the reference. Corrections
covered typography, icon fill, quote positions and form alignment. Remaining visible
differences: reconstructed mark, locally sourced fonts, simplified vector geometry,
disabled remember/Google controls and explicit demo/data provenance. These are not
claimed to be a pixel-perfect raster reconstruction.

## Routes and authority

| Route | Implemented UI | Real capability |
|---|---|---|
| / and /login | Validation, password visibility, loading, errors | Unavailable |
| /forgot-password | Simulated request, neutral result | No email/account change |
| /reset-password | Matching password fields, one-use in-memory demo continuation | No link exchange/password change |
| /invitation | Explicit invitation demo and password fields | No signup/invitation acceptance |
| /mfa/enroll | Explanation, non-enrollable QR placeholder | No factor creation |
| /mfa/verify | Six-digit fixture, invalid/expired states | No real TOTP verification |
| /session/:state | Expired, denied, unavailable, progress, demo completion | No real identity/trading authority |

Paper is a visual preference. Live, Google and Remember me are unavailable.
Register explains invitation-only access. These controls cannot activate execution.
Development explicitly imports the memory-only fixture; production dead-code removal
excludes it and selects an unavailable adapter. Credential input is disabled in that
build. No VITE switch can turn production authentication into a mock.

Passwords/codes clear on submit; work is cancelled on unmount. Duplicate admission
is bounded locally. Fixture fields request no credential/OTP autofill. A browser
extension may ignore autocomplete=off; only invented values may be entered into this
local demo. There is no fetch, provider SDK, cookie writer, storage, telemetry or DB
client in the adapter. The development server binds localhost:3000; preview uses3001.

Startup query/hash is removed without parsing values, then a closed callback-pending
screen is shown. Explicit safe navigation can leave it. No token/code is displayed,
stored or exchanged. Client cleanup cannot prevent an initial URL query reaching an
HTTP server; real callback delivery requires reviewed BFF/server handling before use.
No Supabase settings were changed. A local Site URL is not evidence of secure exchange.

Existing BFF endpoint/DTO types are documented in auth/contracts.ts. Recovery and
invitation remain separately marked NOT_IMPLEMENTED; no imaginary approved endpoints
are assigned. Future transport must use same-origin BFF/CSRF and HttpOnly Secure opaque
cookies, bounded response parsing and closed error mapping. No Supabase JWT belongs
in browser persistence. No BFF transport or generic API proxy is enabled by this phase.

## Checks and evidence

Local:13 unit tests,20 Playwright cases, zero failures/skips/retries, all266 backend
cases preserved and passed, strict builds, dependency audits without known findings.
Axe WCAG2A/AA and2.1AA reports no violations at the seven login resolutions. This is
automated evidence, not a claim of full screen-reader or accessibility certification.

The first unit run failed for absent modules. Browser regressions exposed initial
focus/readiness behavior; the adversarial review reproduced blocked callback return
and unavailable-production credential entry before fixes. A fresh-context internal
review completed two cycles; no remaining actionable findings. It is not independent
audit. Manual external review can use this document, reference, source diff and CI
artifacts; no external review CLI or third-party transmission was used.

Pixelmatch comparison is a coarse drift check (threshold0.1, fraction ceiling0.30).
Local changed fraction was0.0482438405. This is **not** a95% perceptual-fidelity score:
background area dominates it. Visual review and exact card geometry remain necessary.
CI stores the current metric, diff image, screenshots and exact test identities.

The new workflow keeps frontend and backend jobs separate, uses read-only checkout,
pinned official actions, no persistent caches or secrets, and a marked disposable
PostgreSQL17.11 container. It runs the four unchanged backend wrappers with locked
NuGet restore/audits. It never runs the hosted pilot or historical services.
Artifacts retain14 days; archive them externally for longer audit retention.

Reproduce frontend: `cd frontend-react`, `npm ci --ignore-scripts`, `npm run verify`,
`npx --no-install playwright install chromium`, `npm run e2e`,
`node scripts/compare-reference.mjs`, `node scripts/verify-results.mjs`.
Develop locally with `npm run dev`; use invented credentials only. Backend offline
regressions: existing `./build/auth-pilot/local-test.ps1`, with its disposable cluster.

All843 original tracked files and three preexisting untracked documents/scripts are
preserved by hashes. No financial or legacy migration, framework, Vue or backend code
was edited. [Evidence](m01-4a-react-auth-evidence.json) records preservation and results;
final commit/tree, PR, CI and artifact links are reported with the delivery.
M01.4B and hosted M01.3B remain pending separate authorization.
