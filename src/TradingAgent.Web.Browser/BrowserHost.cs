using System.Security.Cryptography.X509Certificates;
using Microsoft.AspNetCore.Builder;
using TradingAgent.Identity.Persistence;
using TradingAgent.Identity.Supabase;
using TradingAgent.Web.Auth;

namespace TradingAgent.Web.Browser;

public static class BrowserHost
{
    public static WebApplication CreateSynthetic(AuthConfiguration configuration, SecurityDatabase runtime, SecurityDatabase issuer,
        Uri origin, X509Certificate2 certificate, string reactRoot, Action<WebApplicationBuilder> configure)
    {
        var app = IntegratedHostFactory.CreateBrowserFixture(configuration, runtime, issuer, origin, certificate, configure);
        BrowserAssets.Map(app, reactRoot);
        return app;
    }
}
