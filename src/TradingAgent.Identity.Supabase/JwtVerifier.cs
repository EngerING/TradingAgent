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
        var diagnostic = AuthDiagnostic.JwtStructureInvalid;
        try
        {
            if (token is null || token.Length is < 80 or > 16384) throw Rejected(diagnostic);
            var segments = token.Split('.'); if (segments.Length != 3) throw Rejected(diagnostic);
            diagnostic = AuthDiagnostic.JwtHeaderInvalid;
            using var header = JsonDocument.Parse(Base64UrlEncoder.DecodeBytes(segments[0])); AuthTransport.EnsureUnique(header.RootElement);
            var h = header.RootElement;
            diagnostic = AuthDiagnostic.JwtAlgorithmInvalid;
            if (h.GetProperty("alg").GetString() != "ES256") throw Rejected(diagnostic);
            diagnostic = AuthDiagnostic.JwtTypeInvalid;
            if (h.GetProperty("typ").GetString() != "JWT") throw Rejected(diagnostic);
            if (h.TryGetProperty("jku", out _) || h.TryGetProperty("x5u", out _) || h.TryGetProperty("crit", out _) || h.TryGetProperty("jwk", out _)) throw Rejected(AuthDiagnostic.JwtRemoteKeyHintRejected);
            diagnostic = AuthDiagnostic.JwtKeyIdInvalid;
            var kid = h.GetProperty("kid").GetString(); if (string.IsNullOrWhiteSpace(kid) || kid.Length > 128) throw Rejected(diagnostic);
            diagnostic = AuthDiagnostic.JwksProfileInvalid;
            SecurityKey[] signingKeys;
            try { signingKeys = await keys.ResolveAsync(kid, cancellationToken).ConfigureAwait(false); }
            catch (AuthException error) when (error.Diagnostic == AuthDiagnostic.Unspecified)
            { throw new AuthException(error.Failure, AuthDiagnostic.JwksResponseRejected); }
            diagnostic = AuthDiagnostic.JwtValidationFailed;
            var lifetimeDiagnostic = AuthDiagnostic.JwtLifetimeInvalid;
            var handler = new JsonWebTokenHandler { MapInboundClaims = false, MaximumTokenSizeInBytes = 16384 };
            var validated = await handler.ValidateTokenAsync(token, new TokenValidationParameters
            {
                RequireSignedTokens = true, ValidateIssuerSigningKey = true, IssuerSigningKeys = signingKeys,
                ValidAlgorithms = ["ES256"], ValidateIssuer = true, ValidIssuer = configuration.Issuer,
                ValidateAudience = true, ValidAudience = "authenticated", RequireAudience = true, RequireExpirationTime = true,
                ValidateLifetime = true, ClockSkew = TimeSpan.Zero,
                LifetimeValidator = (notBefore, expires, _, _) =>
                {
                    // Preserve the original short-circuit checks and clock reads, with zero tolerance.
                    if (!expires.HasValue) { lifetimeDiagnostic = AuthDiagnostic.JwtExpirationMissing; return false; }
                    if (expires.Value <= clock.GetUtcNow().UtcDateTime) { lifetimeDiagnostic = AuthDiagnostic.JwtExpired; return false; }
                    if (notBefore.HasValue && notBefore.Value > clock.GetUtcNow().UtcDateTime) { lifetimeDiagnostic = AuthDiagnostic.JwtNotYetValid; return false; }
                    return true;
                }
            }).ConfigureAwait(false);
            if (!validated.IsValid) throw Rejected(validated.Exception switch
            {
                SecurityTokenInvalidSignatureException or SecurityTokenSignatureKeyNotFoundException => AuthDiagnostic.JwtSignatureInvalid,
                SecurityTokenInvalidIssuerException => AuthDiagnostic.JwtIssuerInvalid,
                SecurityTokenInvalidAudienceException => AuthDiagnostic.JwtAudienceInvalid,
                SecurityTokenNoExpirationException => AuthDiagnostic.JwtExpirationMissing,
                SecurityTokenExpiredException => AuthDiagnostic.JwtExpired,
                SecurityTokenNotYetValidException => AuthDiagnostic.JwtNotYetValid,
                SecurityTokenInvalidLifetimeException => lifetimeDiagnostic,
                SecurityTokenInvalidAlgorithmException => AuthDiagnostic.JwtAlgorithmInvalid,
                _ => AuthDiagnostic.JwtValidationFailed
            });
            diagnostic = AuthDiagnostic.JwtPayloadInvalid;
            using var payload = JsonDocument.Parse(Base64UrlEncoder.DecodeBytes(segments[1])); AuthTransport.EnsureUnique(payload.RootElement);
            var p = payload.RootElement; var now = clock.GetUtcNow();
            diagnostic = AuthDiagnostic.JwtSubjectInvalid; var subject = p.GetProperty("sub").GetGuid();
            diagnostic = AuthDiagnostic.JwtSessionInvalid; var session = p.GetProperty("session_id").GetGuid();
            diagnostic = AuthDiagnostic.JwtIssuedAtInvalid; var issued = DateTimeOffset.FromUnixTimeSeconds(p.GetProperty("iat").GetInt64());
            diagnostic = AuthDiagnostic.JwtExpirationInvalid; var expiry = DateTimeOffset.FromUnixTimeSeconds(p.GetProperty("exp").GetInt64());
            diagnostic = AuthDiagnostic.JwtAalInvalid;
            var aal = p.GetProperty("aal").GetString() switch { "aal1" => 1, "aal2" => 2, _ => 0 };
            if (subject == Guid.Empty) throw Rejected(AuthDiagnostic.JwtSubjectInvalid);
            if (session == Guid.Empty) throw Rejected(AuthDiagnostic.JwtSessionInvalid);
            if (aal == 0) throw Rejected(diagnostic);
            diagnostic = AuthDiagnostic.JwtRoleInvalid;
            if (p.GetProperty("role").GetString() != "authenticated") throw Rejected(diagnostic);
            diagnostic = AuthDiagnostic.JwtAnonymousRejected;
            if (p.GetProperty("is_anonymous").GetBoolean()) throw Rejected(diagnostic);
            if (p.TryGetProperty("ref", out _)) throw Rejected(AuthDiagnostic.JwtRefRejected);
            if (issued > now) throw Rejected(AuthDiagnostic.JwtIssuedAtFuture);
            if (issued >= expiry) throw Rejected(AuthDiagnostic.JwtLifetimeInvalid);
            if (expiry - issued > TimeSpan.FromHours(1)) throw Rejected(AuthDiagnostic.JwtLifetimeTooLong);
            if (expiry <= now) throw Rejected(AuthDiagnostic.JwtExpired);
            diagnostic = AuthDiagnostic.JwtIssuerInvalid;
            if (p.GetProperty("iss").GetString() != configuration.Issuer) throw Rejected(diagnostic);
            DateTimeOffset? mfa = null;
            diagnostic = AuthDiagnostic.JwtAmrInvalid;
            if (p.TryGetProperty("amr", out var methods))
            {
                if (methods.ValueKind != JsonValueKind.Array || methods.GetArrayLength() > 8) throw Rejected(diagnostic);
                foreach (var method in methods.EnumerateArray())
                {
                    diagnostic = AuthDiagnostic.JwtAmrTimestampInvalid;
                    var at = DateTimeOffset.FromUnixTimeSeconds(method.GetProperty("timestamp").GetInt64());
                    if (at > issued || at > now) throw Rejected(diagnostic);
                    diagnostic = AuthDiagnostic.JwtAmrMethodInvalid;
                    if (method.GetProperty("method").GetString() is "totp" or "mfa/totp" && (mfa is null || at > mfa)) mfa = at;
                }
            }
            diagnostic = AuthDiagnostic.JwtPayloadInvalid;
            return new(new IdentityKey(configuration.Issuer, subject), session, aal, issued, expiry, mfa);
        }
        catch (Exception error) when (error is JsonException or FormatException or ArgumentException or KeyNotFoundException or InvalidOperationException or SecurityTokenException)
        { throw Rejected(diagnostic); }
    }
    private static AuthException Rejected(AuthDiagnostic diagnostic) => new(AuthFailure.Invalid, diagnostic);
    public async ValueTask<IdentityProof?> VerifyAsync(ReadOnlyMemory<char> evidence, CancellationToken cancellationToken)
    {
        var identity = await ValidateAsync(evidence.ToString(), cancellationToken).ConfigureAwait(false);
        if (identity.Aal != 2 || identity.MfaAt is null || clock.GetUtcNow() - identity.MfaAt > TimeSpan.FromMinutes(5)) return null;
        return new(identity.Identity, identity.ProviderSessionId, 2, identity.MfaAt.Value, identity.ExpiresAt);
    }
}
