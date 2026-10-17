using System.Text.Json;
using TradingAgent.Core;
using Xunit;

namespace TradingAgent.Tests;

public class ResearchExitEquivalenceTests
{
    private static readonly DateTimeOffset Start=new(2026,9,28,0,0,0,TimeSpan.Zero);
    private static PaperCandle Bar(int i,decimal open=1,decimal low=1,decimal high=1)=>new(Start.AddMinutes(15*i),15,open,high,low,open,null,null);
    [Theory]
    [InlineData("BUY","STOP")][InlineData("SELL","STOP")]
    [InlineData("BUY","TAKE_PROFIT")][InlineData("SELL","TAKE_PROFIT")]
    [InlineData("BUY","STOP_AMBIGUOUS")][InlineData("SELL","STOP_AMBIGUOUS")]
    [InlineData("BUY","GAP")][InlineData("SELL","GAP")]
    [InlineData("BUY","RULE_EXIT_NEXT_OPEN")][InlineData("SELL","RULE_EXIT_NEXT_OPEN")]
    [InlineData("BUY","END_OF_SAMPLE")][InlineData("SELL","END_OF_SAMPLE")]
    public void ResearchAndPaperReplayHaveSameExitForSameCandles(string side,string scenario)
    {
        var buy=side=="BUY";var sign=buy?1m:-1m;var bars=new[]{Bar(0),Bar(1),Bar(2),Bar(3)};
        ResearchExit[] exits=[];var expected=scenario;decimal price=1;
        if(scenario=="STOP"){bars[1]=Bar(1,1,buy?.985m:1,buy?1:1.015m);price=1-sign*.01m;}
        if(scenario=="TAKE_PROFIT"){bars[1]=Bar(1,1,buy?1:.975m,buy?1.025m:1);price=1+sign*.02m;}
        if(scenario=="STOP_AMBIGUOUS"){bars[1]=Bar(1,1,.97m,1.03m);price=1-sign*.01m;}
        if(scenario=="GAP"){price=1-sign*.015m;bars[2]=Bar(2,price,price,price);expected="STOP";}
        if(scenario=="RULE_EXIT_NEXT_OPEN")
        {
            price=1+sign*.003m;bars[2]=Bar(2,price,price,price);
            exits=[new("trend",side,Start.AddMinutes(30))];
        }
        var s=new ResearchSignal("trend",side,Start.AddMinutes(15),Start.AddMinutes(15),1,.01m,.02m,[],JsonSerializer.SerializeToElement(new{}));
        var research=ResearchSimulation.Run("trend",bars,[s],exits,new(),new(0,0,0,0,0,0,1,1,1,"SYNTHETIC_TEST"));
        var trade=Assert.Single(research.Trades);
        var paper=StrategyPaperExitAdapter.Replay(new("trend",side,1,1-sign*.01m,1+sign*.02m,Start.AddMinutes(15)),bars,exits);
        Assert.True(paper.Exit);Assert.Equal(expected,paper.Reason);Assert.Equal(price,paper.Price);
        Assert.Equal(trade.Exit,paper.Price);Assert.Equal(trade.ExitAt,paper.At);Assert.Equal(trade.Reason,paper.Reason);
    }
    [Fact] public void NextOpenRulePrecedesGapStopExactlyAsOriginalSpecification()
    {
        var p=new ResearchExitPosition("trend","BUY",1,.99m,1.02m,Start);
        var b=Bar(1,.98m,.97m,1.03m);
        var decision=StrategyPaperExitAdapter.Decide(p,b,Start,[new("trend","BUY",b.OpenedAt)],true);
        Assert.Equal("RULE_EXIT_NEXT_OPEN",decision.Reason);Assert.Equal(.98m,decision.Price);
    }
    [Fact] public void FutureAndOtherSideRuleExitsCannotClosePosition()
    {
        var p=new ResearchExitPosition("trend","BUY",1,.99m,1.02m,Start);
        Assert.False(StrategyPaperExitAdapter.Decide(p,Bar(1),Start,
            [new("trend","SELL",Start.AddMinutes(15)),new("trend","BUY",Start.AddMinutes(30))],true).Exit);
    }
    [Fact] public void TargetGapDoesNotImproveOriginalTargetPrice()
    {
        var p=new ResearchExitPosition("trend","BUY",1,.99m,1.02m,Start);
        var d=StrategyPaperExitAdapter.Decide(p,Bar(1,1.03m,1.03m,1.03m),Start,[],false);
        Assert.Equal(1.02m,d.Price);Assert.Equal("TAKE_PROFIT",d.Reason);
    }
    [Theory][InlineData("trend")][InlineData("pullback")][InlineData("mean_reversion")]
    public void FrozenAuthenticSixMonthSequencesReplayOriginalResearchExits(string strategy)
    {
        var root=Path.GetFullPath("../../../../..",AppContext.BaseDirectory);
        using var doc=JsonDocument.Parse(File.ReadAllText(Path.Combine(root,
            "artifacts/research/6dd3f0c7e256f1c86fdb397133513a2896ab57822250b0e2748ca1acd6e6ab40.extended.json")));
        var a=doc.RootElement.GetProperty("research").GetProperty("analysis");
        Assert.Equal("bb95c4d5394704af60d7c4ccde15710f504daddf1463f3b9ac44c68f39e87c8c",a.GetProperty("dataset_hash").GetString());
        var bars=a.GetProperty("normalized").GetProperty("15").EnumerateArray().Select(b=>new PaperCandle(
            b.GetProperty("opened_at").GetDateTimeOffset(),15,b.GetProperty("open").GetDecimal(),b.GetProperty("high").GetDecimal(),
            b.GetProperty("low").GetDecimal(),b.GetProperty("close").GetDecimal(),null,null)).ToArray();
        var signals=a.GetProperty("candidates").EnumerateArray().Where(s=>s.GetProperty("strategy_id").GetString()==strategy)
            .Select(s=>new ResearchSignal(strategy,s.GetProperty("side").GetString()!,s.GetProperty("signal_at").GetDateTimeOffset(),
                s.GetProperty("entry_at").ValueKind==JsonValueKind.Null?null:s.GetProperty("entry_at").GetDateTimeOffset(),
                s.GetProperty("entry_midpoint").ValueKind==JsonValueKind.Null?null:s.GetProperty("entry_midpoint").GetDecimal(),
                s.GetProperty("stop_distance").GetDecimal(),s.GetProperty("take_profit_distance").GetDecimal(),
                s.GetProperty("reasons").EnumerateArray().Select(x=>x.GetString()!).ToArray(),s.GetProperty("context"))).ToArray();
        var exits=a.GetProperty("exit_signals").EnumerateArray().Where(e=>e.GetProperty("strategy_id").GetString()==strategy)
            .Select(e=>new ResearchExit(strategy,e.GetProperty("side").GetString()!,e.GetProperty("at").GetDateTimeOffset())).ToArray();
        // Zero-cost fixture isolates original exit semantics, not an economic forecast or changed strategy.
        var research=ResearchSimulation.Run(strategy,bars,signals,exits,new(),new(0,0,0,0,0,0,.01m,.01m,1,"EXIT_EQUIVALENCE_FIXTURE_ONLY"));
        var compared=0;
        foreach(var trade in research.Trades.Where(t=>t.Reason!="RISK_HALT_CLOSE"))
        {
            var s=Assert.Single(signals,s=>s.EntryAt==trade.EntryAt && s.Side==trade.Side);
            var sign=trade.Side=="BUY"?1m:-1m;
            var replay=StrategyPaperExitAdapter.Replay(new(strategy,trade.Side,trade.Entry,
                trade.Entry-sign*s.StopDistance,trade.Entry+sign*s.TakeProfitDistance,trade.EntryAt),bars,exits);
            Assert.Equal(trade.Exit,replay.Price);Assert.Equal(trade.Reason,replay.Reason);Assert.Equal(trade.ExitAt,replay.At);compared++;
        }
        Assert.True(compared>0,"Authentic sequences must include research exits to prove model equivalence.");
    }
}
