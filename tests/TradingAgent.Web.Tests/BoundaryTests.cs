using System.Net;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.TestHost;
using TradingAgent.Web;
using Xunit;

namespace TradingAgent.Web.Tests;

public sealed class BoundaryTests
{
    [Fact]
    public async Task HealthContainsOnlyLivenessAndNeverIssuesACookie()
    {
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(30));
        await using var app = WebHostFactory.Create(builder => builder.WebHost.UseTestServer());
        await app.StartAsync(deadline.Token);
        using var client = app.GetTestClient();
        using var response = await client.GetAsync("/health", deadline.Token);
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal("{\"status\":\"ok\"}", await response.Content.ReadAsStringAsync(deadline.Token));
        Assert.False(response.Headers.Contains("Set-Cookie"));
        Assert.Equal("no-store", response.Headers.CacheControl?.ToString());
    }
}

