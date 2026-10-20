using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using TradingAgent.Identity.Persistence;
using TradingAgent.Identity.Tests;
using TradingAgent.Web.Auth;
using Xunit;

namespace TradingAgent.Auth.Tests;

[Collection("PostgreSQL")]
public sealed class BffTests(DatabaseFixture fixture)
{
    [Fact]
    public async Task CompletePasswordMfaSqlSessionAndExactGrantFlowIsSyntheticOnly()
    {
        await using var harness = new BrowserHarness(); await harness.StartAsync(fixture);
        using (var absent = await harness.Browser.GetAsync("/bff/session")) Assert.Equal(401, (int)absent.StatusCode);
        var preliminary = await harness.PreliminaryAsync();
        using (var aalOne = await harness.Browser.GetAsync($"/bff/probe/{harness.Resource}/Paper")) Assert.Equal(401, (int)aalOne.StatusCode);
        using var verify = await harness.Browser.PostAsync("/bff/auth/mfa/verify", new { challengeId = preliminary.Challenge, code = "123456" });
        Assert.Equal(200, (int)verify.StatusCode);
        var cookie = Assert.Single(verify.Headers.GetValues("Set-Cookie"), c => c.StartsWith("__Host-TradingAgent.Session=", StringComparison.Ordinal));
        Assert.Contains("secure", cookie, StringComparison.OrdinalIgnoreCase); Assert.Contains("httponly", cookie, StringComparison.OrdinalIgnoreCase); Assert.Contains("samesite=strict", cookie, StringComparison.OrdinalIgnoreCase); Assert.Contains("path=/", cookie, StringComparison.OrdinalIgnoreCase); Assert.DoesNotContain("domain=", cookie, StringComparison.OrdinalIgnoreCase);
        Assert.Equal(43, harness.Browser.Cookies["__Host-TradingAgent.Session"].Length);
        Assert.DoesNotContain("eyJ", await verify.Content.ReadAsStringAsync(), StringComparison.Ordinal);
        using var probe = await harness.Browser.GetAsync($"/bff/probe/{harness.Resource}/Paper"); Assert.Equal(200, (int)probe.StatusCode);
        using var body = JsonDocument.Parse(await probe.Content.ReadAsStringAsync()); Assert.True(body.RootElement.GetProperty("synthetic").GetBoolean()); Assert.False(body.RootElement.GetProperty("executionAuthorized").GetBoolean());
        Assert.Equal("no-store", probe.Headers.CacheControl?.ToString());
        Assert.Equal(0L, await fixture.ScalarAsync("SELECT count(*) FROM app_security.web_sessions WHERE encrypted_access_token IS NOT NULL OR encrypted_refresh_token IS NOT NULL"));
        using var session = await harness.Browser.GetAsync("/bff/session"); Assert.Equal(200, (int)session.StatusCode);
        Assert.Contains("\"renewable\":false", await session.Content.ReadAsStringAsync(), StringComparison.Ordinal);
    }
    [Theory]
    [InlineData(false, true, PlatformRole.Viewer)] [InlineData(true, false, PlatformRole.Viewer)] [InlineData(true, false, PlatformRole.Administrator)]
    public async Task RoleAndGrantAreBothRequiredAndAdministratorIsNotUniversal(bool role, bool grant, PlatformRole platformRole)
    {
        await using var harness = new BrowserHarness(); await harness.StartAsync(fixture, role, grant, platformRole); await harness.SignInAsync();
        using var response = await harness.Browser.GetAsync($"/bff/probe/{harness.Resource}/Paper"); Assert.Equal(403, (int)response.StatusCode);
    }
    [Fact]
    public async Task AliceCannotReadAnotherResourceOrLiveUsingPaperGrant()
    {
        await using var harness = new BrowserHarness(); await harness.StartAsync(fixture); await harness.SignInAsync();
        foreach (var path in new[] { $"/bff/probe/{Guid.NewGuid()}/Paper", $"/bff/probe/{harness.Resource}/Live" })
        { using var response = await harness.Browser.GetAsync(path); Assert.Equal(403, (int)response.StatusCode); }
    }
    [Theory]
    [InlineData(false, "https://tradingagent.test", "same-origin")]
    [InlineData(true, "https://attacker.invalid", "same-origin")]
    [InlineData(true, "https://tradingagent.test", "cross-site")]
    public async Task CsrfOriginAndFetchMetadataApplyToLogin(bool csrf, string origin, string site)
    {
        await using var harness = new BrowserHarness(); await harness.StartAsync(fixture);
        using var response = await harness.Browser.PostAsync("/bff/auth/login", new { email = harness.Email, password = "fixture-password" }, csrf, origin, site);
        Assert.Equal(403, (int)response.StatusCode); Assert.Equal(0, harness.Provider.PasswordRequests);
    }
    [Fact]
    public async Task CookieTamperingRevocationDisableAndRestartFailClosed()
    {
        await using var harness = new BrowserHarness(); await harness.StartAsync(fixture); await harness.SignInAsync();
        var cookie = harness.Browser.Cookies["__Host-TradingAgent.Session"];
        harness.Browser.Cookies["__Host-TradingAgent.Session"] = SessionReference.Generate().ExportForCookie();
        using (var tampered = await harness.Browser.GetAsync("/bff/session")) Assert.Equal(401, (int)tampered.StatusCode);
        harness.Browser.Cookies["__Host-TradingAgent.Session"] = cookie;
        Assert.Equal(StoreOutcome.Success, (await fixture.Sessions.RevokeAsync(SessionReference.Parse(cookie), CancellationToken.None)).Outcome);
        using (var revoked = await harness.Browser.GetAsync("/bff/session")) Assert.Equal(401, (int)revoked.StatusCode);
        harness.Browser.Cookies.Remove("__Host-TradingAgent.Session"); await harness.SignInAsync();
        harness.App.Services.GetRequiredService<TemporarySessions>().Clear();
        using (var restarted = await harness.Browser.GetAsync("/bff/session")) Assert.Equal(401, (int)restarted.StatusCode);
        harness.Browser.Cookies.Remove("__Host-TradingAgent.Session"); await harness.SignInAsync();
        await fixture.Administration().ChangeStatusAsync(harness.Admin, harness.User, UserStatus.Disabled, CancellationToken.None);
        using var disabled = await harness.Browser.GetAsync("/bff/session"); Assert.Equal(401, (int)disabled.StatusCode);
    }
    [Fact]
    public async Task LogoutRevokesSqlEvenWhenProviderIsUnavailable()
    {
        await using var harness = new BrowserHarness(); await harness.StartAsync(fixture); await harness.SignInAsync();
        var reference = SessionReference.Parse(harness.Browser.Cookies["__Host-TradingAgent.Session"]);
        var csrf = await harness.Browser.CsrfAsync(); harness.Provider.Unavailable = true;
        using var request = new HttpRequestMessage(HttpMethod.Post, "/bff/auth/logout"); request.Headers.Add("Origin", "https://tradingagent.test"); request.Headers.Add("X-CSRF-TOKEN", csrf);
        using var response = await harness.Browser.SendAsync(request); Assert.Equal(204, (int)response.StatusCode);
        Assert.Null(await fixture.Sessions.FindSelfAsync(reference, CancellationToken.None)); Assert.False(harness.Browser.Cookies.ContainsKey("__Host-TradingAgent.Session"));
    }
}
