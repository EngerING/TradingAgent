using TradingAgent.Core;

namespace TradingAgent.ResearchLab;

// Assumptions for the isolated executable. They are never broker/account facts.
public sealed record ExposureAssumptions(decimal Exposure,decimal InitialMarginRate,
    decimal MaintenanceMarginRate,decimal AnnualFinancingRate,decimal FinancingReserveDays)
{
    public static IReadOnlyList<decimal> Exposures {get;}=Array.AsReadOnly<decimal>([1,2,5,10,15,20]);
    public static IReadOnlyList<decimal> Rates {get;}=Array.AsReadOnly<decimal>(
        [.01m,.02m,.03m,.04m,.05m,.06m,.07m,.075m,.08m,.09m,.10m,.11m,.12m,.125m,.13m,.14m,.15m]);
    public void Validate(decimal rate)
    {
        if(!Exposures.Contains(Exposure) || !Rates.Contains(rate) ||
            InitialMarginRate is not (.025m or .05m or .10m or .20m or 1m) ||
            MaintenanceMarginRate<=0 || MaintenanceMarginRate>InitialMarginRate ||
            AnnualFinancingRate is not (0 or .10m) || FinancingReserveDays is not (0 or 1 or 4) ||
            (AnnualFinancingRate==0)!=(FinancingReserveDays==0))
            throw new ArgumentException("EXPOSURE_STUDY_SCOPE_INVALID");
    }
    public decimal Financing(decimal notional,DateTimeOffset entry,DateTimeOffset at)
    {
        if(at<entry)throw new ArgumentException("FINANCING_TIME_REVERSED");
        return notional*AnnualFinancingRate*(decimal)(at-entry).TotalDays/360;
    }
}

public sealed record MinimumExposureOpportunity(decimal Quantity,decimal Notional,decimal Exposure,
    decimal StopLoss,decimal Costs,decimal GapReserve,decimal FinancingReserve,decimal TotalRisk,
    decimal GrossTarget,decimal NetTarget,decimal MaximumAffordableMarginRate,
    bool WithinFifteenPercent,bool WithinTwentyTimes,bool OddLot,
    string Status="CONDITIONAL_ONLY_IBKR_CONSTRAINTS_UNKNOWN",bool ExecutionAuthorized=false);

public static class ExposureStudy
{
    public static MinimumExposureOpportunity? Minimum(ResearchSignal s,ResearchCosts c,ExposureAssumptions assumptions)
    {
        assumptions.Validate(.15m);
        _=SimulationSizer.Size(new(),s,c,.15m,assumptions);
        if(s.StopDistance<=c.Spread/2 || s.TakeProfitDistance<=c.Spread/2)return null;
        var ask=s.EntryMidpoint!.Value+c.Spread/2;
        var variable=c.Spread+c.Slippage+c.CommissionPerUnitRoundTrip;
        var financing=ask*assumptions.AnnualFinancingRate*assumptions.FinancingReserveDays/360;
        var surplus=s.TakeProfitDistance-variable-c.AdverseGap-financing;
        if(surplus<=0)return null;
        var fees=c.OpeningCommission+c.ClosingCommission;var threshold=fees/surplus;
        var q=Math.Max(c.MinimumQuantity,c.MinimumQuantity+
            (decimal.Floor((threshold-c.MinimumQuantity)/c.QuantityStep)+1)*c.QuantityStep);
        var costs=fees+q*variable;var gap=q*c.AdverseGap;var carry=q*financing;
        var risk=costs+gap+carry+q*s.StopDistance;var nominal=q*ask;
        return new(q,nominal,nominal/100,q*s.StopDistance,costs,gap,carry,risk,q*s.TakeProfitDistance,
            q*surplus-fees,Math.Max(0,(100-risk)/(nominal+q*(s.StopDistance+c.AdverseGap))),
            risk<=15,nominal<=2000,q<20000);
    }
}
