using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Http;
using TradingAgent.Web.Auth;
using Xunit;

namespace TradingAgent.React.Integration.Tests;

public sealed class LocalStartupTests
{
    private static DefaultHttpContext Request(string method, string path, bool anonymous = true)
    {
        var context = new DefaultHttpContext(); context.Request.Method = method; context.Request.Path = path;
        if (anonymous) context.SetEndpoint(new Endpoint(_ => Task.CompletedTask, new EndpointMetadataCollection(new AllowAnonymousAttribute()), "fixture"));
        return context;
    }
    [Fact]
    public void LocalStartupAllowsOnlyMappedAnonymousGetResources()
    {
        Assert.True(LocalStartupBoundary.Allowed(Request("GET", "/health")));
        Assert.True(LocalStartupBoundary.Allowed(Request("GET", "/bff/config")));
        Assert.True(LocalStartupBoundary.Allowed(Request("GET", "/assets/app.js")));
        Assert.False(LocalStartupBoundary.Allowed(Request("GET", "/unknown", false)));
    }
    [Fact]
    public void LocalStartupDeniesAllAuthenticationAndSessionRoutes()
    {
        foreach (var path in new[] { "/bff/auth/login", "/bff/auth/mfa/enroll", "/bff/auth/mfa/verify", "/bff/csrf", "/bff/session", "/bff/probe/x/Paper" })
        {
            Assert.False(LocalStartupBoundary.Allowed(Request("GET", path)));
            Assert.False(LocalStartupBoundary.Allowed(Request("POST", path)));
        }
    }
    [Fact]
    public void LocalStartupCannotAuthenticateAnOldBrowserCookie()
    {
        var context = Request("GET", "/bff/session", false);
        context.Request.Headers.Cookie = "__Host-TradingAgent.Session=PUBLIC_OLD_FIXTURE";
        Assert.False(LocalStartupBoundary.Allowed(context));
        Assert.False(LocalStartupBoundary.Allowed(Request("POST", "/bff/config")));
    }
}
