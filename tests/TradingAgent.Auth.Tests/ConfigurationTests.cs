using TradingAgent.Identity.Supabase;
using Xunit;

namespace TradingAgent.Auth.Tests;

public sealed class ConfigurationTests
{
    [Theory]
    [InlineData("http://project.supabase.co")]
    [InlineData("https://attacker.invalid")]
    [InlineData("https://project.supabase.co@attacker.invalid")]
    [InlineData("https://project.supabase.co/path")]
    public void UntrustedProductionOriginsAreRejected(string origin) => Assert.Throws<ArgumentException>(() => AuthConfiguration.ForProject(new Uri(origin), "sb_publishable_publicfixture"));
    [Fact]
    public void JwksAndIssuerComeOnlyFromTrustedConfiguration()
    {
        var config = AuthConfiguration.ForProject(new Uri("https://fixture.supabase.co"), "sb_publishable_publicfixture");
        Assert.Equal("https://fixture.supabase.co/auth/v1", config.Issuer);
        Assert.Equal("https://fixture.supabase.co/auth/v1/.well-known/jwks.json", config.Jwks.AbsoluteUri);
    }
}
