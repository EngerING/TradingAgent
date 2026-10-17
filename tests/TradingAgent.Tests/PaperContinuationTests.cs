using System.Text.Json;
using TradingAgent.Core;
using TradingAgent.Infrastructure;
using Xunit;

namespace TradingAgent.Tests;

public class PaperContinuationTests
{
    private static readonly DateTimeOffset Now=RiskTests.Now;
    private static AccountState Initial()=>AccountState.Initial("PAPER-STRATEGY",100,Now) with {
        Capital=new VirtualCapital(100,Environment:"PAPER_TRADING")};
    private static RiskRequest Request(DateTimeOffset at)=>RiskTests.Request() with {
        MarketAt=at,CommissionFixedRoundTrip=.1m,Execution=RiskTests.Execution with {
            At=at,Environment="PAPER_TRADING",Mode="ODD_LOT",QuoteStatus="LIVE",OpeningCommission=.05m,
            ClosingCommission=.05m,EquivalentRealAccount=new(1,1,.1m,1,true,true,true)}};
    private static RiskEvaluation Evaluate(AccountState a,DateTimeOffset at)=>
        PaperRiskProfile.Study(PaperRiskProfile.Experimental,new(),a,Request(at),at,"IBKR","StrategyPaper",false).Evaluation;
    private static AccountState Reserve(AccountState a,string id,DateTimeOffset at)=>
        PaperRiskProfile.Reserve(a,Request(at),id,at,new());
    private static AccountState Close(AccountState a,string id,decimal net,DateTimeOffset at)=>
        PaperRiskProfile.Settle(Reserve(a,id,at),id,net,4,true,at,new());
    private static AccountState Restart(AccountState a)=>JsonSerializer.Deserialize<AccountState>(JsonSerializer.Serialize(a))!;

    [Theory][InlineData(4,3,-10,3,"DAILY_FIRST_LOSS_STOP")]
    [InlineData(-10,0,0,1,"DAILY_FIRST_LOSS_STOP")]
    [InlineData(2,0,0,2,"DAILY_WIN_REQUIRED")]
    public void DaysABC(decimal first,decimal second,decimal third,int count,string reason)
    {
        var a=Initial();decimal[] outcomes=[first,second,third];
        for(var i=0;i<count;i++)
        {
            Assert.True(Evaluate(a,Now).Allowed);
            a=Restart(Close(a,$"trade-{i}",outcomes[i],Now));
            Assert.True(PaperRiskProfile.HistoryConsistent(a));
        }
        Assert.Equal(count,a.PaperContinuation!.ClosedTrades);
        Assert.Equal(reason,Evaluate(a,Now).Reason);
        Assert.Throws<InvalidOperationException>(()=>Reserve(a,"extra",Now));
    }

    [Fact] public void DayDCommissionPendingCannotContinueAcrossRestartOrNewDay()
    {
        var a=Close(Initial(),"win",5,Now);
        a=Reserve(a,"pending",Now);
        a=PaperRiskProfile.Settle(a,"pending",3,null,true,Now,new());
        Assert.Equal(105,a.Equity);Assert.NotNull(a.ReservationId);
        a=Restart(a);Assert.Equal("PAPER_RESULT_UNRESOLVED",Evaluate(a,Now).Reason);
        var tomorrow=Now.AddDays(1);a=PaperRiskProfile.Mark(a,tomorrow,new());
        Assert.Equal("PAPER_RESULT_UNRESOLVED",Evaluate(a,tomorrow).Reason);
        a=PaperRiskProfile.Settle(a,"pending",3,4,false,tomorrow,new());
        Assert.Equal("PAPER_RESULT_UNRESOLVED",Evaluate(a,tomorrow).Reason);
        a=PaperRiskProfile.Settle(a,"pending",3,4,true,tomorrow,new());
        Assert.Equal(108,a.Equity);Assert.True(Evaluate(a,tomorrow).Allowed);
        Assert.True(PaperRiskProfile.HistoryConsistent(a));
    }

    [Fact] public void MissingNetCannotUnlockAndLateLossStopsSettlementDay()
    {
        var a=Reserve(Initial(),"pending",Now);
        a=PaperRiskProfile.Settle(a,"pending",null,4,true,Now,new());
        var tomorrow=Now.AddDays(1);
        a=PaperRiskProfile.Settle(Restart(a),"pending",-3,4,true,tomorrow,new());
        Assert.Equal("DAILY_FIRST_LOSS_STOP",Evaluate(a,tomorrow).Reason);
        Assert.Equal(3,a.Capital!.ConsumedLoss);
    }

