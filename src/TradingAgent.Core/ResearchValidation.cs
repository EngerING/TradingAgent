namespace TradingAgent.Core;

public sealed record ResearchMetrics(int Trades,decimal? GrossGains,decimal? GrossLosses,decimal? Costs,
    decimal? NetProfit,decimal? ClosedTradeMaximumDrawdown,decimal? ProfitFactor,decimal? Expectancy,int? MaximumLossStreak,
    string Basis);
public sealed record ResearchPartition(string DatasetRole,DateTimeOffset Start,DateTimeOffset End,
    ResearchBacktestResult[] VerifiableEvaluations,ResearchBacktestResult[] EstimatedFeeLowerBoundScenarios,
    ResearchMetrics[] Metrics,bool ParametersFrozen,bool Optimized);

public static class ResearchValidation
{
    public static ResearchMetrics Metrics(ResearchBacktestResult result)
    {
        var trades=result.Trades;
        if(trades.Length==0 || result.NetProfit is null)return new(trades.Length,null,null,null,null,null,null,null,null,"NOT_EVALUABLE_NO_ADMITTED_TRADES_OR_UNKNOWN_COSTS");
        decimal equity=result.InitialCapital,peak=equity,drawdown=0;int streak=0,longest=0;
        foreach(var trade in trades)
        {
            equity+=trade.NetPnl;peak=Math.Max(peak,equity);drawdown=Math.Max(drawdown,(peak-equity)/peak);
            streak=trade.NetPnl<0?streak+1:0;longest=Math.Max(longest,streak);
        }
        var wins=trades.Where(t=>t.NetPnl>0).Sum(t=>t.NetPnl);var losses=-trades.Where(t=>t.NetPnl<0).Sum(t=>t.NetPnl);
        return new(trades.Length,trades.Where(t=>t.GrossPnl>0).Sum(t=>t.GrossPnl),
            -trades.Where(t=>t.GrossPnl<0).Sum(t=>t.GrossPnl),trades.Sum(t=>t.Costs),trades.Sum(t=>t.NetPnl),drawdown,
            losses>0?wins/losses:null,trades.Sum(t=>t.NetPnl)/trades.Length,longest,"ESTIMATED_COST_SCENARIO_CLOSED_TRADE_EQUITY_NOT_INTRABAR_DRAWDOWN");
    }
    public static ResearchPartition[] Evaluate(PaperCandle[] bars,ResearchSignal[] signals,ResearchExit[] exits,
        RiskPolicy policy,DateTimeOffset start,DateTimeOffset split,DateTimeOffset end)
    {
        if(!(start<split && split<end))throw new ArgumentException("INVALID_CHRONOLOGICAL_SPLIT");
        // Deliberately favorable lower bounds for other costs demonstrate whether fees alone are prohibitive.
        // This is an explicit estimate, never evidence of account tariffs or a source of executable decisions.
        var estimate=new ResearchCosts(0,2,2,0,0,0,1,1,1,"ESTIMATED_USD2_PER_ORDER_OTHER_COSTS_LOWER_BOUND_ZERO_UNVERIFIED_ACCOUNT");
        return new[]{("development",start,split),("validation",split,end)}.Select(p=>
        {
            var sample=bars.Where(b=>b.OpenedAt>=p.Item2 && b.OpenedAt.AddMinutes(15)<=p.Item3).ToArray();
            var s=signals.Where(s=>(s.EntryAt??s.SignalAt)>=p.Item2 && (s.EntryAt??s.SignalAt)<p.Item3).ToArray();
            var available=sample.Select(b=>b.OpenedAt).ToHashSet();
            // A partition-ending signal has no admissible next bar in that partition.
            s=s.Select(signal=>signal.EntryAt is DateTimeOffset at && !available.Contains(at)?
                signal with{EntryAt=null,EntryMidpoint=null,Reasons=signal.Reasons.Append("NO_ENTRY_BAR_IN_PARTITION").ToArray()}:signal).ToArray();
            var strategies=new[]{"trend","pullback","mean_reversion"};
            var actual=strategies.Select(id=>ResearchSimulation.Run(id,sample,s,exits,policy)).ToArray();
            var hypothetical=strategies.Select(id=>ResearchSimulation.Run(id,sample,s,exits,policy,estimate)).ToArray();
            return new ResearchPartition(p.Item1,p.Item2,p.Item3,actual,hypothetical,actual.Select(Metrics).ToArray(),true,false);
        }).ToArray();
    }
}
