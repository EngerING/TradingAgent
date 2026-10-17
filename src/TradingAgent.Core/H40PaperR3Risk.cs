namespace TradingAgent.Core;

// R3 is a separately selected, supervised Paper sizing experiment. Neither the
// original H40 2% configuration nor the ordinary 0.5% boundary is changed.
public static class H40PaperR3Risk
{
    public const string Profile="H40_PAPER_EXPERIMENTAL_R3";
    public static string VariantVersion=>Convert.ToHexStringLower(System.Security.Cryptography.SHA256.HashData(
        System.Text.Encoding.UTF8.GetBytes(StockPaperForwardRisk.H40Version+"|"+Profile+"|RISK_PERCENT=3")));
    public static RiskEvaluation Evaluate(RiskPolicy productive, AccountState account,
        RiskRequest request, DateTimeOffset now, string parentVersion, decimal cash, decimal reserved)
    {
        productive.Validate();
        var experimental=productive with{Version=PaperRiskProfile.Experimental,OrdinaryRisk=.03m,MaximumRisk=.03m};
        RiskEvaluation Deny(string reason)=>new("DENY",reason,Profile,account.Equity,.03m,
            0,0,0,0,0,0,0,0,0,0,0,account.DailyLoss,account.WeeklyLoss,account.Drawdown);
        if(parentVersion!=StockPaperForwardRisk.H40Version || account.Capital?.Environment!="PAPER_TRADING" ||
            request.Execution?.Environment!="PAPER_TRADING" || request.Execution.TakeProfit is null ||
            request.Instrument!="F" || request.Side!="BUY" || request.ProposedRisk!=.03m ||
            request.Multiplier!=1 || request.QuoteToAccountFx!=1 || request.MarginRate!=1 ||
            request.MinQuantity!=1 || request.QuantityStep!=1 || request.MaximumQuantity!=1 ||
            productive.MaxLeverage!=1 || cash is < 0 or > 100 || reserved<0 || reserved>cash ||
            request.AvailableMargin>cash-reserved || account.Equity>100)
            return Deny("H40_R3_SUPERVISED_PAPER_SCOPE_REQUIRED");
        var result=RiskEngine.EvaluateValidated(experimental,account,request,now,paperExperimental:true);
        if(!result.Allowed)return result;
        if(result.Quantity!=1 || result.Budget>3 || result.EstimatedLoss>Math.Min(3,result.Budget) ||
            result.EstimatedLoss>10 || result.NominalExposure>100 || result.NominalExposure+result.Commissions>cash-reserved)
            return result with{Decision="DENY",Reason="H40_R3_BUDGET_OR_ALLOCATION_EXCEEDED",Quantity=0};
        return result;
    }
}
