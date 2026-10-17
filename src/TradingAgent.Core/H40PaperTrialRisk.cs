namespace TradingAgent.Core;

// A calculation boundary for the separately authorized, single supervised Paper
// experiment. It grants no broker capability. The ordinary public entry point
// and RiskPolicy.Validate retain their 0.5% ceiling.
public static class H40PaperTrialRisk
{
    public static RiskEvaluation Evaluate(RiskPolicy productive, AccountState account,
        RiskRequest request, DateTimeOffset now, string version, decimal cash, decimal reserved)
    {
        productive.Validate();
        var experimental = productive with {Version=PaperRiskProfile.Experimental,
            OrdinaryRisk=.02m, MaximumRisk=.10m};
        RiskEvaluation Deny(string reason) => new("DENY",reason,experimental.Version,
            account.Equity,.02m,0,0,0,0,0,0,0,0,0,0,0,account.DailyLoss,account.WeeklyLoss,account.Drawdown);
        if(version!=StockPaperForwardRisk.H40Version || account.Capital?.Environment!="PAPER_TRADING" ||
            request.Execution?.Environment!="PAPER_TRADING" || request.Instrument!="F" || request.Side!="BUY" ||
            request.ProposedRisk!=.02m || request.Multiplier!=1 || request.QuoteToAccountFx!=1 ||
            request.MarginRate!=1 || request.MinQuantity!=1 || request.QuantityStep!=1 ||
            request.MaximumQuantity is not > 0 or > 1 || productive.MaxLeverage!=1 ||
            cash is < 0 or > 100 || reserved is < 0 || reserved>cash || request.AvailableMargin>cash-reserved)
            return Deny("H40_SUPERVISED_PAPER_SCOPE_REQUIRED");
        // Reuse every existing experimental risk and execution check. No
        // fabricated EquivalentRealAccount or productive policy mutation.
        var result=RiskEngine.EvaluateValidated(experimental,account,request,now,paperExperimental:true);
        if(!result.Allowed) return result;
        if(result.Quantity%1!=0 || result.Quantity>1 || result.EstimatedLoss>10 ||
            result.NominalExposure>100 || result.NominalExposure+result.Commissions>cash-reserved)
            return result with {Decision="DENY",Reason="H40_SUPERVISED_ALLOCATION_EXCEEDED",Quantity=0};
        return result;
    }
}
