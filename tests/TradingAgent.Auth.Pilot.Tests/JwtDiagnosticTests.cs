using System.Net;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.IdentityModel.Tokens;
using TradingAgent.Auth.Tests;
using TradingAgent.Identity.Supabase;
using Xunit;

namespace TradingAgent.Auth.Pilot.Tests;

public sealed class JwtDiagnosticTests
{
    [Theory]
    [InlineData("algorithm", "JwtAlgorithmInvalid")]
    [InlineData("type", "JwtTypeInvalid")]
    [InlineData("missing-type", "JwtTypeInvalid")]
    [InlineData("remote-key", "JwtRemoteKeyHintRejected")]
    [InlineData("missing-kid", "JwtKeyIdInvalid")]
    [InlineData("empty-kid", "JwtKeyIdInvalid")]
    [InlineData("long-kid", "JwtKeyIdInvalid")]
    [InlineData("unknown-kid", "JwksKeyNotFound")]
    [InlineData("signature", "JwtSignatureInvalid")]
    [InlineData("issuer", "JwtIssuerInvalid")]
    [InlineData("audience", "JwtAudienceInvalid")]
    [InlineData("expired", "JwtExpired")]
    [InlineData("missing-exp", "JwtExpirationMissing")]
    [InlineData("not-yet-valid", "JwtNotYetValid")]
    [InlineData("subject", "JwtSubjectInvalid")]
    [InlineData("empty-subject", "JwtSubjectInvalid")]
    [InlineData("session", "JwtSessionInvalid")]
    [InlineData("empty-session", "JwtSessionInvalid")]
    [InlineData("aal", "JwtAalInvalid")]
    [InlineData("role", "JwtRoleInvalid")]
    [InlineData("anonymous", "JwtAnonymousRejected")]
    [InlineData("ref", "JwtRefRejected")]
    [InlineData("missing-iat", "JwtIssuedAtInvalid")]
    [InlineData("future", "JwtIssuedAtFuture")]
    [InlineData("long-life", "JwtLifetimeTooLong")]
    [InlineData("amr-type", "JwtAmrInvalid")]
    [InlineData("amr-count", "JwtAmrInvalid")]
    [InlineData("amr-time-type", "JwtAmrTimestampInvalid")]
    [InlineData("amr-future", "JwtAmrTimestampInvalid")]
    [InlineData("amr-method", "JwtAmrMethodInvalid")]
    [InlineData("duplicate-header", "JwtHeaderInvalid")]
    [InlineData("duplicate-payload", "JwtPayloadInvalid")]
    [InlineData("structure", "JwtStructureInvalid")]
    public async Task EachRejectedGateHasAClosedValueFreeDiagnostic(string variant, string expected)
    {
        using var wire = new DiagnosticWire(); using var services = wire.Services();
        var error = await Assert.ThrowsAsync<AuthException>(() => services.GetRequiredService<JwtVerifier>().ValidateAsync(wire.Token(variant), CancellationToken.None));
        Assert.Equal(AuthFailure.Invalid, error.Failure); Assert.Equal(expected, error.Diagnostic.ToString());
        Assert.Equal("AUTH_REQUEST_REJECTED", error.Message); Assert.Null(error.InnerException);
    }

    [Theory]
    [InlineData("profile", "JwksProfileInvalid")]
    [InlineData("empty", "JwksProfileInvalid")]
    [InlineData("duplicate", "JwksProfileInvalid")]
    public async Task InvalidJwksIsUnavailableWithClosedDiagnostic(string variant, string expected)
    {
        using var wire = new DiagnosticWire { JwksVariant = variant }; using var services = wire.Services();
        var error = await Assert.ThrowsAsync<AuthException>(() => services.GetRequiredService<JwtVerifier>().ValidateAsync(wire.Token("valid"), CancellationToken.None));
        Assert.Equal(AuthFailure.Unavailable, error.Failure); Assert.Equal(expected, error.Diagnostic.ToString());
    }

