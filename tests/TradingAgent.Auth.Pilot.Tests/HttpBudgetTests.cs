using System.Net.Http.Json;
using TradingAgent.Auth.Tests;
using TradingAgent.Identity.Tests;
using Xunit;

namespace TradingAgent.Auth.Pilot.Tests;

[Collection("PostgreSQL")]
public sealed class HttpBudgetTests(DatabaseFixture fixture)
{
    [Theory]
    [InlineData("post")]
    [InlineData("pOsT")]
    public async Task MethodCasingCannotBypassCsrf(string method)
    {
        await using var h = new BrowserHarness(); await h.StartAsync(fixture);
        using var request = new HttpRequestMessage(new HttpMethod(method), "/bff/auth/login") { Content = JsonContent.Create(new { email = h.Email, password = "fixture-password" }) };
        request.Headers.Add("Origin", "https://tradingagent.test");
        using var response = await h.Browser.SendAsync(request);
        Assert.True(response.StatusCode is System.Net.HttpStatusCode.Forbidden or System.Net.HttpStatusCode.MethodNotAllowed);
        Assert.Equal(0, h.Provider.PasswordRequests);
    }
    [Fact]
    public async Task ClientForwardedHeaderCannotResetLoginQuota()
    {
        await using var h = new BrowserHarness(); await h.StartAsync(fixture);
        for (var i = 0; i < 21; i++)
        {
            var csrf = await h.Browser.CsrfAsync();
            using var request = new HttpRequestMessage(HttpMethod.Post, "/bff/auth/login") { Content = JsonContent.Create(new { email = h.Email, password = "wrong" }) };
            request.Headers.Add("X-Forwarded-For", $"192.0.2.{i+1}"); request.Headers.Add("Forwarded", $"for=192.0.2.{i+1}");
            request.Headers.Add("Origin", "https://tradingagent.test"); request.Headers.Add("X-CSRF-TOKEN", csrf);
            using var response = await h.Browser.SendAsync(request); Assert.Equal(i < 20 ? 401 : 429, (int)response.StatusCode);
        }
        Assert.Equal(20, h.Provider.PasswordRequests);
    }
    [Fact]
    public async Task LoginExhaustionStillAllowsAuthenticatedLogout()
    {
        await using var h = new BrowserHarness(); await h.StartAsync(fixture); await h.SignInAsync();
        for (var i = 0; i < 20; i++)
        {
            using var response = await h.Browser.PostAsync("/bff/auth/login", new { email = h.Email, password = "fixture-password" });
            Assert.Equal(i < 19 ? 409 : 429, (int)response.StatusCode);
        }
        using var logout = await h.Browser.PostAsync("/bff/auth/logout", new { }); Assert.Equal(204, (int)logout.StatusCode);
        using var denied = await h.Browser.GetAsync("/bff/session"); Assert.Equal(401, (int)denied.StatusCode);
    }
    [Theory]
    [InlineData("/bff/auth/logout/")]
    [InlineData("/BFF/AUTH/LOGOUT")]
    public async Task RoutingAliasesCannotEscapeLogoutBudget(string alias)
    {
        await using var h = new BrowserHarness(); await h.StartAsync(fixture);
        for (var i = 0; i < 20; i++) { using var response = await h.Browser.PostAsync("/bff/auth/logout", new { }); Assert.Equal(204, (int)response.StatusCode); }
        using var denied = await h.Browser.PostAsync(alias, new { }); Assert.Equal(429, (int)denied.StatusCode);
        using var login = await h.Browser.PostAsync("/bff/auth/login/", new { email = h.Email, password = "fixture-password" }); Assert.Equal(200, (int)login.StatusCode);
    }
}
