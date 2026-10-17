using System.Text.Json;
using System.Text.Json.Nodes;
using TradingAgent.Core;
using TradingAgent.Infrastructure;
using Xunit;

namespace TradingAgent.Tests;
public class PaperLabJournalTests
{
    private static string Scope()=>"PAPER-"+Evidence.Hash(Guid.NewGuid().ToString())[..16];
    private static JsonElement State(string account,bool live=false,object? experience=null)=>JsonSerializer.SerializeToElement(new {
        environment="PAPER_TRADING",live_enabled=live,account_key=account,orders=new{},
        experiences=experience??new Dictionary<string,object>()});
    private static JsonElement Event=>JsonSerializer.SerializeToElement(new{reason="SYNTHETIC_TEST"});
    private static JsonObject DiagnosticState(string account)=>new() {
        ["environment"]="PAPER_TRADING",["live_enabled"]=false,["account_key"]=account,["experiences"]=new JsonObject(),
        ["orders"]=new JsonObject { ["experiment"]=new JsonObject {
            ["intent"]="experiment",["category"]="PAPER_DIAGNOSTIC",["session_id"]="one-session",["quantity"]="100",
            ["fills"]=new JsonObject { ["buy"]=new JsonObject { ["quantity"]="100",["side"]="BUY" } },
            ["commissions"]=new JsonObject { ["buy"]=new JsonObject { ["amount"]="2",["currency"]="USD" } },
            ["timeout_close_sent"]=true,["close_deadline_at"]="2026-10-05T14:01:00Z"
        } }
    };
    private static async Task AssertDiagnosticMutationRejected(Action<JsonObject> mutate,string reason)
    {
        var conn=Environment.GetEnvironmentVariable("TRADING_TEST_DB")!;await new PostgresStore(conn).Migrate();
        var id=Scope();var j=new PaperLabJournal(conn);var state=DiagnosticState(id);
        await j.Commit(id,0,JsonSerializer.SerializeToElement(state),Event);mutate(state);
        var error=await Assert.ThrowsAsync<InvalidOperationException>(()=>j.Commit(id,1,JsonSerializer.SerializeToElement(state),Event));
        Assert.Equal(reason,error.Message);var recovered=await new PaperLabJournal(conn).Load(id);
        Assert.Equal(1,recovered.Revision);Assert.Equal("100",recovered.State!.Value.GetProperty("orders").GetProperty("experiment").GetProperty("quantity").GetString());
    }
    [DatabaseFact] public Task DiagnosticAttemptCannotBeErasedOnRestart()=>AssertDiagnosticMutationRejected(
        s=>s["orders"]!.AsObject().Clear(),"LAB_DIAGNOSTIC_HISTORY_RESET_FORBIDDEN");
    [DatabaseFact] public Task DiagnosticQuantityAndSessionRemainBound()=>AssertDiagnosticMutationRejected(
        s=>s["orders"]!["experiment"]!["quantity"]="101","LAB_DIAGNOSTIC_INTENT_IMMUTABLE");
    [DatabaseFact] public Task DiagnosticFillHistoryCannotBeRewritten()=>AssertDiagnosticMutationRejected(
        s=>s["orders"]!["experiment"]!["fills"]!["buy"]!["quantity"]="0","LAB_DIAGNOSTIC_EXECUTION_HISTORY_IMMUTABLE");
    [DatabaseFact] public Task DiagnosticCloseAttemptCannotBeReset()=>AssertDiagnosticMutationRejected(
        s=>s["orders"]!["experiment"]!["timeout_close_sent"]=false,"LAB_DIAGNOSTIC_ATTEMPT_RESET_FORBIDDEN");
    [DatabaseFact] public Task DiagnosticSecondExperimentIsRejectedAcrossSessions()=>AssertDiagnosticMutationRejected(
        s=>s["orders"]!["another"]=new JsonObject { ["category"]="PAPER_DIAGNOSTIC",["session_id"]="new-session" },"LAB_SINGLE_DIAGNOSTIC_ONLY");
    private static async Task AssertRecoveryMutationRejected(Action<JsonObject> mutate,string reason)
    {
        var conn=Environment.GetEnvironmentVariable("TRADING_TEST_DB")!;await new PostgresStore(conn).Migrate();
        var id=Scope();var j=new PaperLabJournal(conn);var state=DiagnosticState(id);
        var record=new JsonObject { ["order_id"]=4,["authorization_id"]="one-use",["quantity"]="100",["side"]="SELL",["price"]="1.1" };
        state["recovery_authorizations"]=new JsonObject { ["one-use"]=record.DeepClone() };
        state["orders"]!["experiment"]!["recovery_orders"]=new JsonObject { ["4"]=record.DeepClone() };
        state["orders"]!["experiment"]!["recovery_order_ids"]=new JsonArray(4);
        await j.Commit(id,0,JsonSerializer.SerializeToElement(state),Event);mutate(state);
        var error=await Assert.ThrowsAsync<InvalidOperationException>(()=>j.Commit(id,1,JsonSerializer.SerializeToElement(state),Event));
        Assert.Equal(reason,error.Message);Assert.Equal(1,(await new PaperLabJournal(conn).Load(id)).Revision);
    }
    [DatabaseFact] public Task ConsumedRecoveryAuthorizationCannotBeReset()=>AssertRecoveryMutationRejected(
        s=>s["recovery_authorizations"]!.AsObject().Clear(),"LAB_RECOVERY_AUTHORIZATION_RESET_FORBIDDEN");
    [DatabaseFact] public Task RecoveryOrderQuantityCannotBeRewritten()=>AssertRecoveryMutationRejected(
        s=>s["orders"]!["experiment"]!["recovery_orders"]!["4"]!["quantity"]="101","LAB_RECOVERY_ORDER_IMMUTABLE");
    [DatabaseFact] public Task RecoveryOrderIdentityCannotBeErased()=>AssertRecoveryMutationRejected(
        s=>s["orders"]!["experiment"]!["recovery_order_ids"]!.AsArray().Clear(),"LAB_RECOVERY_HISTORY_RESET_FORBIDDEN");
    [DatabaseFact] public async Task JournalPersistsScopeRevisionAndRestartWithoutReset()
    {
        var conn=Environment.GetEnvironmentVariable("TRADING_TEST_DB")!;await new PostgresStore(conn).Migrate();
        var id=Scope();var journal=new PaperLabJournal(conn);Assert.Equal(0,(await journal.Load(id)).Revision);
        await journal.Commit(id,0,State(id),Event);var recovered=await new PaperLabJournal(conn).Load(id);
        Assert.Equal(1,recovered.Revision);Assert.Equal(id,recovered.State!.Value.GetProperty("account_key").GetString());
        await Assert.ThrowsAsync<InvalidOperationException>(()=>journal.Commit(id,0,State(id),Event));
        Assert.Equal(1,(await journal.Load(id)).Revision);
    }
    [DatabaseFact] public async Task ConcurrentReservationsCannotBothCommit()
    {
        var conn=Environment.GetEnvironmentVariable("TRADING_TEST_DB")!;await new PostgresStore(conn).Migrate();var id=Scope();
        var a=new PaperLabJournal(conn);var b=new PaperLabJournal(conn);
        async Task<bool> Attempt(PaperLabJournal j){try{await j.Commit(id,0,State(id),Event);return true;}catch(InvalidOperationException){return false;}}
        var results=await Task.WhenAll(Attempt(a),Attempt(b));Assert.Single(results,x=>x);
    }
    [DatabaseFact] public async Task CompletedExperienceIsImmutableAndConflictRollsBackState()
    {
        var conn=Environment.GetEnvironmentVariable("TRADING_TEST_DB")!;await new PostgresStore(conn).Migrate();var id=Scope();var j=new PaperLabJournal(conn);
        var experiences=new Dictionary<string,object>{{id+":trade",new{category="PAPER_DIAGNOSTIC",net="-4",simulated=true}}};
        await j.Commit(id,0,State(id,experience:experiences),Event);await j.Commit(id,1,State(id,experience:experiences),Event);
        experiences[id+":trade"]=new{category="PAPER_DIAGNOSTIC",net="100",simulated=true};
        await Assert.ThrowsAsync<InvalidOperationException>(()=>j.Commit(id,2,State(id,experience:experiences),Event));
        Assert.Equal(2,(await j.Load(id)).Revision);
    }
    [Fact] public async Task RawIdentityAndLiveCannotEnterTheJournal()
    {
        var j=new PaperLabJournal("unused");var id=Scope();
        await Assert.ThrowsAsync<ArgumentException>(()=>j.Commit(id,0,State(id,true),Event));
        await Assert.ThrowsAsync<ArgumentException>(()=>j.Load("DU12345678"));
        var raw=JsonSerializer.SerializeToElement(new{environment="PAPER_TRADING",live_enabled=false,account_key=id,account="DUR12345678",experiences=new{}});
        await Assert.ThrowsAsync<ArgumentException>(()=>j.Commit(id,0,raw,Event));
    }
    [Fact] public void StrategyPaperUsesExistingRiskAndRejectsUnverifiedCostsAndRealConstraints()
    {
        var now=DateTimeOffset.UtcNow;var p=new RiskPolicy();var a=AccountState.Initial("PAPER-STRATEGY",100,now);
        a=a with {Capital=a.Capital! with {Environment="PAPER_TRADING"}};
        var r=RiskTests.Request() with {MarketAt=now,Execution=RiskTests.Execution with{Environment="PAPER_TRADING",At=now,QuoteStatus="LIVE",
            OpeningCommission=2,ClosingCommission=2,EquivalentRealAccount=new(1,1,1,1,true,true,true)},CommissionFixedRoundTrip=4};
        Assert.Equal("COST_EXCEEDS_RISK_BUDGET",RiskEngine.Evaluate(p,a,r,now).Reason);
        Assert.Equal("EXECUTION_DATA_INCOMPLETE",RiskEngine.Evaluate(p,a,r with {Execution=null},now).Reason);
        Assert.Equal(100,a.Capital.Equity);Assert.Equal(20,a.Capital.LossAllowance);
    }
}
