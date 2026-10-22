# B5 — password-only login for isolated development preview

**Goal:** accept a valid Supabase Auth Dev email/password (AAL1) to open a limited local read-only preview, without requiring a TOTP challenge or modifying the existing unverified factor.

**Strict separation:** the ordinary `/bff/auth/*`, `/bff/session`, `/bff/probe`, `app_security`, real dashboard, IBKR and all financial endpoints retain their prior security requirements. This milestone does not change `JwtVerifier`, AAL2 policy, user grants, factor status or provider configuration.

- Use the existing HTTPS BFF and approved `local-pilot.ps1`, but only `-Mode Run -PasswordOnlyPreview` prompts for a separate local consent and a single allowed Auth Dev email, process-only.
- New process-only approval `M014B_B2_PASSWORD_PREVIEW=APPROVED_PASSWORD_ONLY_DEV_VIEW_NO_TRADE` is validated server side. A preview cannot combine with `-EnableFreshEnrollment` or `LOCAL_STARTUP_CHECKS_ONLY`.
- Distinct HTTPS same-origin `/bff/preview/login`, `/bff/preview/session`, `/bff/preview/logout` endpoints, no other preview routes. They validate a fresh ES256 Supabase password token plus `/auth/v1/user`; unverified factors do not become an operational capability.
- Bounded one-session, process-local credential store, eight-hour absolute and thirty-minute idle limit (B6), separate `__Host-TradingAgent.Preview` HttpOnly Secure SameSite=Strict cookie. No provider token or secret reaches React.
- The React `/preview` route requires an independent preview-session GET before showing confirmed access. The read-only preview clearly states that the operational dashboard is not yet connected.
- AAL2 session issuance, SQL and resource authorizations remain independent and unchanged, and the preview cookie is rejected by these routes.
- No factor removal or enrollment, no administrative API key, no SQL grants, no migration, no deployment, no trading. **OFFLINE / NO_TRADE**.

### Windows runbook after CI and explicit merge approval

From repository root, use a newly prepared and locally trusted disposable run with an unexpired certificate and no other PostgreSQL/BFF listener:

```powershell
.\build\react-bff\local-pilot.ps1 -Mode Run -RunId $newPilot -PasswordOnlyPreview
```

Approve both explicit dialogs and type the allowed email **only in PowerShell**. Enter the password **only in Chrome** at the HTTPS URL printed. On accepted credentials, the page navigates to `/preview`, where access is confirmed only after a fresh `/bff/preview/session` read. B6 allows five rate-limited login attempts in an explicitly authorized preview run and shuts down at eight hours. A newly prepared 10-hour leaf certificate and 12-hour root are required. Do not treat the preview as production login or trading access.

No hosted Supabase request is made by CI. Existing MFA fixtures remain valid for the protected AAL2 flow.
