# M01.4B-B6 — Renewable Supabase Auth Dev session, isolated AAL1 preview

The account owner authorized 8h absolute session duration and 30m idle expiration after B5 merged to develop. These limits are for the password-only **read-only development preview**; production authentication and financial operations remain separately gated.

## Security design
- Separate `__Host-TradingAgent.Preview` HTTPS-only / HttpOnly / SameSite=Strict cookie; expiry is fixed at eight hours from login, never sliding. The protected AAL2 `/bff/session`, `app_security` and financial routes are unchanged.
- Provider ES256 JWT remains validated with `ClockSkew=0`. BFF alone retains a *single rotating refresh token in process memory*. React never receives the access/refresh token.
- `PasswordWithRefreshAsync` and `RefreshAsync` use fixed Supabase Auth token endpoints; each response must have a signed JWT and a bounded opaque rotating refresh token.
- One server-side `SemaphoreSlim` serializes all reads, login and renewal. Refresh occurs only when JWT expiration is within two minutes. A rotated token must retain the original issuer/subject/provider session ID and AAL1. Missing/ambiguous response, compromised identity, provider outage or failed validation **invalidates** the preview capability without automatic retries.
- Explicit human pointer or keyboard activity invokes CSRF-protected `POST /bff/preview/activity` at most once per 90 seconds, renewing a 30-minute idle deadline but never the 8h absolute deadline.
- `GET /bff/preview/session` polling, now once per minute, validates without extending the idle lease. Idle and absolute expirations are checked both before and after provider calls.
- Logout locally revokes the one preview session before requesting remote Supabase logout. The app restart ends the session (no persistent credentials or refresh token across restarts).
- HTTPS preview pilot now survives for up to 8h and permits five rate-limited password attempts. Other AAL2 pilot remains 20min/one attempt. Newly prepared localhost certificates have 10h leaf/12h trust-root validity and require explicit owned Windows CurrentUser approval; a preview run refuses fewer than 8h validity. Existing owned Cleanup remains mandatory.
- **No migration, MFA factor update, SQL grants, financial authority or IBKR traffic. OFFLINE / NO_TRADE.**

## Regression expectations
The 362-test B5 baseline stays green. B6 adds two .NET tests for lease deadlines and real signed synthetic refresh token rotation, polling not extending idle, and fail-closed on foreign subject. The frontend adapter fixture checks separate CSRF activity and bounded renewal response. Expected total 364 distinct tests, zero failures/skips. CI uses synthetic signed fixtures; **hosted Supabase real-session renewal is not claimed verified**.

## Development-only run (after reviewed merge)
Pull exact approved develop, rebuild .NET BrowserFixture and React, `Prepare` a fresh local pilot RunId, `Trust` its owned dev root, then:
```powershell
.\build\react-bff\local-pilot.ps1 -Mode Run -RunId $newPilot -PasswordOnlyPreview
```
Approve the two prompts; type the allowed email only in PowerShell and password only in HTTPS Chrome. A new preview cookie lives until inactivity >30m, absolute >8h, logout, process stop, or a fail-closed provider event. The frontend remains **read-only auth landing**, not the financial dashboard.

**PR draft; explicit review and merge approval required. No changes to main.**
