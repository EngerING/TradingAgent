using System.Net;
using System.Text;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;
using TradingAgent.Api;
using Xunit;

namespace TradingAgent.Tests;

public class LegacyRetirementTests
{
    // An in-memory host: no Program startup, DB, credentials, or broker transport.
    static TestServer Server() => new(new WebHostBuilder().ConfigureServices(s=>s.AddRouting())
        .Configure(app=>
        {
            app.UseRouting();
            app.UseMiddleware<LegacyOperationRetirement>();
            app.Run(async c=>{c.Response.StatusCode=202;await c.Response.WriteAsync("EXISTING_HANDLER");});
        }));

    [Theory]
    [InlineData("/simulation/accounts")]
    [InlineData("/simulation/strategies")]
    [InlineData("/simulation/decisions")]
    [InlineData("/SIMULATION/DECISIONS/")]
    public async Task CreationIsDeniedBeforeBodyOrExistingHandler(string path)
    {
        using var server=Server();using var client=server.CreateClient();
        using var response=await client.PostAsync(path,new StringContent("invalid-json",Encoding.UTF8,"application/json"));
        Assert.Equal(HttpStatusCode.Gone,response.StatusCode);
        Assert.Contains("LEGACY_OPERATION_RETIRED_R20_ONLY",await response.Content.ReadAsStringAsync());
    }

    [Theory]
    [InlineData("GET","/simulation/accounts/SIM-old")]
    [InlineData("GET","/simulation/decisions/old")]
    [InlineData("POST","/simulation/settle")]
    [InlineData("POST","/simulation/mark")]
    [InlineData("POST","/simulation/valuation")]
    [InlineData("POST","/safety/stop/SIM-old")]
    [InlineData("POST","/experiences/rejected-observation")]
    [InlineData("GET","/api/ui/dashboard")]
    public async Task ReadSettlementAndSafetyStillReachTheirExistingHandlers(string method,string path)
    {
        using var server=Server();using var client=server.CreateClient();
        using var response=await client.SendAsync(new HttpRequestMessage(new HttpMethod(method),path));
        Assert.Equal(HttpStatusCode.Accepted,response.StatusCode);
        Assert.Equal("EXISTING_HANDLER",await response.Content.ReadAsStringAsync());
    }
}
