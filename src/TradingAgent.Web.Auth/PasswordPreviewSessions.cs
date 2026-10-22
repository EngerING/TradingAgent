using TradingAgent.Identity.Persistence;
using TradingAgent.Identity.Supabase;

namespace TradingAgent.Web.Auth;

/// <summary>Process-only Auth Dev password preview; NEVER a financial or SQL session.</summary>
public sealed class PasswordPreviewSessions(SupabaseAuthClient provider, JwtVerifier verifier, TimeProvider clock, string allowedEmail)
{
    private readonly object gate = new();
    private readonly string allowed = allowedEmail.Trim();
    private SessionReference? reference;
    private AccessCredential? credential;
    private DateTimeOffset expires;

    public async Task<(SessionReference Reference, DateTimeOffset Expires)> LoginAsync(string email, string password, CancellationToken ct)
    {
        if (!string.Equals(email.Trim(), allowed, StringComparison.OrdinalIgnoreCase)) throw new AuthException(AuthFailure.Invalid);
        var verified = await provider.PasswordAsync(email.Trim(), password, ct).ConfigureAwait(false);
        if (verified.Identity.Aal is < 1 or > 2) throw new AuthException(AuthFailure.Invalid);
        await provider.CheckUserAsync(verified, ct).ConfigureAwait(false);
        var now = clock.GetUtcNow();
        var end = verified.Identity.ExpiresAt < now.AddMinutes(5) ? verified.Identity.ExpiresAt : now.AddMinutes(5);
        if (end <= now) throw new AuthException(AuthFailure.Invalid);
        var issued = SessionReference.Generate();
        lock (gate) { reference = issued; credential = verified; expires = end; }
        return (issued, end);
    }

    public async Task<object> SessionAsync(SessionReference? cookie, CancellationToken ct)
    {
        if (cookie is null) throw new AuthException(AuthFailure.Invalid);
        AccessCredential saved; DateTimeOffset end;
        lock (gate)
        {
            if (reference is null || credential is null || expires <= clock.GetUtcNow() ||
                !reference.LookupHash().AsSpan().SequenceEqual(cookie.LookupHash()))
                throw new AuthException(AuthFailure.Invalid);
            saved = credential; end = expires;
        }
        var identity = await verifier.ValidateAsync(saved.Token, ct).ConfigureAwait(false);
        if (identity != saved.Identity || identity.Aal is < 1 or > 2 || end <= clock.GetUtcNow())
            throw new AuthException(AuthFailure.Invalid);
        await provider.CheckUserAsync(saved, ct).ConfigureAwait(false);
        lock (gate)
        {
            if (reference is null || credential != saved || expires <= clock.GetUtcNow() ||
                !reference.LookupHash().AsSpan().SequenceEqual(cookie.LookupHash()))
                throw new AuthException(AuthFailure.Invalid);
        }
        return new { authenticated = true, aal = "aal1", profile = "PASSWORD_ONLY_DEV_PREVIEW", expiresAt = end,
            renewable = false, executionAuthorized = false, mode = "OFFLINE", decision = "NO_TRADE" };
    }

    public async Task LogoutAsync(SessionReference? cookie, CancellationToken ct)
    {
        AccessCredential? old = null;
        lock (gate)
        {
            if (cookie is not null && reference is not null &&
                reference.LookupHash().AsSpan().SequenceEqual(cookie.LookupHash()))
            {
                old = credential; credential = null; reference = null; expires = DateTimeOffset.MinValue;
            }
        }
        if (old is not null) await provider.LogoutAsync(old, ct).ConfigureAwait(false);
    }
}
