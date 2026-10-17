namespace TradingAgent.Core;

// Independent execution measurement; not an H40 candidate or strategy approval.
// The null target is deliberate ONLY in this diagnostic source. A physical
// bracket target is still mandatory in the guarded transport's frozen plan.
public static class FordDiagnosticRisk
{
    public const string Scope="FORD_EXECUTION_DIAGNOSTIC_ONE_SHARE_V1";
    public const string R10Scope="FORD_DIAGNOSTIC_R10";
    public static RiskEvaluation Evaluate(RiskPolicy productive, AccountState a, RiskRequest r,
        DateTimeOffset now, string scope, decimal cash, decimal reserved)
    {
        productive.Validate();
        var fraction=scope==R10Scope ? .10m : .03m;
        var budget=100*fraction;
        RiskEvaluation Deny()=>new("DENY","FORD_DIAGNOSTIC_SCOPE_REQUIRED",scope==R10Scope ? R10Scope : Scope,a.Equity,fraction,
            0,0,0,0,0,0,0,0,0,0,0,a.DailyLoss,a.WeeklyLoss,a.Drawdown);
        if(scope is not (Scope or R10Scope) || a.Capital?.Environment!="PAPER_TRADING" || a.Capital.InitialCapital!=100 ||
            a.AccountId!="PAPER-FORD-EXECUTION-DIAGNOSTIC" || a.Equity>100 ||
            r.Execution?.Environment!="PAPER_TRADING" || r.Execution.Source!=scope ||
            r.Execution.TakeProfit is not null || r.Instrument!="F" || r.Side!="BUY" ||
            r.ProposedRisk!=fraction || r.Multiplier!=1 || r.QuoteToAccountFx!=1 || r.MarginRate!=1 ||
            r.MinQuantity!=1 || r.QuantityStep!=1 || r.MaximumQuantity!=1 || productive.MaxLeverage!=1 ||
            cash is <0 or >100 || reserved<0 || reserved>cash || r.AvailableMargin>cash-reserved ||
            r.CommissionFixedRoundTrip<=0 || r.SlippagePerUnit<=0 || r.AdverseGapPerUnit<=0)
            return Deny();
        var policy=productive with{Version=PaperRiskProfile.Experimental,OrdinaryRisk=fraction,MaximumRisk=fraction};
        var result=RiskEngine.EvaluateValidated(policy,a,r,now,paperExperimental:true);
        if(result.Allowed && (result.Quantity!=1 || result.Budget>budget || result.EstimatedLoss>budget ||
            result.EstimatedLoss>10 || result.NominalExposure+result.Commissions>cash-reserved))
            return result with{Decision="DENY",Reason="FORD_DIAGNOSTIC_BUDGET_EXCEEDED",Quantity=0};
        return result;
    }
}
