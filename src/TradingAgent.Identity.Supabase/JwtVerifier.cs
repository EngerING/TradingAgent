using System.Text.Json;
using Microsoft.IdentityModel.JsonWebTokens;
using Microsoft.IdentityModel.Tokens;
using TradingAgent.Identity.Persistence;

namespace TradingAgent.Identity.Supabase;

public sealed record VerifiedIdentity(IdentityKey Identity, Guid ProviderSessionId, int Aal, DateTimeOffset IssuedAt, DateTimeOffset ExpiresAt, DateTimeOffset? MfaAt);

public sealed class JwtVerifier(JwksCache keys, AuthConfiguration configuration, TimeProvider clock) : IIdentityEvidenceVerifier
{
    public async Task<VerifiedIdentity> ValidateAsync(string token, CancellationToken cancellationToken)
    {
        try
        {
            if (token is null || token.Length is < 80 or > 16384) throw new AuthException(AuthFailure.Invalid);
            var segments = token.Split('.'); if (segments.Length != 3) throw new AuthException(AuthFailure.Invalid);
            using var header = JsonDocument.Parse(Base64UrlEncoder.DecodeBytes(segments[0])); AuthTransport.EnsureUnique(header.RootElement);
            var h = header.RootElement;
            if (h.GetProperty("alg").GetString() != "ES256" || h.GetProperty("typ").GetString() != "JWT" || h.TryGetProperty("jku", out _) || h.TryGetProperty("x5u", out _) || h.TryGetProperty("crit", out _) || h.TryGetProperty("jwk", out _)) throw new AuthException(AuthFailure.Invalid);
            var kid = h.GetProperty("kid").GetString(); if (string.IsNullOrWhiteSpace(kid) || kid.Length > 128) throw new AuthException(AuthFailure.Invalid);
            var signingKeys = await keys.ResolveAsync(kid, cancellationToken).ConfigureAwait(false);
            var handler = new JsonWebTokenHandler { MapInboundClaims = false, MaximumTokenSizeInBytes = 16384 };
            var validated = await handler.ValidateTokenAsync(token, new TokenValidationParameters
            {
                RequireSignedTokens = true, ValidateIssuerSigningKey = true, IssuerSigningKeys = signingKeys,
                ValidAlgorithms = ["ES256"], ValidateIssuer = true, ValidIssuer = configuration.Issuer,
                ValidateAudience = true, ValidAudience = "authenticated", RequireAudience = true, RequireExpirationTime = true,
                ValidateLifetime = true, ClockSkew = TimeSpan.Zero,
                LifetimeValidator = (notBefore, expires, _, _) => expires.HasValue && expires.Value > clock.GetUtcNow().UtcDateTime && (!notBefore.HasValue || notBefore.Value <= clock.GetUtcNow().UtcDateTime)
            }).ConfigureAwait(false);
            if (!validated.IsValid) throw new AuthException(AuthFailure.Invalid);
            using var payload = JsonDocument.Parse(Base64UrlEncoder.DecodeBytes(segments[1])); AuthTransport.EnsureUnique(payload.RootElement);
            var p = payload.RootElement; var now = clock.GetUtcNow();
            var subject = p.GetProperty("sub").GetGuid(); var session = p.GetProperty("session_id").GetGuid();
            var issued = DateTimeOffset.FromUnixTimeSeconds(p.GetProperty("iat").GetInt64()); var expiry = DateTimeOffset.FromUnixTimeSeconds(p.GetProperty("exp").GetInt64());
            var aal = p.GetProperty("aal").GetString() switch { "aal1" => 1, "aal2" => 2, _ => 0 };
            if (subject == Guid.Empty || session == Guid.Empty || aal == 0 || p.GetProperty("role").GetString() != "authenticated" || p.GetProperty("is_anonymous").GetBoolean() || p.TryGetProperty("ref", out _) ||
                issued > now || issued >= expiry || expiry - issued > TimeSpan.FromHours(1) || expiry <= now || p.GetProperty("iss").GetString() != configuration.Issuer) throw new AuthException(AuthFailure.Invalid);
            DateTimeOffset? mfa = null;
            if (p.TryGetProperty("amr", out var methods))
            {
                if (methods.ValueKind != JsonValueKind.Array || methods.GetArrayLength() > 8) throw new AuthException(AuthFailure.Invalid);
                foreach (var method in methods.EnumerateArray())
                {
                    var at = DateTimeOffset.FromUnixTimeSeconds(method.GetProperty("timestamp").GetInt64());
                    if (at > issued || at > now) throw new AuthException(AuthFailure.Invalid);
                    if (method.GetProperty("method").GetString() is "totp" or "mfa/totp" && (mfa is null || at > mfa)) mfa = at;
                }
            }
            return new(new IdentityKey(configuration.Issuer, subject), session, aal, issued, expiry, mfa);
        }
        catch (Exception error) when (error is JsonException or FormatException or ArgumentException or KeyNotFoundException or InvalidOperationException or SecurityTokenException)
        { throw new AuthException(AuthFailure.Invalid); }
    }
    public async ValueTask<IdentityProof?> VerifyAsync(ReadOnlyMemory<char> evidence, CancellationToken cancellationToken)
    {
        var identity = await ValidateAsync(evidence.ToString(), cancellationToken).ConfigureAwait(false);
        if (identity.Aal != 2 || identity.MfaAt is null || clock.GetUtcNow() - identity.MfaAt > TimeSpan.FromMinutes(5)) return null;
        return new(identity.Identity, identity.ProviderSessionId, 2, identity.MfaAt.Value, identity.ExpiresAt);
    }
}
