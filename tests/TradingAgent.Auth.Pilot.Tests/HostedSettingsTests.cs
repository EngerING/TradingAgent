using TradingAgent.Identity.Supabase;
using TradingAgent.Web.Auth;
using Xunit;

namespace TradingAgent.Auth.Pilot.Tests;

public sealed class HostedSettingsTests
{
    private const string Reference = "abcdefghijklmnopqrst";
    [Theory]
    [InlineData("Production", "https://127.0.0.1:24443")]
    [InlineData("Staging", "https://127.0.0.1:24443")]
    [InlineData("Development", "http://127.0.0.1:24443")]
    [InlineData("Development", "https://0.0.0.0:24443")]
    [InlineData("Development", "https://attacker.invalid:24443")]
    [InlineData("Development", "https://127.0.0.1:24443/path")]
    [InlineData("Development", "https://127.0.0.1:24443/?secret=x")]
    public void InvalidEnvironmentOrOriginCannotComposeHostedPilot(string environment, string origin)
    {
        Assert.Throws<ArgumentException>(() => HostedPilotSettings.FromExternalValues(environment, Reference,
            new Uri($"https://{Reference}.supabase.co"), "sb_publishable_publicfixture", new Uri(origin)));
    }
    [Fact]
    public void ConfirmationMustMatchExactProjectAndCannotBeSynthetic()
    {
        Assert.Throws<ArgumentException>(() => HostedPilotSettings.FromExternalValues("Development", Reference,
            new Uri("https://otherproject.supabase.co"), "sb_publishable_publicfixture", new Uri("https://127.0.0.1:24443")));
    }
    [Theory]
    [InlineData("service_role")]
    [InlineData("sb_secret_not_allowed")]
    public void AdministrativeKeysCannotConfigureRuntime(string key)
    {
        Assert.Throws<ArgumentException>(() => HostedPilotSettings.FromExternalValues("Development", Reference,
            new Uri($"https://{Reference}.supabase.co"), key, new Uri("https://127.0.0.1:24443")));
    }
    [Fact]
    public void ExternalValuesDeriveClosedIssuerAudienceAndJwks()
    {
        var settings = HostedPilotSettings.FromExternalValues("Development", Reference,
            new Uri($"https://{Reference}.supabase.co"), "sb_publishable_publicfixture", new Uri("https://127.0.0.1:24443"));
        Assert.False(settings.Authentication.Simulation);
        Assert.Equal($"https://{Reference}.supabase.co/auth/v1", settings.Authentication.Issuer);
        Assert.Equal($"https://{Reference}.supabase.co/auth/v1/.well-known/jwks.json", settings.Authentication.Jwks.AbsoluteUri);
        Assert.DoesNotContain("sb_publishable", settings.ToString(), StringComparison.Ordinal);
    }
}
