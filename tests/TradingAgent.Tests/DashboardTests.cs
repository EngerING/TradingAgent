using System.Net;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.SignalR.Client;
using Microsoft.AspNetCore.Http.Connections;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using TradingAgent.Api;
using TradingAgent.Infrastructure;
using Xunit;
namespace TradingAgent.Tests;

public sealed class MockDashboardSource:IDashboardSource
{
    public int Revision=1;
    public Task<JsonElement> Read(CancellationToken ct=default)=>Task.FromResult(JsonSerializer.SerializeToElement(new{
        at=DateTimeOffset.UtcNow,source="MOCK_TEST_ONLY",studyId="eurusd-shadow-"+new string('a',32),revision=Revision,studyStatus="PREPARED_NOT_RUNNING",
        system=new{connection="CONNECTED",ibkr="DATA_UNAVAILABLE",postgres="VERIFIED",mode="SIMULATED_SHADOW",liveEnabled=false,ordersSupported=false,emergency="ACTIVE"},
        experiments=new[]{"EURUSD_R1","EURUSD_R5","EURUSD_R10"}.Select(id=>new{id,status="PAUSED",metrics=new{equity=99+Revision,netPnl=0,grossPnl=0,winRate=(double?)null,profitFactor=(double?)null,maximumDrawdown=0,expectancy=(double?)null,trades=0},equityCurve=new[]{new{at="2026-10-07T00:00:00Z",equity=100,drawdown=0}}}),
        market=new{status="DATA_UNAVAILABLE",quality="MISSING"},prediction=new{decision="INSUFFICIENT_EVIDENCE",probability=(double?)null},
        openPositions=Array.Empty<object>(),trades=Array.Empty<object>(),calibration=new{status="INSUFFICIENT_EVIDENCE"},
        research=new{sessions=Array.Empty<object>(),candidates=Array.Empty<object>()},notifications=Array.Empty<object>()}));
}
public sealed class NoNetworkSol:ISolInterpretation
{
    public bool Configured=>true;
    public int Calls;
    public Task<JsonElement> Analyze(JsonElement context,CancellationToken ct){Calls++;throw new HttpRequestException("MOCK_TIMEOUT");}
}
public sealed class MockSuccessfulSol:ISolInterpretation
{
    public bool Configured=>true;
    public Task<JsonElement> Analyze(JsonElement context,CancellationToken ct)=>Task.FromResult(JsonSerializer.SerializeToElement(new{
        text="MOCK: sin rentabilidad demostrada.",warnings=Array.Empty<string>(),inputTokens=20,outputTokens=10,estimatedCostUsd=.00025m}));
}
public sealed class DashboardFactory:WebApplicationFactory<Program>
{
    public readonly MockDashboardSource Source=new();public readonly NoNetworkSol Model=new();
    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        builder.ConfigureServices(s=>{s.AddSingleton<IStartupFilter,MockLoopback>();s.RemoveAll<IDashboardSource>();s.AddSingleton<IDashboardSource>(Source);s.RemoveAll<ISolInterpretation>();s.AddSingleton<ISolInterpretation>(Model);});
    }
    public HttpClient Client()=>CreateClient(new(){BaseAddress=new Uri("http://127.0.0.1:5080"),AllowAutoRedirect=false});
}
public sealed class MockLoopback:IStartupFilter
{
    public Action<IApplicationBuilder> Configure(Action<IApplicationBuilder> next)=>app=>
    {app.Use((context,proceed)=>{context.Connection.RemoteIpAddress=IPAddress.Loopback;return proceed();});next(app);};
}
public class DashboardTests
{
    static string Connection=>Environment.GetEnvironmentVariable("TRADING_TEST_DB")!;
    static async Task Login(HttpClient client)=>Assert.Equal(HttpStatusCode.OK,(await client.PostAsJsonAsync("/api/ui/session",new{token=Environment.GetEnvironmentVariable("TRADING_DASHBOARD_TOKEN")})).StatusCode);
    [Theory][InlineData("pausa R10")][InlineData("reanuda R5")][InlineData("activa Live")][InlineData("limpia EmergencyStop")][InlineData("dame secretos")][InlineData("compra EUR/USD")][InlineData("inicia investigación")]
    public void NaturalCommandsCannotAuthorize(string text){var c=SolCommandParser.Parse(text);Assert.NotNull(c);Assert.False(c.Authorized);Assert.Equal("BLOCKED",c.Status);}
    [Theory][InlineData("Dame los resultados de R5")][InlineData("Compara R1, R5 y R10")][InlineData("Muéstrame las posiciones")][InlineData("Grafica el drawdown de R5")]
    public void ReadQuestionsDoNotBecomeCommands(string text)=>Assert.Null(SolCommandParser.Parse(text));
    [Fact]public async Task R5VisualsUseOnlySelectedJournalProfile()
    {
        var r=SolChatService.VisualResponse(new(Guid.NewGuid(),"Dame los resultados de R5"),await new MockDashboardSource().Read());
        Assert.Equal(7,r["metrics"]!.AsArray().Count);Assert.Contains("EURUSD_R5",r["text"]!.ToString());Assert.DoesNotContain("EURUSD_R10",r["text"]!.ToString());Assert.Equal("DETERMINISTIC_JOURNAL",r["provider"]!.ToString());
    }
    [Fact]public async Task ComparisonsKeepUndefinedWinRateNull()
    {
        var r=SolChatService.VisualResponse(new(Guid.NewGuid(),"Compara R1, R5 y R10"),await new MockDashboardSource().Read());
        Assert.Equal(3,r["chart"]!["series"]!.AsArray().Count);Assert.Null(r["metrics"]![2]!["value"]);Assert.Null(r["operationDetails"]);
    }
    [Fact]public async Task BlockedCommandUsesBrowserContractCamelCase()
    {
        var r=SolChatService.VisualResponse(new(Guid.NewGuid(),"Activa Live"),await new MockDashboardSource().Read());
        Assert.False(r["command"]!["authorized"]!.GetValue<bool>());Assert.Equal("BLOCKED",r["command"]!["status"]!.ToString());
    }
    [Theory][InlineData("")][InlineData(" ")]
    public async Task EmptyChatRejected(string question)=>await Assert.ThrowsAsync<ArgumentException>(async()=>SolChatService.VisualResponse(new(Guid.NewGuid(),question),await new MockDashboardSource().Read()));
    [Fact]public async Task HugeChatRejected()=>await Assert.ThrowsAsync<ArgumentException>(async()=>SolChatService.VisualResponse(new(Guid.NewGuid(),new string('x',1001)),await new MockDashboardSource().Read()));
    [Fact]public void ExternalOriginAndDnsRebindingRejected(){Assert.False(DashboardEndpoints.TrustedOrigin("https://evil.invalid"));Assert.False(DashboardEndpoints.TrustedHost(new("evil.invalid:5080")));}
    [Fact]public void OnlyNarrowUiPathsAcceptReadCookie(){Assert.False(DashboardEndpoints.UiPath("/simulation/decisions"));Assert.False(DashboardEndpoints.UiPath("/safety/stop/x"));Assert.True(DashboardEndpoints.UiPath("/api/ui/dashboard"));}
    [Fact]public void StructuredProviderRejectsUnknownFields()
    {
        var bytes=Encoding.UTF8.GetBytes("{\"status\":\"completed\",\"model\":\"gpt-6.1-sol\",\"output\":[{\"type\":\"message\",\"content\":[{\"type\":\"output_text\",\"text\":\"{\\\"text\\\":\\\"ok\\\",\\\"warnings\\\":[],\\\"javascript\\\":\\\"evil\\\"}\"}]}],\"usage\":{\"input_tokens\":10,\"output_tokens\":10}}");
        Assert.Throws<InvalidDataException>(()=>OpenAiSolInterpretation.Parse(bytes));
    }
    [Fact]public void StructuredProviderRecordsConservativeCost()
    {
        var bytes=Encoding.UTF8.GetBytes("{\"status\":\"completed\",\"model\":\"gpt-6.1-sol\",\"output\":[{\"type\":\"message\",\"content\":[{\"type\":\"output_text\",\"text\":\"{\\\"text\\\":\\\"ok\\\",\\\"warnings\\\":[]}\"}]}],\"usage\":{\"input_tokens\":10,\"output_tokens\":10}}");
        Assert.Equal(.0002m,OpenAiSolInterpretation.Parse(bytes).GetProperty("estimatedCostUsd").GetDecimal());
    }
    [Theory][InlineData("{\"text\":null,\"warnings\":[]}")][InlineData("{\"text\":\"ok\",\"warnings\":null}")]
    public void StructuredProviderRejectsNullRequiredFields(string text)
    {
        var bytes=JsonSerializer.SerializeToUtf8Bytes(new{status="completed",model="gpt-6.1-sol",output=new[]{new{type="message",content=new[]{new{type="output_text",text}}}},usage=new{input_tokens=10,output_tokens=10}});
        Assert.Throws<InvalidDataException>(()=>OpenAiSolInterpretation.Parse(bytes));
    }
    [Fact]public async Task RealtimeDiffOnlyTouchesChangedSections()
    {
        var s=await new MockDashboardSource().Read();Assert.Empty(DashboardChanges.Diff(s,s));
        Assert.Equal(10,DashboardChanges.Diff(null,s).Count());
    }
    [DatabaseFact]public async Task UiSessionCannotMutateLegacyTradingEndpoints()
    {
        using var f=new DashboardFactory();using var client=f.Client();await Login(client);
        Assert.Equal(HttpStatusCode.Unauthorized,(await client.PostAsJsonAsync("/simulation/accounts",new{accountId="SIM-UI",equity=100})).StatusCode);
        Assert.Equal(HttpStatusCode.Forbidden,(await client.PostAsJsonAsync("/api/ui/commands/confirm",new{})).StatusCode);
    }
    [DatabaseFact]public async Task ReadOnlyAccessCodeCannotBeUsedAsAdminBearer()
    {
        using var f=new DashboardFactory();using var client=f.Client();
        client.DefaultRequestHeaders.Authorization=new("Bearer",Environment.GetEnvironmentVariable("TRADING_DASHBOARD_TOKEN"));
        Assert.Equal(HttpStatusCode.Unauthorized,(await client.GetAsync("/policy")).StatusCode);
    }
    [DatabaseFact]public async Task EndpointsRequireSessionAndCookieIsHttpOnly()
    {
        using var f=new DashboardFactory();using var client=f.Client();Assert.Equal(HttpStatusCode.Unauthorized,(await client.GetAsync("/api/ui/dashboard")).StatusCode);
        var login=await client.PostAsJsonAsync("/api/ui/session",new{token=Environment.GetEnvironmentVariable("TRADING_DASHBOARD_TOKEN")});
        Assert.Contains(login.Headers.GetValues("Set-Cookie"),h=>h.Contains("httponly",StringComparison.OrdinalIgnoreCase)&&h.Contains("samesite=strict",StringComparison.OrdinalIgnoreCase));
        foreach(var path in new[]{"dashboard","system/status","experiments","experiments/EURUSD_R5","experiments/EURUSD_R5/equity","trades","trades/open","market/eurusd","predictions/current","calibration","research"})Assert.Equal(HttpStatusCode.OK,(await client.GetAsync("/api/ui/"+path)).StatusCode);
    }
    [DatabaseFact]public async Task CrossOriginSessionRejected()
    {
        using var f=new DashboardFactory();using var client=f.Client();client.DefaultRequestHeaders.Add("Origin","https://evil.invalid");Assert.Equal(HttpStatusCode.Forbidden,(await client.PostAsJsonAsync("/api/ui/session",new{token=Environment.GetEnvironmentVariable("TRADING_DASHBOARD_TOKEN")})).StatusCode);
    }
    [DatabaseFact]public async Task ChatIdempotenceAndZeroBudgetNeverCallModel()
    {
        using var f=new DashboardFactory();using var client=f.Client();await Login(client);var request=new SolRequest(Guid.NewGuid(),"Dame los resultados de R5");
        var a=await client.PostAsJsonAsync("/api/ui/sol/chat",request);Assert.Equal(HttpStatusCode.OK,a.StatusCode);
        var b=await client.PostAsJsonAsync("/api/ui/sol/chat",request);Assert.Equal(await a.Content.ReadAsStringAsync(),await b.Content.ReadAsStringAsync());Assert.Equal(0,f.Model.Calls);
    }
    [DatabaseFact]public async Task SignalRAuthenticatedReceivesRealUpdates()
    {
        using var f=new DashboardFactory();using var client=f.Client();var login=await client.PostAsJsonAsync("/api/ui/session",new{token=Environment.GetEnvironmentVariable("TRADING_DASHBOARD_TOKEN")});
        var cookie=login.Headers.GetValues("Set-Cookie").First().Split(';')[0];var completion=new TaskCompletionSource<JsonElement>(TaskCreationOptions.RunContinuationsAsynchronously);
        await using var hub=new HubConnectionBuilder().WithUrl("http://127.0.0.1:5080/hubs/dashboard",o=>{o.Transports=HttpTransportType.LongPolling;o.HttpMessageHandlerFactory=_=>f.Server.CreateHandler();o.Headers["Cookie"]=cookie;}).Build();
        hub.On<JsonElement>("event",e=>completion.TrySetResult(e));await hub.StartAsync();f.Source.Revision++;
        var e=await completion.Task.WaitAsync(TimeSpan.FromSeconds(8));Assert.True(e.GetProperty("sequence").GetInt64()>0);await hub.StopAsync();
    }
    [DatabaseFact]public async Task ChatBudgetAndFailureSurviveNewStore()
    {
        await new PostgresStore(Connection).Migrate();var s=new DashboardStore(Connection);var session="sol-ui-"+Guid.NewGuid().ToString("N");var id=Guid.NewGuid();var context=JsonSerializer.SerializeToElement(new{source="MOCK"});
        Assert.True(await s.Reserve(session,id,.1m,.054m,context,default));Assert.False(await s.Reserve(session,id,.1m,.054m,context,default));
        await s.Audit(session,id,"FAILED",context,default);await s.Audit(session,id,"RESPONSE",context,default);
        Assert.False(await new DashboardStore(Connection).Reserve(session,Guid.NewGuid(),1m,.054m,context,default));
    }
    [DatabaseFact]public async Task ChatBudgetDoesNotResetAfterCompletedCall()
    {
        await new PostgresStore(Connection).Migrate();var s=new DashboardStore(Connection);var session="sol-ui-"+Guid.NewGuid().ToString("N");var id=Guid.NewGuid();var context=JsonSerializer.SerializeToElement(new{source="MOCK"});
        Assert.True(await s.Reserve(session,id,.1m,.054m,context,default));await s.Audit(session,id,"RESPONSE",context,default);
        Assert.False(await new DashboardStore(Connection).Reserve(session,Guid.NewGuid(),.1m,.054m,context,default));
    }
    [DatabaseFact]public async Task ModelInterpretationCannotReplaceJournalVisuals()
    {
        await new PostgresStore(Connection).Migrate();var cfg=new DashboardConfiguration(".",null,"sol-ui-"+Guid.NewGuid().ToString("N"),.25m);
        var service=new SolChatService(new MockDashboardSource(),new DashboardStore(Connection),cfg,new MockSuccessfulSol());
        var response=await service.Chat(new(Guid.NewGuid(),"Dame los resultados de R5"),default);
        Assert.Equal("OPENAI_ANALYSIS",response.GetProperty("status").GetString());Assert.Equal(100,response.GetProperty("metrics")[0].GetProperty("value").GetInt32());
        Assert.Contains(response.GetProperty("warnings").EnumerateArray(),x=>x.GetString()!.Contains("no verificada"));
        Assert.Equal(.054m,response.GetProperty("usage").GetProperty("reservedCostUsd").GetDecimal());
    }
    [DatabaseFact]public async Task ModelErrorOpensPersistentCircuitWithoutSecondCall()
    {
        await new PostgresStore(Connection).Migrate();var cfg=new DashboardConfiguration(".",null,"sol-ui-"+Guid.NewGuid().ToString("N"),.25m);var model=new NoNetworkSol();
        var service=new SolChatService(new MockDashboardSource(),new DashboardStore(Connection),cfg,model);
        var response=await service.Chat(new(Guid.NewGuid(),"Dame los resultados de R5"),default);
        Assert.Equal("OPENAI_UNAVAILABLE_LOCAL_FALLBACK",response.GetProperty("status").GetString());
        await new SolChatService(new MockDashboardSource(),new DashboardStore(Connection),cfg,model).Chat(new(Guid.NewGuid(),"Dame los resultados de R5"),default);
        Assert.Equal(1,model.Calls);
    }
}