    [Theory][InlineData(-10)][InlineData(0)]
    public void OnlyTradingDayRolloverRestoresFirstOpportunity(decimal net)
    {
        var a=Close(Initial(),"closed",net,Now);
        Assert.False(Evaluate(Restart(a),Now).Allowed);
        // Same instant expressed in another zone cannot reset a day.
        a=PaperRiskProfile.Mark(a,Now.ToOffset(TimeSpan.FromHours(-4)),new());
        Assert.False(Evaluate(a,Now).Allowed);
        var tomorrow=Now.AddDays(1);a=PaperRiskProfile.Mark(Restart(a),tomorrow,new());
        Assert.True(Evaluate(a,tomorrow).Allowed);Assert.Equal(100+net,a.Equity);
        Assert.Equal(Math.Max(0,-net),a.Capital!.ConsumedLoss);
        Assert.Equal(net<0?9:10,Evaluate(a,tomorrow).Budget);
    }

    [Fact] public void GainsDoNotRestoreLossesAndTwentySuspendsEveryFollowingDay()
    {
        var a=Close(Initial(),"a-win",4,Now);a=Close(a,"a-win2",3,Now);a=Close(a,"a-loss",-10,Now);
        Assert.Equal(97,a.Equity);Assert.Equal(10,a.Capital!.ConsumedLoss);
        var dayB=Now.AddDays(1);a=PaperRiskProfile.Mark(Restart(a),dayB,new());
        a=Close(a,"b-win",20,dayB);
        Assert.Equal(117,a.Equity);Assert.Equal(10,a.Capital!.RemainingLoss);
        Assert.Equal(10,Evaluate(a,dayB).Budget); // dollar cap despite growth
        a=Close(a,"b-loss",-10,dayB);
        Assert.Equal(107,a.Equity);Assert.Equal(20,a.Capital!.ConsumedLoss);
        var dayC=Now.AddDays(2);a=PaperRiskProfile.Mark(Restart(a),dayC,new());
        Assert.Equal("CUMULATIVE_LOSS_LIMIT",Evaluate(a,dayC).Reason);
    }

    [Fact] public void ExactlyOneReservationAndSettlementReplayIsIdempotent()
    {
        var a=Reserve(Initial(),"one",Now);
        Assert.Throws<InvalidOperationException>(()=>Reserve(Restart(a),"two",Now));
        a=PaperRiskProfile.Settle(a,"one",-10,4,true,Now,new());a=Restart(a);
        var replay=PaperRiskProfile.Settle(a,"one",-10,4,true,Now,new());
        Assert.Same(a,replay);Assert.Equal(10,replay.Capital!.ConsumedLoss);
        Assert.Equal("DAILY_FIRST_LOSS_STOP",Evaluate(replay,Now).Reason);
        Assert.Throws<InvalidOperationException>(()=>PaperRiskProfile.Settle(a,"one",1,4,true,Now,new()));
        Assert.Throws<InvalidOperationException>(()=>Reserve(a,"one",Now.AddDays(1)));
    }

    [Fact] public void MissingOrAlteredHistoryCannotResetLossOrDayStop()
    {
        var a=Close(Initial(),"loss",-10,Now);
        Assert.Equal("PAPER_CONTINUATION_HISTORY_REQUIRED",Evaluate(a with {PaperContinuation=null},Now).Reason);
        Assert.Equal("PAPER_CONTINUATION_HISTORY_INVALID",Evaluate(a with {
            PaperContinuation=a.PaperContinuation! with {FirstLossStopped=false}},Now).Reason);
        Assert.Throws<ArgumentException>(()=>PaperRiskProfile.Mark(a,Now.AddSeconds(-1),new()));
    }

    [Fact] public void BrokerMillionCannotSizeOrSupplyCapital()
    {
        var a=Initial();Assert.True(Evaluate(a,Now).NominalExposure<=100);
        Assert.Equal("VIRTUAL_CAPITAL_MISMATCH",Evaluate(a with {Equity=1_000_000},Now).Reason);
        Assert.Throws<ArgumentException>(()=>Evaluate(a with {Capital=new(1_000_000,Environment:"PAPER_TRADING")},Now));
        a=PaperRiskProfile.Mark(a,Now,new());
        Assert.Equal("PAPER_CONTINUATION_HISTORY_INVALID",Evaluate(a with {
            Equity=1_000_000,Capital=a.Capital! with {UnrealizedGrossPnl=999_900}},Now).Reason);
    }

    [Fact] public void DayBoundaryIsMidnightUtcAndZeroNeverBecomesAWin()
    {
        var before=Now.Date.AddHours(23).AddMinutes(59);
        var at=new DateTimeOffset(before,TimeSpan.Zero);
        var a=Close(Initial(),"zero",0,at);
        a=PaperRiskProfile.Mark(a,at.AddSeconds(30),new());
        Assert.Equal("DAILY_WIN_REQUIRED",Evaluate(a,at.AddSeconds(30)).Reason);
        a=PaperRiskProfile.Mark(a,at.AddMinutes(1),new());
        Assert.True(Evaluate(a,at.AddMinutes(1)).Allowed);
    }

