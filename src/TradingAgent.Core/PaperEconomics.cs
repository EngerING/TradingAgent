namespace TradingAgent.Core;

public sealed record PaperEconomicSize(string Scenario, decimal Quantity, decimal NotionalUsd,
    decimal ExposureMultiple, decimal StopLossUsd, decimal CostsUsd, decimal TotalLossAtStopUsd,
    decimal GrossAtTargetUsd, decimal NetAtTargetUsd, decimal MaximumAffordableMarginRate,
    bool WithinOneTimesExposure, bool WithinRisk, bool OddLot);
public sealed record PaperEconomicStudy(decimal Budget, decimal UnitRisk, decimal UnitCosts,
    decimal TargetDistance, PaperEconomicSize[] Sizes, decimal RecommendedQuantity = 0,
    string Reason = "INSPECTION_ONLY_NO_EXECUTION", bool ExecutionAuthorized = false, bool LiveEnabled = false);

public static partial class RiskEngine
{
    // A diagnostic calculation, never RiskEvaluation/ALLOW. Hypothetical exposure does not alter policy.
    public static PaperEconomicStudy StudyPaperEconomics(AccountState a, RiskRequest r)
    {
        if(a.Capital?.Environment!="PAPER_TRADING" || a.Capital.InitialCapital!=100 || a.Capital.LossAllowance!=20 ||
           a.Equity<=0 || a.Equity!=a.Capital.Equity || r.Instrument!="EUR/USD" || r.Side!="BUY" || r.Multiplier!=1 || r.QuoteToAccountFx!=1 ||
           r.Bid<=0 || r.Ask<r.Bid || r.Stop<=0 || r.Stop>=r.Bid || r.Execution?.TakeProfit is not decimal target || target<=r.Ask ||
           r.MinQuantity<=0 || r.QuantityStep<=0 || r.CommissionFixedRoundTrip<0 || r.CommissionPerUnitRoundTrip<0 ||
           r.SlippagePerUnit<0 || r.AdverseGapPerUnit<0 || r.Execution.Environment!="PAPER_TRADING" ||
           r.Execution.OpeningCommission is null || r.Execution.ClosingCommission is null ||
           r.Execution.OpeningCommission<0 || r.Execution.ClosingCommission<0 ||
           r.Execution.OpeningCommission+r.Execution.ClosingCommission!=r.CommissionFixedRoundTrip)
            throw new ArgumentException("PAPER_ECONOMICS_INPUT_INVALID");
        a.Capital.Validate();
        var mid=(r.Bid+r.Ask)/2;var stop=mid-r.Stop;var profit=target-mid;
        var costs=r.Ask-r.Bid+r.SlippagePerUnit+r.CommissionPerUnitRoundTrip;
        var risk=stop+costs+r.AdverseGapPerUnit;var fixedFees=r.CommissionFixedRoundTrip;
        var budget=Math.Min(10,Math.Min(a.Equity*.10m,a.Capital.RemainingLoss));
        decimal Floor(decimal x)=>Math.Max(0,r.MinQuantity+decimal.Floor((x-r.MinQuantity)/r.QuantityStep)*r.QuantityStep);
        decimal Above(decimal x)=>Math.Max(r.MinQuantity,r.MinQuantity+(decimal.Floor((x-r.MinQuantity)/r.QuantityStep)+1)*r.QuantityStep);
        PaperEconomicSize Row(string label,decimal q)
        {
            var nominal=q*r.Ask;var totalCosts=fixedFees+q*costs;var loss=q*stop+totalCosts+q*r.AdverseGapPerUnit;
            return new(label,q,nominal,nominal/a.Equity,q*stop,totalCosts,loss,q*profit,q*profit-totalCosts,
                nominal>0?Math.Min(1,Math.Max(0,(a.Equity-totalCosts)/nominal)):0,nominal<=a.Equity,loss<=budget,q<20000);
        }
        var sizes=new List<PaperEconomicSize>{Row("EXPOSURE_1X",Floor(a.Equity/r.Ask))};
        if(profit>costs)
        {
            sizes.Add(Row("FIRST_STRICTLY_POSITIVE_TARGET",Above(fixedFees/(profit-costs))));
            sizes.Add(Row("TARGET_NET_USD_1",Above((fixedFees+1)/(profit-costs))));
        }
        if(budget>fixedFees)sizes.Add(Row("MAXIMUM_RISK_QUANTITY",Floor((budget-fixedFees)/risk)));
        // Fees need collateral too; never assume IBKR's simulated buying power finances a $100 sleeve.
        var cashCap=Floor((a.Equity-fixedFees)/(r.Ask+costs));
        var operational=Row("CASH_COLLATERAL_1X",Math.Min(cashCap,Floor(Math.Max(0,budget-fixedFees)/risk)));
        sizes.Insert(1,operational);
        var recommended=operational.NetAtTargetUsd>0 && operational.WithinRisk && operational.WithinOneTimesExposure &&
            a.OpenPositions.Length==0 && a.PendingOrders.Length==0 && a.Halts.Length==0 ? operational.Quantity:0;
        return new(budget,risk,costs,profit,sizes.ToArray(),recommended,
            recommended>0?"CONDITIONAL_ESTIMATE_REQUIRES_VALID_SIGNAL_AND_VERIFIED_RESTRICTIONS":"NO_ECONOMIC_ENTRY_WITHIN_CURRENT_LIMITS");
    }
}