    [Theory]
    [InlineData(400, AuthFailure.Invalid)]
    [InlineData(401, AuthFailure.Invalid)]
    [InlineData(403, AuthFailure.Invalid)]
    [InlineData(422, AuthFailure.Invalid)]
    [InlineData(503, AuthFailure.Unavailable)]
    public async Task JwksHttpFailureKeepsFailureAndGetsClosedDiagnostic(int status, AuthFailure failure)
    {
        using var wire = new DiagnosticWire { Status = (HttpStatusCode)status }; using var services = wire.Services();
        var error = await Assert.ThrowsAsync<AuthException>(() => services.GetRequiredService<JwtVerifier>().ValidateAsync(wire.Token("valid"), CancellationToken.None));
        Assert.Equal(failure, error.Failure); Assert.Equal("JwksResponseRejected", error.Diagnostic.ToString());
        Assert.Equal("AUTH_REQUEST_REJECTED", error.Message); Assert.Null(error.InnerException);
    }

    [Fact]
    public async Task FutureIatBoundaryKeepsZeroToleranceAndDoesNotCreateMfaEvidence()
    {
        using var wire = new DiagnosticWire(); using var services = wire.Services(); var verifier = services.GetRequiredService<JwtVerifier>();
        var token = wire.Token("future");
        wire.Clock.Now = wire.Clock.Now.AddSeconds(29);
        Assert.Equal("JwtIssuedAtFuture", (await Assert.ThrowsAsync<AuthException>(() => verifier.ValidateAsync(token, CancellationToken.None))).Diagnostic.ToString());
        wire.Clock.Now = wire.Clock.Now.AddSeconds(1);
        Assert.Equal(1, (await verifier.ValidateAsync(token, CancellationToken.None)).Aal);
        Assert.Null(await verifier.VerifyAsync(token.AsMemory(), CancellationToken.None));
    }

    [Theory]
    [InlineData(false, "JwtIssuedAtFuture")]
    [InlineData(true, "JwtSignatureInvalid")]
    public async Task SameFuturePayloadRequiresDistinctSignedAndTamperedDiagnostics(bool tamper, string expected)
    {
        await using var provider = new SimulatedAuth(); await provider.StartAsync();
        var token = provider.Token(Guid.NewGuid(), Guid.NewGuid(), variant: "future");
        if (tamper) token = token[..^5] + "AAAAA";
        var verifier = provider.Services.GetRequiredService<JwtVerifier>();
        var error = await Assert.ThrowsAsync<AuthException>(() => verifier.ValidateAsync(token, CancellationToken.None));
        Assert.Equal(AuthFailure.Invalid, error.Failure);
        Assert.Equal(expected, error.Diagnostic.ToString());
        Assert.Equal("AUTH_REQUEST_REJECTED", error.Message); Assert.Null(error.InnerException);
        Assert.DoesNotContain(token, error.ToString(), StringComparison.Ordinal);
        if (!tamper)
        {
            provider.Clock.Advance(TimeSpan.FromSeconds(30));
            Assert.Equal(2, (await verifier.ValidateAsync(token, CancellationToken.None)).Aal);
        }
    }

    private sealed class FixedClock : TimeProvider
    {
        internal DateTimeOffset Now { get; set; } = new(2030, 1, 1, 0, 0, 0, TimeSpan.Zero);
        public override DateTimeOffset GetUtcNow() => Now;
    }

