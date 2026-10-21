using System.Text.Json;
using Microsoft.IdentityModel.Tokens;

namespace TradingAgent.HostedPilot;

/// <summary>Compatibility diagnostics only. Untrusted JWT shape never authorizes anything.</summary>
internal sealed class RedactedAuthObserver(string expectedIssuer) : DelegatingHandler
{
    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        var response = await base.SendAsync(request, cancellationToken).ConfigureAwait(false);
        var phase = request.RequestUri!.AbsolutePath switch
        {
            "/auth/v1/token" => "PASSWORD", "/auth/v1/user" => "USER", "/auth/v1/.well-known/jwks.json" => "JWKS", "/auth/v1/settings" => "SETTINGS", _ => "MFA_OR_LOGOUT"
        };
        HostedRun.Observe("http_" + phase, (int)response.StatusCode);
        if (phase != "PASSWORD" || !response.IsSuccessStatusCode) return response;
        try
        {
            await response.Content.LoadIntoBufferAsync(65536, cancellationToken).ConfigureAwait(false);
            using var body = JsonDocument.Parse(await response.Content.ReadAsByteArrayAsync(cancellationToken).ConfigureAwait(false));
            var raw = body.RootElement.GetProperty("access_token").GetString();
            if (raw is null || raw.Length > 16384 || raw.Split('.').Length != 3) return response;
            var parts = raw.Split('.'); using var header = JsonDocument.Parse(Base64UrlEncoder.DecodeBytes(parts[0])); using var claims = JsonDocument.Parse(Base64UrlEncoder.DecodeBytes(parts[1]));
            var h = header.RootElement; var p = claims.RootElement;
            bool Text(JsonElement element, string name, string expected) => element.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String && value.GetString() == expected;
            bool GuidPresent(string name) => p.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String && Guid.TryParse(value.GetString(), out var parsed) && parsed != Guid.Empty;
            var now = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            var issued = p.TryGetProperty("iat", out var iat) && iat.TryGetInt64(out var i) ? i : long.MinValue;
            var expires = p.TryGetProperty("exp", out var exp) && exp.TryGetInt64(out var e) ? e : long.MinValue;
            HostedRun.Observe("UNTRUSTED_PASSWORD_JWT_COMPATIBILITY_NOT_VALIDATION", new
            {
                alg_es256 = Text(h, "alg", "ES256"), typ_jwt = Text(h, "typ", "JWT"), kid_present = h.TryGetProperty("kid", out _),
                issuer_matches = Text(p, "iss", expectedIssuer), audience_authenticated = Text(p, "aud", "authenticated"),
                subject_uuid = GuidPresent("sub"), session_uuid = GuidPresent("session_id"), aal1 = Text(p, "aal", "aal1"),
                role_authenticated = Text(p, "role", "authenticated"), anonymous_false = p.TryGetProperty("is_anonymous", out var anon) && anon.ValueKind == JsonValueKind.False,
                iat_present_numeric = issued != long.MinValue, exp_present_numeric = expires != long.MinValue,
                iat_is_future = issued > now, exp_is_future = expires > now,
                declared_lifetime_over_one_hour = issued != long.MinValue && expires != long.MinValue && expires - issued > 3600,
                source_ref_claim_present = p.TryGetProperty("ref", out _), nbf_present = p.TryGetProperty("nbf", out _), amr_present = p.TryGetProperty("amr", out _)
            });
        }
        catch (Exception error) when (error is JsonException or KeyNotFoundException or FormatException or InvalidOperationException or ArgumentException)
        { HostedRun.Observe("jwt_compatibility_diagnostic", "UNAVAILABLE_MALFORMED; validator unchanged"); }
        return response;
    }
}
