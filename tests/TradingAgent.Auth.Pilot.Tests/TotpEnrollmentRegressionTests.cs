using System.Net;
using System.Text;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using TradingAgent.Identity.Persistence;
using TradingAgent.Identity.Supabase;
using Xunit;

namespace TradingAgent.Auth.Pilot.Tests;

public sealed class TotpEnrollmentRegressionTests
{
    [Theory]
    [InlineData(true)] [InlineData(false)]
    public async Task ValidEnrollmentWithLargeIgnoredSvgIsAcceptedWithinSpecificBudget(bool declaredLength)
    {
        using var wire = new EnrollmentWire(EnrollmentBody(96 * 1024), declaredLength);
        using var services = wire.Services();
        var result = await services.GetRequiredService<SupabaseAuthClient>().EnrollAsync(wire.Credential, CancellationToken.None);
        Assert.Equal(EnrollmentWire.FactorId, result.FactorId);
        Assert.DoesNotContain("<svg", result.ToString(), StringComparison.Ordinal);
        Assert.DoesNotContain("JBSWY", result.ToString(), StringComparison.Ordinal);
        Assert.Equal(1, wire.Requests);
    }

    [Theory]
    [InlineData(true)] [InlineData(false)]
    public async Task EnrollmentAboveSpecificBudgetRemainsRejected(bool declaredLength)
    {
        using var wire = new EnrollmentWire(EnrollmentBody(256 * 1024), declaredLength);
        using var services = wire.Services();
        var error = await Assert.ThrowsAsync<AuthException>(() => services.GetRequiredService<SupabaseAuthClient>().EnrollAsync(wire.Credential, CancellationToken.None));
        Assert.Equal(AuthFailure.Unavailable, error.Failure); Assert.Equal(1, wire.Requests);
        Assert.Equal(AuthDiagnostic.ResponseTooLarge, error.Diagnostic);
    }

    [Theory]
    [InlineData("GET", "/auth/v1/user")]
    [InlineData("POST", "/auth/v1/token?grant_type=password")]
    [InlineData("POST", "/auth/v1/factors/00000000-0000-0000-0000-000000000001/verify")]
    [InlineData("GET", "/auth/v1/factors")]
    public async Task OtherResponsesKeep64KiBBudget(string method, string path)
    {
        using var wire = new EnrollmentWire(EnrollmentBody(96 * 1024), false);
        using var services = wire.Services();
        var error = await Assert.ThrowsAsync<AuthException>(() => services.GetRequiredService<AuthTransport>().SendAsync(new HttpMethod(method), path, null, null, CancellationToken.None));
        Assert.Equal(AuthFailure.Unavailable, error.Failure);
        Assert.Equal(AuthDiagnostic.ResponseTooLarge, error.Diagnostic);
    }

    [Theory]
    [InlineData("missing-uri")] [InlineData("null-secret")] [InlineData("wrong-type")]
    [InlineData("duplicate")] [InlineData("invalid-uri")] [InlineData("empty-id")]
    public async Task MalformedEnrollmentRemainsDeniedWithoutSensitiveErrors(string variant)
    {
        var body = EnrollmentBody(16);
        body = variant switch
        {
            "missing-uri" => body.Replace("\"uri\"", "\"unrecognized\"", StringComparison.Ordinal),
            "null-secret" => body.Replace("\"JBSWY3DPEHPK3PXP\"", "null", StringComparison.Ordinal),
            "wrong-type" => body.Replace("\"type\":\"totp\"", "\"type\":\"phone\"", StringComparison.Ordinal),
            "duplicate" => body.Replace("\"type\":\"totp\"", "\"type\":\"totp\",\"type\":\"totp\"", StringComparison.Ordinal),
            "invalid-uri" => body.Replace("otpauth://totp/", "https://fixture.invalid/", StringComparison.Ordinal),
            "empty-id" => body.Replace(EnrollmentWire.FactorId.ToString(), Guid.Empty.ToString(), StringComparison.Ordinal),
            _ => throw new InvalidOperationException()
        };
        using var wire = new EnrollmentWire(body, false); using var services = wire.Services();
        var error = await Assert.ThrowsAsync<AuthException>(() => services.GetRequiredService<SupabaseAuthClient>().EnrollAsync(wire.Credential, CancellationToken.None));
        Assert.Equal(AuthFailure.Unavailable, error.Failure);
        Assert.Equal(variant == "duplicate" ? AuthDiagnostic.InvalidJson : AuthDiagnostic.EnrollmentContractInvalid, error.Diagnostic);
        Assert.Equal("AUTH_REQUEST_REJECTED", error.Message);
        Assert.DoesNotContain("JBSWY", error.ToString(), StringComparison.Ordinal);
    }

