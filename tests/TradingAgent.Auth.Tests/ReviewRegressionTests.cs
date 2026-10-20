using System.Text.Json;
using TradingAgent.Identity.Persistence;
using TradingAgent.Identity.Tests;
using Xunit;

namespace TradingAgent.Auth.Tests;

[Collection("PostgreSQL")]
public sealed class ReviewRegressionTests(DatabaseFixture fixture)
{
    [Fact]
    public async Task LogoutWithOnlyOldPreauthRevokesCompletedButDelayedVerifyCookie()
    {
        await using var harness = new BrowserHarness(); await harness.StartAsync(fixture); var pending = await harness.PreliminaryAsync();
        var preliminaryCookie = harness.Browser.Cookies["__Host-TradingAgent.PreAuth"];
        using var verify = await harness.Browser.PostAsync("/bff/auth/mfa/verify", new { challengeId = pending.Challenge, code = "123456" }); Assert.Equal(200, (int)verify.StatusCode);
        var installed = harness.Browser.Cookies["__Host-TradingAgent.Session"];
        using var verifiedBody = JsonDocument.Parse(await verify.Content.ReadAsStringAsync());
        Assert.True(verifiedBody.RootElement.GetProperty("expiresAt").GetDateTimeOffset() <= harness.Provider.Clock.GetUtcNow().AddMinutes(5));
        // Model a browser whose verify response was delayed after server Complete, so logout only has preauth.
        harness.Browser.Cookies.Remove("__Host-TradingAgent.Session"); harness.Browser.Cookies["__Host-TradingAgent.PreAuth"] = preliminaryCookie;
        using var logout = await harness.Browser.PostAsync("/bff/auth/logout", new { }); Assert.Equal(204, (int)logout.StatusCode);
        harness.Browser.Cookies["__Host-TradingAgent.Session"] = installed;
        using var replay = await harness.Browser.GetAsync("/bff/session"); Assert.Equal(401, (int)replay.StatusCode);
        Assert.Null(await fixture.Sessions.FindSelfAsync(SessionReference.Parse(installed), CancellationToken.None));
    }
    [Fact]
    public async Task NewDeviceDiscoversVerifiedFactorThroughBffOnly()
    {
        await using var harness = new BrowserHarness(); await harness.StartAsync(fixture); await harness.SignInAsync();
        using var second = harness.NewBrowser();
        using var login = await second.PostAsync("/bff/auth/login", new { email = harness.Email, password = "fixture-password" });
        using var body = JsonDocument.Parse(await login.Content.ReadAsStringAsync()); var factor = Assert.Single(body.RootElement.GetProperty("factors").EnumerateArray());
        Assert.True(factor.GetProperty("verified").GetBoolean());
        using var challenge = await second.PostAsync("/bff/auth/mfa/challenge", new { factorId = factor.GetProperty("id").GetGuid() });
        using var challengeBody = JsonDocument.Parse(await challenge.Content.ReadAsStringAsync());
        using var verify = await second.PostAsync("/bff/auth/mfa/verify", new { challengeId = challengeBody.RootElement.GetProperty("id").GetGuid(), code = "123456" }); Assert.Equal(200, (int)verify.StatusCode);
    }
    [Fact]
    public async Task OrphanedUnverifiedEnrollmentCanBeReplacedWithoutResettingVerifiedMfa()
    {
        await using var harness = new BrowserHarness(); await harness.StartAsync(fixture);
        using var login = await harness.Browser.PostAsync("/bff/auth/login", new { email = harness.Email, password = "fixture-password" });
        using var enrollment = await harness.Browser.PostAsync("/bff/auth/mfa/enroll", new { }); Assert.Equal(200, (int)enrollment.StatusCode);
        using var body = JsonDocument.Parse(await enrollment.Content.ReadAsStringAsync()); var orphan = body.RootElement.GetProperty("factorId").GetGuid();
        Assert.False(harness.Provider.VerifiedFactors.ContainsKey(orphan));
        using var freshBrowser = harness.NewBrowser(); await harness.SignInAsync(freshBrowser);
        Assert.False(harness.Provider.Factors.ContainsKey(orphan)); Assert.Single(harness.Provider.VerifiedFactors);
        using var third = harness.NewBrowser(); using var thirdLogin = await third.PostAsync("/bff/auth/login", new { email = harness.Email, password = "fixture-password" });
        using var resetVerified = await third.PostAsync("/bff/auth/mfa/enroll", new { }); Assert.Equal(409, (int)resetVerified.StatusCode); Assert.Single(harness.Provider.VerifiedFactors);
    }
    [Fact]
    public async Task IdentityAttemptBudgetSurvivesNewPreauthCookies()
    {
        await using var harness = new BrowserHarness(); await harness.StartAsync(fixture);
        var factor = Guid.NewGuid(); harness.Provider.Factors[factor] = harness.Subject; harness.Provider.VerifiedFactors[factor] = true;
        for (var browserIndex = 0; browserIndex < 4; browserIndex++)
        {
            using var browser = harness.NewBrowser(); using var login = await browser.PostAsync("/bff/auth/login", new { email = harness.Email, password = "fixture-password" });
            Assert.Equal(200, (int)login.StatusCode);
            for (var attempt = 0; attempt < 4; attempt++)
            {
                using var challenge = await browser.PostAsync("/bff/auth/mfa/challenge", new { factorId = factor });
                // This is POST20 globally, still inside its budget; only account challenge16 must reject.
                Assert.Equal(browserIndex == 3 && attempt == 3 ? 429 : 200, (int)challenge.StatusCode);
            }
        }
        Assert.Equal(4, harness.Provider.PasswordRequests);
    }
}
