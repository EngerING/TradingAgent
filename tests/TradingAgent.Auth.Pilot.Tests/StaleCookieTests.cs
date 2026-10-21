using Microsoft.Extensions.DependencyInjection;
using TradingAgent.Auth.Tests;
using TradingAgent.Identity.Persistence;
using TradingAgent.Identity.Tests;
using TradingAgent.Web.Auth;
using Xunit;

namespace TradingAgent.Auth.Pilot.Tests;

[Collection("PostgreSQL")]
public sealed class StaleCookieTests(DatabaseFixture fixture)
{
    [Theory]
    [InlineData("restart")]
    [InlineData("expired")]
    [InlineData("revoked")]
    [InlineData("unknown")]
    public async Task StaleCookieAllowsFreshPasswordAndMfaWithoutReusingReference(string reason)
    {
        await using var h = new BrowserHarness(); await h.StartAsync(fixture); await h.SignInAsync();
        var old = h.Browser.Cookies["__Host-TradingAgent.Session"];
        if (reason == "restart") h.App.Services.GetRequiredService<TemporarySessions>().Clear();
        if (reason == "expired") h.Provider.Clock.Advance(TimeSpan.FromMinutes(6));
        if (reason == "revoked") await fixture.Sessions.RevokeAsync(SessionReference.Parse(old), CancellationToken.None);
        if (reason == "unknown") h.Browser.Cookies["__Host-TradingAgent.Session"] = SessionReference.Generate().ExportForCookie();
        var rejected = h.Browser.Cookies["__Host-TradingAgent.Session"];
        if (reason == "expired")
        {
            // Provider clock advances independently of PostgreSQL's real clock. Verify recovery to AAL1,
            // without claiming that SQL accepts a simulated MFA timestamp six minutes in the future.
            using var login = await h.Browser.PostAsync("/bff/auth/login", new { email = h.Email, password = "fixture-password" });
            Assert.Equal(200, (int)login.StatusCode); Assert.False(h.Browser.Cookies.ContainsKey("__Host-TradingAgent.Session"));
            Assert.True(h.Browser.Cookies.ContainsKey("__Host-TradingAgent.PreAuth"));
        }
        else { await h.SignInAsync(); Assert.NotEqual(old, h.Browser.Cookies["__Host-TradingAgent.Session"]); }
        using var client = h.NewBrowser(); client.Cookies["__Host-TradingAgent.Session"] = rejected;
        using var denied = await client.GetAsync("/bff/session"); Assert.Equal(401, (int)denied.StatusCode);
    }
    [Fact]
    public async Task LiveCookiePreventsAccidentalSecondLogin()
    {
        await using var h = new BrowserHarness(); await h.StartAsync(fixture); await h.SignInAsync();
        var old = h.Browser.Cookies["__Host-TradingAgent.Session"]; var requests = h.Provider.PasswordRequests;
        using var login = await h.Browser.PostAsync("/bff/auth/login", new { email = h.Email, password = "fixture-password" });
        Assert.Equal(409, (int)login.StatusCode); Assert.Equal(requests, h.Provider.PasswordRequests);
        Assert.Equal(old, h.Browser.Cookies["__Host-TradingAgent.Session"]);
    }
    [Fact]
    public async Task ProviderOutagePreservesCookieAndReturns503OnRelogin()
    {
        await using var h = new BrowserHarness(); await h.StartAsync(fixture); await h.SignInAsync();
        var old = h.Browser.Cookies["__Host-TradingAgent.Session"]; h.Provider.Unavailable = true;
        using var login = await h.Browser.PostAsync("/bff/auth/login", new { email = h.Email, password = "fixture-password" });
        Assert.Equal(503, (int)login.StatusCode); Assert.Equal(old, h.Browser.Cookies["__Host-TradingAgent.Session"]);
    }
    [Fact]
    public async Task RecoveryStillRequiresCsrf()
    {
        await using var h = new BrowserHarness(); await h.StartAsync(fixture); await h.SignInAsync();
        h.App.Services.GetRequiredService<TemporarySessions>().Clear(); var count = h.Provider.PasswordRequests;
        using var login = await h.Browser.PostAsync("/bff/auth/login", new { email = h.Email, password = "fixture-password" }, csrf: false);
        Assert.Equal(403, (int)login.StatusCode); Assert.Equal(count, h.Provider.PasswordRequests);
    }
    [Fact]
    public async Task SqlUnavailablePreservesCookieAndDoesNotAttemptPassword()
    {
        await using var h = new BrowserHarness(); await h.StartAsync(fixture); await h.SignInAsync();
        var old = h.Browser.Cookies["__Host-TradingAgent.Session"]; var count = h.Provider.PasswordRequests;
        await using var runtime = await fixture.Database(DatabasePurpose.Runtime).OpenAsync(CancellationToken.None);
        await using var query = new Npgsql.NpgsqlCommand("SELECT session_user", runtime); var login = (string)(await query.ExecuteScalarAsync())!;
        try
        {
            await using var owner = await fixture.OpenOwnerAsync(); await DatabaseFixture.ExecuteAsync(owner, $"ALTER ROLE {login} NOLOGIN");
            using var response = await h.Browser.PostAsync("/bff/auth/login", new { email = h.Email, password = "fixture-password" });
            Assert.Equal(503, (int)response.StatusCode); Assert.Equal(old, h.Browser.Cookies["__Host-TradingAgent.Session"]); Assert.Equal(count, h.Provider.PasswordRequests);
        }
        finally { await using var owner = await fixture.OpenOwnerAsync(); await DatabaseFixture.ExecuteAsync(owner, $"ALTER ROLE {login} LOGIN"); }
    }
}
