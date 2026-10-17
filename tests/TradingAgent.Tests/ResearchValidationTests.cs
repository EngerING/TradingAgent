using System.Text.Json;
using TradingAgent.Core;
using Xunit;

namespace TradingAgent.Tests;
public class ResearchValidationTests
{
    private static readonly DateTimeOffset Start=new(2026,4,3,0,0,0,TimeSpan.Zero);
    private static ResearchSignal Signal(int i)=>new("trend","BUY",Start.AddMinutes(i*15),Start.AddMinutes(i*15),1,.01m,.02m,[],JsonSerializer.SerializeToElement(new{}));
    [Fact] public void PartitionsAreChronologicalAndFeesAloneBlockBothSamples()
    {
        var bars=Enumerable.Range(0,8).Select(i=>new PaperCandle(Start.AddMinutes(i*15),15,1,1,1,1,null,null)).ToArray();
        var partitions=ResearchValidation.Evaluate(bars,[Signal(1),Signal(5)],[],new(),Start,Start.AddHours(1),Start.AddHours(2));
        Assert.Equal(2,partitions.Length);
        foreach(var p in partitions)
        {
            Assert.True(p.ParametersFrozen);Assert.False(p.Optimized);
            Assert.Single(p.VerifiableEvaluations[0].Assessments);Assert.Null(p.Metrics[0].NetProfit);
            var estimate=p.EstimatedFeeLowerBoundScenarios[0];Assert.Empty(estimate.Trades);
            Assert.Contains("COST_EXCEEDS_RISK_BUDGET",estimate.Assessments[0].Reasons);
            Assert.Equal(100,estimate.InitialCapital);Assert.Equal(20,estimate.LossAllowance);
        }
        Assert.All(partitions[0].VerifiableEvaluations[0].Assessments,a=>Assert.True(a.Signal.EntryAt<Start.AddHours(1)));
        Assert.All(partitions[1].VerifiableEvaluations[0].Assessments,a=>Assert.True(a.Signal.EntryAt>=Start.AddHours(1)));
    }
    [Fact] public void MetricsUseKnownNetCostsAndClosedTradeDrawdown()
    {
        var values=new[]{(2m,.2m),(-1m,.1m),(-1m,.1m),(3m,.2m)};
        var trades=values.Select((v,i)=>new ResearchTrade(Start,Start.AddDays(i),"BUY",1,1,1,v.Item1,v.Item2,v.Item1-v.Item2,"reference")).ToArray();
        var r=new ResearchBacktestResult("trend","ESTIMATED_COST_SCENARIO_ONLY",100,20,102.4m,2.2m,2.4m,[],trades,"fixture","fixture");
        var m=ResearchValidation.Metrics(r);Assert.Equal(5,m.GrossGains);Assert.Equal(2,m.GrossLosses);Assert.Equal(.6m,m.Costs);
        Assert.Equal(2.4m,m.NetProfit);Assert.Equal(.6m,m.Expectancy);Assert.Equal(2,m.MaximumLossStreak);
        Assert.Equal(2.2m/101.8m,m.ClosedTradeMaximumDrawdown);Assert.Equal(4.6m/2.2m,m.ProfitFactor);
    }
    [Fact] public void UnknownCostResultsDoNotCreateProfitStatistics()
    {
        var r=new ResearchBacktestResult("trend","INCOMPLETE_COSTS",100,20,100,0,null,[],[],"UNKNOWN","");
        var m=ResearchValidation.Metrics(r);Assert.Null(m.NetProfit);Assert.Null(m.ProfitFactor);Assert.Null(m.Expectancy);Assert.Null(m.ClosedTradeMaximumDrawdown);
    }
}
