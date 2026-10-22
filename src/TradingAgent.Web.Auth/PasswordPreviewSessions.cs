using TradingAgent.Identity.Persistence;
using TradingAgent.Identity.Supabase;

namespace TradingAgent.Web.Auth;

/// <summary>
/// Hosted Auth Dev AAL1-only preview session. Refresh token is kept only in BFF process memory.
/// Never generates an app_security capability, money movement or an operational session.
/// </summary>
public sealed class PasswordPreviewSessions(SupabaseAuthClient provider, JwtVerifier verifier, TimeProvider clock, string allowedEmail)
{
    private sealed class Entry(SessionReference reference, RefreshableCredential credential, DateTimeOffset absolute, DateTimeOffset idle)
    {
        internal SessionReference Reference { get; } = reference;
        internal RefreshableCredential Credential { get; set; } = credential;
        internal DateTimeOffset Absolute { get; } = absolute;
        internal DateTimeOffset Idle { get; set; } = idle;
    }

    private readonly SemaphoreSlim mutex = new(1, 1);
    private readonly string allowed = allowedEmail.Trim();
    private Entry? current;

    public async Task<(SessionReference Reference, DateTimeOffset Expires, DateTimeOffset IdleExpires)> LoginAsync(string email, string password, CancellationToken ct)
    {
        if (!string.Equals(email.Trim(), allowed, StringComparison.OrdinalIgnoreCase))
            throw new AuthException(AuthFailure.Invalid);
        await mutex.WaitAsync(ct).ConfigureAwait(false);
        try
        {
            // A new password login revokes the previous process capability before remote I/O.
            current = null;
            var issued = await provider.PasswordWithRefreshAsync(email.Trim(), password, ct).ConfigureAwait(false);
            if (issued.Access.Identity.Aal != 1) throw new AuthException(AuthFailure.Invalid);
            await provider.CheckUserAsync(issued.Access, ct).ConfigureAwait(false);
            var now = clock.GetUtcNow();
            var absolute = PreviewLeasePolicy.Absolute(now);
            var idle = PreviewLeasePolicy.Idle(now, absolute);
            if (issued.Access.Identity.ExpiresAt <= now) throw new AuthException(AuthFailure.Invalid);
            var entry = new Entry(SessionReference.Generate(), issued, absolute, idle);
            current = entry;
            return (entry.Reference, absolute, idle);
        }
        finally { mutex.Release(); }
    }

    public Task<object> SessionAsync(SessionReference? cookie, CancellationToken ct) => ReadAsync(cookie, false, ct);
    public Task<object> ActivityAsync(SessionReference? cookie, CancellationToken ct) => ReadAsync(cookie, true, ct);

    private async Task<object> ReadAsync(SessionReference? cookie, bool activity, CancellationToken ct)
    {
        if (cookie is null) throw new AuthException(AuthFailure.Invalid);
        await mutex.WaitAsync(ct).ConfigureAwait(false);
        try
        {
            var entry = current;
            var now = clock.GetUtcNow();
            if (entry is null || !Matches(entry.Reference, cookie) ||
                !PreviewLeasePolicy.Active(now, entry.Absolute, entry.Idle))
            {
                // Revoke expired entries even when still retained by the browser.
                if (entry is not null && !PreviewLeasePolicy.Active(now, entry.Absolute, entry.Idle)) current = null;
                throw new AuthException(AuthFailure.Invalid);
            }
            try
            {
                // Refresh at most once under mutex. No replay of the consumed refresh token.
                if (entry.Credential.Access.Identity.ExpiresAt <= now.AddMinutes(2))
                {
                    var rotated = await provider.RefreshAsync(entry.Credential.RefreshToken, ct).ConfigureAwait(false);
                    if (rotated.Access.Identity.Identity != entry.Credential.Access.Identity.Identity ||
                        rotated.Access.Identity.ProviderSessionId != entry.Credential.Access.Identity.ProviderSessionId ||
                        rotated.Access.Identity.Aal != 1 ||
                        rotated.Access.Identity.ExpiresAt <= clock.GetUtcNow())
                        throw new AuthException(AuthFailure.Invalid);
                    // Commit each successful token rotation before subsequent remote validation.
                    entry.Credential = rotated;
                }
                var identity = await verifier.ValidateAsync(entry.Credential.Access.Token, ct).ConfigureAwait(false);
                if (identity != entry.Credential.Access.Identity || identity.Aal != 1) throw new AuthException(AuthFailure.Invalid);
                await provider.CheckUserAsync(entry.Credential.Access, ct).ConfigureAwait(false);
            }
            catch
            {
                // Network ambiguity may consume a refresh token. Fail closed; no automatic retry.
                current = null;
                throw;
            }
            now = clock.GetUtcNow();
            if (!PreviewLeasePolicy.Active(now, entry.Absolute, entry.Idle))
            {
                current = null;
                throw new AuthException(AuthFailure.Invalid);
            }
            // Polling must never extend idle lifetime. Only an explicit same-origin CSRF POST does.
            if (activity) entry.Idle = PreviewLeasePolicy.Idle(now, entry.Absolute);
            return new { authenticated = true, aal = "aal1", profile = "PASSWORD_ONLY_DEV_PREVIEW",
                expiresAt = entry.Absolute, idleExpiresAt = entry.Idle, renewable = true,
                executionAuthorized = false, mode = "OFFLINE", decision = "NO_TRADE" };
        }
        finally { mutex.Release(); }
    }

    public async Task LogoutAsync(SessionReference? cookie, CancellationToken ct)
    {
        if (cookie is null) return;
        RefreshableCredential? cancelled = null;
        await mutex.WaitAsync(ct).ConfigureAwait(false);
        try
        {
            if (current is not null && Matches(current.Reference, cookie))
            {
                cancelled = current.Credential;
                current = null; // Locally revoked before contacting Supabase.
            }
        }
        finally { mutex.Release(); }
        if (cancelled is not null)
            await provider.LogoutAsync(cancelled.Access, ct).ConfigureAwait(false);
    }

    private static bool Matches(SessionReference a, SessionReference b) =>
        a.LookupHash().AsSpan().SequenceEqual(b.LookupHash());
}

/// <summary>Absolute 8h / human-activity idle 30m, deliberately independent of JWT expiry.</summary>
public static class PreviewLeasePolicy
{
    public static DateTimeOffset Absolute(DateTimeOffset issued) => issued.AddHours(8);
    public static DateTimeOffset Idle(DateTimeOffset activity, DateTimeOffset absolute) =>
        activity.AddMinutes(30) < absolute ? activity.AddMinutes(30) : absolute;
    public static bool Active(DateTimeOffset now, DateTimeOffset absolute, DateTimeOffset idle) =>
        now < absolute && now < idle;
}
