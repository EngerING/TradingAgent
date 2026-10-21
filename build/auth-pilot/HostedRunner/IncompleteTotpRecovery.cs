using TradingAgent.Identity.Persistence;
using TradingAgent.Identity.Supabase;

namespace TradingAgent.HostedPilot;

internal sealed record TotpRecoveryTarget(IdentityKey Identity, Guid FactorId);

/// <summary>Local pilot only, before any MFA elevation of this fresh password session.</summary>
internal static class IncompleteTotpRecovery
{
    internal static async Task RecoverAsync(SupabaseAuthClient auth, JwtVerifier verifier, AccessCredential credential,
        TotpRecoveryTarget target, Func<TotpRecoveryTarget, bool> confirm, TimeProvider clock, CancellationToken token)
    {
        var expires = clock.GetUtcNow().AddMinutes(2);
        await VerifyIdentityAsync();
        EnsureCandidate(await auth.CheckUserAsync(credential, token));
        // Confirmation is local and refers to this exact identity/factor, never a JSON flag.
        if (!confirm(target)) throw new OperationCanceledException("RECOVERY_NOT_CONFIRMED");
        token.ThrowIfCancellationRequested();
        if (clock.GetUtcNow() >= expires) throw new AuthException(AuthFailure.Conflict);
        await VerifyIdentityAsync();
        EnsureCandidate(await auth.CheckUserAsync(credential, token));
        token.ThrowIfCancellationRequested();
        if (clock.GetUtcNow() >= expires) throw new AuthException(AuthFailure.Conflict);
        // This method performs one more authenticated ownership/status check before DELETE.
        // The fresh AAL1 session is never elevated here; provider also denies verified-factor
        // removal to AAL1. This is not an atomic status lock: exclusive use of the fictitious
        // account must be confirmed locally. No admin key, retry or alternative target.
        await auth.RemoveUnverifiedFactorAsync(credential, target.FactorId, token, expires, clock);
        if ((await auth.CheckUserAsync(credential, token)).Any(f => f.Id == target.FactorId))
            throw new AuthException(AuthFailure.Conflict);

        async Task VerifyIdentityAsync()
        {
            var proof = await verifier.ValidateAsync(credential.Token, token);
            if (proof.Aal != 1 || credential.Identity.Aal != 1 || proof.Identity != target.Identity ||
                proof.Identity != credential.Identity.Identity || proof.ProviderSessionId != credential.Identity.ProviderSessionId || target.FactorId == Guid.Empty)
                throw new AuthException(AuthFailure.Invalid);
        }
        void EnsureCandidate(IReadOnlyList<TotpFactor> factors)
        {
            if (factors.Count != 1 || factors[0].Id != target.FactorId || factors[0].Verified)
                throw new AuthException(AuthFailure.Conflict);
        }
    }
}
