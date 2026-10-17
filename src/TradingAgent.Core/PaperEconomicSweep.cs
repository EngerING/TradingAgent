namespace TradingAgent.Core;

public sealed record PaperScenarioSize(bool ConditionalAdmissible,string Reason,decimal Budget,decimal Quantity,
    decimal Notional,decimal Exposure,decimal Risk,decimal Costs,decimal GrossTarget,decimal ConservativeNetTarget,
    decimal MaximumAffordableMarginRate,bool OddLot,bool MarginVerified=false,bool ExecutionAuthorized=false);

public static partial class RiskEngine
{
    public sealed record MinimumPaperOpportunity(decimal? Quantity,decimal? Notional,decimal? Exposure,
        decimal? StopLoss,decimal? Costs,decimal? GapReserve,decimal? TotalRisk,decimal? GrossTarget,
        decimal? ConservativeNetTarget,bool WithinTenDollarRisk,bool OddLot,
        string Status="CONDITIONAL_ONLY_MARGIN_AND_EXECUTION_UNKNOWN");
    public static MinimumPaperOpportunity MinimumPaperOpportunitySize(ResearchSignal s,ResearchCosts c)
    {
        if(s.EntryMidpoint is null || s.EntryMidpoint<=0 || s.StopDistance<=0 || s.TakeProfitDistance<=0 ||
           s.Side is not ("BUY" or "SELL") || c.Spread<0 || c.Slippage<0 || c.AdverseGap<0 ||
           c.OpeningCommission<0 || c.ClosingCommission<0 || c.CommissionPerUnitRoundTrip<0 ||
           c.MinimumQuantity<=0 || c.QuantityStep<=0)throw new ArgumentException("INVALID_MINIMUM_OPPORTUNITY");
        var unit=c.Spread+c.Slippage+c.CommissionPerUnitRoundTrip;
        var surplus=s.TakeProfitDistance-unit-c.AdverseGap;
        if(surplus<=0)return new(null,null,null,null,null,null,null,null,null,false,true,"NO_POSITIVE_NET_TARGET_AT_ANY_SIZE");
        var fees=c.OpeningCommission+c.ClosingCommission;
        var threshold=fees/surplus;
        var q=Math.Max(c.MinimumQuantity,c.MinimumQuantity+(decimal.Floor((threshold-c.MinimumQuantity)/c.QuantityStep)+1)*c.QuantityStep);
        var costs=fees+q*unit;var gap=q*c.AdverseGap;var risk=costs+gap+q*s.StopDistance;
        var nominal=q*(s.EntryMidpoint.Value+c.Spread/2);var gross=q*s.TakeProfitDistance;
        return new(q,nominal,nominal/100,q*s.StopDistance,costs,gap,risk,gross,gross-costs-gap,risk<=10,q<20000);
    }
    // Pure research scenario. Never returned as an ALLOW evaluation, never used by transport/reservations.
    public static PaperScenarioSize SizePaperOfflineScenario(AccountState account,RiskRequest r,decimal exposure)
    {
        if(account.Capital is null || account.Capital.InitialCapital!=100 || account.Capital.LossAllowance!=20 ||
           account.Capital.Environment!="SIMULATION" || account.Equity!=account.Capital.Equity ||
           exposure is not (1 or 5 or 10 or 20 or 30 or 50) || r.Execution?.Environment!="SIMULATION" ||
           r.Execution.TakeProfit is null || r.Side is not ("BUY" or "SELL") || r.Instrument!="EUR/USD" ||
           r.Bid<=0 || r.Ask<r.Bid || r.Stop<=0 || r.Multiplier!=1 || r.QuoteToAccountFx!=1 ||
           r.QuantityStep<=0 || r.MinQuantity<=0 || r.CommissionFixedRoundTrip<0 || r.CommissionPerUnitRoundTrip<0 ||
           r.SlippagePerUnit<0 || r.AdverseGapPerUnit<0)
            throw new ArgumentException("OFFLINE_PAPER_SCENARIO_SCOPE_INVALID");
        account.Capital.Validate();
        var budget=Math.Max(0,Math.Min(10,Math.Min(account.Equity*.1m,account.Capital.RemainingLoss)));
        PaperScenarioSize Deny(string reason)=>new(false,reason,budget,0,0,0,0,0,0,0,0,true);
        if(account.OpenPositions.Length+account.PendingOrders.Length>0 || account.ReservationId is not null)return Deny("POSITION_LIMIT");
        if(account.Halts.Length>0 || budget<=0)return Deny("CUMULATIVE_LOSS_LIMIT");
        var mid=(r.Bid+r.Ask)/2;var buy=r.Side=="BUY";var target=r.Execution.TakeProfit.Value;
        if(buy?r.Stop>=r.Bid:r.Stop<=r.Ask)return Deny("INVALID_STOP");
        if(buy?target<=r.Ask:target>=r.Bid)return Deny("INVALID_TAKE_PROFIT");
        var costsUnit=r.Ask-r.Bid+r.SlippagePerUnit+r.CommissionPerUnitRoundTrip;
        var riskUnit=Math.Abs(mid-r.Stop)+costsUnit+r.AdverseGapPerUnit;var fixedFees=r.CommissionFixedRoundTrip;
        if(fixedFees>=budget)return Deny("COST_EXCEEDS_RISK_BUDGET");
        var cap=Math.Min((budget-fixedFees)/riskUnit,account.Equity*exposure/r.Ask);
        var q=r.MinQuantity+decimal.Floor((cap-r.MinQuantity)/r.QuantityStep)*r.QuantityStep;
        if(q<r.MinQuantity)return Deny("MIN_SIZE_EXCEEDS_BUDGET");
        var costs=fixedFees+q*costsUnit;var risk=fixedFees+q*riskUnit;var gross=q*Math.Abs(target-mid);
        // Gap is reserved even in the potential-target screen; not booked as a fee if it never occurs.
        var net=gross-costs-q*r.AdverseGapPerUnit;var notional=q*r.Ask;
        return new(net>0,net>0?"CONDITIONAL_COST_SCENARIO_MARGIN_AND_BROKER_UNKNOWN":"TARGET_DOES_NOT_COVER_COSTS_AND_GAP_RESERVE",
            budget,q,notional,notional/account.Equity,risk,costs,gross,net,
            Math.Min(1,Math.Max(0,(account.Equity-costs)/notional)),q<20000);
    }
}

