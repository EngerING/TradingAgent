# M01.4B-B6 — durable local password-only development sessions

Scope: the isolated read-only Supabase Auth Dev preview in `HOSTED_PASSWORD_ONLY_PREVIEW` only. NOT the AAL2 app_security session, protected financial routes, IBKR, or operational React dashboard.

## Limits and lifecycle

- **Absolute session lifetime**: 8 hours from login, never renewable beyond that.
- **Inactivity**: 30 minutes since the last explicit user interaction accepted through `POST /bff/preview/activity`; passive `GET /bff/preview/session` polling does NOT extend it. No traffic from a completely idle tab keeps login active.
- **Access JWT**: only the BFF holds Supabase `access_token` and `refresh_token` in volatile memory. `PreviewTokenProvider` rotates Supabase refresh tokens server-side when the access JWT has <=2 minutes of validity. Each response is revalidated for ES256/JWKS/issuer/audience/subject/session, and the provider's current user endpoint confirms identity. No refresh token is ever delivered to React, localStorage, sessionStorage or cookie.
- **Ambiguous rotation**: one in-flight refresh protected by `SemaphoreSlim`; on failure, cancellation, subject/session substitution or reuse ambiguity the local preview cookie is invalidated. No retry of one-time tokens.
- **Browser**: separate `__Host-TradingAgent.Preview` HttpOnly Secure SameSite Strict cookie expires at absolute deadline; React validates `expiresAt` and `idleExpiresAt` plus `renewable: true` and strictly `executionAuthorized:false, mode:OFFLINE, decision:NO_TRADE`. POST activity is CSRF-protected, same-origin, bounded by rate limits and sent only on pointer/keyboard interaction while tab is visible.
- **Backend process**: the explicitly approved hosted password-preview runner lasts up to 8h15m. All other hosted BFF/MFA pilots remain 20 minutes. `LOCAL_STARTUP_CHECKS_ONLY` remains login-disabled. Still a local runner, not a production service or persistent daemon; restarting it logs the user out.
- **TLS**: new disposable pilot preparation `-ExtendedPreviewCertificate` selects locally generated root valid ~11h and leaf ~10h, only CurrentUser trust with manual approval. Existing 4h/3h ordinary profiles unchanged. The runner refuses an insufficient certificate lifetime.
- **Windows**: B5 launcher had malformed `$previewEmail` input validation; this PR replaces its entire limited Run opt-in block, preserving double consent and normal MFA enrollment. CI `check.ps1` now parses the whole PowerShell launcher before tests.

## Reproducing locally after review and authorized merge

From repository root using committed `develop`, build frontend and BFF with pinned toolchains. Prepare a new owned run (do NOT reuse a previous RunId):

```powershell
$newPilot = [guid]::NewGuid().ToString('N')
.\build\react-bff\local-pilot.ps1 -Mode Prepare -RunId $newPilot -ExtendedPreviewCertificate
.\build\react-bff\local-pilot.ps1 -Mode Trust -RunId $newPilot
.\build\react-bff\local-pilot.ps1 -Mode Run -RunId $newPilot -PasswordOnlyPreview
```

Trust and Run require explicit local Windows confirmation. Run requires additional separate password-only permission and an allowlisted Auth Dev email, entered locally. Password must be typed **only into the HTTPS browser**, never logs or ChatGPT. Verify `/bff/config` advertises `HOSTED_PASSWORD_ONLY_PREVIEW`, sign in and confirm `/preview`. Session expires after 30m inactivity or 8h absolute. `Stop`/`Cleanup` remove only owned local resources; clean up the local CurrentUser trust root after usage.

## Proof and limits

Tests use a fake `IPreviewTokenProvider` and synthetic BFF fixtures to verify idle/absolute deadlines, concurrent serial token refresh, same-session invariant, invalidated local cookie after logout failure. No CI connection to Supabase hosted. No app_security grants, MFA factor updates, SQL migrations, or financial access. Dashboard integration is a later distinct task. PR stays draft until all required CI succeeds and review is complete.
