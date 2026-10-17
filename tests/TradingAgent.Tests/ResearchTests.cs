using System.Text.Json;
using TradingAgent.Api;
using TradingAgent.Core;
using TradingAgent.Infrastructure;
using Xunit;

namespace TradingAgent.Tests;

public class ResearchTests
{
    private static readonly DateTimeOffset Start=new(2026,9,28,0,0,0,TimeSpan.Zero);
    private static ResearchSignal Signal(int index=1,string side="BUY",string[]? reasons=null)=>
        new("trend",side,Start.AddMinutes(index*15),Start.AddMinutes(index*15),1,.01m,.02m,reasons??[],JsonSerializer.SerializeToElement(new{}));
    private static PaperCandle[] Bars(int count=3)=>Enumerable.Range(0,count).Select(i=>new PaperCandle(Start.AddMinutes(i*15),15,1,1,1,1,null,null)).ToArray();
    private static ResearchCosts Costs(decimal spread=0,decimal open=0,decimal close=0,decimal slip=0)=>new(spread,open,close,0,slip,0,1,1,1,"explicit-synthetic-reference");
    [Fact] public void MissingCostsRejectEveryHypotheticalTradeAndKeepNetUnknown()
    {
        var result=ResearchSimulation.Run("trend",Bars(),[Signal()],[],new());
        Assert.Equal("INCOMPLETE_COSTS",result.Status);Assert.Null(result.NetProfit);Assert.Empty(result.Trades);
        Assert.False(Assert.Single(result.Assessments).Accepted);Assert.Contains("EXECUTION_DATA_INCOMPLETE",result.Assessments[0].Reasons);
        Assert.Equal(100,result.FinalEquity);Assert.Equal(20,result.LossAllowance);Assert.Equal(0,result.ConsumedLoss);
    }
    [Theory][InlineData("BUY",.98,1.03)][InlineData("SELL",.97,1.03)]
    public void AmbiguousBarsUseStopFirstAndCoreSizing(string side,double low,double high)
    {
        var bars=Bars();bars[1]=bars[1] with {Low=(decimal)low,High=(decimal)high};
        var r=ResearchSimulation.Run("trend",bars,[Signal(side:side)],[],new(),Costs());
        var trade=Assert.Single(r.Trades);Assert.Equal("STOP_AMBIGUOUS",trade.Reason);Assert.Equal(25,trade.Quantity);
        Assert.Equal(-.25m,trade.NetPnl);Assert.Equal(.25m,r.ConsumedLoss);Assert.Equal(99.75m,r.FinalEquity);
    }
    [Fact] public void RoundTripCostsIncludeBothCommissionsSpreadAndSlippageOnce()
    {
        var bars=Bars();bars[1]=bars[1] with {Low=.98m};
        var r=ResearchSimulation.Run("trend",bars,[Signal()],[],new(),Costs(.0002m,.01m,.02m,.0001m));
        var trade=Assert.Single(r.Trades);Assert.Equal(21,trade.Quantity);Assert.Equal(.0363m,trade.Costs);
        Assert.Equal(-.2463m,trade.NetPnl);Assert.Equal(trade.NetPnl,r.NetProfit);
    }
    [Fact] public void KnownTargetGainsDoNotReplenishAccumulatedLoss()
    {
        var bars=Bars(4);bars[1]=bars[1] with {Low=.98m};bars[2]=bars[2] with {High=1.03m};
        var r=ResearchSimulation.Run("trend",bars,[Signal(),Signal(2)],[],new(),Costs());
        Assert.Equal(2,r.Trades.Length);Assert.True(r.Trades[1].NetPnl>0);Assert.Equal(.25m,r.ConsumedLoss);
        Assert.Equal(r.Trades.Sum(t=>t.NetPnl),r.NetProfit);
    }
    [Fact] public void CoreViabilityRejectsExpensiveOrOversizedResearchTrades()
    {
        foreach(var c in new[]{Costs(open:1,close:1),Costs() with{MinimumQuantity=20000}})
        {
            var r=ResearchSimulation.Run("trend",Bars(),[Signal()],[],new(),c);
            Assert.False(Assert.Single(r.Assessments).Accepted);Assert.Empty(r.Trades);
        }
    }
    [Fact] public void GapLossExhaustsBudgetAndBlocksSubsequentEntries()
    {
        var bars=Bars(4);bars[2]=bars[2] with {Open=.1m,High=.1m,Low=.1m,Close=.1m};
        var r=ResearchSimulation.Run("trend",bars,[Signal(),Signal(3)],[],new(),Costs());
        Assert.Equal(-22.5m,Assert.Single(r.Trades).NetPnl);
        Assert.Equal(22.5m,r.ConsumedLoss);Assert.False(r.Assessments[1].Accepted);
        Assert.Equal(20,r.LossAllowance);
    }
    [Fact] public void ClosedBarExitExecutesAtNextOpen()
    {
        var bars=Bars(4);bars[2]=bars[2] with {Open=1.005m,High=1.005m,Low=1.005m,Close=1.005m};
        var exit=new ResearchExit("trend","BUY",Start.AddMinutes(30));
        var r=ResearchSimulation.Run("trend",bars,[Signal()],[exit],new(),Costs());
        var trade=Assert.Single(r.Trades);Assert.Equal("RULE_EXIT_NEXT_OPEN",trade.Reason);
        Assert.Equal(Start.AddMinutes(30),trade.ExitAt);Assert.Equal(.125m,trade.NetPnl);
    }
    [Fact] public void ContextRejectionIsPreservedEvenIfEconomicScenarioIsFeasible()
    {
        var r=ResearchSimulation.Run("trend",Bars(),[Signal(reasons:["MULTITIMEFRAME_INSUFFICIENT_DATA"])],[],new(),Costs());
        Assert.Empty(r.Trades);Assert.True(r.Assessments[0].Risk!.Allowed);Assert.False(r.Assessments[0].Accepted);
    }
    [Fact] public void FutureFeatureOrMismatchedEntryIsRejected()
    {
        var signal=Signal() with {SignalAt=Start.AddMinutes(31)};
        Assert.Throws<ArgumentException>(()=>ResearchSimulation.Run("trend",Bars(),[signal],[],new(),Costs()));
        signal=Signal() with {EntryMidpoint=2};
        Assert.Throws<ArgumentException>(()=>ResearchSimulation.Run("trend",Bars(),[signal],[],new(),Costs()));
        signal=Signal() with {Context=JsonSerializer.SerializeToElement(new{h1=new{as_of=Start.AddDays(1)}})};
        Assert.Throws<ArgumentException>(()=>ResearchSimulation.Run("trend",Bars(),[signal],[],new(),Costs()));
    }
    [Fact] public void AllocatedCapitalCannotBeReplacedByPaperBalance()
    {
        Assert.Throws<ArgumentException>(()=>ResearchSimulation.Run("trend",Bars(),[Signal()],[],new(AllocatedCapital:1000000),Costs()));
        var r=ResearchSimulation.Run("trend",Bars(),[Signal()],[],new(),Costs());
        Assert.All(r.Assessments,a=>Assert.True(a.Risk!.NominalExposure<=100));
    }
    [Fact] public void RejectedTradesAndFutureBarsDoNotChangeEarlierSizing()
    {
        var a=ResearchSimulation.Run("trend",Bars(),[Signal()],[],new(),Costs());
        var bars=Bars(8);bars[^1]=bars[^1] with {High=100};
        var b=ResearchSimulation.Run("trend",bars,[Signal()],[],new(),Costs());
        Assert.Equal(a.Assessments[0].Risk,b.Assessments[0].Risk);
    }
    [DatabaseFact] public async Task OfflinePipelinePersistsVersionsSignalsAndOriginalsIdempotently()
    {
        var root=Path.GetFullPath("../../../../..",AppContext.BaseDirectory);
        var store=new PostgresStore(Environment.GetEnvironmentVariable("TRADING_TEST_DB")!);await store.Migrate();
        var source="PAPER-"+Guid.NewGuid().ToString("N")[..16];var received=DateTimeOffset.UtcNow;
        foreach(var minutes in new[]{15,60,240})
        {
            var bars=Enumerable.Range(0,3).Select(i=>new PaperCandle(Start.AddMinutes(i*minutes),minutes,1,1.1m,.9m,1,null,null)).ToArray();
            await store.SavePaper(new("candles",source,received,JsonSerializer.SerializeToElement(bars,PaperData.Json)),source,received);
        }
        var cutoff=Start.AddDays(2);var unavailable=Path.Combine(root,".local","unused-originals-"+Guid.NewGuid().ToString("N"));
        var a=await ResearchRunner.Run(store,new(),source,root,cutoff,Path.Combine(root,"config/forex-sessions.json"),Path.Combine(root,"config/research-indicators.json"),originalDirectory:unavailable);
        var b=await ResearchRunner.Run(store,new(),source,root,cutoff,Path.Combine(root,"config/forex-sessions.json"),Path.Combine(root,"config/research-indicators.json"),originalDirectory:unavailable);
        Assert.Equal(a.GetProperty("runId").GetString(),b.GetProperty("runId").GetString());
        var id=a.GetProperty("runId").GetString()!;
        Assert.NotNull(await store.Get<object>("market_snapshots",id+":originals"));
        Assert.NotNull(await store.Get<object>("backtest_runs",id+":trend"));
        Assert.Equal(3,(await store.PaperCandles(source,240)).Count);
        Assert.False(a.GetProperty("openaiEnabled").GetBoolean());Assert.False(a.GetProperty("ordersSupported").GetBoolean());
    }
}