public sealed record PaperDailyStop(DateOnly Day,DateTimeOffset At,decimal Net,string Reason);
public sealed record PaperSweepMetrics(int Trades,decimal? MeanQuantity,decimal? MedianQuantity,decimal? MeanRisk,
    decimal? MaximumRisk,decimal? Costs,decimal? GrossPnl,decimal? NetPnl,decimal? WinRate,decimal? NetProfitFactor,
    decimal? NetExpectancy,decimal? MaximumClosedDrawdown,decimal? MaximumIntrabarDrawdownBound,
    int DaysWithEntries,int PotentialOperableDays,int StructurallyEligibleSignals,decimal? TargetNotCoveringCostPercent,
    decimal FinalEquity,decimal ConsumedLoss,PaperDailyStop[] DailyStops,int OddLotTrades,
    string MarginStatus="UNKNOWN_NO_VIABILITY_CLAIM",string Validation="OFFLINE_ESTIMATED_COSTS_ONLY");
public sealed record PaperSweepResult(string Strategy,decimal ExposureLimit,PaperSweepMetrics Metrics,
    ResearchTrade[] Trades,PaperScenarioSize[] EntrySizes,Dictionary<string,int> Rejections,
    bool ExecutionAuthorized=false,bool LiveEnabled=false);

public static class PaperEconomicSweep
{
    private sealed record Position(ResearchSignal Signal,PaperScenarioSize Size,decimal Stop,decimal Target);
    public static PaperSweepResult Run(string strategy,PaperCandle[] bars,ResearchSignal[] signals,ResearchExit[] exits,
        ResearchCosts costs,decimal exposure)
    {
        if(strategy is not ("trend" or "pullback" or "mean_reversion") || costs.Source.Length==0 ||
           costs.Spread<0 || costs.OpeningCommission<0 || costs.ClosingCommission<0 || costs.Slippage<0 ||
           costs.AdverseGap<0 || costs.CommissionPerUnitRoundTrip<0 || costs.MinimumQuantity<=0 || costs.QuantityStep<=0 ||
           bars.Any(b=>b.Minutes!=15 || b.Open<=0 || b.Low<=0 || b.High<Math.Max(b.Open,b.Close) || b.Low>Math.Min(b.Open,b.Close)) ||
           bars.Zip(bars.Skip(1)).Any(b=>b.First.OpenedAt.AddMinutes(15)>b.Second.OpenedAt))
            throw new ArgumentException("INVALID_SWEEP_DATA");
        var account=AccountState.Initial("SIM-PAPER-ECONOMIC-STUDY",100,bars.FirstOrDefault()?.OpenedAt??DateTimeOffset.UnixEpoch);
        var selected=signals.Where(s=>s.StrategyId==strategy).ToArray();
        foreach(var s in selected)
        {
            if(s.SignalAt.Offset!=TimeSpan.Zero || s.EntryAt is DateTimeOffset entry && (entry.Offset!=TimeSpan.Zero || entry<s.SignalAt))
                throw new ArgumentException("INVALID_RESEARCH_TIMESTAMP");
            if(s.Context.ValueKind==System.Text.Json.JsonValueKind.Object)
                foreach(var frame in s.Context.EnumerateObject())
                {
                    if(frame.Value.TryGetProperty("as_of",out var cut) && DateTimeOffset.Parse(cut.GetString()!)>s.SignalAt)
                        throw new ArgumentException("LOOK_AHEAD_CONTEXT");
                    if(frame.Value.TryGetProperty("indicators",out var indicators) && indicators.ValueKind==System.Text.Json.JsonValueKind.Object &&
                       indicators.TryGetProperty("closed_at",out var close) && DateTimeOffset.Parse(close.GetString()!)>s.SignalAt)
                        throw new ArgumentException("LOOK_AHEAD_CONTEXT");
                }
        }
        var entryLookup=selected.Where(s=>s.EntryAt is not null).ToLookup(s=>s.EntryAt!.Value);
        var barOpens=bars.Select(b=>b.OpenedAt).ToHashSet();
        var eligible=selected.Where(s=>s.Reasons.Length==0 && s.EntryAt is not null && barOpens.Contains(s.EntryAt.Value)).ToArray();
        var trades=new List<ResearchTrade>();var sizes=new List<PaperScenarioSize>();var stops=new List<PaperDailyStop>();
        var days=new HashSet<DateOnly>();var potentialDays=new HashSet<DateOnly>();var rejected=new Dictionary<string,int>();
        Position? position=null;DateOnly? stoppedDay=null;decimal peak=100,closedDrawdown=0,intrabarDrawdown=0;int badTargets=0;
        void Reject(string reason)=>rejected[reason]=rejected.GetValueOrDefault(reason)+1;
        RiskRequest Request(ResearchSignal s)
        {
            var mid=s.EntryMidpoint!.Value;var sign=s.Side=="BUY"?1m:-1m;var target=mid+sign*s.TakeProfitDistance;
            return new("EUR/USD",s.Side,mid-costs.Spread/2,mid+costs.Spread/2,mid-sign*s.StopDistance,1,1,
                costs.MinimumQuantity,costs.QuantityStep,1,100,costs.OpeningCommission+costs.ClosingCommission,
                costs.CommissionPerUnitRoundTrip,costs.Slippage,costs.AdverseGap,s.EntryAt!.Value,
                Execution:new(costs.Source,"SIMULATION","SIMULATED",s.EntryAt.Value,costs.OpeningCommission,costs.ClosingCommission,
                    QuoteStatus:"SIMULATED",TakeProfit:target));
        }
        foreach(var s in eligible)
        {
            var size=RiskEngine.SizePaperOfflineScenario(AccountState.Initial("SIM-SCREEN",100,s.EntryAt!.Value),Request(s),exposure);
            if(size.GrossTarget<=size.Costs || size.Quantity==0)badTargets++;
            if(size.ConditionalAdmissible)potentialDays.Add(DateOnly.FromDateTime(s.EntryAt.Value.UtcDateTime));
        }
        foreach(var s in selected.Where(s=>s.EntryAt is null || !barOpens.Contains(s.EntryAt.Value)))Reject("NO_ENTRY_BAR_IN_PARTITION");
        void Settle(ResearchExitDecision decision)
        {
            var p=position!;var entry=p.Signal.EntryMidpoint!.Value;var price=decision.Price!.Value;
            var gross=(p.Signal.Side=="BUY"?price-entry:entry-price)*p.Size.Quantity;var net=gross-p.Size.Costs;
            trades.Add(new(p.Signal.EntryAt!.Value,decision.At,p.Signal.Side,entry,price,p.Size.Quantity,gross,p.Size.Costs,net,decision.Reason));
            account=account with {Capital=account.Capital!.Settle(net,p.Size.Costs),At=decision.At};
            account=account with {Equity=account.Capital!.Equity};peak=Math.Max(peak,account.Equity);
            closedDrawdown=Math.Max(closedDrawdown,(peak-account.Equity)/peak);
            if(net<=0)
            {
                stoppedDay=DateOnly.FromDateTime(decision.At.UtcDateTime);
                stops.Add(new(stoppedDay.Value,decision.At,net,net<0?"DAILY_FIRST_LOSS_STOP":"DAILY_WIN_REQUIRED"));
            }
            if(account.Capital.RemainingLoss<=0)account=account.Halt("CUMULATIVE_LOSS_LIMIT");
            position=null;
        }
        for(var i=0;i<bars.Length;i++)
        {
            var b=bars[i];var previous=bars[Math.Max(0,i-1)].OpenedAt;
            ResearchExitPosition Shape(Position p)=>new(strategy,p.Signal.Side,p.Signal.EntryMidpoint!.Value,p.Stop,p.Target,p.Signal.EntryAt!.Value);
            if(position is not null)
            {
                var open=ResearchExitSemantics.Decide(Shape(position),b,previous,exits,true);
                if(open.Exit)Settle(open);
            }
            foreach(var s in entryLookup[b.OpenedAt])
            {
                if(s.SignalAt>b.OpenedAt || s.EntryMidpoint!=b.Open)throw new ArgumentException("LOOK_AHEAD_OR_ENTRY_MISMATCH");
                if(s.Reasons.Length>0){foreach(var reason in s.Reasons)Reject(reason);continue;}
                if(position is not null){Reject("POSITION_LIMIT");continue;}
                if(stoppedDay==DateOnly.FromDateTime(b.OpenedAt.UtcDateTime)){Reject("DAILY_WIN_REQUIRED_OR_FIRST_LOSS_STOP");continue;}
                var size=RiskEngine.SizePaperOfflineScenario(account,Request(s),exposure);
                if(!size.ConditionalAdmissible){Reject(size.Reason);continue;}
                sizes.Add(size);days.Add(DateOnly.FromDateTime(b.OpenedAt.UtcDateTime));
                var sign=s.Side=="BUY"?1m:-1m;position=new(s,size,b.Open-sign*s.StopDistance,b.Open+sign*s.TakeProfitDistance);
            }
            if(position is null)continue;
            var p=position;var buy=p.Signal.Side=="BUY";var stopHit=buy?b.Low<=p.Stop:b.High>=p.Stop;
            var worst=stopHit?(buy?Math.Min(b.Open,p.Stop):Math.Max(b.Open,p.Stop)):(buy?b.Low:b.High);
            var worstNet=(buy?worst-p.Signal.EntryMidpoint!.Value:p.Signal.EntryMidpoint!.Value-worst)*p.Size.Quantity-p.Size.Costs;
            intrabarDrawdown=Math.Max(intrabarDrawdown,(peak-(account.Equity+worstNet))/peak);
            var halt=account.Equity+worstNet<=80 || account.Capital!.ConsumedLoss+Math.Max(0,-worstNet)>=20;
            var decision=ResearchExitSemantics.Decide(Shape(p),b,previous,exits,false,halt,i==bars.Length-1);
            if(decision.Exit)Settle(decision);
        }
        decimal? Median(decimal[] values)=>values.Length==0?null:values.Length%2==1?values[values.Length/2]:(values[values.Length/2-1]+values[values.Length/2])/2;
        var q=sizes.Select(s=>s.Quantity).Order().ToArray();var wins=trades.Where(t=>t.NetPnl>0).Sum(t=>t.NetPnl);
        var losses=-trades.Where(t=>t.NetPnl<0).Sum(t=>t.NetPnl);var n=trades.Count;
        var metrics=new PaperSweepMetrics(n,n>0?q.Average():null,Median(q),n>0?sizes.Average(s=>s.Risk):null,
            n>0?sizes.Max(s=>s.Risk):null,n>0?trades.Sum(t=>t.Costs):null,n>0?trades.Sum(t=>t.GrossPnl):null,
            n>0?trades.Sum(t=>t.NetPnl):null,n>0?(decimal)trades.Count(t=>t.NetPnl>0)/n:null,
            losses>0?wins/losses:null,n>0?trades.Sum(t=>t.NetPnl)/n:null,n>0?closedDrawdown:null,n>0?Math.Max(closedDrawdown,intrabarDrawdown):null,
            days.Count,potentialDays.Count,eligible.Length,eligible.Length>0?100m*badTargets/eligible.Length:null,
            account.Equity,account.Capital!.ConsumedLoss,stops.ToArray(),sizes.Count(s=>s.OddLot));
        return new(strategy,exposure,metrics,trades.ToArray(),sizes.ToArray(),rejected);
    }
}
