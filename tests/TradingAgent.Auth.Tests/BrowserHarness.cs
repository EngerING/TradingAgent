using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.Logging;
using TradingAgent.Identity.Persistence;
using TradingAgent.Identity.Tests;
using TradingAgent.Web.Auth;
using Xunit;

namespace TradingAgent.Auth.Tests;

public sealed class BrowserHarness : IAsyncDisposable
{
    public SimulatedAuth Provider { get; } = new();
    public CollectedLogs Logs { get; } = new();
    public WebApplication App { get; private set; } = null!;
    public Browser Browser { get; private set; } = null!;
    public string Email { get; } = Guid.NewGuid().ToString("N") + "@fixture.invalid";
    public Guid User { get; private set; }
    public Guid Subject { get; } = Guid.NewGuid();
    public Guid Resource { get; } = Guid.NewGuid();
    public SessionReference Admin { get; private set; } = null!;
    public async Task StartAsync(DatabaseFixture fixture, bool role = true, bool grant = true, PlatformRole platformRole = PlatformRole.Viewer)
    {
        await Provider.StartAsync(); Provider.Users[Email] = Subject;
        Admin = (await fixture.AdministratorAsync()).Session;
        var registration = await fixture.Administration().RegisterAsync(Admin, new(Provider.Configuration.Issuer, Subject), null, CancellationToken.None);
        Assert.Equal(StoreOutcome.Success, registration.Outcome); User = registration.Id!.Value;
        Assert.Equal(StoreOutcome.Success, (await fixture.Administration().ChangeStatusAsync(Admin, User, UserStatus.Active, CancellationToken.None)).Outcome);
        if (role) Assert.Equal(StoreOutcome.Success, (await fixture.Administration().GrantRoleAsync(Admin, User, platformRole, DateTimeOffset.UtcNow.AddHours(1), CancellationToken.None)).Outcome);
        if (grant) Assert.Equal(StoreOutcome.Success, (await fixture.Administration().GrantResourceAsync(Admin, User, ResourceKind.Study, Resource, EnvironmentScope.Paper, Capability.Read, DateTimeOffset.UtcNow.AddHours(1), CancellationToken.None)).Outcome);
        App = IntegratedHostFactory.CreateSyntheticPilot(Provider.Configuration, fixture.Database(DatabasePurpose.Runtime), fixture.Database(DatabasePurpose.SessionIssuer), builder =>
        { builder.WebHost.UseTestServer(); Provider.ConfigureTransport(builder.Services); builder.Logging.AddProvider(Logs); });
        await App.StartAsync(); Browser = NewBrowser();
    }
    public Browser NewBrowser() => new(App.GetTestClient());
    public async Task<(Guid Factor, Guid Challenge)> PreliminaryAsync(Browser? browser = null)
    {
        browser ??= Browser;
        using var login = await browser.PostAsync("/bff/auth/login", new { email = Email, password = "fixture-password" }); Assert.Equal(200, (int)login.StatusCode);
        Guid factor;
        using var loginBody = JsonDocument.Parse(await login.Content.ReadAsStringAsync());
        var existing = loginBody.RootElement.GetProperty("factors").EnumerateArray().FirstOrDefault(f => f.GetProperty("verified").GetBoolean());
        if (existing.ValueKind != JsonValueKind.Undefined) factor = existing.GetProperty("id").GetGuid();
        else
        {
            using var enroll = await browser.PostAsync("/bff/auth/mfa/enroll", new { }); Assert.Equal(200, (int)enroll.StatusCode);
            using var body = JsonDocument.Parse(await enroll.Content.ReadAsStringAsync()); factor = body.RootElement.GetProperty("factorId").GetGuid();
        }
        using var challenge = await browser.PostAsync("/bff/auth/mfa/challenge", new { factorId = factor }); Assert.Equal(200, (int)challenge.StatusCode);
        using var parsed = JsonDocument.Parse(await challenge.Content.ReadAsStringAsync());
        return (factor, parsed.RootElement.GetProperty("id").GetGuid());
    }
    public async Task SignInAsync(Browser? browser = null)
    {
        browser ??= Browser; var preliminary = await PreliminaryAsync(browser);
        using var verify = await browser.PostAsync("/bff/auth/mfa/verify", new { challengeId = preliminary.Challenge, code = "123456" }); Assert.Equal(200, (int)verify.StatusCode);
    }
    public async ValueTask DisposeAsync()
    {
        if (Browser is not null) Browser.Dispose(); if (App is not null) await App.DisposeAsync(); await Provider.DisposeAsync(); GC.SuppressFinalize(this);
    }
}

public sealed class Browser(HttpClient client) : IDisposable
{
    public Dictionary<string, string> Cookies { get; } = new(StringComparer.Ordinal);
    public async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request)
    {
        request.RequestUri = new Uri(new Uri("https://tradingagent.test"), request.RequestUri!);
        if (!request.Headers.Contains("Cookie") && Cookies.Count > 0) request.Headers.Add("Cookie", string.Join("; ", Cookies.Select(c => c.Key + "=" + c.Value)));
        var response = await client.SendAsync(request);
        if (response.Headers.TryGetValues("Set-Cookie", out var headers))
            foreach (var header in headers)
            {
                var pair = header.Split(';')[0].Split('=', 2);
                if (pair[1].Length == 0) Cookies.Remove(pair[0]); else Cookies[pair[0]] = pair[1];
            }
        return response;
    }
    public async Task<string> CsrfAsync()
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, "/bff/csrf"); using var response = await SendAsync(request);
        Assert.Equal(200, (int)response.StatusCode); using var body = JsonDocument.Parse(await response.Content.ReadAsStringAsync()); return body.RootElement.GetProperty("token").GetString()!;
    }
    public async Task<HttpResponseMessage> PostAsync(string path, object body, bool csrf = true, string origin = "https://tradingagent.test", string fetchSite = "same-origin")
    {
        var token = csrf ? await CsrfAsync() : null;
        using var request = new HttpRequestMessage(HttpMethod.Post, path) { Content = JsonContent.Create(body) };
        request.Headers.Add("Origin", origin); request.Headers.Add("Sec-Fetch-Site", fetchSite);
        if (token is not null) request.Headers.Add("X-CSRF-TOKEN", token);
        return await SendAsync(request);
    }
    public async Task<HttpResponseMessage> GetAsync(string path)
    { using var request = new HttpRequestMessage(HttpMethod.Get, path); return await SendAsync(request); }
    public void Dispose() { client.Dispose(); GC.SuppressFinalize(this); }
}
