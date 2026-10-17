using TradingAgent.Core;

namespace TradingAgent.ResearchLab;

// Separate simulation assembly: no broker, operational policy or authorization.
public static class ResearchScope
{
    public static IReadOnlyList<decimal> Rates {get;}=Array.AsReadOnly<decimal>([.01m,.02m,.03m,.05m,.075m,.10m,.125m,.15m]);
    public const decimal Capital=100,LossAllowance=20,Exposure=1;
    public static readonly TimeZoneInfo Zone=TimeZoneInfo.FindSystemTimeZoneById("America/Santo_Domingo");
    public static DateOnly Day(DateTimeOffset at)=>DateOnly.FromDateTime(TimeZoneInfo.ConvertTime(at,Zone).DateTime);
    public static void Rate(decimal rate)
    {if(!Rates.Contains(rate))throw new ArgumentException("RESEARCH_RATE_OUT_OF_SCOPE");}
}

public sealed record FinalResult(string Id,DateTimeOffset At,decimal Net,decimal Commission);
public sealed record LedgerSnapshot(string Environment,decimal InitialCapital,decimal LossAllowance,
    FinalResult[] Results,string? PendingId,DateTimeOffset LastObservedAt);

public sealed class ResearchLedger
{
    private readonly List<FinalResult> results;
    public string? PendingId {get;private set;}
    public DateTimeOffset LastObservedAt {get;private set;}
    public decimal Equity=>100+results.Sum(x=>x.Net);
    public decimal ConsumedLoss=>results.Sum(x=>Math.Max(0,-x.Net));
    public decimal RemainingLoss=>Math.Max(0,Math.Min(20-ConsumedLoss,Equity-80));
    public bool ManagementRequired=>PendingId is not null;
    public ResearchLedger():this(new("SIMULATION",100,20,[],null,DateTimeOffset.UnixEpoch)){}
    public ResearchLedger(LedgerSnapshot snapshot)
    {
        if(snapshot.Environment!="SIMULATION" || snapshot.InitialCapital!=100 || snapshot.LossAllowance!=20 ||
            snapshot.Results.Any(x=>string.IsNullOrWhiteSpace(x.Id) || x.Commission<0 || x.At>snapshot.LastObservedAt) ||
            snapshot.Results.Select(x=>x.Id).Distinct().Count()!=snapshot.Results.Length ||
            snapshot.Results.Zip(snapshot.Results.Skip(1)).Any(x=>x.First.At>x.Second.At) ||
            snapshot.PendingId is not null && (string.IsNullOrWhiteSpace(snapshot.PendingId) || snapshot.Results.Any(x=>x.Id==snapshot.PendingId)))
            throw new ArgumentException("INVALID_SIMULATION_LEDGER");
        results=[..snapshot.Results];PendingId=snapshot.PendingId;LastObservedAt=snapshot.LastObservedAt;
    }
    public LedgerSnapshot Snapshot()=>new("SIMULATION",100,20,results.ToArray(),PendingId,LastObservedAt);
    public string? EntryBlock(DateTimeOffset at)
    {
        if(at<LastObservedAt)return "OUT_OF_ORDER_OBSERVATION";
        if(PendingId is not null)return "RESULT_RECONCILIATION_PENDING";
        if(RemainingLoss<=0)return "CUMULATIVE_LOSS_LIMIT";
        var today=results.Where(x=>ResearchScope.Day(x.At)==ResearchScope.Day(at)).ToArray();
        if(today.Any(x=>x.Net<0))return "DAILY_FIRST_LOSS_STOP";
        return today.Length>0 && today[^1].Net==0?"DAILY_BREAK_EVEN_STOP":null;
    }
    public void Begin(string id,DateTimeOffset at)
    {
        var block=EntryBlock(at);if(block is not null)throw new InvalidOperationException(block);
        if(string.IsNullOrWhiteSpace(id) || results.Any(x=>x.Id==id))throw new ArgumentException("DUPLICATE_SIMULATION_INTENT");
        PendingId=id;LastObservedAt=at;
    }
    public bool Settle(string id,DateTimeOffset at,decimal? net,decimal? commission,bool reconciled)
    {
        if(PendingId!=id || at<LastObservedAt || commission is <0)throw new ArgumentException("INVALID_SIMULATION_SETTLEMENT");
        LastObservedAt=at;
        if(!reconciled || net is null || commission is null)return false;
        results.Add(new(id,at,net.Value,commission.Value));PendingId=null;return true;
    }
}

