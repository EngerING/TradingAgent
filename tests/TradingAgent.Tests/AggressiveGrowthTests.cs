using System.Text.Json;
using System.Text.Json.Nodes;
using Npgsql;
using TradingAgent.Api;
using TradingAgent.Core;
using TradingAgent.Infrastructure;
using Xunit;

namespace TradingAgent.Tests;

public class AggressiveGrowthTests
{
    static JsonObject Portfolio()=>JsonSerializer.SerializeToNode(new {
        initial_capital="100",cash_equity="100",equity="100",realized_gross="0",realized_net="0",
        fees="0",spread_cost="0",slippage_cost="0",financing_cost="0",consumed_loss="0",
        peak_equity="100",maximum_drawdown="0",current_drawdown="0",active=(object?)null,trades=Array.Empty<object>()
    })!.AsObject();
    static JsonObject Payload(string id)=>new() {
        ["experiment"]=id,["scope"]="AGGRESSIVE_GROWTH_R20",["classification"]="SHADOW_SIMULATED",
        ["broker_orders"]=0,["live_enabled"]=false,["at"]="2026-10-09T17:00:00Z",["event"]="EXPERIMENT_PREREGISTERED",
        ["state"]=new JsonObject {
            ["protocol"]=new JsonObject {["profile"]="AGGRESSIVE_GROWTH_R20",["initial_capital_usd"]="100",["price_risk_fraction"]="0.20",["max_leverage"]="10",["broker_orders_enabled"]=false,["live_enabled"]=false,["openai_budget_usd"]="0"},
            ["engine_hash"]=new string('a',64),["strategy_version"]=new string('b',64),["status"]="PREPARED_SHADOW",["run_kind"]="FORWARD",
            ["started_at"]="2026-10-09T17:00:00Z",["updated_at"]="2026-10-09T17:00:00Z",["stop_requested"]=false,
            ["seen"]=new JsonArray(),["signals"]=new JsonArray(),["events"]=new JsonArray(),
            ["portfolios"]=new JsonObject {["R20"]=Portfolio(),["BASELINE_1X"]=Portfolio()},
            ["paper"]=new JsonObject {["state"]="BLOCKED",["authorization_granted"]=false}
        }
    };
    static JsonElement Element(JsonNode n)=>JsonSerializer.SerializeToElement(n);
    static ShadowEvent Event(JsonObject p,long revision=1,string previous="")
    {
        var raw=p.ToJsonString();var material=$"[{revision},{raw},{JsonSerializer.Serialize(previous)}]";
        return new(revision,raw,previous,Evidence.Hash(material),material);
    }
    [Fact] public void IndependentInitialCapitalAccepted()=>AggressiveGrowthStore.Validate(Element(Payload("x")),null);
    [Theory][InlineData("live_enabled",true)][InlineData("broker_orders",1)][InlineData("classification","IBKR_PAPER")]
    public void RejectsBrokerAuthority(string field,object value)
    {var p=Payload("x");p[field]=JsonSerializer.SerializeToNode(value);Assert.Throws<InvalidDataException>(()=>AggressiveGrowthStore.Validate(Element(p),null));}
    [Theory][InlineData("initial_capital_usd","1000000")][InlineData("max_leverage","11")][InlineData("price_risk_fraction","0.21")][InlineData("openai_budget_usd","1")]
    public void RejectsChangedPolicy(string field,string value)
    {var p=Payload("x");p["state"]!["protocol"]![field]=value;Assert.Throws<InvalidDataException>(()=>AggressiveGrowthStore.Validate(Element(p),null));}
    [Fact] public void CannotClaimPaperEligibility()
    {var p=Payload("x");p["state"]!["paper"]!["authorization_granted"]=true;Assert.Throws<InvalidDataException>(()=>AggressiveGrowthStore.Validate(Element(p),null));}
    [Fact] public void CannotResetSeenSignals()
    {var old=Payload("x");old["state"]!["seen"]!.AsArray().Add("signal");var p=old.DeepClone();p["state"]!["seen"]=new JsonArray();Assert.Throws<InvalidDataException>(()=>AggressiveGrowthStore.Validate(Element(p),old.ToJsonString()));}
    [Fact] public void CannotReenableStoppedExperiment()
    {var old=Payload("x");old["state"]!["status"]="STOPPED";var p=old.DeepClone();p["state"]!["status"]="SHADOW_RUNNING";Assert.Throws<InvalidDataException>(()=>AggressiveGrowthStore.Validate(Element(p),old.ToJsonString()));}
    [Theory][InlineData("run_kind","HISTORICAL")][InlineData("engine_hash","changed")][InlineData("strategy_version","changed")]
    public void CannotReinterpretPreregisteredHistory(string field,string value)
    {var old=Payload("x");var p=old.DeepClone();p["state"]![field]=value;Assert.Throws<InvalidDataException>(()=>AggressiveGrowthStore.Validate(Element(p),old.ToJsonString()));}
    [Fact] public void CannotInjectCashOrBrokerBuyingPower()
    {var p=Payload("x");p["state"]!["portfolios"]!["R20"]!["cash_equity"]="1000000";Assert.Throws<InvalidDataException>(()=>AggressiveGrowthStore.Validate(Element(p),null));}
    [Fact] public void CannotClearDurableStopLatch()
    {
        var old=Payload("x");old["state"]!["stop_requested"]=true;old["state"]!["status"]="STOPPING_MANAGING_SHADOW";
        var next=old.DeepClone();next["state"]!["stop_requested"]=false;
        Assert.Throws<InvalidDataException>(()=>AggressiveGrowthStore.Validate(Element(next),old.ToJsonString()));
    }
    [Fact] public void CannotRewindJournalClock()
    {
        var old=Payload("x");var next=old.DeepClone();next["state"]!["updated_at"]="2026-10-09T16:59:59Z";
        Assert.Throws<InvalidDataException>(()=>AggressiveGrowthStore.Validate(Element(next),old.ToJsonString()));
    }
    [DatabaseFact] public async Task ConcurrentWritersHaveExactlyOneWinnerAndRejectedCasLeavesHeadIntact()
    {
        var cs=Environment.GetEnvironmentVariable("TRADING_TEST_DB")!;await new PostgresStore(cs).Migrate();
        var id="aggressive-r20-"+Guid.NewGuid().ToString("N");var p=Payload(id);
        var head=await new AggressiveGrowthStore(cs).Execute(id,Event(p));
        async Task<bool> Write(string reason)
        {
            var next=(JsonObject)p.DeepClone();next["event"]=reason;
            try {await new AggressiveGrowthStore(cs).Execute(id,Event(next,2,head.Hash));return true;}
            catch(InvalidDataException e) when(e.Message=="R20_INTEGRITY_OR_CAS_CONFLICT"){return false;}
        }
        var outcomes=await Task.WhenAll(Write("FIRST"),Write("SECOND"));
        Assert.Single(outcomes,x=>x);Assert.Single(outcomes,x=>!x);
        var committed=await new AggressiveGrowthStore(cs).Execute(id,null);
        Assert.Equal(2,committed.Revision);
        await Assert.ThrowsAsync<InvalidDataException>(()=>new AggressiveGrowthStore(cs).Execute(id,Event(p,3,head.Hash)));
        Assert.Equal(committed,await new AggressiveGrowthStore(cs).Execute(id,null));
    }
    [Fact] public void SignalREmitsOnlyNewR20Slice()
    {
        JsonElement Snapshot(string equity)=>JsonSerializer.SerializeToElement(new{aggressiveGrowth=new{equity},system=new{},studyStatus="SHADOW_RUNNING",experiments=Array.Empty<object>(),market=new{},prediction=new{},openPositions=Array.Empty<object>(),trades=Array.Empty<object>(),calibration=new{},research=new{},notifications=Array.Empty<object>()});
        var before=Snapshot("100");var after=Snapshot("99");
        Assert.Contains(DashboardChanges.Diff(before,after),x=>x.Type=="aggressiveGrowth.updated");
        Assert.DoesNotContain(DashboardChanges.Diff(after,after),x=>x.Type=="aggressiveGrowth.updated");
    }
    [Theory][InlineData(0,"RECENT_JOURNAL")][InlineData(181,"STALE")][InlineData(-1,"STALE")]
    public void FreshnessCannotAdvertiseDeadRunner(int age,string expected)
    {var now=DateTimeOffset.UtcNow;var s=new JsonObject{["updatedAt"]=now.AddSeconds(-age).ToString("O"),["status"]="SHADOW_RUNNING"};AggressiveGrowthFreshness.Apply(s,now);Assert.Equal(expected,s["evidenceQuality"]!.GetValue<string>());}
    [Theory][InlineData("¿Cómo está funcionando R20?",true)][InlineData("¿Cuánto capital queda?",true)][InlineData("¿Qué habría sucedido sin apalancamiento?",true)][InlineData("¿Kronos apoyaba la señal?",true)][InlineData("Compara R1 R5 R10",false)][InlineData("Comisiones de R10",false)]
    public void LocalQueriesSelectOwnCohort(string q,bool expected)=>Assert.Equal(expected,AggressiveGrowthChat.Matches(q));
    [Fact] public void CachedForecastCannotRetainAgreementAfterExpiry()
    {
        var now=DateTimeOffset.UtcNow;
        var state=new JsonObject{["updatedAt"]=now.ToString("O"),["status"]="SHADOW_RUNNING",
            ["kronos"]=new JsonObject{["status"]="OBSERVER_ONLY",["agreement"]="AGREE",["expiresAt"]=now.AddSeconds(-1).ToString("O")}};
        AggressiveGrowthFreshness.Apply(state,now);
        Assert.Null(state["kronos"]!["agreement"]);
        Assert.Equal("KRONOS_UNAVAILABLE",state["kronos"]!["status"]!.GetValue<string>());
    }
    [Fact] public void SolPreservesUnknownCostsAndUsesNoModelBudget()
    {
        var view=JsonSerializer.SerializeToElement(new{equity="100",status="PREPARED_SHADOW",evidenceQuality="RECENT_JOURNAL",
            commissions=(string?)null,baseline=new{equity="100",closedTrades=0},kronos=new{status="KRONOS_UNAVAILABLE",agreement=(string?)null},shadowTrades=0});
        var response=AggressiveGrowthChat.Respond(new(Guid.NewGuid(),"R20 comisiones"),JsonSerializer.SerializeToElement(new{prediction=new{}}),view);
        Assert.Null(response["metrics"]![4]!["value"]);
        Assert.Equal(0,response["usage"]!["estimatedCostUsd"]!.GetValue<int>());
        Assert.Null(response["command"]);Assert.Contains("no ha transmitido órdenes",response["text"]!.GetValue<string>());
    }
    [DatabaseFact] public async Task JournalSurvivesRestartAndRejectsTamperingAndHistoricalOverwrite()
    {
        var cs=Environment.GetEnvironmentVariable("TRADING_TEST_DB")!;await new PostgresStore(cs).Migrate();
        var id="aggressive-r20-"+Guid.NewGuid().ToString("N");var s=new AggressiveGrowthStore(cs);var p=Payload(id);var head=await s.Execute(id,Event(p));
        Assert.Equal(head,await new AggressiveGrowthStore(cs).Execute(id,null));
        await Assert.ThrowsAsync<InvalidDataException>(()=>s.Execute(id,Event(p)));
        await Assert.ThrowsAsync<InvalidDataException>(()=>s.Execute(id,Event(p,2,head.Hash) with{Hash="forged"}));
        await using var c=new NpgsqlConnection(cs);await c.OpenAsync();
        await using var cmd=new NpgsqlCommand("DELETE FROM aggressive_growth.events WHERE experiment_id=$1",c);cmd.Parameters.AddWithValue(id);
        await Assert.ThrowsAsync<PostgresException>(()=>cmd.ExecuteNonQueryAsync());
    }
    [Fact] public async Task RefusesLiveOrUnapprovedDatabase()=>await Assert.ThrowsAsync<InvalidDataException>(()=>new AggressiveGrowthStore("Host=127.0.0.1;Port=5432;Username=other;Database=postgres").Execute("aggressive-r20-"+Guid.NewGuid().ToString("N"),null));
}
