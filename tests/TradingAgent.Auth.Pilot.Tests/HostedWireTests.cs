using System.Net;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.IdentityModel.JsonWebTokens;
using Microsoft.IdentityModel.Tokens;
using TradingAgent.Identity.Supabase;
using Xunit;

namespace TradingAgent.Auth.Pilot.Tests;

/// <summary>HTTPS-shaped protocol fixtures only. Never opens a hosted connection.</summary>
public sealed class HostedWireTests
{
    [Fact]
    public async Task ExactHostedProfileValidatesSignedPasswordMfaAndLogoutWithoutExposingTokens()
    {
        using var wire = new HostedWire(); using var services = wire.Services(); var auth = services.GetRequiredService<SupabaseAuthClient>();
        var initial = await auth.PasswordAsync("fixture@fixture.invalid", "fixture-password", CancellationToken.None);
        Assert.Equal(1, initial.Identity.Aal); await auth.CheckUserAsync(initial, CancellationToken.None);
        var factor = await auth.EnrollAsync(initial, CancellationToken.None);
        var challenge = await auth.ChallengeAsync(initial, factor.FactorId, CancellationToken.None);
        var elevated = await auth.VerifyAsync(initial, factor.FactorId, challenge.Id, "123456", CancellationToken.None);
        Assert.Equal(2, elevated.Identity.Aal); Assert.Equal(initial.Identity.Identity, elevated.Identity.Identity);
        Assert.Equal(initial.Identity.ProviderSessionId, elevated.Identity.ProviderSessionId);
        Assert.NotNull(elevated.Identity.MfaAt); Assert.DoesNotContain("eyJ", JsonSerializer.Serialize(elevated), StringComparison.Ordinal);
        await auth.LogoutAsync(elevated, CancellationToken.None);
        Assert.Equal(7, wire.Requests); Assert.Equal(1, wire.JwksRequests);
    }
    [Theory]
    [InlineData("audience")] [InlineData("issuer")] [InlineData("nbf")] [InlineData("anonymous")] [InlineData("missing-session")]
    public async Task HostedClaimIncompatibilitiesRemainDenied(string variant)
    {
        using var wire = new HostedWire { Variant = variant }; using var services = wire.Services();
        var error = await Assert.ThrowsAsync<AuthException>(() => services.GetRequiredService<SupabaseAuthClient>().PasswordAsync("fixture@fixture.invalid", "fixture-password", CancellationToken.None));
        Assert.Equal(AuthFailure.Invalid, error.Failure);
    }
    [Fact]
    public async Task HostedRateLimitIs429EquivalentAndNoRetryOccurs()
    {
        using var wire = new HostedWire { RateLimited = true }; using var services = wire.Services();
        var error = await Assert.ThrowsAsync<AuthException>(() => services.GetRequiredService<SupabaseAuthClient>().PasswordAsync("fixture@fixture.invalid", "fixture-password", CancellationToken.None));
        Assert.Equal(AuthFailure.RateLimited, error.Failure); Assert.Equal(1, wire.Requests);
    }
    private sealed class HostedWire : HttpMessageHandler
    {
        private readonly ECDsa key = ECDsa.Create(ECCurve.NamedCurves.nistP256);
        private readonly Guid subject = Guid.NewGuid(), session = Guid.NewGuid(), factor = Guid.NewGuid(), challenge = Guid.NewGuid();
        private readonly AuthConfiguration config = AuthConfiguration.ForProject(new Uri("https://abcdefghijklmnopqrst.supabase.co"), "sb_publishable_publicfixture");
        internal string Variant { get; init; } = "valid";
        internal bool RateLimited { get; init; }
        internal int Requests { get; private set; }
        internal int JwksRequests { get; private set; }
        internal ServiceProvider Services()
        {
            var services = new ServiceCollection(); services.AddSupabaseAuth(config).ConfigurePrimaryHttpMessageHandler(() => this);
            return services.BuildServiceProvider();
        }
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            Requests++; Assert.Equal(config.Project.Host, request.RequestUri!.Host); Assert.Equal("https", request.RequestUri.Scheme);
            Assert.Equal(config.PublicKey, request.Headers.GetValues("apikey").Single());
            if (RateLimited) return Task.FromResult(new HttpResponseMessage(HttpStatusCode.TooManyRequests) { RequestMessage = request });
            object response;
            var path = request.RequestUri.AbsolutePath;
            if (path.EndsWith("/jwks.json", StringComparison.Ordinal))
            {
                JwksRequests++; var p = key.ExportParameters(false);
                response = new { keys = new[] { new { kty = "EC", crv = "P-256", alg = "ES256", use = "sig", kid = "pilot-key", x = Base64UrlEncoder.Encode(p.Q.X!), y = Base64UrlEncoder.Encode(p.Q.Y!) } } };
            }
            else if (path.EndsWith("/user", StringComparison.Ordinal)) response = new { id = subject, is_anonymous = false, factors = Array.Empty<object>() };
            else if (path.EndsWith("/factors", StringComparison.Ordinal)) response = new { id = factor, type = "totp", totp = new { secret = "PUBLICSYNTHETICTOTPONLY", uri = "otpauth://totp/fixture?secret=PUBLICSYNTHETICTOTPONLY" } };
            else if (path.EndsWith("/challenge", StringComparison.Ordinal)) response = new { id = challenge, expires_at = DateTimeOffset.UtcNow.AddMinutes(1).ToUnixTimeSeconds() };
            else if (path.EndsWith("/logout", StringComparison.Ordinal)) return Task.FromResult(new HttpResponseMessage(HttpStatusCode.NoContent) { RequestMessage = request });
            else
            {
                var now = DateTimeOffset.UtcNow.ToUnixTimeSeconds(); var aal = path.EndsWith("/verify", StringComparison.Ordinal) ? 2 : 1;
                var payload = new Dictionary<string, object> { ["iss"] = Variant == "issuer" ? "https://other.invalid/auth/v1" : config.Issuer, ["aud"] = Variant == "audience" ? "anon" : "authenticated", ["sub"] = subject, ["session_id"] = session, ["iat"] = now, ["exp"] = now+300, ["nbf"] = Variant == "nbf" ? now+60 : now-1, ["aal"] = "aal"+aal, ["role"] = "authenticated", ["is_anonymous"] = Variant == "anonymous", ["amr"] = new[] { new { method = aal == 2 ? "mfa/totp" : "password", timestamp = now } } };
                if (Variant == "missing-session") payload.Remove("session_id");
                var token = new JsonWebTokenHandler { SetDefaultTimesOnTokenCreation = false }.CreateToken(JsonSerializer.Serialize(payload), new SigningCredentials(new ECDsaSecurityKey(key) { KeyId = "pilot-key" }, "ES256"));
                response = new { token_type = "bearer", access_token = token, refresh_token = "PUBLIC_FIXTURE_DISCARDED" };
            }
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { RequestMessage = request, Content = JsonContent.Create(response) });
        }
        protected override void Dispose(bool disposing) { if (disposing) key.Dispose(); base.Dispose(disposing); }
    }
}
