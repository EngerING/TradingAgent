using System.Text.Json;
using Npgsql;
using TradingAgent.Core;
using TradingAgent.Infrastructure;
using Xunit;

namespace TradingAgent.Tests;
public sealed class DatabaseFactAttribute : FactAttribute
{
    public DatabaseFactAttribute() { if(string.IsNullOrEmpty(Environment.GetEnvironmentVariable("TRADING_TEST_DB")))Skip="Set TRADING_TEST_DB to a disposable PostgreSQL database"; }
}
public class PostgresTests
{
    private static string Connection=>Environment.GetEnvironmentVariable("TRADING_TEST_DB")!;
    private static async Task<(PostgresStore Store,RiskPolicy Policy,string Account,StrategyVersion Strategy)> Setup()
    {
        var store=new PostgresStore(Connection);await store.Migrate();
        var id=Guid.NewGuid().ToString();var policy=new RiskPolicy(Version:"test-"+id,MaxLeverage:10);
        await store.Initialize(AccountState.Initial("SIM-"+id,100,RiskTests.Now),policy);
        var strategy=new StrategyVersion(id,"Test",1,"EUR/USD","15","test","stop",.001m,.002m,1000,"simulation","{}");
        await store.Save("strategy_versions",strategy.Hash,"SIM-"+id,strategy,RiskTests.Now,"EUR/USD");
        return(store,policy,"SIM-"+id,strategy);
    }
    private static DecisionCommand Command(string account,string strategy)=>new(Guid.NewGuid().ToString(),account,strategy,RiskTests.Request(),"London",new(){["rsi"]=50},"{}");
    [DatabaseFact]public async Task PersistRecoverAndReplayDecision()
    {
        var (s,p,a,v)=await Setup();var command=Command(a,v.Hash);var result=await s.Evaluate(command,p,RiskTests.Now);Assert.True(result.Evaluation.Allowed);
        var recovered=new PostgresStore(Connection);var read=await recovered.Get<StoredDecision>("trading_decisions",command.Id);Assert.Equal(result.CommandHash,read!.CommandHash);
        Assert.Equal(result.Evaluation,(await recovered.Evaluate(command,p,RiskTests.Now)).Evaluation);
        await Assert.ThrowsAsync<InvalidOperationException>(()=>recovered.Evaluate(command with{Session="NewYork"},p,RiskTests.Now));
        Assert.Equal(command.Id,(await recovered.State(a)).ReservationId);
    }
    [DatabaseFact]public async Task SettleOnceAndRetrieveExperience()
    {
        var(s,p,a,v)=await Setup();var cmd=Command(a,v.Hash);await s.Evaluate(cmd,p,RiskTests.Now);
        await s.Settle(a,cmd.Id,-.2m,.01m,"{}",p,RiskTests.Now.AddSeconds(1));
        await s.Settle(a,cmd.Id,-.2m,.01m,"{}",p,RiskTests.Now.AddSeconds(2));
        Assert.Equal(99.8m,(await s.State(a)).Equity);
        var episode=Assert.Single(await s.Experiences(a,RiskTests.Now.AddMinutes(1)));Assert.Equal(-.2m,episode.SimulatedPnl);
        Assert.Null(Assert.Single(await s.Experiences(a,RiskTests.Now.AddMilliseconds(500))).SimulatedPnl);
    }
    [DatabaseFact]public async Task ParallelDecisionsHaveOneReservation()
    {
        var(s,p,a,v)=await Setup();var results=await Task.WhenAll(Enumerable.Range(0,5).Select(_=>s.Evaluate(Command(a,v.Hash),p,RiskTests.Now)));
        Assert.Single(results,r=>r.Evaluation.Allowed);Assert.Equal(4,results.Count(r=>r.Experience.Rejected));
    }
    [DatabaseFact]public async Task EmergencyHaltSurvivesRestartWithoutDroppingPosition()
    {
        var(s,p,a,v)=await Setup();var cmd=Command(a,v.Hash);await s.Evaluate(cmd,p,RiskTests.Now);await s.EmergencyStop(a,RiskTests.Now);
        var state=await new PostgresStore(Connection).State(a);Assert.Contains("EMERGENCY_STOP",state.Halts);Assert.Equal(cmd.Id,state.ReservationId);Assert.Single(state.OpenPositions);
    }
    [DatabaseFact]public async Task PolicyAndStrategyCannotBeOverwritten()
    {
        var(s,p,a,v)=await Setup();await Assert.ThrowsAsync<InvalidOperationException>(()=>s.Save("strategy_versions",v.Hash,a,v with{StopDistance=.01m},RiskTests.Now));
        await Assert.ThrowsAsync<PostgresException>(()=>s.Save("strategy_versions",(v with{StopDistance=.01m}).Hash,a,v with{StopDistance=.01m},RiskTests.Now));
        await using var c=new NpgsqlConnection(Connection);await c.OpenAsync();await using var cmd=new NpgsqlCommand("UPDATE risk_policies SET payload='{}'::jsonb WHERE id=$1",c);cmd.Parameters.AddWithValue(p.Version);
        await Assert.ThrowsAsync<PostgresException>(()=>cmd.ExecuteNonQueryAsync());
    }
    [DatabaseFact]public async Task PolicyCannotChangeUnderSameVersion()
    {
        var(s,p,a,v)=await Setup();await Assert.ThrowsAsync<InvalidOperationException>(()=>s.Evaluate(Command(a,v.Hash),p with{DailyLimit=.1m},RiskTests.Now));
    }
    [DatabaseFact]public async Task MarkLossHaltsAndNewInstanceRetainsState()
    {
        var(s,p,a,_)=await Setup();await s.Mark(a,"mark-"+a,99,p,RiskTests.Now);var recovered=await new PostgresStore(Connection).State(a);Assert.Contains("DAILY_LIMIT",recovered.Halts);
    }
    [DatabaseFact]public async Task RejectedSignalsKeepLaterObservationsWithoutFakeProfit()
    {
        var(s,p,a,v)=await Setup();var cmd=Command(a,v.Hash) with{Request=RiskTests.Request(.01m)};
        Assert.True((await s.Evaluate(cmd,p,RiskTests.Now)).Experience.Rejected);
        await s.ObserveRejected(cmd.Id,"{\"spread\":0.001}","Spread widened",RiskTests.Now.AddHours(1));
        var e=Assert.Single(await s.Experiences(a,RiskTests.Now.AddHours(2)));Assert.Null(e.SimulatedPnl);Assert.Equal("Spread widened",e.BehaviorChange);
    }
    [DatabaseFact]public async Task AllRequiredEntitiesCanRoundTrip()
    {
        var(s,_,a,_)=await Setup();foreach(var table in new[]{"market_candles","market_snapshots","strategies","backtest_runs","backtest_trades","strategy_approvals","system_events"})
        {var id=Guid.NewGuid().ToString();await s.Save(table,id,a,new{sample="fixture"},RiskTests.Now,"EUR/USD",15);var value=await s.Get<JsonElement>(table,id);Assert.Equal("fixture",value.GetProperty("sample").GetString());}
    }
    [DatabaseFact]public async Task RetentionAggregatesAndKeepsPinnedCandles()
    {
        var(s,_,a,_)=await Setup();var at=new DateTimeOffset(2020,1,6,0,0,0,TimeSpan.Zero);
        await s.Save("market_candles",a+"-1",a,new{low=1m,high=2m,close=1.5m,volume=(decimal?)null,pinned=false},at,"TEST",15);
        await s.Save("market_candles",a+"-2",a,new{low=1m,high=2m,close=1.5m,volume=(decimal?)null,pinned=true},at.AddMinutes(15),"TEST",15);
        await using var c=new NpgsqlConnection(Connection);await c.OpenAsync();await using var cmd=new NpgsqlCommand("SELECT aggregate_and_prune_candles('2021-01-01'::timestamptz)",c);await cmd.ExecuteScalarAsync();
        Assert.Null(await s.Get<object>("market_candles",a+"-1"));Assert.NotNull(await s.Get<object>("market_candles",a+"-2"));
        await using var summary=new NpgsqlCommand("SELECT samples FROM daily_market_stats WHERE account_id=$1",c);summary.Parameters.AddWithValue(a);Assert.Equal(1L,await summary.ExecuteScalarAsync());
    }
}