public sealed record SimulationSize(bool ConditionalAdmissible,string Reason,decimal Budget,decimal Quantity=0,
    decimal Notional=0,decimal StopLoss=0,decimal Commission=0,decimal Spread=0,decimal Slippage=0,decimal GapReserve=0,
    decimal TotalRisk=0,decimal GrossTarget=0,decimal ConservativeNetTarget=0,bool OddLot=true,
    bool ExecutionAuthorized=false,bool LiveEnabled=false,
    decimal FinancingReserve=0,decimal InitialMarginRequired=0,decimal MaintenanceMarginAtStop=0,
    decimal MaximumAffordableMarginRate=0,decimal EntryEquity=100);

public static class SimulationSizer
{
    public static SimulationSize Size(ResearchLedger ledger,ResearchSignal signal,ResearchCosts costs,decimal rate,
        ExposureAssumptions? assumptions=null)
    {
        if(assumptions is null)ResearchScope.Rate(rate);else assumptions.Validate(rate);
        var mid=signal.EntryMidpoint;
        if(mid is null || mid<=0 || signal.StopDistance<=0 || signal.TakeProfitDistance<=0 || signal.Side is not ("BUY" or "SELL") ||
            costs.Spread<0 || costs.OpeningCommission<0 || costs.ClosingCommission<0 || costs.Slippage<0 || costs.AdverseGap<0 ||
            costs.CommissionPerUnitRoundTrip<0 || costs.MinimumQuantity<=0 || costs.QuantityStep<=0 || costs.MarginRate!=1 ||
            string.IsNullOrWhiteSpace(costs.Source))throw new ArgumentException("INVALID_RESEARCH_SIZE_INPUT");
        var budget=Math.Max(0,Math.Min(ledger.Equity*rate,ledger.RemainingLoss));
        SimulationSize Reject(string reason)=>new(false,reason,budget);
        if(ledger.PendingId is not null)return Reject("RESULT_RECONCILIATION_PENDING");
        if(budget<=0)return Reject("CUMULATIVE_LOSS_LIMIT");
        if(signal.StopDistance<=costs.Spread/2 || signal.TakeProfitDistance<=costs.Spread/2)return Reject("INVALID_PRICE_GEOMETRY");
        var fixedCost=costs.OpeningCommission+costs.ClosingCommission;
        if(fixedCost>=budget)return Reject("COMMISSION_EXCEEDS_RISK_BUDGET");
        var variableCost=costs.Spread+costs.Slippage+costs.CommissionPerUnitRoundTrip;
        var ask=mid.Value+costs.Spread/2;
        var financingUnit=ask*(assumptions?.AnnualFinancingRate??0)*(assumptions?.FinancingReserveDays??0)/360;
        var unitRisk=signal.StopDistance+variableCost+costs.AdverseGap+financingUnit;
        // Full notional funded by own virtual equity; never broker buying power.
        var cap=Math.Min((budget-fixedCost)/unitRisk,(ledger.Equity-fixedCost)/(ask+variableCost));
        if(assumptions is not null)
        {
            var unitMargin=Math.Max(ask*assumptions.InitialMarginRate,
                (ask+signal.StopDistance+costs.AdverseGap)*assumptions.MaintenanceMarginRate);
            cap=Math.Min((budget-fixedCost)/unitRisk,Math.Min(ledger.Equity*assumptions.Exposure/ask,
                (ledger.Equity-fixedCost)/(unitMargin+unitRisk)));
        }
        var quantity=costs.MinimumQuantity+decimal.Floor((cap-costs.MinimumQuantity)/costs.QuantityStep)*costs.QuantityStep;
        if(quantity<costs.MinimumQuantity)return Reject("MINIMUM_QUANTITY_EXCEEDS_BUDGET");
        var gross=quantity*signal.TakeProfitDistance;
        var commission=fixedCost+quantity*costs.CommissionPerUnitRoundTrip;
        var spread=quantity*costs.Spread;var slip=quantity*costs.Slippage;var gap=quantity*costs.AdverseGap;
        var carry=quantity*financingUnit;var net=gross-commission-spread-slip-gap-carry;
        var margin=quantity*ask*(assumptions?.InitialMarginRate??1);
        var maintenance=quantity*(ask+signal.StopDistance+costs.AdverseGap)*(assumptions?.MaintenanceMarginRate??1);
        return new(net>0,net>0?"CONDITIONAL_SIMULATION_ONLY":"TARGET_DOES_NOT_COVER_COSTS",budget,quantity,quantity*ask,
            quantity*signal.StopDistance,commission,spread,slip,gap,quantity*unitRisk+fixedCost,gross,net,quantity<20000,
            FinancingReserve:carry,InitialMarginRequired:margin,MaintenanceMarginAtStop:maintenance,
            MaximumAffordableMarginRate:Math.Max(0,(ledger.Equity-quantity*unitRisk-fixedCost)/
                (quantity*(ask+signal.StopDistance+costs.AdverseGap))),EntryEquity:ledger.Equity);
    }
}

