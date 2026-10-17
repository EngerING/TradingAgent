using System.Text.Json;

namespace TradingAgent.Core;

public sealed record ResearchSignal(string StrategyId,string Side,DateTimeOffset SignalAt,DateTimeOffset? EntryAt,
    decimal? EntryMidpoint,decimal StopDistance,decimal TakeProfitDistance,string[] Reasons,JsonElement Context);
public sealed record ResearchExit(string StrategyId,string Side,DateTimeOffset At);
public sealed record ResearchCosts(decimal Spread,decimal OpeningCommission,decimal ClosingCommission,
    decimal CommissionPerUnitRoundTrip,decimal Slippage,decimal AdverseGap,decimal MinimumQuantity,
    decimal QuantityStep,decimal MarginRate,string Source);
public sealed record ResearchAssessment(ResearchSignal Signal,bool Accepted,string[] Reasons,RiskEvaluation? Risk);
public sealed record ResearchTrade(DateTimeOffset EntryAt,DateTimeOffset ExitAt,string Side,decimal Entry,decimal Exit,
    decimal Quantity,decimal GrossPnl,decimal Costs,decimal NetPnl,string Reason);
public sealed record ResearchBacktestResult(string StrategyId,string Status,decimal InitialCapital,decimal LossAllowance,
    decimal FinalEquity,decimal ConsumedLoss,decimal? NetProfit,ResearchAssessment[] Assessments,ResearchTrade[] Trades,
    string CostSource,string Limitation);

