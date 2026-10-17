using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using TradingAgent.Core;
using TradingAgent.Infrastructure;
using TradingAgent.Api;

var builder=WebApplication.CreateBuilder(args);
builder.Logging.ClearProviders();builder.Logging.AddJsonConsole();
if((Environment.GetEnvironmentVariable("LIVE_TRADING")??"false").ToLowerInvariant()!="false" || builder.Configuration.GetValue<bool>("Trading:LiveEnabled") ||
    builder.Configuration.GetValue<string>("Trading:Environment") is string env && env!="PAPER_TRADING")
{
    Console.Error.WriteLine("LIVE_DISABLED: phase 2 supports simulation and Paper data only");
    Environment.ExitCode=1;
    return;
}
var policyPath=Environment.GetEnvironmentVariable("TRADING_POLICY_PATH");
var policy=policyPath is null ? new RiskPolicy() : JsonSerializer.Deserialize<RiskPolicy>(File.ReadAllText(policyPath),Evidence.Json)??throw new InvalidDataException("Missing policy");
if(args.Contains("--ford-diagnostic-risk")){await FordDiagnosticCommand.Run(policy);return;}
if(args.Contains("--ford-diagnostic-evidence")){await FordDiagnosticEvidenceCommand.Run();return;}
if(args.Contains("--eurusd-shadow-journal")){await EurusdShadowCommand.Run();return;}
if(args.Contains("--r10-price-journal")){await PriceRiskCommand.Run();return;}
if(args.Contains("--aggressive-growth-journal")){await AggressiveGrowthCommand.Run();return;}
if(args.Contains("--eurusd-exploratory-journal")){await ExploratoryCommand.Run();return;}
if(args.Contains("--kronos-journal")){await KronosCommand.Run();return;}
if(args.Contains("--h40-paper-r3-risk")){await StockPaperForwardCommand.Run(policy,true,true);return;}
if(args.Contains("--h40-paper-trial-risk")){await StockPaperForwardCommand.Run(policy,true);return;}
if(args.Contains("--stock-paper-forward-risk")){await StockPaperForwardCommand.Run(policy);return;}
if(args.Contains("--paper-risk-profile-study")){await PaperRiskProfileCommand.Run(policy);return;}
if(args.Contains("--paper-lab-journal")){await PaperLabCommand.Run(policy);return;}
if(args.Contains("--economic-study"))
{
    var root=Path.GetFullPath(Environment.GetEnvironmentVariable("ECONOMIC_STUDY_ROOT")??".");
    Console.WriteLine(EconomicStudyRunner.Run(policy,Path.Combine(root,"config","economic-study.json"),DateTimeOffset.UtcNow).GetRawText());
    return;
}
policy.Validate();
if(args.Contains("--demo"))
{
    var now=DateTimeOffset.UtcNow;
    var account=AccountState.Initial("SIM-PAPER",100,now);
    var facts=new ExecutionFacts("synthetic-demo","SIMULATION","SIMULATED",now,0,0,true,true,true,true,"SIMULATED");
    var request=new RiskRequest("EUR/USD","BUY",1.0999m,1.1001m,1.099m,1,1,1,1,1,100,0,0,.0001m,.0002m,now,Execution:facts);
    foreach(var capital in new[]{100m,110m,98m})
    {
        var a=account.Mark(capital,now,policy);
        Console.WriteLine(JsonSerializer.Serialize(new {scenario="equity",capital,result=RiskEngine.Evaluate(policy,a,request with {AvailableMargin=capital},now)},Evidence.Json));
    }
    Console.WriteLine(JsonSerializer.Serialize(new {scenario="minimum-too-large",result=RiskEngine.Evaluate(policy,account,request with{MinQuantity=20000},now)},Evidence.Json));
    Console.WriteLine(JsonSerializer.Serialize(new {scenario="daily-halt",result=RiskEngine.Evaluate(policy,account.Mark(99,now,policy),request,now)},Evidence.Json));
    Console.WriteLine("{\"liveEnabled\":false,\"ordersSupported\":false,\"aiEnabled\":false}");
    return;
}
var connection=Environment.GetEnvironmentVariable("TRADING_DB")??throw new InvalidOperationException("Set TRADING_DB; no credentials are stored in the repository");
var store=new PostgresStore(connection);
if(args.Contains("--migrate") || Environment.GetEnvironmentVariable("TRADING_DB_AUTO_MIGRATE")!="false")await store.Migrate();
else await store.VerifySchema();
if(args.Contains("--migrate")){Console.WriteLine("Migrations applied");return;}
if(args.Contains("--research"))
{
    var sourceAccount=Environment.GetEnvironmentVariable("RESEARCH_SOURCE_ACCOUNT")??throw new InvalidOperationException("RESEARCH_SOURCE_ACCOUNT_REQUIRED");
    var root=Path.GetFullPath(Environment.GetEnvironmentVariable("RESEARCH_ROOT")??".");
    var cutoff=DateTimeOffset.Parse(Environment.GetEnvironmentVariable("RESEARCH_AS_OF")??DateTimeOffset.UtcNow.ToString("O"));
    var result=await ResearchRunner.Run(store,policy,sourceAccount,root,cutoff,
        Environment.GetEnvironmentVariable("RESEARCH_CALENDAR_PATH")??Path.Combine(root,"config","forex-sessions.json"),
        Environment.GetEnvironmentVariable("RESEARCH_INDICATOR_PATH")??Path.Combine(root,"config","research-indicators.json"));
    Console.WriteLine(result.GetRawText());return;
}
var token=Environment.GetEnvironmentVariable("TRADING_ADMIN_TOKEN");
if(token is null || token.Length<32)throw new InvalidOperationException("Set a random TRADING_ADMIN_TOKEN of at least 32 characters");
var tokenHash=SHA256.HashData(Encoding.UTF8.GetBytes(token));
var uiToken=Environment.GetEnvironmentVariable("TRADING_DASHBOARD_TOKEN");
if(uiToken is not null && (uiToken.Length<32 || CryptographicOperations.FixedTimeEquals(tokenHash,SHA256.HashData(Encoding.UTF8.GetBytes(uiToken)))))
    throw new InvalidOperationException("DASHBOARD_REQUIRES_DISTINCT_READ_ONLY_CREDENTIAL");
