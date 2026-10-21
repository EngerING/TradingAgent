using System.Text.Json;
using System.Text.Json.Serialization;

namespace TradingAgent.Identity.Supabase;

public sealed class AccessCredential(string token, VerifiedIdentity identity)
{
    [JsonIgnore] public string Token { get; } = token;
    public VerifiedIdentity Identity { get; } = identity;
    public override string ToString() => "[REDACTED_AUTH_CREDENTIAL]";
}
public sealed record TotpFactor(Guid Id, bool Verified);
public sealed record TotpEnrollment(Guid FactorId, string Secret, string Uri)
{
    public override string ToString() => "[REDACTED_TOTP_ENROLLMENT]";
}
public sealed record TotpChallenge(Guid Id, DateTimeOffset ExpiresAt);

public sealed class SupabaseAuthClient(AuthTransport transport, JwtVerifier verifier)
{
    public async Task<AccessCredential> PasswordAsync(string email, string password, CancellationToken cancellationToken)
    {
        using var document = await transport.SendAsync(HttpMethod.Post, "/auth/v1/token?grant_type=password", new { email, password }, null, cancellationToken).ConfigureAwait(false);
        return await CredentialAsync(document, cancellationToken).ConfigureAwait(false);
    }
    private async Task<AccessCredential> CredentialAsync(JsonDocument document, CancellationToken cancellationToken)
    {
        try
        {
            var root = document.RootElement;
            if (root.GetProperty("token_type").GetString() != "bearer") throw new AuthException(AuthFailure.Invalid);
            var token = root.GetProperty("access_token").GetString() ?? throw new AuthException(AuthFailure.Invalid);
            var identity = await verifier.ValidateAsync(token, cancellationToken).ConfigureAwait(false);
            // refresh_token is deliberately not read or retained.
            return new(token, identity);
        }
        catch (Exception error) when (error is KeyNotFoundException or InvalidOperationException) { throw new AuthException(AuthFailure.Unavailable); }
    }
    public async Task<IReadOnlyList<TotpFactor>> CheckUserAsync(AccessCredential credential, CancellationToken cancellationToken)
    {
        using var document = await transport.SendAsync(HttpMethod.Get, "/auth/v1/user", null, credential.Token, cancellationToken).ConfigureAwait(false);
        try
        {
            var root = document.RootElement;
            if (root.GetProperty("id").GetGuid() != credential.Identity.Identity.Subject || root.GetProperty("is_anonymous").GetBoolean()) throw new AuthException(AuthFailure.Invalid);
            if (!root.TryGetProperty("factors", out var factors)) return [];
            if (factors.ValueKind != JsonValueKind.Array || factors.GetArrayLength() > 10) throw new AuthException(AuthFailure.Unavailable);
            var result = new List<TotpFactor>(); var seen = new HashSet<Guid>();
            foreach (var factor in factors.EnumerateArray())
            {
                var id = factor.GetProperty("id").GetGuid();
                if (id == Guid.Empty || !seen.Add(id)) throw new AuthException(AuthFailure.Unavailable);
                if (factor.GetProperty("factor_type").GetString() != "totp") continue;
                var verified = factor.GetProperty("status").GetString() switch
                {
                    "verified" => true, "unverified" => false, _ => throw new AuthException(AuthFailure.Unavailable)
                };
                result.Add(new(id, verified));
            }
            return result;
        }
        catch (Exception error) when (error is KeyNotFoundException or InvalidOperationException or FormatException) { throw new AuthException(AuthFailure.Unavailable); }
    }
    public async Task<TotpEnrollment> EnrollAsync(AccessCredential credential, CancellationToken cancellationToken)
    {
        using var document = await transport.SendAsync(HttpMethod.Post, "/auth/v1/factors", new { factor_type = "totp", friendly_name = "TradingAgent" }, credential.Token, cancellationToken).ConfigureAwait(false);
        try
        {
            var root = document.RootElement; var totp = root.GetProperty("totp"); var id = root.GetProperty("id").GetGuid();
            var secret = totp.GetProperty("secret").GetString()!; var uri = totp.GetProperty("uri").GetString()!;
            if (id == Guid.Empty || root.GetProperty("type").GetString() != "totp" || secret.Length is < 16 or > 128 || uri.Length > 2048 || !uri.StartsWith("otpauth://totp/", StringComparison.Ordinal)) throw new AuthException(AuthFailure.Unavailable, AuthDiagnostic.EnrollmentContractInvalid);
            // No raw provider SVG/HTML is reflected. Only text fields for a future trusted UI.
            return new(id, secret, uri);
        }
        catch (Exception error) when (error is KeyNotFoundException or InvalidOperationException or FormatException or NullReferenceException) { throw new AuthException(AuthFailure.Unavailable, AuthDiagnostic.EnrollmentContractInvalid); }
    }
    public async Task<TotpChallenge> ChallengeAsync(AccessCredential credential, Guid factor, CancellationToken cancellationToken)
    {
        using var document = await transport.SendAsync(HttpMethod.Post, $"/auth/v1/factors/{factor:D}/challenge", new { }, credential.Token, cancellationToken).ConfigureAwait(false);
        try { return new(document.RootElement.GetProperty("id").GetGuid(), DateTimeOffset.FromUnixTimeSeconds(document.RootElement.GetProperty("expires_at").GetInt64())); }
        catch (Exception error) when (error is KeyNotFoundException or InvalidOperationException or FormatException or ArgumentOutOfRangeException) { throw new AuthException(AuthFailure.Unavailable); }
    }
    public async Task<AccessCredential> VerifyAsync(AccessCredential credential, Guid factor, Guid challenge, string code, CancellationToken cancellationToken)
    {
        using var document = await transport.SendAsync(HttpMethod.Post, $"/auth/v1/factors/{factor:D}/verify", new { challenge_id = challenge, code }, credential.Token, cancellationToken).ConfigureAwait(false);
        return await CredentialAsync(document, cancellationToken).ConfigureAwait(false);
    }
    public async Task LogoutAsync(AccessCredential credential, CancellationToken cancellationToken)
    {
        using var document = await transport.SendAsync(HttpMethod.Post, "/auth/v1/logout?scope=local", null, credential.Token, cancellationToken).ConfigureAwait(false);
    }
    public async Task RemoveUnverifiedFactorAsync(AccessCredential credential, Guid factor, CancellationToken cancellationToken,
        DateTimeOffset? notAfter = null, TimeProvider? clock = null)
    {
        var time = clock ?? TimeProvider.System;
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        if (notAfter is { } end)
        {
            var remaining = end - time.GetUtcNow();
            if (remaining <= TimeSpan.Zero || remaining > TimeSpan.FromMinutes(2)) throw new AuthException(AuthFailure.Conflict);
            deadline.CancelAfter(remaining);
        }
        var factors = await CheckUserAsync(credential, deadline.Token).ConfigureAwait(false);
        if (!factors.Any(f => f.Id == factor && !f.Verified)) throw new AuthException(AuthFailure.Invalid);
        deadline.Token.ThrowIfCancellationRequested();
        if (notAfter.HasValue && time.GetUtcNow() >= notAfter.Value) throw new AuthException(AuthFailure.Conflict);
        using var document = await transport.SendAsync(HttpMethod.Delete, $"/auth/v1/factors/{factor:D}", null, credential.Token, deadline.Token).ConfigureAwait(false);
    }
}
