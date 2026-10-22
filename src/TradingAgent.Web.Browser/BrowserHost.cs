using System.Security.Cryptography.X509Certificates;
using Microsoft.AspNetCore.Builder;
using TradingAgent.Identity.Persistence;
using TradingAgent.Identity.Supabase;
using TradingAgent.Web.Auth;

namespace TradingAgent.Web.Browser;

public static class BrowserHost
{
    /// <summary>Explicit hosted development composition; this method does not provision identities or database permissions.</summary>
    public static WebApplication CreateHosted(HostedPilotSettings settings, SecurityDatabase runtime, SecurityDatabase issuer,
        X509Certificate2 certificate, string reactRoot, bool localChecksOnly = false)
    {
        ArgumentNullException.ThrowIfNull(settings);
        var app = IntegratedHostFactory.CreateHostedBrowserPilot(settings, runtime, issuer, certificate, localChecksOnly);
        BrowserAssets.Map(app, reactRoot);
        return app;
    }

    public static WebApplication CreateSynthetic(AuthConfiguration configuration, SecurityDatabase runtime, SecurityDatabase issuer,
        Uri origin, X509Certificate2 certificate, string reactRoot, Action<WebApplicationBuilder> configure)
    {
        var app = IntegratedHostFactory.CreateBrowserFixture(configuration, runtime, issuer, origin, certificate, configure);
        BrowserAssets.Map(app, reactRoot);
        return app;
    }
}
