using System.Net;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using TradingAgent.React.BrowserFixture;
using TradingAgent.Auth.Tests;
using Microsoft.IdentityModel.JsonWebTokens;
using System.Text.Json;
using Xunit;
using Microsoft.Extensions.Logging;
using TradingAgent.Identity.Supabase;
using TradingAgent.Identity.Persistence;
using TradingAgent.Web.Auth;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.DependencyInjection;

namespace TradingAgent.React.Integration.Tests;

public sealed class LocalPilotSafetyTests
{
    [Fact]
    public async Task HostedEnrollmentEndpointDeniesBeforePreauthOrProviderAccess()
    {
        using var material = LocalPilotPreparation.Certificate();
        var target = new DisposableTarget("127.0.0.1", 24444, "m012_test_" + Guid.NewGuid().ToString("N"));
        var runtime = new SecurityDatabase(target, "public_fixture", "public_fixture", DatabasePurpose.Runtime);
        var issuer = new SecurityDatabase(target, "public_fixture", "public_fixture", DatabasePurpose.SessionIssuer);
        var settings = HostedPilotSettings.FromExternalValues("Development", "ocwabwmzhpedyxlkjpje", new Uri("https://ocwabwmzhpedyxlkjpje.supabase.co/"), "sb_publishable_publicfixture", new Uri("https://127.0.0.1:24443/"));
        await using var app = IntegratedHostFactory.CreateHostedBrowserPilot(settings, runtime, issuer, material.Leaf);
        var endpoint = ((IEndpointRouteBuilder)app).DataSources.SelectMany(s => s.Endpoints).OfType<RouteEndpoint>().Single(e => e.RoutePattern.RawText == "/bff/auth/mfa/enroll");
        var context = new DefaultHttpContext { RequestServices = app.Services };
        // Invoke only the endpoint: no listener, TLS trust, SQL or hosted request starts.
        var error = await Assert.ThrowsAsync<AuthException>(() => endpoint.RequestDelegate!(context));
        Assert.Equal(AuthFailure.Conflict, error.Failure);
        // Opt-in is not automatically enabled, and does not bypass preauth.
        await using var enabled = IntegratedHostFactory.CreateHostedBrowserPilot(settings, runtime, issuer, material.Leaf, allowHostedEnrollment: true);
        var enabledEndpoint = ((IEndpointRouteBuilder)enabled).DataSources.SelectMany(s => s.Endpoints)
            .OfType<RouteEndpoint>().Single(e => e.RoutePattern.RawText == "/bff/auth/mfa/enroll");
        var noPreauth = new DefaultHttpContext { RequestServices = enabled.Services };
        var missingIdentity = await Assert.ThrowsAsync<AuthException>(() => enabledEndpoint.RequestDelegate!(noPreauth));
        Assert.Equal(AuthFailure.Invalid, missingIdentity.Failure);
        Assert.Throws<InvalidOperationException>(() => IntegratedHostFactory.CreateHostedBrowserPilot(settings, runtime, issuer, material.Leaf, localChecksOnly: true, allowHostedEnrollment: true));
        var regularPaths = ((IEndpointRouteBuilder)app).DataSources.SelectMany(s => s.Endpoints).OfType<RouteEndpoint>()
            .Select(e => e.RoutePattern.RawText).ToArray();
        Assert.DoesNotContain("/bff/preview/login", regularPaths);
        await using var preview = IntegratedHostFactory.CreateHostedBrowserPilot(settings, runtime, issuer, material.Leaf, passwordPreviewEmail: "fixture@fixture.invalid");
        var previewPaths = ((IEndpointRouteBuilder)preview).DataSources.SelectMany(s => s.Endpoints).OfType<RouteEndpoint>()
            .Select(e => e.RoutePattern.RawText).ToArray();
        Assert.Contains("/bff/preview/login", previewPaths);
        Assert.Contains("/bff/preview/session", previewPaths);
        Assert.DoesNotContain("/orders", previewPaths);
        Assert.Throws<InvalidOperationException>(() => IntegratedHostFactory.CreateHostedBrowserPilot(settings, runtime, issuer, material.Leaf, localChecksOnly: true, passwordPreviewEmail: "fixture@fixture.invalid"));
    }
    private sealed class RotatingRefreshHandler(SimulatedAuth sim, Guid user) : DelegatingHandler
    {
        internal int Rotations { get; private set; }
        internal bool ChangeSubject { get; set; }
        private Guid session;
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            if (request.RequestUri?.AbsolutePath == "/auth/v1/user" && request.Headers.Authorization is { } bearer)
            {
                var jwt = new JsonWebTokenHandler().ReadJsonWebToken(bearer.Parameter!);
                session = Guid.Parse(jwt.GetClaim("session_id").Value);
            }
            if (request.Method == HttpMethod.Post && request.RequestUri?.AbsolutePath == "/auth/v1/token" &&
                request.RequestUri.Query == "?grant_type=refresh_token")
            {
                using var requestBody = JsonDocument.Parse(await request.Content!.ReadAsStringAsync(ct));
                Assert.Equal("PUBLIC_FIXTURE_REFRESH_DISCARD", requestBody.RootElement.GetProperty("refresh_token").GetString());
                Rotations++;
                var token = sim.Token(ChangeSubject ? Guid.NewGuid() : user, session, 1);
                return new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent(JsonSerializer.Serialize(new
                    {
                        token_type = "bearer", access_token = token,
                        refresh_token = "PUBLIC_ROTATED_TOKEN_NUMBER_" + Rotations
                    }), System.Text.Encoding.UTF8, "application/json"),
                    RequestMessage = request
                };
            }
            return await base.SendAsync(request, ct);
        }
    }

    [Fact]
    public async Task PasswordPreviewRefreshRotatesOnceAndRejectsForeignSubject()
    {
        await using var sim = new SimulatedAuth();
        await sim.StartAsync();
        var subject = Guid.NewGuid();
        const string email = "preview@fixture.invalid";
        sim.Users[email] = subject;
        var handler = new RotatingRefreshHandler(sim, subject);
        var services = new ServiceCollection();
        sim.Configure(services);
        services.AddHttpClient<AuthTransport>().AddHttpMessageHandler(() => handler);
        await using var container = services.BuildServiceProvider();
        var preview = new PasswordPreviewSessions(
            container.GetRequiredService<SupabaseAuthClient>(),
            container.GetRequiredService<JwtVerifier>(), sim.Clock, email);

        var login = await preview.LoginAsync(email, "fixture-password", CancellationToken.None);
        Assert.InRange(login.Expires - sim.Clock.GetUtcNow(), TimeSpan.FromHours(8) - TimeSpan.FromSeconds(5), TimeSpan.FromHours(8));
        Assert.InRange(login.IdleExpires - sim.Clock.GetUtcNow(), TimeSpan.FromMinutes(30) - TimeSpan.FromSeconds(5), TimeSpan.FromMinutes(30));
        sim.Clock.Advance(TimeSpan.FromMinutes(4));
        var first = await preview.SessionAsync(login.Reference, CancellationToken.None);
        Assert.Contains("\"renewable\":true", JsonSerializer.Serialize(first));
        Assert.Equal(1, handler.Rotations);
        await preview.SessionAsync(login.Reference, CancellationToken.None);
        Assert.Equal(1, handler.Rotations); // Polling neither rotates again nor renews idle deadline.
        sim.Clock.Advance(TimeSpan.FromMinutes(27));
        await Assert.ThrowsAsync<AuthException>(() => preview.SessionAsync(login.Reference, CancellationToken.None));

        // A successful rotated JWT for an unrelated identity must invalidate the local session.
        var second = await preview.LoginAsync(email, "fixture-password", CancellationToken.None);
        handler.ChangeSubject = true;
        sim.Clock.Advance(TimeSpan.FromMinutes(4));
        await Assert.ThrowsAsync<AuthException>(() => preview.SessionAsync(second.Reference, CancellationToken.None));
        await Assert.ThrowsAsync<AuthException>(() => preview.SessionAsync(second.Reference, CancellationToken.None));
        Assert.Equal(2, handler.Rotations);
    }

    [Fact]
    public void DiagnosticOnlyWritesClosedCodesAndNeverFormatsPayloadsOrExceptions()
    {
        var path = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N") + ".jsonl");
        try
        {
            using var log = new LocalPilotDiagnostic(path);
            var state = new Dictionary<string, object?> { ["DiagnosticCode"] = AuthDiagnostic.JwtIssuedAtFuture, ["password"] = "PUBLIC_SECRET_SENTINEL" };
            log.Log(LogLevel.Warning, new EventId(1302), state, new InvalidOperationException("PUBLIC_SECRET_SENTINEL"), (_, _) => throw new InvalidOperationException("Formatter must not run"));
            log.Log(LogLevel.Warning, new EventId(42), state, null, (_, _) => "PUBLIC_SECRET_SENTINEL");
            Assert.Equal("{\"diagnostic\":\"JwtIssuedAtFuture\"}\n", File.ReadAllText(path));
        }
        finally { if (File.Exists(path)) File.Delete(path); }
    }
    [Fact]
    public void GeneratedCertificateHasLoopbackSanServerAuthAndValidCustomChain()
    {
        using var material = LocalPilotPreparation.Certificate();
        LocalPilotPreparation.ValidateCertificate(material.Leaf, material.Root);
        var san = new X509SubjectAlternativeNameExtension();
        san.CopyFrom(material.Leaf.Extensions["2.5.29.17"]!);
        Assert.Contains(IPAddress.Loopback, san.EnumerateIPAddresses());
        Assert.True(material.Leaf.HasPrivateKey);
    }

    [Fact]
    public void WrongNameOrMissingServerAuthCannotPassPreflight()
    {
        using var key = RSA.Create(2048);
        var request = new CertificateRequest("CN=wrong.invalid", key, HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1);
        using var bad = request.CreateSelfSigned(DateTimeOffset.UtcNow.AddMinutes(-1), DateTimeOffset.UtcNow.AddMinutes(5));
        Assert.Throws<InvalidOperationException>(() => LocalPilotPreparation.ValidateCertificate(bad, bad));
    }

    [Fact]
    public void CredentialsDoNotContainApplicationOrAdministrativeAuthority()
    {
        var purposes = LocalPilotPreparation.LoginPurposes;
        Assert.Equal(3, purposes.Count);
        Assert.DoesNotContain(TradingAgent.Identity.Persistence.DatabasePurpose.Administration, purposes);
        Assert.DoesNotContain(TradingAgent.Identity.Persistence.DatabasePurpose.Reader, purposes);
    }
}
