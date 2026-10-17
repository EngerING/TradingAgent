namespace TradingAgent.Core;

// Additional Paper stock boundary. It delegates to the unchanged production
// RiskEngine; neither experimental studies nor a grant can relax its ceiling.
public static class StockPaperForwardRisk
{
    public const string H40Version = "2459b8fbe73d4dec3bff7a1baaf3e382b9473fa5908d25e6d6b58ffd151072d8";
    public static RiskEvaluation Evaluate(RiskPolicy policy, AccountState account,
        RiskRequest request, DateTimeOffset now, string strategyVersion,
        decimal allocatedCash, decimal reservations)
    {
        policy.Validate();
        var result = RiskEngine.Evaluate(policy, account, request, now);
        RiskEvaluation Deny(string why) => result with {Decision="DENY", Reason=why, Quantity=0};
        if (strategyVersion != H40Version || account.Capital?.Environment != "PAPER_TRADING" ||
            request.Instrument != "F" || request.Side != "BUY" || request.Multiplier != 1 ||
            request.QuoteToAccountFx != 1 || request.MarginRate != 1 || policy.MaxLeverage > 1 ||
            policy.AllocatedCapital != 100 || policy.CumulativeLossLimit != 20)
            return Deny("STOCK_FORWARD_SCOPE_REQUIRED");
        if (reservations < 0 || allocatedCash < 0 || allocatedCash > 100 ||
            reservations > allocatedCash || request.MinQuantity < 1 || request.QuantityStep < 1 ||
            request.MinQuantity % 1 != 0 || request.QuantityStep % 1 != 0)
            return Deny("STOCK_FORWARD_CASH_OR_WHOLE_SHARES_REQUIRED");
        if (!result.Allowed) return result;
        // Limit-price BUY plus full round-trip fee reserve must fit cash, even
        // when equity increases. The million-dollar Paper balance is no input.
        if (result.Quantity % 1 != 0 || result.Quantity * request.Ask + result.Commissions >
            Math.Min(100, allocatedCash) - reservations || result.NominalExposure > 100)
            return Deny("STOCK_FORWARD_ALLOCATION_EXCEEDED");
        return result;
    }
}
