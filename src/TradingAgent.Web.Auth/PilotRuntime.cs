using TradingAgent.Identity.Persistence;
using TradingAgent.Identity.Supabase;

namespace TradingAgent.Web.Auth;

/// <summary>Explicit pilot composition. No endpoint may consume this as operational authority.</summary>
public sealed class PilotRuntime(SecurityDatabase runtime, SecurityDatabase issuer, JwtVerifier verifier, SupabaseAuthClient provider, TemporarySessions state, TimeProvider clock)
{
    private readonly SessionRepository repository = new(runtime);
    public async Task<bool> IsActiveForLoginAsync(SessionReference reference, CancellationToken cancellationToken)
    {
        if (state.Find(reference) is null) return false;
        try { await AuthenticateAsync(reference, cancellationToken).ConfigureAwait(false); return true; }
        catch (AuthException error) when (error.Failure == AuthFailure.Invalid) { state.Remove(reference); return false; }
    }
    public async Task<(SessionReference Reference, DateTimeOffset Expires, IReadOnlyList<TotpFactor> Factors)> LoginAsync(string email, string password, CancellationToken cancellationToken)
    {
        var credential = await provider.PasswordAsync(email, password, cancellationToken).ConfigureAwait(false);
        // Always require a fresh challenge, including a cached password response already claiming aal2.
        var factors = await provider.CheckUserAsync(credential, cancellationToken).ConfigureAwait(false);
        return (state.AddPending(credential), TemporarySessions.Min(credential.Identity.ExpiresAt, clock.GetUtcNow().AddMinutes(5)), factors);
    }
    private async Task CheckPendingAsync(PendingMfa pending, CancellationToken cancellationToken)
    {
        var identity = await verifier.ValidateAsync(pending.Credential.Token, cancellationToken).ConfigureAwait(false);
        if (identity != pending.Credential.Identity || pending.Expires <= clock.GetUtcNow()) throw new AuthException(AuthFailure.Invalid);
    }
    public async Task<TotpEnrollment> EnrollAsync(SessionReference reference, CancellationToken cancellationToken)
    {
        var pending = state.Acquire(reference);
        try
        {
            await CheckPendingAsync(pending, cancellationToken).ConfigureAwait(false);
            var factors = await provider.CheckUserAsync(pending.Credential, cancellationToken).ConfigureAwait(false);
            if (factors.Any(f => f.Verified)) throw new AuthException(AuthFailure.Conflict);
            // Recovery is limited to this user's unverified enrollments, never verified MFA factors.
            pending.Challenge = null;
            foreach (var factor in factors) await provider.RemoveUnverifiedFactorAsync(pending.Credential, factor.Id, cancellationToken).ConfigureAwait(false);
            var enrollment = await provider.EnrollAsync(pending.Credential, cancellationToken).ConfigureAwait(false); pending.Enrolled = enrollment.FactorId; return enrollment;
        }
        finally { state.Release(pending); }
    }
    public async Task<TotpChallenge> ChallengeAsync(SessionReference reference, Guid factor, CancellationToken cancellationToken)
    {
        var pending = state.Acquire(reference);
        try
        {
            await CheckPendingAsync(pending, cancellationToken).ConfigureAwait(false);
            var factors = await provider.CheckUserAsync(pending.Credential, cancellationToken).ConfigureAwait(false);
            if (factor == Guid.Empty || factor != pending.Enrolled && !factors.Any(f => f.Id == factor && f.Verified)) throw new AuthException(AuthFailure.Invalid);
            pending.Challenge = null; var started = clock.GetUtcNow();
            var challenge = await provider.ChallengeAsync(pending.Credential, factor, cancellationToken).ConfigureAwait(false);
            if (challenge.Id == Guid.Empty || challenge.ExpiresAt <= started || challenge.ExpiresAt > started.AddMinutes(5)) throw new AuthException(AuthFailure.Unavailable);
            pending.Factor = factor; pending.Challenge = challenge.Id; pending.ChallengeAt = started; pending.ChallengeExpires = challenge.ExpiresAt;
            return challenge;
        }
        finally { state.Release(pending); }
    }
    public async Task<(SessionReference Reference, DateTimeOffset Expires)> VerifyAsync(SessionReference reference, Guid challenge, string code, CancellationToken cancellationToken)
    {
        var pending = state.Acquire(reference);
        try
        {
            await CheckPendingAsync(pending, cancellationToken).ConfigureAwait(false);
            if (pending.Challenge != challenge || pending.ChallengeExpires <= clock.GetUtcNow() || pending.Factor is null) throw new AuthException(AuthFailure.Invalid);
            pending.Challenge = null; // One-shot before remote I/O; never restore after timeout or cancellation.
            var elevated = await provider.VerifyAsync(pending.Credential, pending.Factor.Value, challenge, code, cancellationToken).ConfigureAwait(false);
            var identity = elevated.Identity;
            if (identity.Identity != pending.Credential.Identity.Identity || identity.ProviderSessionId != pending.Credential.Identity.ProviderSessionId || identity.Aal != 2 || identity.MfaAt is null ||
                identity.MfaAt < pending.ChallengeAt.AddSeconds(-1) || identity.MfaAt > clock.GetUtcNow() || clock.GetUtcNow() - identity.MfaAt > TimeSpan.FromMinutes(5)) throw new AuthException(AuthFailure.Invalid);
            await provider.CheckUserAsync(elevated, cancellationToken).ConfigureAwait(false);
            var creation = await new SessionIssuer(issuer, verifier).CreateAsync(elevated.Token.AsMemory(), cancellationToken).ConfigureAwait(false);
            if (creation.Outcome != StoreOutcome.Success || creation.Reference is null || creation.Session is null) throw new AuthException(creation.Outcome == StoreOutcome.Unavailable ? AuthFailure.Unavailable : AuthFailure.Invalid);
            try
            {
                // The pilot lease cannot outlive the cancellation bridge for a delayed verify response.
                var end = TemporarySessions.Min(creation.Session.ExpiresAt, pending.Expires);
                state.Complete(reference, pending, new(elevated, creation.Reference, creation.Session.UserId, end));
                return (creation.Reference, end);
            }
            catch
            {
                // Lost response may leave an inaccessible SQL row, never a reusable browser reference.
                await repository.RevokeAsync(creation.Reference, CancellationToken.None).ConfigureAwait(false); throw;
            }
        }
        finally { state.Release(pending); }
    }
    private async Task<BrowserSession> AuthenticateAsync(SessionReference reference, CancellationToken cancellationToken)
    {
        var entry = state.Find(reference) ?? throw new AuthException(AuthFailure.Invalid);
        var identity = await verifier.ValidateAsync(entry.Credential.Token, cancellationToken).ConfigureAwait(false);
        if (identity != entry.Credential.Identity || identity.Aal != 2 || entry.Expires <= clock.GetUtcNow()) throw new AuthException(AuthFailure.Invalid);
        await provider.CheckUserAsync(entry.Credential, cancellationToken).ConfigureAwait(false);
        // One connection and status-bearing read; the M01.2 nullable reader deliberately collapses outages.
        try
        {
            await using var connection = await runtime.OpenAsync(cancellationToken).ConfigureAwait(false);
            await using var command = new Npgsql.NpgsqlCommand("SELECT * FROM app_security.self_user($1)", connection);
            command.Parameters.AddWithValue(reference.LookupHash());
            await using var reader = await command.ExecuteReaderAsync(cancellationToken).ConfigureAwait(false);
            if (!await reader.ReadAsync(cancellationToken).ConfigureAwait(false) || reader.GetGuid(0) != entry.User ||
                reader.GetString(1) != identity.Identity.Issuer || reader.GetGuid(2) != identity.Identity.Subject ||
                !string.Equals(reader.GetString(3), "Active", StringComparison.OrdinalIgnoreCase) || state.Find(reference) != entry) throw new AuthException(AuthFailure.Invalid);
        }
        catch (Exception error) when (error is Npgsql.NpgsqlException or InvalidOperationException or TimeoutException) { throw new AuthException(AuthFailure.Unavailable); }
        return entry;
    }
    public async Task<object> SessionAsync(SessionReference reference, CancellationToken cancellationToken)
    {
        var entry = await AuthenticateAsync(reference, cancellationToken).ConfigureAwait(false);
        return new { authenticated = true, aal = "aal2", expiresAt = entry.Expires, renewable = false, providerSessionConfirmedActive = false, executionAuthorized = false, mode = "OFFLINE", decision = "NO_TRADE" };
    }
    public async Task<Guid> ValidateSessionAsync(SessionReference reference, CancellationToken cancellationToken) =>
        (await AuthenticateAsync(reference, cancellationToken).ConfigureAwait(false)).User;
    public async Task<object> ProbeAsync(SessionReference reference, Guid resource, EnvironmentScope environment, CancellationToken cancellationToken)
    {
        await AuthenticateAsync(reference, cancellationToken).ConfigureAwait(false);
        var decision = await repository.AuthorizeAsync(reference, ResourceKind.Study, resource, environment, Capability.Read, cancellationToken).ConfigureAwait(false);
        if (decision.Outcome == StoreOutcome.Unavailable) throw new AuthException(AuthFailure.Unavailable);
        if (!decision.Allowed) throw new ProbeDeniedException();
        if (state.Find(reference) is null) throw new AuthException(AuthFailure.Invalid);
        return new { synthetic = true, value = "M013_AUTHORIZATION_PROBE", executionAuthorized = false, mode = "OFFLINE", decision = "NO_TRADE" };
    }
    public async Task<StoreOutcome> TouchAsync(SessionReference reference, long version, CancellationToken cancellationToken)
    {
        await AuthenticateAsync(reference, cancellationToken).ConfigureAwait(false);
        return (await repository.TouchAsync(reference, version, cancellationToken).ConfigureAwait(false)).Outcome;
    }
    public async Task<bool> LogoutAsync(SessionReference? reference, SessionReference? preliminary, CancellationToken cancellationToken)
    {
        var durable = true;
        if (preliminary is not null)
        {
            var cancelled = state.CancelPreliminary(preliminary); var completed = cancelled.Completed;
            if (cancelled.PreliminaryCredential is not null)
            {
                try { await provider.LogoutAsync(cancelled.PreliminaryCredential, cancellationToken).ConfigureAwait(false); }
                catch (AuthException) { /* No SQL session was issued; process-local pending capability is gone. */ }
            }
            if (completed is not null && reference is not null && !completed.LookupHash().AsSpan().SequenceEqual(reference.LookupHash()))
            {
                state.Remove(completed); durable = (await repository.RevokeAsync(completed, cancellationToken).ConfigureAwait(false)).Outcome != StoreOutcome.Unavailable;
            }
            reference ??= completed;
        }
        if (reference is null) return true;
        var entry = state.Remove(reference); // Local process capability is removed even when storage fails.
        var result = await repository.RevokeAsync(reference, cancellationToken).ConfigureAwait(false);
        if (entry is not null)
        {
            try { await provider.LogoutAsync(entry.Credential, cancellationToken).ConfigureAwait(false); }
            catch (AuthException) { /* Local revocation remains effective. Remote status remains unconfirmed. */ }
        }
        return durable && result.Outcome != StoreOutcome.Unavailable;
    }
}
public sealed class ProbeDeniedException : Exception
{
    public ProbeDeniedException() : base("RESOURCE_ACCESS_DENIED") { }
}