if(builder.Configuration.GetSection("Kestrel:Endpoints").GetChildren().Any())
    throw new InvalidOperationException("EXTERNAL_ENDPOINT_CONFIGURATION_DISABLED");
builder.WebHost.ConfigureKestrel(o=>{o.Listen(System.Net.IPAddress.Loopback,5080);o.Limits.MaxRequestBodySize=2*1024*1024;});
builder.Services.ConfigureHttpJsonOptions(o=>o.SerializerOptions.UnmappedMemberHandling=System.Text.Json.Serialization.JsonUnmappedMemberHandling.Disallow);
builder.Services.AddSingleton(store);builder.Services.AddSingleton(policy);
builder.Services.AddSingleton<IResearchAi,DisabledResearchAi>();
var paperConfig=PaperFeedConfiguration.Load();
builder.Services.AddSingleton(paperConfig);
builder.Services.AddSingleton<PaperFeedService>();
builder.Services.AddHostedService(sp=>sp.GetRequiredService<PaperFeedService>());
builder.AddDashboard();
var app=builder.Build();
app.UseAuthentication();
app.UseAuthorization();
app.Use(async(context,next)=>
{
    if(context.Connection.RemoteIpAddress is null || !System.Net.IPAddress.IsLoopback(context.Connection.RemoteIpAddress))
    {context.Response.StatusCode=403;return;}
    if(!DashboardEndpoints.TrustedHost(context.Request.Host) || !DashboardEndpoints.TrustedOrigin(context.Request.Headers.Origin.FirstOrDefault()))
    {context.Response.StatusCode=403;return;}
    context.Response.Headers["X-Content-Type-Options"]="nosniff";
    context.Response.Headers["Referrer-Policy"]="no-referrer";
    context.Response.Headers["Content-Security-Policy"]="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' ws://127.0.0.1:5080 ws://127.0.0.1:5173; frame-ancestors 'none'; object-src 'none'; base-uri 'self'";
    if(context.Request.Path!="/health" && !DashboardEndpoints.PublicUi(context.Request))
    {
        var raw=context.Request.Headers.Authorization.ToString();
        var bearer=raw.StartsWith("Bearer ",StringComparison.Ordinal)&&CryptographicOperations.FixedTimeEquals(tokenHash,SHA256.HashData(Encoding.UTF8.GetBytes(raw[7..])));
        if(!bearer && !(DashboardEndpoints.UiPath(context.Request.Path)&&DashboardEndpoints.SessionAuthorized(context)))
        {context.Response.StatusCode=401;return;}
    }
    try{await next();}
    catch(Exception e) when(e is ArgumentException or InvalidOperationException or InvalidDataException or KeyNotFoundException or JsonException)
    {context.Response.StatusCode=400;await context.Response.WriteAsJsonAsync(new{error=e.Message});}
    catch(Exception e)
    {app.Logger.LogError("Request failed: {ExceptionType}",e.GetType().Name);context.Response.StatusCode=503;await context.Response.WriteAsJsonAsync(new{error="DEPENDENCY_UNAVAILABLE"});}
});
app.MapGet("/health",()=>new{mode="SIMULATION",liveEnabled=false,ordersSupported=false,aiEnabled=false});
app.MapDashboard(uiToken);
app.MapGet("/policy",()=>policy);
app.MapGet("/api/broker/status",(PaperFeedService feed)=>feed.Status());
async Task<IResult> PaperObservation(string kind,PaperFeedService feed,CancellationToken ct)
{
    if(!paperConfig.Enabled)return Results.Json(new{error="PAPER_DATA_DISABLED"},statusCode:503);
    var snapshot=await store.LatestPaper(paperConfig.AccountId,kind,ct);
    if(snapshot is null)return Results.Json(new{error="PAPER_DATA_UNAVAILABLE"},statusCode:503);
    var stale=!feed.Connected || DateTimeOffset.UtcNow-snapshot.ReceivedAt>TimeSpan.FromSeconds(kind=="quote"?30:120);
    return Results.Ok(new{accountId=paperConfig.AccountId,connected=feed.Connected,stale,executable=false,
        receivedAt=snapshot.ReceivedAt,data=snapshot.Data});
}
app.MapGet("/api/broker/account",(PaperFeedService feed,CancellationToken ct)=>PaperObservation("account",feed,ct));
app.MapGet("/api/broker/positions",(PaperFeedService feed,CancellationToken ct)=>PaperObservation("positions",feed,ct));
app.MapGet("/api/market/eurusd/quote",(PaperFeedService feed,CancellationToken ct)=>PaperObservation("quote",feed,ct));
app.MapGet("/api/market/eurusd/contract",(PaperFeedService feed,CancellationToken ct)=>PaperObservation("contract",feed,ct));
app.MapGet("/api/market/eurusd/candles",async(string timeframe,PaperFeedService feed,CancellationToken ct)=>
{
    var minutes=timeframe switch {"15m"=>15,"1h"=>60,"4h"=>240,_=>throw new ArgumentException("INVALID_TIMEFRAME")};
    if(!paperConfig.Enabled)return Results.Json(new{error="PAPER_DATA_DISABLED"},statusCode:503);
    var rows=await store.PaperCandles(paperConfig.AccountId,minutes,ct:ct);
    return Results.Ok(new{accountId=paperConfig.AccountId,source="IBKR_TWS",whatToShow="MIDPOINT",connected=feed.Connected,
        executable=false,timeframe,rows,gapsFilled=false,volumeInterpretation="MIDPOINT_HAS_NO_TRADED_VOLUME"});
});
app.MapPost("/simulation/accounts",async(InitializeRequest request,CancellationToken ct)=>
{if(!request.AccountId.StartsWith("SIM-",StringComparison.Ordinal) || request.Equity!=policy.AllocatedCapital)throw new ArgumentException("Simulation requires the configured virtual allocation");await store.Initialize(AccountState.Initial(request.AccountId,request.Equity,DateTimeOffset.UtcNow,policy.CumulativeLossLimit),policy,ct);return Results.Ok();});
app.MapGet("/simulation/accounts/{account}",(string account,CancellationToken ct)=>store.State(account,ct));
app.MapPost("/simulation/strategies",async(StrategyVersion strategy,CancellationToken ct)=>
{strategy.Validate();await store.Save("strategy_versions",strategy.Hash,"SIM-PAPER",strategy,DateTimeOffset.UtcNow,strategy.Instrument,ct:ct);return new{strategy.Hash,status="CANDIDATE"};});
app.MapPost("/simulation/decisions",(DecisionCommand command,CancellationToken ct)=>store.Evaluate(command,policy,DateTimeOffset.UtcNow,ct));
app.MapGet("/simulation/decisions/{id}",(string id,CancellationToken ct)=>store.Get<StoredDecision>("trading_decisions",id,ct));
app.MapPost("/simulation/settle",async(SettleRequest r,CancellationToken ct)=>
{await store.Settle(r.AccountId,r.DecisionId,r.NetPnl,r.ObservedCosts,r.MarketAfterJson,policy,DateTimeOffset.UtcNow,ct);return Results.Ok();});
app.MapPost("/simulation/mark",async(MarkRequest r,CancellationToken ct)=>
{await store.Mark(r.AccountId,r.EventId,r.Equity,policy,DateTimeOffset.UtcNow,ct);return Results.Ok();});
app.MapPost("/simulation/valuation",async(PositionValuationRequest r,CancellationToken ct)=>
{await store.ValuePosition(r.AccountId,r.EventId,r.DecisionId,r.UnrealizedNetPnl,r.OpenCosts,r.RemainingRisk,policy,DateTimeOffset.UtcNow,ct);return Results.Ok();});
app.MapPost("/safety/stop/{account}",async(string account,CancellationToken ct)=>{await store.EmergencyStop(account,DateTimeOffset.UtcNow,ct);return Results.Ok(new{stopped=true,protectiveOrdersTouched=false});});
app.MapGet("/experiences/{account}",(string account,CancellationToken ct)=>store.Experiences(account,DateTimeOffset.UtcNow,ct:ct));
app.MapPost("/experiences/rejected-observation",async(RejectedObservation r,CancellationToken ct)=>
{await store.ObserveRejected(r.DecisionId,r.MarketAfterJson,r.BehaviorChange,DateTimeOffset.UtcNow,ct);return Results.Ok();});
app.MapPost("/experiences/{account}/similar",async(string account,SimilarityRequest r,CancellationToken ct)=>
    ExperienceSimilarity.Find(r.Features,await store.Experiences(account,r.Before,ct:ct),r.Scales,r.Instrument,r.Before)
        .Select(x=>new{episode=x.Episode,distance=x.Distance,interpretation="Statistical similarity, not predictive evidence"}));
