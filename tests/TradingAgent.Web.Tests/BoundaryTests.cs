using System.Net;
using System.Text.Json;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Routing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;
using TradingAgent.Web.Security;
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
        Assert.Equal("nosniff", Assert.Single(response.Headers.GetValues("X-Content-Type-Options")));
        Assert.False(response.Headers.Contains("Server"));
    }

    [Theory]
    [InlineData("POST", "/health", 405)]
    [InlineData("DELETE", "/health", 405)]
    [InlineData("GET", "/bff/session", 404)]
    [InlineData("POST", "/bff/auth/login", 404)]
    [InlineData("POST", "/api/orders", 404)]
    [InlineData("POST", "/api/emergency/settle", 404)]
    [InlineData("GET", "/proxy/api/dashboard", 404)]
    [InlineData("GET", "/dashboardHub", 404)]
    [InlineData("GET", "/swagger/v1/swagger.json", 404)]
    public async Task OtherRoutesAndMethodsCannotExposeDataOrExecute(string method, string path, int expected)
    {
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(30));
        await using var app = WebHostFactory.Create(builder => builder.WebHost.UseTestServer());
        await app.StartAsync(deadline.Token);
        using var client = app.GetTestClient();
        using var request = new HttpRequestMessage(new HttpMethod(method), path + "?value=must-not-echo");
        request.Headers.Add("Authorization", "Bearer public-invalid-fixture");
        request.Headers.Add("Cookie", "TradingAgent.ReadOnly=public-invalid-fixture");
        request.Headers.Add("X-Correlation-Id", "must-not-echo");
        using var response = await client.SendAsync(request, deadline.Token);
        Assert.Equal(expected, (int)response.StatusCode);
        var text = await response.Content.ReadAsStringAsync(deadline.Token);
        Assert.DoesNotContain("must-not-echo", text, StringComparison.Ordinal);
        using var body = JsonDocument.Parse(text);
        Assert.Equal(expected == 404 ? "NOT_FOUND" : "METHOD_NOT_ALLOWED", body.RootElement.GetProperty("code").GetString());
        Assert.True(Guid.TryParse(body.RootElement.GetProperty("correlationId").GetString(), out _));
        Assert.False(response.Headers.Contains("Set-Cookie"));
    }

    [Fact]
    public async Task OnlyHealthIsMappedAndFutureProtectedRoutesFailClosed()
    {
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(30));
        await using var app = WebHostFactory.Create(builder => builder.WebHost.UseTestServer());
        var routes = ((IEndpointRouteBuilder)app).DataSources.SelectMany(source => source.Endpoints).OfType<RouteEndpoint>();
        Assert.Equal("/health", Assert.Single(routes).RoutePattern.RawText);
        app.MapGet("/future-protected", () => "must-never-be-exposed");
        await app.StartAsync(deadline.Token);
        using var client = app.GetTestClient();
        using var response = await client.GetAsync("/future-protected", deadline.Token);
        Assert.Equal(HttpStatusCode.ServiceUnavailable, response.StatusCode);
        using var body = JsonDocument.Parse(await response.Content.ReadAsStringAsync(deadline.Token));
        Assert.Equal("SERVICE_UNAVAILABLE", body.RootElement.GetProperty("code").GetString());
        Assert.Equal(AccessDecision.Denied, await app.Services.GetRequiredService<IWebAuthorizer>()
            .CheckAsync(Guid.NewGuid(), WebCapability.ResearchRead, Guid.NewGuid(), deadline.Token));
    }

    [Fact]
    public async Task ExceptionResponsesContainNoInternalDetailsEvenInDevelopment()
    {
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(30));
        await using var app = WebHostFactory.Create(builder =>
        {
            builder.WebHost.UseTestServer();
            builder.Environment.EnvironmentName = "Development";
        });
        app.MapGet("/test-error", (Func<string>)(() => throw new InvalidOperationException("private-operational-detail")))
            .AllowAnonymous();
        await app.StartAsync(deadline.Token);
        using var client = app.GetTestClient();
        using var response = await client.GetAsync("/test-error", deadline.Token);
        Assert.Equal(HttpStatusCode.InternalServerError, response.StatusCode);
        var body = await response.Content.ReadAsStringAsync(deadline.Token);
        Assert.DoesNotContain("private-operational-detail", body, StringComparison.Ordinal);
        Assert.DoesNotContain("Exception", body, StringComparison.Ordinal);
        using var json = JsonDocument.Parse(body);
        Assert.Equal("INTERNAL_ERROR", json.RootElement.GetProperty("code").GetString());
    }
}