    [Fact] public void AutomaticQuantityHonorsAuthorizationCapAndRechecksProfitAfterCosts()
    {
        var a=Initial();var r=Request(Now) with {MaximumQuantity=5.9m};
        var risk=PaperRiskProfile.Study(PaperRiskProfile.Experimental,new(),a,r,Now,"IBKR","StrategyPaper",false).Evaluation;
        Assert.True(risk.Allowed);Assert.Equal(5,risk.Quantity);Assert.True(risk.NominalExposure<=100);
        r=r with {Execution=r.Execution! with {TakeProfit=1.1002m}};
        Assert.Equal("COST_EXCEEDS_POTENTIAL_PROFIT",PaperRiskProfile.Study(PaperRiskProfile.Experimental,new(),a,r,Now,"IBKR","StrategyPaper",false).Evaluation.Reason);
    }

    [Fact] public void CancelledUnfilledIntentReleasesReservationWithoutInventingBreakEven()
    {
        var a=Reserve(Initial(),"unfilled",Now);a=PaperRiskProfile.ReleaseUnfilled(a,"unfilled",Now,new());
        Assert.True(Evaluate(a,Now).Allowed);Assert.Equal(0,a.PaperContinuation!.ClosedTrades);
        Assert.Contains("unfilled",a.PaperContinuation.CancelledIds!);Assert.True(PaperRiskProfile.HistoryConsistent(a));
        a=Restart(a);Assert.Throws<InvalidOperationException>(()=>Reserve(a,"unfilled",Now));
        Assert.True(PaperRiskProfile.HistoryConsistent(Reserve(a,"new",Now)));
    }

    [DatabaseFact] public async Task DurableJournalPreservesPendingAndLossAndRejectsReset()
    {
        var conn=Environment.GetEnvironmentVariable("TRADING_TEST_DB")!;
        await new PostgresStore(conn).Migrate();var scope="PAPER-"+Evidence.Hash(Guid.NewGuid().ToString())[..16];
        JsonElement State(AccountState? a)=>JsonSerializer.SerializeToElement(new {
            environment="PAPER_TRADING",live_enabled=false,account_key=scope,
            strategy_account=a,experiences=new{}},Evidence.Json);
        var evt=JsonSerializer.SerializeToElement(new {reason="OFFLINE_EXPERIMENTAL_REGRESSION"});
        var j=new PaperLabJournal(conn);var a=Reserve(Initial(),"pending",Now);
        await j.Commit(scope,0,State(a),evt);
        async Task<AccountState> Load()=> (await new PaperLabJournal(conn).Load(scope)).State!.Value
            .GetProperty("strategy_account").Deserialize<AccountState>(Evidence.Json)!;
        a=await Load();Assert.Equal("PAPER_RESULT_UNRESOLVED",Evaluate(a,Now).Reason);
        await Assert.ThrowsAsync<InvalidOperationException>(()=>j.Commit(scope,1,State(PaperRiskProfile.Mark(Initial(),Now,new())),evt));
        a=PaperRiskProfile.Settle(a,"pending",-10,4,true,Now,new());
        await j.Commit(scope,1,State(a),evt);a=await Load();
        Assert.Equal("DAILY_FIRST_LOSS_STOP",Evaluate(a,Now).Reason);
        await Assert.ThrowsAsync<InvalidOperationException>(()=>j.Commit(scope,2,State(PaperRiskProfile.Mark(Initial(),Now,new())),evt));
        await Assert.ThrowsAsync<InvalidOperationException>(()=>j.Commit(scope,2,State(a with {PaperContinuation=null}),evt));
        await Assert.ThrowsAsync<InvalidOperationException>(()=>j.Commit(scope,2,State(a with {
            PaperContinuation=a.PaperContinuation! with {FirstLossStopped=false}}),evt));
        Assert.Equal(2,(await j.Load(scope)).Revision);
        var tomorrow=Now.AddDays(1);a=PaperRiskProfile.Mark(await Load(),tomorrow,new());
        await j.Commit(scope,2,State(a),evt);a=await Load();Assert.True(Evaluate(a,tomorrow).Allowed);
        Assert.Equal(10,a.Capital!.ConsumedLoss);
        a=Close(a,"second-loss",-10,tomorrow);
        await j.Commit(scope,3,State(a),evt);
        a=PaperRiskProfile.Mark(await Load(),tomorrow.AddDays(1),new());
        await j.Commit(scope,4,State(a),evt);
        Assert.Equal("CUMULATIVE_LOSS_LIMIT",Evaluate(await Load(),tomorrow.AddDays(1)).Reason);
    }
}
