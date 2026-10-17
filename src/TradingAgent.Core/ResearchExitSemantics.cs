namespace TradingAgent.Core;

public sealed record ResearchExitPosition(string StrategyId,string Side,decimal Entry,decimal Stop,decimal Target,DateTimeOffset EntryAt);
public sealed record ResearchExitDecision(bool Exit,decimal? Price,string Reason,DateTimeOffset At);

// Original D/D.1 precedence, shared by research and the Paper decision adapter. No broker methods.
public static class ResearchExitSemantics
{
    public const string Version="research-d-exits-v1";
    public static ResearchExitDecision Decide(ResearchExitPosition p,PaperCandle bar,DateTimeOffset previousOpenedAt,
        ResearchExit[] exits,bool opening,bool riskHalt=false,bool endOfSample=false)
    {
        if(p.Side is not ("BUY" or "SELL") || p.Entry<=0 || p.Stop<=0 || p.Target<=0 || bar.Minutes!=15 ||
           bar.Open<=0 || bar.Low<=0 || bar.High<Math.Max(bar.Open,bar.Close) || bar.Low>Math.Min(bar.Open,bar.Close) ||
           previousOpenedAt>bar.OpenedAt || bar.OpenedAt<p.EntryAt)
            throw new ArgumentException("INVALID_EXIT_OBSERVATION");
        if(opening)
            return exits.Any(e=>e.StrategyId==p.StrategyId && e.Side==p.Side && e.At<=bar.OpenedAt && e.At>previousOpenedAt)
                ? new(true,bar.Open,"RULE_EXIT_NEXT_OPEN",bar.OpenedAt) : new(false,null,"HOLD",bar.OpenedAt);
        var buy=p.Side=="BUY";var stop=buy?bar.Low<=p.Stop:bar.High>=p.Stop;
        var target=buy?bar.High>=p.Target:bar.Low<=p.Target;var at=bar.OpenedAt.AddMinutes(15);
        if(stop)return new(true,buy?Math.Min(bar.Open,p.Stop):Math.Max(bar.Open,p.Stop),target?"STOP_AMBIGUOUS":"STOP",at);
        if(target)return new(true,p.Target,"TAKE_PROFIT",at);
        if(riskHalt)return new(true,bar.Close,"RISK_HALT_CLOSE",at);
        if(endOfSample)return new(true,bar.Close,"END_OF_SAMPLE",at);
        return new(false,null,"HOLD",at);
    }
}

// The continuous runner calls this same adapter; replay preserves exact original model prices.
public static class StrategyPaperExitAdapter
{
    public static ResearchExitDecision Decide(ResearchExitPosition position,PaperCandle bar,DateTimeOffset previousOpenedAt,
        ResearchExit[] exits,bool opening,bool riskHalt=false,bool endOfSample=false)
        => ResearchExitSemantics.Decide(position,bar,previousOpenedAt,exits,opening,riskHalt,endOfSample);

    public static ResearchExitDecision Replay(ResearchExitPosition position,PaperCandle[] bars,ResearchExit[] exits)
    {
        var sample=bars.Where(b=>b.OpenedAt>=position.EntryAt).ToArray();
        for(var i=0;i<sample.Length;i++)
        {
            var b=sample[i];
            if(i>0)
            {
                var opening=Decide(position,b,sample[i-1].OpenedAt,exits,true);
                if(opening.Exit)return opening;
            }
            var closed=Decide(position,b,i>0?sample[i-1].OpenedAt:b.OpenedAt,exits,false,endOfSample:i==sample.Length-1);
            if(closed.Exit)return closed;
        }
        throw new ArgumentException("NO_EXIT_SAMPLE");
    }
}