// Offline historical-clock simulation only. It contains no broker or order transport.
public static class ResearchSimulation
{
    private sealed record Position(ResearchSignal Signal,decimal Entry,decimal Quantity,decimal Stop,decimal Target,decimal Cost);
    public static ResearchBacktestResult Run(string strategy,PaperCandle[] bars,ResearchSignal[] signals,
        ResearchExit[] exits,RiskPolicy policy,ResearchCosts? costs=null)
    {
        policy.Validate();
        if(policy.AllocatedCapital!=100 || policy.CumulativeLossLimit!=20)throw new ArgumentException("RESEARCH_ALLOCATION_REQUIRED");
        if(costs is not null && (string.IsNullOrWhiteSpace(costs.Source) || costs.Spread<0 || costs.OpeningCommission<0 ||
            costs.ClosingCommission<0 || costs.CommissionPerUnitRoundTrip<0 || costs.Slippage<0 || costs.AdverseGap<0 ||
            costs.MinimumQuantity<=0 || costs.QuantityStep<=0 || costs.MarginRate<=0 || costs.MarginRate>1))
            throw new ArgumentException("INVALID_RESEARCH_COST_ASSUMPTIONS");
        if(bars.Any(b=>b.Minutes!=15 || b.Open<=0 || b.Low<=0 || b.High<Math.Max(b.Open,b.Close) || b.Low>Math.Min(b.Open,b.Close)) ||
            bars.Zip(bars.Skip(1)).Any(p=>p.First.OpenedAt.AddMinutes(15)>p.Second.OpenedAt))throw new ArgumentException("INVALID_RESEARCH_SERIES");
        var at=bars.FirstOrDefault()?.OpenedAt ?? DateTimeOffset.UnixEpoch;
        var account=AccountState.Initial("SIM-RESEARCH-D",100,at,20) with {PolicyVersion=policy.Version};
        var assessments=new List<ResearchAssessment>();var trades=new List<ResearchTrade>();Position? position=null;
        var candidates=signals.Where(s=>s.StrategyId==strategy).ToArray();
        foreach(var signal in candidates)
        {
            if(signal.SignalAt.Offset!=TimeSpan.Zero || signal.EntryAt is DateTimeOffset entry && (entry.Offset!=TimeSpan.Zero || entry<signal.SignalAt))
                throw new ArgumentException("INVALID_RESEARCH_TIMESTAMP");
            if(signal.Context.ValueKind==JsonValueKind.Object)
                foreach(var frame in signal.Context.EnumerateObject())
                {
                    if(frame.Value.TryGetProperty("as_of",out var cut) && DateTimeOffset.Parse(cut.GetString()!)>signal.SignalAt)
                        throw new ArgumentException("LOOK_AHEAD_CONTEXT");
                    if(frame.Value.TryGetProperty("indicators",out var indicators) && indicators.ValueKind==JsonValueKind.Object &&
                        indicators.TryGetProperty("closed_at",out var close) && DateTimeOffset.Parse(close.GetString()!)>signal.SignalAt)
                        throw new ArgumentException("LOOK_AHEAD_CONTEXT");
                }
        }
        foreach(var signal in candidates.Where(s=>s.EntryAt is null))
            assessments.Add(new(signal,false,signal.Reasons.Append("NO_ENTRY_PRICE").Distinct().ToArray(),null));
        for(var i=0;i<bars.Length;i++)
        {
            var bar=bars[i];var closed=bar.OpenedAt.AddMinutes(15);
            decimal Pnl(Position p,decimal price)=>(p.Signal.Side=="BUY"?price-p.Entry:p.Entry-price)*p.Quantity-p.Cost;
            void Settle(decimal price,string reason,DateTimeOffset when)
            {
                var p=position!;var net=Pnl(p,price);
                trades.Add(new(p.Signal.EntryAt!.Value,when,p.Signal.Side,p.Entry,price,p.Quantity,net+p.Cost,p.Cost,net,reason));
                account=account.Settle(net,p.Cost,when,policy);position=null;
            }
            if(position is not null)
            {
                account=account.ValuePosition(Pnl(position,bar.Open),position.Cost,account.OpenPositions[0].RemainingLoss,bar.OpenedAt,policy);
                var opening=ResearchExitSemantics.Decide(new(strategy,position.Signal.Side,position.Entry,position.Stop,position.Target,position.Signal.EntryAt!.Value),
                    bar,bars[Math.Max(0,i-1)].OpenedAt,exits,true);
                if(opening.Exit)Settle(opening.Price!.Value,opening.Reason,opening.At);
            }
            else account=account.Mark(account.Equity,bar.OpenedAt,policy);
            foreach(var signal in candidates.Where(s=>s.EntryAt==bar.OpenedAt))
            {
                if(signal.SignalAt>bar.OpenedAt || signal.EntryMidpoint!=bar.Open)throw new ArgumentException("LOOK_AHEAD_OR_ENTRY_MISMATCH");
                var c=costs;var mid=bar.Open;var sign=signal.Side=="BUY"?1m:-1m;
                var stop=mid-sign*signal.StopDistance;var target=mid+sign*signal.TakeProfitDistance;
                ExecutionFacts? facts=c is null?null:new(c.Source,"SIMULATION","SIMULATED",bar.OpenedAt,c.OpeningCommission,
                    c.ClosingCommission,true,true,true,true,"SIMULATED",target);
                // Missing-cost numeric placeholders cannot authorize: ExecutionFacts is null and the core fails closed.
                var request=new RiskRequest("EUR/USD",signal.Side,mid-(c?.Spread??0)/2,mid+(c?.Spread??0)/2,stop,1,1,
                    c?.MinimumQuantity??1,c?.QuantityStep??1,c?.MarginRate??1,account.Equity,
                    (c?.OpeningCommission??0)+(c?.ClosingCommission??0),c?.CommissionPerUnitRoundTrip??0,
                    c?.Slippage??0,c?.AdverseGap??0,bar.OpenedAt,Execution:facts);
                var risk=RiskEngine.Evaluate(policy,account,request,bar.OpenedAt);
                var reasons=signal.Reasons.Concat(risk.Allowed?[]:new[]{risk.Reason}).Distinct().ToArray();
                var accepted=risk.Allowed && reasons.Length==0;
                assessments.Add(new(signal,accepted,reasons,risk));
                if(accepted)
                {
                    var cost=risk.SpreadCost+risk.Commissions+risk.SlippageCost;
                    position=new(signal,mid,risk.Quantity,stop,target,cost);
                    account=account with {ReservationId="offline",OpenPositions=[new(risk.EstimatedLoss,risk.NominalExposure,risk.RequiredMargin)]};
                }
            }
            if(position is null)continue;
            var p=position;var buy=p.Signal.Side=="BUY";
            var stopHit=buy?bar.Low<=p.Stop:bar.High>=p.Stop;
            var stopPrice=buy?Math.Min(bar.Open,p.Stop):Math.Max(bar.Open,p.Stop);
            var worst=stopHit?stopPrice:buy?bar.Low:bar.High;
            account=account.ValuePosition(Pnl(p,worst),p.Cost,account.OpenPositions[0].RemainingLoss,closed,policy);
            var decision=ResearchExitSemantics.Decide(new(strategy,p.Signal.Side,p.Entry,p.Stop,p.Target,p.Signal.EntryAt!.Value),bar,
                bars[Math.Max(0,i-1)].OpenedAt,exits,false,account.Halts.Length>0,i==bars.Length-1);
            if(decision.Exit)Settle(decision.Price!.Value,decision.Reason,decision.At);
            else account=account.ValuePosition(Pnl(p,bar.Close),p.Cost,account.OpenPositions[0].RemainingLoss,closed,policy);
        }
        if(assessments.Count!=candidates.Length)throw new ArgumentException("SIGNAL_OUTSIDE_RESEARCH_SERIES");
        return new(strategy,costs is null?"INCOMPLETE_COSTS":"ESTIMATED_COST_SCENARIO_ONLY",100,20,account.Equity,
            account.Capital!.ConsumedLoss,costs is null?null:account.Capital.RealizedNetPnl,assessments.ToArray(),trades.ToArray(),
            costs?.Source??"UNKNOWN", "MIDPOINT; technical demonstration, not profitability evidence; no execution");
    }
}
