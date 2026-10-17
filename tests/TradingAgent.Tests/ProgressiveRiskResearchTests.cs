using System.Text.Json;
using TradingAgent.Core;
using TradingAgent.ResearchLab;
using Xunit;

namespace TradingAgent.Tests;

public class ProgressiveRiskResearchTests
{
    private static readonly DateTimeOffset At=new(2026,8,4,12,0,0,TimeSpan.Zero);
    private static ResearchSignal Signal(DateTimeOffset? at=null,decimal stop=.005m,decimal target=.05m,string side="BUY")
        =>new("trend",side,at??At,at??At,1,stop,target,[],JsonSerializer.SerializeToElement(new{}));
    private static ResearchCosts Costs(decimal open=.05m,decimal close=.05m)=>new(.00005m,open,close,0,.00045m,.00005m,.01m,.01m,1,"SYNTHETIC_ONLY");
    private static PaperCandle Bar(DateTimeOffset at,decimal low=1,decimal high=1,decimal open=1,decimal close=1)
        =>new(at,15,open,high,low,close,null,null);

    [Theory][InlineData(.01)][InlineData(.02)][InlineData(.03)][InlineData(.05)][InlineData(.075)][InlineData(.10)][InlineData(.125)][InlineData(.15)]
    public void EveryRateKeepsExposureFundedCostsInRiskAndCannotAuthorize(double rate)
    {
        var ledger=new ResearchLedger();var x=SimulationSizer.Size(ledger,Signal(),Costs(),(decimal)rate);
        Assert.True(x.ConditionalAdmissible);Assert.True(x.TotalRisk<=100*(decimal)rate);
        Assert.True(x.Notional+x.Commission+x.Spread+x.Slippage<=100);
        Assert.Equal(x.StopLoss+x.Commission+x.Spread+x.Slippage+x.GapReserve,x.TotalRisk);
        Assert.Equal(x.GrossTarget-x.Commission-x.Spread-x.Slippage-x.GapReserve,x.ConservativeNetTarget);
        Assert.False(x.ExecutionAuthorized);Assert.False(x.LiveEnabled);Assert.True(x.OddLot);
    }
    [Fact] public void FifteenPercentIsAnOfflineCeilingAndOperativeRiskStillRejectsIt()
    {
        Assert.Throws<ArgumentException>(()=>SimulationSizer.Size(new(),Signal(),Costs(),.20m));
        Assert.Throws<ArgumentException>(()=>new RiskPolicy(MaximumRisk:.15m).Validate());
        Assert.Throws<ArgumentException>(()=>PaperRiskProfile.Candidate(new RiskPolicy()).Validate());
        Assert.Equal(.005m,new RiskPolicy().MaximumRisk);
    }
    [Theory][InlineData(.01)][InlineData(.02)][InlineData(.03)]
    public void ObservedFourDollarFeesExceedLowRiskBudget(double rate)
    {
        var x=SimulationSizer.Size(new(),Signal(),Costs(2,2),(decimal)rate);
        Assert.False(x.ConditionalAdmissible);Assert.Equal("COMMISSION_EXCEEDS_RISK_BUDGET",x.Reason);Assert.Equal(0,x.Quantity);
    }
    [Fact] public void MoreRiskWithoutMoreExposureDoesNotFixNegativeTarget()
    {
        var s=Signal(target:.001m);var low=SimulationSizer.Size(new(),s,Costs(2,2),.05m);
        var high=SimulationSizer.Size(new(),s,Costs(2,2),.15m);
        Assert.False(low.ConditionalAdmissible);Assert.False(high.ConditionalAdmissible);
        Assert.Equal(low.Quantity,high.Quantity);Assert.True(high.ConservativeNetTarget<0);
    }
    [Fact] public void WinsContinueWithoutQuotaThenFirstLossBlocksSameDay()
    {
        var ledger=new ResearchLedger();
        foreach(var (id,net) in new[]{("a",4m),("b",3m),("c",-10m)})
        {ledger.Begin(id,At);Assert.True(ledger.Settle(id,At,net,0,true));}
        Assert.Equal("DAILY_FIRST_LOSS_STOP",ledger.EntryBlock(At));Assert.Equal(97,ledger.Equity);
        Assert.Equal(10,ledger.ConsumedLoss);Assert.Null(ledger.EntryBlock(At.AddDays(1)));
    }
    [Fact] public void FirstOperationLossStopsDayAndBreakEvenIsNotWin()
    {
        var ledger=new ResearchLedger();ledger.Begin("a",At);ledger.Settle("a",At,-1,0,true);
        Assert.Equal("DAILY_FIRST_LOSS_STOP",ledger.EntryBlock(At));
        var zero=new ResearchLedger();zero.Begin("a",At);zero.Settle("a",At,0,0,true);
        Assert.Equal("DAILY_BREAK_EVEN_STOP",zero.EntryBlock(At));
    }
    [Fact] public void SantoDomingoDayDoesNotResetAtUtcMidnight()
    {
        var at=new DateTimeOffset(2026,8,5,0,30,0,TimeSpan.Zero);var ledger=new ResearchLedger();
        ledger.Begin("a",at);ledger.Settle("a",at,-1,0,true);
        Assert.Equal(new DateOnly(2026,8,4),ResearchScope.Day(at));
        Assert.Equal("DAILY_FIRST_LOSS_STOP",ledger.EntryBlock(at.AddHours(3)));
        Assert.Null(ledger.EntryBlock(new(2026,8,5,4,0,0,TimeSpan.Zero)));
    }
    [Fact] public void PartialUncertainOrLateCommissionRetainsLockAcrossDayAndRestart()
    {
        var ledger=new ResearchLedger();ledger.Begin("a",At);
        Assert.False(ledger.Settle("a",At,5,null,true));Assert.True(ledger.ManagementRequired);
        Assert.False(ledger.Settle("a",At,5,2,false));
        var saved=JsonSerializer.Deserialize<LedgerSnapshot>(JsonSerializer.Serialize(ledger.Snapshot()))!;
        var restarted=new ResearchLedger(saved);
        Assert.Equal("RESULT_RECONCILIATION_PENDING",restarted.EntryBlock(At.AddDays(1)));
        Assert.True(restarted.Settle("a",At.AddDays(1),3,2,true));Assert.Null(restarted.EntryBlock(At.AddDays(1)));
    }
    [Fact] public void LossBudgetPersistsAndWinnersNeverRestoreIt()
    {
        var ledger=new ResearchLedger();ledger.Begin("a",At);ledger.Settle("a",At,-10,0,true);
        ledger=new(ledger.Snapshot());ledger.Begin("b",At.AddDays(1));ledger.Settle("b",At.AddDays(1),20,0,true);
        Assert.Equal(10,ledger.ConsumedLoss);ledger.Begin("c",At.AddDays(1));ledger.Settle("c",At.AddDays(1),-10,0,true);
        Assert.Equal(100,ledger.Equity);Assert.Equal("CUMULATIVE_LOSS_LIMIT",ledger.EntryBlock(At.AddDays(2)));
    }
    [Fact] public void FictitiousCapitalAndPaperLedgerCannotEnterResearch()
    {
        Assert.Throws<ArgumentException>(()=>new ResearchLedger(new("SIMULATION",1000000,20,[],null,At)));
        Assert.Throws<ArgumentException>(()=>new ResearchLedger(new("PAPER_TRADING",100,20,[],null,At)));
    }
    [Fact] public void NoTradeCreatesNoPositionOutcomeOrDailyLoss()
    {
        var result=ProgressiveRiskSimulation.Run("trend",[Bar(At)],
            [Signal() with {Reasons=["NO_TRADE"]}],[],Costs(),.1m);
        Assert.Equal(0,result.Metrics.Admitted);Assert.Equal(1,result.Metrics.NoTradeCandidates);
        Assert.Empty(result.Trades);Assert.Empty(result.Ledger.Results);Assert.Null(result.Metrics.WinRate);
    }
    [Fact] public void SimulationAppliesOriginalStopFirstAndDailyPolicy()
    {
        var bars=new[]{Bar(At,.994m,1.06m),Bar(At.AddMinutes(15),1,1.06m),Bar(At.AddDays(1),1,1.06m)};
        var result=ProgressiveRiskSimulation.Run("trend",bars,[Signal(),Signal(At.AddMinutes(15)),Signal(At.AddDays(1))],[],Costs(),.1m);
        Assert.Equal(2,result.Metrics.Admitted);Assert.Equal("STOP_AMBIGUOUS",result.Trades[0].Trade.Reason);
        Assert.True(result.Trades[1].Trade.NetPnl>0);Assert.Equal(1,result.Metrics.FirstLossDays);
        Assert.Equal(1,result.Rejections["DAILY_FIRST_LOSS_STOP"]);
    }
    [Fact] public void GapAndNextOpenExitUseSharedResearchSemantics()
    {
        var bars=new[]{Bar(At),Bar(At.AddMinutes(15),.97m,.99m,.98m,.98m)};
        var s=Signal();var result=ProgressiveRiskSimulation.Run("trend",bars,[s],[],Costs(),.1m);
        Assert.Equal(.98m,Assert.Single(result.Trades).Trade.Exit);Assert.Equal("STOP",result.Trades[0].Trade.Reason);
        var rule=ProgressiveRiskSimulation.Run("trend",[Bar(At),Bar(At.AddMinutes(15),1.01m,1.01m,1.01m,1.01m)],
            [s],[new("trend","BUY",At.AddMinutes(15))],Costs(),.1m);
        Assert.Equal("RULE_EXIT_NEXT_OPEN",Assert.Single(rule.Trades).Trade.Reason);
    }
    [Fact] public void ChronologyAndFutureFeaturesAreRejected()
    {
        Assert.Throws<ArgumentException>(()=>ProgressiveRiskSimulation.Run("trend",[Bar(At.AddMinutes(15)),Bar(At)],[Signal()],[],Costs(),.1m));
        var s=Signal() with {Context=JsonSerializer.SerializeToElement(new {frame=new {as_of=At.AddDays(1)}})};
        Assert.Throws<ArgumentException>(()=>ProgressiveRiskSimulation.Run("trend",[Bar(At)],[s],[],Costs(),.1m));
    }
    [Fact] public void ExistingPositionPreventsOverlappingEntry()
    {
        var bars=new[]{Bar(At),Bar(At.AddMinutes(15)),Bar(At.AddMinutes(30),1,1.06m)};
        var result=ProgressiveRiskSimulation.Run("trend",bars,[Signal(),Signal(At.AddMinutes(15))],[],Costs(),.1m);
        Assert.Single(result.Trades);Assert.Equal(1,result.Rejections["RESULT_RECONCILIATION_PENDING"]);
    }
}