    private static string EnrollmentBody(int svgPadding) => JsonSerializer.Serialize(new
    {
        id = EnrollmentWire.FactorId, type = "totp", friendly_name = "Fixture",
        totp = new { secret = "JBSWY3DPEHPK3PXP", uri = "otpauth://totp/Fixture?secret=JBSWY3DPEHPK3PXP&issuer=Fixture", qr_code = "<svg>" + new string('x', svgPadding) + "</svg>" }
    });

    [Theory]
    [InlineData("pending")] [InlineData("missing-status")] [InlineData("duplicate-id")] [InlineData("empty-id")]
    public async Task RecoveryDiscoveryCannotTreatUnknownOrAmbiguousFactorAsUnverified(string variant)
    {
        using var wire = new EnrollmentWire("{}", true);
        var factor = new { id = variant == "empty-id" ? Guid.Empty : EnrollmentWire.FactorId, factor_type = "totp", status = variant == "pending" ? "pending" : "unverified" };
        wire.Body = JsonSerializer.Serialize(new { id = wire.Credential.Identity.Identity.Subject, is_anonymous = false, factors = variant == "duplicate-id" ? new[] { factor, factor } : new[] { factor } });
        if (variant == "missing-status") wire.Body = wire.Body.Replace("\"status\"", "\"unknown\"", StringComparison.Ordinal);
        using var services = wire.Services();
        var error = await Assert.ThrowsAsync<AuthException>(() => services.GetRequiredService<SupabaseAuthClient>().CheckUserAsync(wire.Credential, CancellationToken.None));
        Assert.Equal(AuthFailure.Unavailable, error.Failure);
    }

    private sealed class EnrollmentWire(string body, bool declaredLength) : HttpMessageHandler
    {
        internal static Guid FactorId { get; } = Guid.NewGuid();
        internal int Requests { get; private set; }
        internal string Body { get; set; } = body;
        internal AccessCredential Credential { get; } = new("PUBLIC_FIXTURE_NOT_A_JWT", new(new IdentityKey("https://abcdefghijklmnopqrst.supabase.co/auth/v1", Guid.NewGuid()), Guid.NewGuid(), 1, DateTimeOffset.UtcNow.AddSeconds(-1), DateTimeOffset.UtcNow.AddMinutes(5), null));
        internal ServiceProvider Services()
        {
            var services = new ServiceCollection(); services.AddSupabaseAuth(AuthConfiguration.ForProject(new Uri("https://abcdefghijklmnopqrst.supabase.co"), "sb_publishable_publicfixture")).ConfigurePrimaryHttpMessageHandler(() => this);
            return services.BuildServiceProvider();
        }
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            Requests++;
            HttpContent content = declaredLength ? new StringContent(Body, Encoding.UTF8, "application/json") : new UnknownLengthContent(Body);
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { RequestMessage = request, Content = content });
        }
    }
    private sealed class UnknownLengthContent : HttpContent
    {
        private readonly byte[] bytes;
        internal UnknownLengthContent(string body) { bytes = Encoding.UTF8.GetBytes(body); Headers.ContentType = new("application/json"); }
        protected override bool TryComputeLength(out long length) { length = 0; return false; }
        protected override Task SerializeToStreamAsync(Stream stream, TransportContext? context) => stream.WriteAsync(bytes).AsTask();
        protected override Task<Stream> CreateContentReadStreamAsync() => Task.FromResult<Stream>(new MemoryStream(bytes, false));
    }
}
