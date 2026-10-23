using System.Net;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.TestHost;
using TradingAgent.Web.Browser;
using Xunit;

namespace TradingAgent.React.Integration.Tests;

public sealed class BrowserSpaRouteTests
{
    [Fact]
    public async Task ExplicitPreviewDeepLinksSurviveFullReloadWithoutFallbackForProtectedRoutes()
    {
        var root = Path.Combine(Path.GetTempPath(), "tradingagent-spa-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        await File.WriteAllTextAsync(Path.Combine(root, "index.html"), "<!doctype html><html><body>TradingAgent static route fixture</body></html>");
        try
        {
            var builder = WebApplication.CreateBuilder(new WebApplicationOptions { EnvironmentName = "Development" });
            builder.WebHost.UseTestServer();
            await using var app = builder.Build();
            BrowserAssets.Map(app, root);
            await app.StartAsync();
            using var client = app.GetTestClient();

            foreach (var route in new[] { "/", "/login", "/preview", "/mfa/recovery" })
            {
                using var response = await client.GetAsync(route);
                Assert.Equal(HttpStatusCode.OK, response.StatusCode);
                Assert.Equal("text/html", response.Content.Headers.ContentType?.MediaType);
                Assert.Contains("TradingAgent static route fixture", await response.Content.ReadAsStringAsync());
            }

            foreach (var route in new[] { "/orders", "/trading/live", "/bff/preview/unknown" })
            {
                using var response = await client.GetAsync(route);
                Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
            }
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }
}