public sealed record LabTrade(ResearchTrade Trade,SimulationSize Size,string Reconciliation="FINAL_ESTIMATED_FEES",
    string Environment="SIMULATION",decimal FinancingCost=0,bool RiskBudgetBreached=false,
    bool FinancingReserveExceeded=false);
public sealed record LabDailyStop(DateOnly Day,DateTimeOffset At,decimal Net,string Reason);
public sealed record LabMetrics(int Admitted,int Rejected,int NoTradeCandidates,int Wins,int Losses,int BreakEven,
    decimal? WinRate,decimal? AverageWin,decimal? AverageLoss,decimal? NetExpectancy,decimal? NetProfitFactor,
    decimal GrossPnl,decimal NetPnl,decimal Commissions,decimal SpreadCost,decimal SlippageCost,decimal GapReserved,
    decimal ClosedDrawdown,decimal IntrabarDrawdownBound,decimal FinalEquity,decimal ConsumedLoss,
    int FirstLossDays,int BreakEvenDays,int DaysWithEntries,int OddLots,decimal? MeanQuantity,decimal? MeanRisk,
    decimal? MaximumRisk,decimal? MaximumNotional,decimal? MaximumConservativeTarget,
    string IbkrExecutability="UNKNOWN_MARGIN_TARIFF_AND_SEMANTICS_NOT_VERIFIED",
    decimal FinancingCost=0,int RiskBudgetBreaches=0,int FinancingReserveExceedances=0,
    bool LossBudgetExhausted=false,bool CapitalExhausted=false,
    decimal? MaximumInitialMargin=null,decimal? MaximumMaintenanceMargin=null,
    decimal? MinimumAffordableMarginRate=null);
public sealed record LabResult(string Strategy,decimal RiskFraction,LabMetrics Metrics,LabTrade[] Trades,
    LabDailyStop[] DailyStops,Dictionary<string,int> Rejections,LedgerSnapshot Ledger,
    string Environment="SIMULATION",decimal ExposureLimit=1,bool ExecutionAuthorized=false,bool LiveEnabled=false,
    ExposureAssumptions? MarginAssumptions=null);