    // Pure HTTPS-shaped handler: no socket, SQL, user endpoint, account or persisted key.
    private sealed class DiagnosticWire : HttpMessageHandler
    {
        private readonly ECDsa key = ECDsa.Create(ECCurve.NamedCurves.nistP256);
        private readonly AuthConfiguration config = AuthConfiguration.ForProject(new Uri("https://abcdefghijklmnopqrst.supabase.co"), "sb_publishable_publicfixture");
        internal FixedClock Clock { get; } = new();
        internal string JwksVariant { get; init; } = "valid";
        internal HttpStatusCode Status { get; init; } = HttpStatusCode.OK;
        internal ServiceProvider Services()
        {
            var services = new ServiceCollection(); services.AddSupabaseAuth(config).ConfigurePrimaryHttpMessageHandler(() => this);
            services.AddSingleton<TimeProvider>(Clock); return services.BuildServiceProvider();
        }
        internal string Token(string variant)
        {
            var now = Clock.Now.ToUnixTimeSeconds();
            var header = new Dictionary<string, object> { ["alg"] = "ES256", ["typ"] = "JWT", ["kid"] = "diagnostic-key" };
            var payload = new Dictionary<string, object> { ["iss"] = config.Issuer, ["aud"] = "authenticated", ["sub"] = Guid.NewGuid(), ["session_id"] = Guid.NewGuid(), ["iat"] = now, ["exp"] = now+300, ["aal"] = "aal1", ["role"] = "authenticated", ["is_anonymous"] = false, ["amr"] = new[] { new { method = "password", timestamp = now } } };
            switch (variant)
            {
                case "algorithm": header["alg"] = "HS256"; break;
                case "type": header["typ"] = "at+jwt"; break;
                case "missing-type": header.Remove("typ"); break;
                case "remote-key": header["jku"] = "https://attacker.invalid"; break;
                case "missing-kid": header.Remove("kid"); break;
                case "empty-kid": header["kid"] = ""; break;
                case "long-kid": header["kid"] = new string('k', 129); break;
                case "unknown-kid": header["kid"] = "other-key"; break;
                case "issuer": payload["iss"] = "https://other.invalid/auth/v1"; break;
                case "audience": payload["aud"] = "anon"; break;
                case "expired": payload["exp"] = now; break;
                case "missing-exp": payload.Remove("exp"); break;
                case "not-yet-valid": payload["nbf"] = now+1; break;
                case "subject": payload["sub"] = "not-uuid"; break;
                case "empty-subject": payload["sub"] = Guid.Empty; break;
                case "session": payload.Remove("session_id"); break;
                case "empty-session": payload["session_id"] = Guid.Empty; break;
                case "aal": payload["aal"] = "aal9"; break;
                case "role": payload["role"] = "service_role"; break;
                case "anonymous": payload["is_anonymous"] = true; break;
                case "ref": payload["ref"] = "fixture-ref"; break;
                case "missing-iat": payload.Remove("iat"); break;
                case "future": payload["iat"] = now+30; break;
                case "long-life": payload["exp"] = now+3601; break;
                case "amr-type": payload["amr"] = new { method = "password" }; break;
                case "amr-count": payload["amr"] = Enumerable.Repeat(new { method = "password", timestamp = now }, 9).ToArray(); break;
                case "amr-time-type": payload["amr"] = new[] { new { method = "password", timestamp = "not-a-time" } }; break;
                case "amr-future": payload["amr"] = new[] { new { method = "password", timestamp = now+1 } }; break;
                case "amr-method": payload["amr"] = new[] { new { timestamp = now } }; break;
                case "structure": return "invalid";
            }
            var h = JsonSerializer.Serialize(header); var p = JsonSerializer.Serialize(payload);
            if (variant == "duplicate-header") h = h[..^1] + ",\"typ\":\"JWT\"}";
            if (variant == "duplicate-payload") p = p[..^1] + ",\"aal\":\"aal1\"}";
            var input = Base64UrlEncoder.Encode(h) + "." + Base64UrlEncoder.Encode(p);
            var signature = key.SignData(Encoding.ASCII.GetBytes(input), HashAlgorithmName.SHA256, DSASignatureFormat.IeeeP1363FixedFieldConcatenation);
            if (variant == "signature") signature[0] ^= 1;
            return input + "." + Base64UrlEncoder.Encode(signature);
        }
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            Assert.Equal(config.Jwks, request.RequestUri); Assert.Equal(HttpMethod.Get, request.Method);
            if (Status != HttpStatusCode.OK) return Task.FromResult(new HttpResponseMessage(Status) { RequestMessage = request });
            var p = key.ExportParameters(false);
            object profile = new { kty = "EC", crv = "P-256", alg = "ES256", use = JwksVariant == "profile" ? "enc" : "sig", kid = "diagnostic-key", x = Base64UrlEncoder.Encode(p.Q.X!), y = Base64UrlEncoder.Encode(p.Q.Y!) };
            object[] keys = JwksVariant switch { "empty" => [], "duplicate" => [profile, profile], _ => [profile] };
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { RequestMessage = request, Content = JsonContent.Create(new { keys }) });
        }
        protected override void Dispose(bool disposing) { if (disposing) key.Dispose(); base.Dispose(disposing); }
    }
}
