using System.Net.Http.Json;
using Microsoft.Extensions.DependencyInjection;
using TradingAgent.Identity.Persistence;
using TradingAgent.Identity.Supabase;
using TradingAgent.Identity.Tests;
using TradingAgent.Web.Auth;
using Xunit;

namespace TradingAgent.Auth.Tests;

[Collection("PostgreSQL")]
public sealed class AdversarialBffTests(DatabaseFixture fixture)
{
    [Theory]
    [InlineData("subject")] [InlineData("session")] [InlineData("stale")]
    public async Task ElevatedTokenMustMatchPreliminaryIdentitySessionAndChallengeTime(string change)
    {
        await using var harness = new BrowserHarness(); await harness.StartAsync(fixture); var preliminary = await harness.PreliminaryAsync();
        harness.Provider.ChangeVerifySubject = change == "subject"; harness.Provider.ChangeVerifySession = change == "session"; harness.Provider.StaleMfa = change == "stale";
        using var verify = await harness.Browser.PostAsync("/bff/auth/mfa/verify", new { challengeId = preliminary.Challenge, code = "123456" });
        Assert.Equal(401, (int)verify.StatusCode); Assert.False(harness.Browser.Cookies.ContainsKey("__Host-TradingAgent.Session"));
        Assert.Equal(0L, await fixture.ScalarAsync("SELECT count(*) FROM app_security.web_sessions WHERE app_user_id=$1", harness.User));
    }
    [Fact]
    public async Task WrongCodeConsumesChallengeAndPreventsReplay()
    {
        await using var harness = new BrowserHarness(); await harness.StartAsync(fixture); var preliminary = await harness.PreliminaryAsync();
        using var wrong = await harness.Browser.PostAsync("/bff/auth/mfa/verify", new { challengeId = preliminary.Challenge, code = "000000" }); Assert.Equal(401, (int)wrong.StatusCode);
        using var repeated = await harness.Browser.PostAsync("/bff/auth/mfa/verify", new { challengeId = preliminary.Challenge, code = "123456" }); Assert.Equal(401, (int)repeated.StatusCode);
        Assert.Equal(1, harness.Provider.VerifyRequests);
    }
    [Fact]
    public async Task AnotherBrowserCannotUseForeignChallengeAndExpiredChallengeFails()
    {
        await using var harness = new BrowserHarness(); await harness.StartAsync(fixture);
        // Both browsers use an existing verified factor. A foreign unverified enrollment is now intentionally blocked.
        var factor = Guid.NewGuid(); harness.Provider.Factors[factor] = harness.Subject; harness.Provider.VerifiedFactors[factor] = true;
        var preliminary = await harness.PreliminaryAsync();
        using var other = harness.NewBrowser(); await harness.PreliminaryAsync(other);
        using var foreign = await other.PostAsync("/bff/auth/mfa/verify", new { challengeId = preliminary.Challenge, code = "123456" }); Assert.Equal(401, (int)foreign.StatusCode);
        harness.Provider.Clock.Advance(TimeSpan.FromSeconds(61));
        using var expired = await harness.Browser.PostAsync("/bff/auth/mfa/verify", new { challengeId = preliminary.Challenge, code = "123456" }); Assert.Equal(401, (int)expired.StatusCode);
        Assert.Equal(0, harness.Provider.VerifyRequests);
    }
    [Fact]
    public async Task ConcurrentVerifyIssuesAtMostOneSqlSession()
    {
        await using var harness = new BrowserHarness(); await harness.StartAsync(fixture); var preliminary = await harness.PreliminaryAsync(); var csrf = await harness.Browser.CsrfAsync();
        harness.Provider.VerifyEntered = new(TaskCreationOptions.RunContinuationsAsynchronously); harness.Provider.ReleaseVerify = new(TaskCreationOptions.RunContinuationsAsynchronously);
        using var one = new HttpRequestMessage(HttpMethod.Post, "/bff/auth/mfa/verify") { Content = JsonContent.Create(new { challengeId = preliminary.Challenge, code = "123456" }) };
        one.Headers.Add("Origin", "https://tradingagent.test"); one.Headers.Add("X-CSRF-TOKEN", csrf);
        var pending = harness.Browser.SendAsync(one); await harness.Provider.VerifyEntered.Task.WaitAsync(TimeSpan.FromSeconds(3));
        using var second = await harness.Browser.PostAsync("/bff/auth/mfa/verify", new { challengeId = preliminary.Challenge, code = "123456" }); Assert.Equal(409, (int)second.StatusCode);
        harness.Provider.ReleaseVerify.TrySetResult(); using var completed = await pending; Assert.Equal(200, (int)completed.StatusCode);
        Assert.Equal(1L, await fixture.ScalarAsync("SELECT count(*) FROM app_security.web_sessions WHERE app_user_id=$1", harness.User));
    }
    [Fact]
    public async Task PreliminaryLogoutDuringVerifyCannotCreateUsableSession()
    {
        await using var harness = new BrowserHarness(); await harness.StartAsync(fixture); var preliminary = await harness.PreliminaryAsync(); var csrf = await harness.Browser.CsrfAsync();
        harness.Provider.VerifyEntered = new(TaskCreationOptions.RunContinuationsAsynchronously); harness.Provider.ReleaseVerify = new(TaskCreationOptions.RunContinuationsAsynchronously);
        using var request = new HttpRequestMessage(HttpMethod.Post, "/bff/auth/mfa/verify") { Content = JsonContent.Create(new { challengeId = preliminary.Challenge, code = "123456" }) };
        request.Headers.Add("Origin", "https://tradingagent.test"); request.Headers.Add("X-CSRF-TOKEN", csrf);
        var pending = harness.Browser.SendAsync(request); await harness.Provider.VerifyEntered.Task.WaitAsync(TimeSpan.FromSeconds(3));
        using var logout = await harness.Browser.PostAsync("/bff/auth/logout", new { }); Assert.Equal(204, (int)logout.StatusCode);
        harness.Provider.ReleaseVerify.TrySetResult(); using var result = await pending; Assert.Equal(401, (int)result.StatusCode);
        Assert.Equal(0L, await fixture.ScalarAsync("SELECT count(*) FROM app_security.web_sessions WHERE app_user_id=$1 AND revoked_at IS NULL", harness.User));
    }
    [Fact]
    public async Task ProviderFailureExpiredJwtAndOnlineIdentityChangeDenyAccess()
    {
        await using var harness = new BrowserHarness(); await harness.StartAsync(fixture); await harness.SignInAsync();
        harness.Provider.Unavailable = true;
        using (var down = await harness.Browser.GetAsync("/bff/session")) Assert.Equal(503, (int)down.StatusCode);
        harness.Provider.Unavailable = false; harness.Provider.RejectUser = true;
        using (var revoked = await harness.Browser.GetAsync("/bff/session")) Assert.Equal(401, (int)revoked.StatusCode);
        harness.Provider.RejectUser = false; harness.Provider.Clock.Advance(TimeSpan.FromMinutes(6));
        using var expired = await harness.Browser.GetAsync("/bff/session"); Assert.Equal(401, (int)expired.StatusCode);
    }
    [Fact]
    public async Task GetUserCanContinueAcceptingSignedTokenAfterRemoteLogout()
    {
        await using var harness = new BrowserHarness(); await harness.StartAsync(fixture);
        var provider = harness.Provider.Services.GetRequiredService<SupabaseAuthClient>(); harness.Provider.IgnoreRemoteLogout = true;
        var credential = await provider.PasswordAsync(harness.Email, "fixture-password", CancellationToken.None);
        await provider.LogoutAsync(credential, CancellationToken.None);
        await provider.CheckUserAsync(credential, CancellationToken.None); // Simulates the documented JWT survival limit, not hosted Supabase evidence.
        await harness.SignInAsync(); using var session = await harness.Browser.GetAsync("/bff/session");
        Assert.Contains("\"providerSessionConfirmedActive\":false", await session.Content.ReadAsStringAsync(), StringComparison.Ordinal);
        using var sensitive = await harness.Browser.GetAsync("/bff/admin/users"); Assert.Equal(404, (int)sensitive.StatusCode);
    }
    [Fact]
    public async Task SessionCasConflictAndLogoutRequireCsrf()
    {
        await using var harness = new BrowserHarness(); await harness.StartAsync(fixture); await harness.SignInAsync();
        using var missingCsrf = await harness.Browser.PostAsync("/bff/auth/logout", new { }, csrf: false); Assert.Equal(403, (int)missingCsrf.StatusCode);
        using var touch = await harness.Browser.PostAsync("/bff/session/touch", new { rowVersion = 1 }); Assert.Equal(204, (int)touch.StatusCode);
        using var stale = await harness.Browser.PostAsync("/bff/session/touch", new { rowVersion = 1 }); Assert.Equal(409, (int)stale.StatusCode);
    }
    [Fact]
    public async Task PostgreSqlUnavailableReturns503AndNeverReadsFinancialResources()
    {
        await using var harness = new BrowserHarness(); await harness.StartAsync(fixture); await harness.SignInAsync();
        // Revoke CONNECT only for this disposable fixture database, terminate runtime connections, then restore.
        await using var runtime = await fixture.Database(DatabasePurpose.Runtime).OpenAsync(CancellationToken.None);
        await using var query = new Npgsql.NpgsqlCommand("SELECT session_user", runtime); var login = (string)(await query.ExecuteScalarAsync())!;
        try
        {
            await using var owner = await fixture.OpenOwnerAsync(); await DatabaseFixture.ExecuteAsync(owner, $"ALTER ROLE {login} NOLOGIN");
            using var down = await harness.Browser.GetAsync($"/bff/probe/{harness.Resource}/Paper"); Assert.Equal(503, (int)down.StatusCode);
        }
        finally { await using var owner = await fixture.OpenOwnerAsync(); await DatabaseFixture.ExecuteAsync(owner, $"ALTER ROLE {login} LOGIN"); }
        Assert.Equal("UNCHANGED", await fixture.ScalarAsync("SELECT value FROM financial_fixture.sentinel WHERE id=1"));
    }
    [Fact]
    public async Task GlobalAttemptLimitBodyLimitAndGenericErrorsPreventEnumeration()
    {
        await using var harness = new BrowserHarness(); await harness.StartAsync(fixture); string? previous = null;
        for (var i = 0; i < 21; i++)
        {
            using var response = await harness.Browser.PostAsync("/bff/auth/login", new { email = i % 2 == 0 ? harness.Email : "missing@fixture.invalid", password = "wrong" });
            Assert.Equal(i == 20 ? 429 : 401, (int)response.StatusCode);
            var text = await response.Content.ReadAsStringAsync(); Assert.DoesNotContain("PRIVATE_PROVIDER_ERROR", text, StringComparison.Ordinal);
            if (i < 20) { using var parsed = System.Text.Json.JsonDocument.Parse(text); var code = parsed.RootElement.GetProperty("code").GetString(); if (previous is not null) Assert.Equal(previous, code); previous = code; }
        }
        var csrf = await harness.Browser.CsrfAsync();
        using var request = new HttpRequestMessage(HttpMethod.Post, "/bff/auth/login") { Content = new StringContent("{\"password\":\"" + new string('x', 5000) + "\"}", System.Text.Encoding.UTF8, "application/json") };
        request.Headers.Add("Origin", "https://tradingagent.test"); request.Headers.Add("X-CSRF-TOKEN", csrf);
        using var huge = await harness.Browser.SendAsync(request); Assert.Equal(413, (int)huge.StatusCode);
    }
}