public static class ProgressiveRiskSimulation
{
    private sealed record Position(ResearchSignal Signal,SimulationSize Size,string Id);
    public static LabResult Run(string strategy,PaperCandle[] bars,ResearchSignal[] signals,ResearchExit[] exits,ResearchCosts costs,decimal rate,
        ExposureAssumptions? assumptions=null)
    {
        if(assumptions is null)ResearchScope.Rate(rate);else assumptions.Validate(rate);
        if(strategy is not ("trend" or "pullback" or "mean_reversion") || bars.Any(b=>b.Minutes!=15 || b.OpenedAt.Offset!=TimeSpan.Zero ||
            b.Open<=0 || b.Low<=0 || b.Close<=0 || b.High<Math.Max(b.Open,b.Close) || b.Low>Math.Min(b.Open,b.Close)) ||
            bars.Zip(bars.Skip(1)).Any(b=>b.First.OpenedAt.AddMinutes(15)>b.Second.OpenedAt) ||
            exits.Any(e=>e.At.Offset!=TimeSpan.Zero))throw new ArgumentException("INVALID_CHRONOLOGICAL_RESEARCH_INPUT");
        var candidates=signals.Where(s=>s.StrategyId==strategy).ToArray();var ledger=new ResearchLedger();
        var opens=bars.Select(b=>b.OpenedAt).ToHashSet();var lookup=candidates.Where(s=>s.EntryAt is not null).ToLookup(s=>s.EntryAt!.Value);
        var rejected=new Dictionary<string,int>();var trades=new List<LabTrade>();var stops=new List<LabDailyStop>();
        var days=new HashSet<DateOnly>();Position? position=null;decimal peak=100,dd=0,intrabar=0;var admitted=0;
        var noTrade=candidates.Count(s=>s.Reasons.Length>0 || s.EntryAt is null);
        void Reject(string reason)=>rejected[reason]=rejected.GetValueOrDefault(reason)+1;
        foreach(var s in candidates)
        {
            if(s.SignalAt.Offset!=TimeSpan.Zero || s.EntryAt is DateTimeOffset entry && (entry.Offset!=TimeSpan.Zero || entry<s.SignalAt))
                throw new ArgumentException("LOOK_AHEAD_SIGNAL");
            if(s.Context.ValueKind==System.Text.Json.JsonValueKind.Object)
                foreach(var f in s.Context.EnumerateObject())
                {
                    if(f.Value.TryGetProperty("as_of",out var t) && DateTimeOffset.Parse(t.GetString()!)>s.SignalAt)throw new ArgumentException("LOOK_AHEAD_CONTEXT");
                    if(f.Value.TryGetProperty("indicators",out var indicators) && indicators.TryGetProperty("closed_at",out var end) &&
                        DateTimeOffset.Parse(end.GetString()!)>s.SignalAt)throw new ArgumentException("LOOK_AHEAD_CONTEXT");
                }
            if(s.EntryAt is null || s.Reasons.Length>0)continue;
            if(!opens.Contains(s.EntryAt.Value))Reject("NO_ENTRY_BAR_IN_PARTITION");
        }
        ResearchExitPosition Shape(Position p)
        {var sign=p.Signal.Side=="BUY"?1m:-1m;var mid=p.Signal.EntryMidpoint!.Value;
            return new(strategy,p.Signal.Side,mid,mid-sign*p.Signal.StopDistance,mid+sign*p.Signal.TakeProfitDistance,p.Signal.EntryAt!.Value);}
        void Settle(ResearchExitDecision exit)
        {
            var p=position!;var mid=p.Signal.EntryMidpoint!.Value;
            var gross=(p.Signal.Side=="BUY"?exit.Price!.Value-mid:mid-exit.Price!.Value)*p.Size.Quantity;
            var carry=assumptions?.Financing(p.Size.Notional,p.Signal.EntryAt!.Value,exit.At)??0;
            var cost=p.Size.Commission+p.Size.Spread+p.Size.Slippage+carry;var net=gross-cost;
            ledger.Settle(p.Id,exit.At,net,p.Size.Commission,true);
            trades.Add(new(new(p.Signal.EntryAt!.Value,exit.At,p.Signal.Side,mid,exit.Price.Value,p.Size.Quantity,gross,cost,net,exit.Reason),p.Size,
                FinancingCost:carry,RiskBudgetBreached:Math.Max(0,-net)>p.Size.Budget,
                FinancingReserveExceeded:carry>p.Size.FinancingReserve));
            peak=Math.Max(peak,ledger.Equity);dd=Math.Max(dd,(peak-ledger.Equity)/peak);
            if(net<=0)stops.Add(new(ResearchScope.Day(exit.At),exit.At,net,net<0?"DAILY_FIRST_LOSS_STOP":"DAILY_BREAK_EVEN_STOP"));
            position=null;
        }
        decimal? maxTarget=null;
        for(var i=0;i<bars.Length;i++)
        {
            var bar=bars[i];var previous=bars[Math.Max(0,i-1)].OpenedAt;
            if(position is not null)
            {var exit=ResearchExitSemantics.Decide(Shape(position),bar,previous,exits,true);if(exit.Exit)Settle(exit);}
            foreach(var s in lookup[bar.OpenedAt])
            {
                if(s.SignalAt>bar.OpenedAt || s.EntryMidpoint!=bar.Open)throw new ArgumentException("ENTRY_BAR_MISMATCH");
                if(s.Reasons.Length>0)continue; // NO_TRADE never consumes an opportunity.
                var block=ledger.EntryBlock(bar.OpenedAt);if(block is not null){Reject(block);continue;}
                var size=SimulationSizer.Size(ledger,s,costs,rate,assumptions);
                if(size.Quantity>0)maxTarget=maxTarget is null?size.ConservativeNetTarget:Math.Max(maxTarget.Value,size.ConservativeNetTarget);
                if(!size.ConditionalAdmissible){Reject(size.Reason);continue;}
                var id=$"SIM-{strategy}-{bar.OpenedAt:O}-{admitted++}";ledger.Begin(id,bar.OpenedAt);
                position=new(s,size,id);days.Add(ResearchScope.Day(bar.OpenedAt));
            }
            if(position is null)continue;
            var p=position;var shape=Shape(p);var buy=p.Signal.Side=="BUY";var hit=buy?bar.Low<=shape.Stop:bar.High>=shape.Stop;
            var worst=hit?(buy?Math.Min(bar.Open,shape.Stop):Math.Max(bar.Open,shape.Stop)):(buy?bar.Low:bar.High);
            var accrued=assumptions?.Financing(p.Size.Notional,p.Signal.EntryAt!.Value,bar.OpenedAt.AddMinutes(15))??0;
            var worstNet=(buy?worst-shape.Entry:shape.Entry-worst)*p.Size.Quantity-p.Size.Commission-p.Size.Spread-p.Size.Slippage-accrued;
            intrabar=Math.Max(intrabar,(peak-(ledger.Equity+worstNet))/peak);
            var halt=ledger.ConsumedLoss+Math.Max(0,-worstNet)>=20 || ledger.Equity+worstNet<=80;
            var close=ResearchExitSemantics.Decide(shape,bar,previous,exits,false,halt,i==bars.Length-1);
            if(close.Exit)Settle(close);
        }
        var n=trades.Count;var wins=trades.Where(t=>t.Trade.NetPnl>0).ToArray();var losses=trades.Where(t=>t.Trade.NetPnl<0).ToArray();
        var winSum=wins.Sum(x=>x.Trade.NetPnl);var lossSum=-losses.Sum(x=>x.Trade.NetPnl);
        var metrics=new LabMetrics(admitted,rejected.Values.Sum(),noTrade,wins.Length,losses.Length,n-wins.Length-losses.Length,
            n>0?(decimal)wins.Length/n:null,wins.Length>0?winSum/wins.Length:null,losses.Length>0?lossSum/losses.Length:null,
            n>0?trades.Sum(x=>x.Trade.NetPnl)/n:null,lossSum>0?winSum/lossSum:null,
            trades.Sum(x=>x.Trade.GrossPnl),trades.Sum(x=>x.Trade.NetPnl),trades.Sum(x=>x.Size.Commission),
            trades.Sum(x=>x.Size.Spread),trades.Sum(x=>x.Size.Slippage),trades.Sum(x=>x.Size.GapReserve),dd,Math.Max(dd,intrabar),
            ledger.Equity,ledger.ConsumedLoss,stops.Where(x=>x.Net<0).Select(x=>x.Day).Distinct().Count(),
            stops.Where(x=>x.Net==0).Select(x=>x.Day).Distinct().Count(),days.Count,trades.Count(x=>x.Size.OddLot),
            n>0?trades.Average(x=>x.Size.Quantity):null,n>0?trades.Average(x=>x.Size.TotalRisk):null,
            n>0?trades.Max(x=>x.Size.TotalRisk):null,n>0?trades.Max(x=>x.Size.Notional):null,maxTarget,
            FinancingCost:trades.Sum(x=>x.FinancingCost),RiskBudgetBreaches:trades.Count(x=>x.RiskBudgetBreached),
            FinancingReserveExceedances:trades.Count(x=>x.FinancingReserveExceeded),
            LossBudgetExhausted:ledger.RemainingLoss<=0,CapitalExhausted:ledger.Equity<=0,
            MaximumInitialMargin:n>0?trades.Max(x=>x.Size.InitialMarginRequired):null,
            MaximumMaintenanceMargin:n>0?trades.Max(x=>x.Size.MaintenanceMarginAtStop):null,
            MinimumAffordableMarginRate:n>0?trades.Min(x=>x.Size.MaximumAffordableMarginRate):null);
        return new(strategy,rate,metrics,trades.ToArray(),stops.ToArray(),rejected,ledger.Snapshot(),
            ExposureLimit:assumptions?.Exposure??1,MarginAssumptions:assumptions);
    }
}