app.MapPost("/research/backtests",async(JsonElement report,CancellationToken ct)=>
{
    var hash=report.GetProperty("run_hash").GetString()??throw new ArgumentException("run_hash required");
    if(hash.Length!=64||!report.TryGetProperty("dataset_hash",out _)||!report.TryGetProperty("trades",out var trades)||trades.ValueKind!=JsonValueKind.Array)
        throw new ArgumentException("Invalid backtest report");
    await store.Save("backtest_runs",hash,"SIM-PAPER",report,DateTimeOffset.UtcNow,ct:ct);
    var index=0;foreach(var trade in trades.EnumerateArray())await store.Save("backtest_trades",hash+":"+index++,"SIM-PAPER",trade,DateTimeOffset.UtcNow,ct:ct);
    return Results.Ok(new{hash,source="offline-research-unverified",liveApproval=false});
});
await app.RunAsync();
public sealed record InitializeRequest(string AccountId,decimal Equity);
public sealed record SettleRequest(string AccountId,string DecisionId,decimal NetPnl,decimal ObservedCosts,string MarketAfterJson);
public sealed record MarkRequest(string AccountId,string EventId,decimal Equity);
public sealed record PositionValuationRequest(string AccountId,string EventId,string DecisionId,decimal UnrealizedNetPnl,decimal OpenCosts,decimal RemainingRisk);
public sealed record SimilarityRequest(string Instrument,DateTimeOffset Before,Dictionary<string,decimal> Features,Dictionary<string,decimal> Scales);
public sealed record RejectedObservation(string DecisionId,string MarketAfterJson,string BehaviorChange);
public partial class Program { }
