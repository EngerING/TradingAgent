using TradingAgent.Identity.Persistence;
using TradingAgent.Identity.Supabase;

namespace TradingAgent.Web.Auth;

/// <summary>AAL1 developer preview is not an app_security session or financial capability.</summary>
public static class PreviewSessionPolicy
{
    public static readonly TimeSpan MaximumLifetime = TimeSpan.FromHours(8);
    public static readonly TimeSpan InactivityLimit = TimeSpan.FromMinutes(30);
    public static readonly TimeSpan RefreshThreshold = TimeSpan.FromMinutes(2);
    public static bool Active(DateTimeOffset now, DateTimeOffset absoluteEnd, DateTimeOffset lastActivity) =>
        now < absoluteEnd && now < lastActivity + InactivityLimit;
    public static bool NeedsRefresh(DateTimeOffset now, DateTimeOffset tokenEnd) => now + RefreshThreshold >= tokenEnd;
}
public sealed record PreviewSessionSnapshot(DateTimeOffset ExpiresAt, DateTimeOffset IdleExpiresAt);

/// <summary>
/// Single local process-only slot with rotating server-held refresh token.
/// Browser owns just the separate short random preview reference. No disk or durable SQL.
/// </summary>
public sealed class PasswordPreviewSessions(IPreviewTokenProvider tokens, TimeProvider clock, string allowedEmail) : IDisposable
{
    public void Dispose() => gate.Dispose();
    private sealed record Slot(SessionReference Reference, PreviewTokenPair Tokens,
        DateTimeOffset AbsoluteEnd, DateTimeOffset LastActivity);
    private readonly SemaphoreSlim gate = new(1, 1);
    private readonly string allowed = allowedEmail.Trim();
    private Slot? current;
    private static PreviewSessionSnapshot Snapshot(Slot entry) =>
        new(entry.AbsoluteEnd, entry.LastActivity + PreviewSessionPolicy.InactivityLimit);

    public async Task<(SessionReference Reference, PreviewSessionSnapshot Session)> LoginAsync(
        string email, string password, CancellationToken ct)
    {
        if (!string.Equals(email.Trim(), allowed, StringComparison.OrdinalIgnoreCase))
            throw new AuthException(AuthFailure.Invalid);
        await gate.WaitAsync(ct).ConfigureAwait(false);
        try
        {
            var now = clock.GetUtcNow();
            if (current is { } existing && PreviewSessionPolicy.Active(now, existing.AbsoluteEnd, existing.LastActivity))
                throw new AuthException(AuthFailure.Conflict);
            current = null;
            var issued = await tokens.PasswordAsync(email.Trim(), password, ct).ConfigureAwait(false);
            if (issued.Credential.Identity.Aal is < 1 or > 2) throw new AuthException(AuthFailure.Invalid);
            now = clock.GetUtcNow();
            if (issued.Credential.Identity.ExpiresAt <= now) throw new AuthException(AuthFailure.Invalid);
            var saved = new Slot(SessionReference.Generate(), issued, now + PreviewSessionPolicy.MaximumLifetime, now);
            ct.ThrowIfCancellationRequested();
            current = saved;
            return (saved.Reference, Snapshot(saved));
        }
        finally { gate.Release(); }
    }

    public async Task<PreviewSessionSnapshot> SessionAsync(SessionReference? cookie, bool activity, CancellationToken ct)
    {
        if (cookie is null) throw new AuthException(AuthFailure.Invalid);
        await gate.WaitAsync(ct).ConfigureAwait(false);
        try
        {
            var entry = current;
            var now = clock.GetUtcNow();
            if (entry is null || !entry.Reference.LookupHash().AsSpan().SequenceEqual(cookie.LookupHash()) ||
                !PreviewSessionPolicy.Active(now, entry.AbsoluteEnd, entry.LastActivity))
            {
                if (entry is not null && !PreviewSessionPolicy.Active(now, entry.AbsoluteEnd, entry.LastActivity)) current = null;
                throw new AuthException(AuthFailure.Invalid);
            }
            var access = entry.Tokens.Credential;
            if (PreviewSessionPolicy.NeedsRefresh(now, access.Identity.ExpiresAt))
            {
                try
                {
                    var renewed = await tokens.RefreshAsync(entry.Tokens.RefreshToken, ct).ConfigureAwait(false);
                    // Refresh token reuse, account change or cross-session substitution is forbidden.
                    if (renewed.Credential.Identity.Identity != access.Identity.Identity ||
                        renewed.Credential.Identity.ProviderSessionId != access.Identity.ProviderSessionId ||
                        renewed.Credential.Identity.Aal is < 1 or > 2 ||
                        renewed.Credential.Identity.ExpiresAt <= clock.GetUtcNow() ||
                        string.Equals(renewed.RefreshToken, entry.Tokens.RefreshToken, StringComparison.Ordinal))
                        throw new AuthException(AuthFailure.Invalid);
                    entry = entry with { Tokens = renewed };
                    current = entry;
                }
                catch
                {
                    // A late/ambiguous refresh may have consumed the one-time token.
                    // Never replay it or return an authenticated UI.
                    current = null;
                    throw;
                }
            }
            else
            {
                try { await tokens.CheckAsync(access, ct).ConfigureAwait(false); }
                catch (AuthException error) when (error.Failure == AuthFailure.Invalid) { current = null; throw; }
            }
            now = clock.GetUtcNow();
            if (!PreviewSessionPolicy.Active(now, entry.AbsoluteEnd, entry.LastActivity))
            {
                current = null; throw new AuthException(AuthFailure.Invalid);
            }
            if (activity) entry = entry with { LastActivity = now };
            current = entry;
            return Snapshot(entry);
        }
        finally { gate.Release(); }
    }
    public async Task LogoutAsync(SessionReference? cookie, CancellationToken ct)
    {
        if (cookie is null) return;
        AccessCredential? token = null;
        await gate.WaitAsync(ct).ConfigureAwait(false);
        try
        {
            if (current is { } entry && entry.Reference.LookupHash().AsSpan().SequenceEqual(cookie.LookupHash()))
            {
                token = entry.Tokens.Credential;
                current = null; // Always revoke the local capability before remote I/O.
            }
        }
        finally { gate.Release(); }
        if (token is not null) await tokens.LogoutAsync(token, ct).ConfigureAwait(false);
    }
}
