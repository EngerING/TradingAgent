using TradingAgent.Identity.Persistence;
using TradingAgent.Identity.Supabase;

namespace TradingAgent.Web.Auth;

internal sealed class PendingMfa(AccessCredential credential, DateTimeOffset expires)
{
    internal AccessCredential Credential { get; } = credential;
    internal DateTimeOffset Expires { get; } = expires;
    internal Guid? Enrolled { get; set; }
    internal Guid? Factor { get; set; }
    internal Guid? Challenge { get; set; }
    internal DateTimeOffset ChallengeAt { get; set; }
    internal DateTimeOffset ChallengeExpires { get; set; }
    internal bool Busy;
    internal int Attempts { get; set; }
}
internal sealed record BrowserSession(AccessCredential Credential, SessionReference Reference, Guid User, DateTimeOffset Expires);

/// <summary>Bounded process-local pilot state. No refresh tokens, disk, persistence or recovery fallback.</summary>
public sealed class TemporarySessions(TimeProvider clock)
{
    private readonly object gate = new();
    private readonly Dictionary<string, PendingMfa> pending = new(StringComparer.Ordinal);
    private readonly Dictionary<string, BrowserSession> sessions = new(StringComparer.Ordinal);
    private readonly Dictionary<string, (SessionReference Reference, DateTimeOffset Expires)> completions = new(StringComparer.Ordinal);
    private readonly Dictionary<Guid, (int Count, DateTimeOffset Expires)> accountAttempts = [];
    private readonly Dictionary<IdentityKey, DateTimeOffset> enrollmentReservations = [];
    private static string Key(SessionReference reference) => Convert.ToHexString(reference.LookupHash());
    internal SessionReference AddPending(AccessCredential credential)
    {
        lock (gate)
        {
            Prune(); if (pending.Count + completions.Count >= 128) throw new AuthException(AuthFailure.RateLimited);
            var reference = SessionReference.Generate(); pending.Add(Key(reference), new(credential, Min(clock.GetUtcNow().AddMinutes(5), credential.Identity.ExpiresAt))); return reference;
        }
    }
    internal PendingMfa Acquire(SessionReference reference)
    {
        lock (gate)
        {
            Prune();
            if (!pending.TryGetValue(Key(reference), out var value)) throw new AuthException(AuthFailure.Invalid);
            if (value.Busy) throw new AuthException(AuthFailure.Conflict);
            if (value.Attempts >= 5) throw new AuthException(AuthFailure.RateLimited);
            var user = value.Credential.Identity.Identity.Subject;
            accountAttempts.TryGetValue(user, out var budget);
            if (budget.Count >= 15 || accountAttempts.Count >= 256 && budget.Count == 0) throw new AuthException(AuthFailure.RateLimited);
            accountAttempts[user] = (budget.Count + 1, budget.Count == 0 ? clock.GetUtcNow().AddMinutes(5) : budget.Expires);
            value.Attempts++; value.Busy = true; return value;
        }
    }
    // Single-process, bounded exclusion survives lost responses and distinct preauth cookies.
    // Provider API cannot supply a cross-process atomic compare-and-enroll transaction.
    internal void ReserveEnrollment(PendingMfa value)
    {
        lock (gate)
        {
            Prune(); var identity = value.Credential.Identity.Identity;
            if (enrollmentReservations.ContainsKey(identity)) throw new AuthException(AuthFailure.Conflict);
            if (enrollmentReservations.Count >= 128) throw new AuthException(AuthFailure.RateLimited);
            enrollmentReservations.Add(identity, value.Expires);
        }
    }
    internal void Release(PendingMfa pendingMfa) { lock (gate) pendingMfa.Busy = false; }
    internal (SessionReference? Completed, AccessCredential? PreliminaryCredential) CancelPreliminary(SessionReference reference)
    {
        lock (gate)
        {
            pending.Remove(Key(reference), out var preliminary); completions.Remove(Key(reference), out var completed); return (completed.Reference, preliminary?.Credential);
        }
    }
    internal void Complete(SessionReference preliminary, PendingMfa expected, BrowserSession session)
    {
        lock (gate)
        {
            Prune();
            if (!pending.TryGetValue(Key(preliminary), out var current) || !ReferenceEquals(current, expected)) throw new AuthException(AuthFailure.Invalid);
            if (sessions.Count >= 128) throw new AuthException(AuthFailure.RateLimited);
            pending.Remove(Key(preliminary)); sessions.Add(Key(session.Reference), session);
            // Retain the completion bridge until preauth expiry so a delayed verify response
            // cannot install a usable cookie after logout sent with only the old preauth cookie.
            completions.Add(Key(preliminary), (session.Reference, expected.Expires));
        }
    }
    internal BrowserSession? Find(SessionReference reference) { lock (gate) { Prune(); return sessions.GetValueOrDefault(Key(reference)); } }
    internal BrowserSession? Remove(SessionReference reference)
    {
        lock (gate) { sessions.Remove(Key(reference), out var value); return value; }
    }
    public void Clear() { lock (gate) { pending.Clear(); sessions.Clear(); completions.Clear(); accountAttempts.Clear(); enrollmentReservations.Clear(); } }
    private void Prune()
    {
        var now = clock.GetUtcNow();
        foreach (var item in pending.Where(p => p.Value.Expires <= now).Select(p => p.Key).ToArray()) pending.Remove(item);
        foreach (var item in sessions.Where(p => p.Value.Expires <= now).Select(p => p.Key).ToArray()) sessions.Remove(item);
        foreach (var item in completions.Where(p => p.Value.Expires <= now).Select(p => p.Key).ToArray()) completions.Remove(item);
        foreach (var item in enrollmentReservations.Where(p => p.Value <= now).Select(p => p.Key).ToArray()) enrollmentReservations.Remove(item);
        foreach (var item in accountAttempts.Where(p => p.Value.Expires <= now).Select(p => p.Key).ToArray()) accountAttempts.Remove(item);
    }
    internal static DateTimeOffset Min(DateTimeOffset first, DateTimeOffset second) => first < second ? first : second;
}
