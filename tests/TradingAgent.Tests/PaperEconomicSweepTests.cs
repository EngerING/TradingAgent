using System.Text.Json;
using TradingAgent.Core;
using Xunit;

namespace TradingAgent.Tests;
public class PaperEconomicSweepTests
{
    private static readonly DateTimeOffset At=new(2026,9,28,0,0,0,TimeSpan.Zero);
    private static ResearchCosts Costs=new(.00005m,2,2,0,.00045m,.00005m,.01m,.01m,1,"ESTIMATED_TEST");
    private static ResearchSignal Signal(int i=0)=>new("trend","BUY",At.AddMinutes(i*15),At.AddMinutes(i*15),1,.001m,.003m,[],JsonSerializer.SerializeToElement(new{}));
    [Theory][InlineData(1)][InlineData(5)][InlineData(10)][InlineData(20)][InlineData(30)][InlineData(50)]
    public void HypotheticalExposureNeverAuthorizesExecutionAndRiskIncludesAllCosts(int exposure)
    {
        var r=new RiskRequest("EUR/USD","BUY",.999975m,1.000025m,.999m,1,1,.01m,.01m,1,100,4,0,.00045m,.00005m,At,
            Execution:new("ESTIMATED_TEST","SIMULATION","SIMULATED",At,2,2,TakeProfit:1.003m));
        var x=RiskEngine.SizePaperOfflineScenario(AccountState.Initial("SIM",100,At),r,exposure);
        Assert.False(x.ExecutionAuthorized);Assert.False(x.MarginVerified);Assert.True(x.Risk<=10);
        Assert.True(x.Notional<=100*exposure);Assert.Equal(4+x.Quantity*.00155m,x.Risk);
    }
    [Fact] public void MinimumNetTargetIsStrictlyPositiveAndPreviousLatticeSizeIsNot()
    {
        var x=RiskEngine.MinimumPaperOpportunitySize(Signal(),Costs);
        Assert.True(x.ConservativeNetTarget>0);Assert.True(x.WithinTenDollarRisk);
        Assert.True((x.Quantity!.Value-.01m)*(.003m-.00055m)-4<=0);
        Assert.Equal(x.StopLoss+x.Costs+x.GapReserve,x.TotalRisk);
    }
    [Fact] public void NoSizeCanOvercomePerUnitCostsAboveTarget()
    {
        var x=RiskEngine.MinimumPaperOpportunitySize(Signal() with{TakeProfitDistance=.0004m},Costs);
        Assert.Null(x.Quantity);Assert.False(x.WithinTenDollarRisk);
    }
    [Fact] public void FirstLossStopsDayAndNextDayDoesNotRestoreConsumedLoss()
    {
        var bars=new[]{new PaperCandle(At,15,1,1,.998m,1,null,null),new PaperCandle(At.AddMinutes(15),15,1,1.004m,1,1,null,null),
            new PaperCandle(At.AddDays(1),15,1,1.004m,1,1,null,null)};
        var result=PaperEconomicSweep.Run("trend",bars,[Signal(),Signal(1),Signal() with{EntryAt=At.AddDays(1),SignalAt=At.AddDays(1)}],[],Costs,50);
        Assert.Equal(2,result.Metrics.Trades);Assert.Single(result.Metrics.DailyStops);
        Assert.True(result.Trades[1].NetPnl>0);Assert.Equal(-result.Trades[0].NetPnl,result.Metrics.ConsumedLoss);
        Assert.Equal("DAILY_FIRST_LOSS_STOP",result.Metrics.DailyStops[0].Reason);
    }
    [Fact] public void MillionDollarPaperBalanceCannotSizeOfflineScenario()
    {
        var r=new RiskRequest("EUR/USD","BUY",1,1,.999m,1,1,1,1,1,100,0,0,0,0,At,
            Execution:new("TEST","SIMULATION","SIMULATED",At,0,0,TakeProfit:1.003m));
        Assert.Throws<ArgumentException>(()=>RiskEngine.SizePaperOfflineScenario(AccountState.Initial("SIM",1000000,At),r,50));
    }
}
