using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.Extensions.DependencyInjection;
using TradingAgent.Identity.Persistence;
using TradingAgent.Identity.Supabase;
using TradingAgent.Identity.Tests;
using TradingAgent.Web.Auth;
using Xunit;

namespace TradingAgent.Auth.Pilot.Tests;

[Collection("PostgreSQL")]
public sealed class HostedCompositionTests(DatabaseFixture fixture)
{
    [Fact]
    public async Task BuildingExplicitHostedCompositionDoesNotConnectOrStartAListener()
    {
        using var key = ECDsa.Create(ECCurve.NamedCurves.nistP256);
        var request = new CertificateRequest("CN=127.0.0.1", key, HashAlgorithmName.SHA256);
        using var certificate = request.CreateSelfSigned(DateTimeOffset.UtcNow.AddMinutes(-1), DateTimeOffset.UtcNow.AddMinutes(5));
        var settings = HostedPilotSettings.FromExternalValues("Development", "abcdefghijklmnopqrst", new Uri("https://abcdefghijklmnopqrst.supabase.co"), "sb_publishable_publicfixture", new Uri("https://127.0.0.1:24443"));
        using var observer = new ConnectionObserver();
        await using var app = IntegratedHostFactory.CreateHostedDevelopmentPilot(settings, fixture.Database(DatabasePurpose.Runtime), fixture.Database(DatabasePurpose.SessionIssuer), certificate);
        Assert.Equal("Development", app.Environment.EnvironmentName);
        Assert.False(app.Services.GetRequiredService<AuthConfiguration>().Simulation);
        Assert.Contains("Kestrel", app.Services.GetRequiredService<IServer>().GetType().FullName!, StringComparison.Ordinal);
        Assert.Empty(observer.Addresses);
        // Do not StartAsync: hosted pilot remains pending exact human project confirmation.
    }
}
