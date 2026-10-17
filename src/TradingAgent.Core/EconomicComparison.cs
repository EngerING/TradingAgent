namespace TradingAgent.Core;

public enum EconomicEvidenceStatus { Unknown, PublicSchedule, ManualEstimate, HistoricalObservation, Scenario, AccountVerified }

// Quantity scope prevents extrapolating a preview of 100 EUR to another ticket.
// Values are in the unit declared by the input: price, units, ratio, or USD.
public sealed record EconomicEvidence(decimal? Value, EconomicEvidenceStatus Status, string Source,
    DateTimeOffset At, DateTimeOffset ValidUntil, decimal? QuantityScope = null)
{
    public bool Verified(decimal quantity, DateTimeOffset now) => Value is not null &&
        Status == EconomicEvidenceStatus.AccountVerified && At <= now && now <= ValidUntil &&
        (QuantityScope is null || QuantityScope == quantity);
    public decimal? Known(decimal quantity) => QuantityScope is null || QuantityScope == quantity ? Value : null;
    public void Validate()
    {
        if (!Enum.IsDefined(Status) || string.IsNullOrWhiteSpace(Source) || At > ValidUntil || QuantityScope is <= 0 ||
            Value < 0 || (Value is null) != (Status == EconomicEvidenceStatus.Unknown))
            throw new ArgumentException("INVALID_ECONOMIC_EVIDENCE");
    }
}

public sealed record EconomicCommission(EconomicEvidence Amount, string? Currency, EconomicEvidence ToUsd)
{
    public decimal? Usd(decimal quantity) => string.IsNullOrWhiteSpace(Currency) ? null :
        Amount.Known(quantity) * ToUsd.Known(quantity);
    public bool Verified(decimal quantity, DateTimeOffset now) => !string.IsNullOrWhiteSpace(Currency) &&
        Amount.Verified(quantity, now) && ToUsd.Verified(quantity, now);
}

public sealed record EconomicComparisonInput(string Instrument, decimal Quantity, decimal Multiplier,
    EconomicEvidence Price, EconomicEvidence QuoteToUsd, decimal StopDistance, decimal TargetDistance,
    EconomicCommission Opening, EconomicCommission Closing, EconomicEvidence RoundTripSpread,
    EconomicEvidence RoundTripSlippage, EconomicEvidence AdverseGap, EconomicEvidence MarginRate,
    EconomicEvidence MinimumQuantity, EconomicEvidence QuantityStep, EconomicEvidence AccountPermitted,
    decimal? ProposedRisk = null);

public sealed record EconomicComparisonResult(string Instrument, decimal Quantity, string Status, string[] Reasons,
    decimal Capital, decimal LossAllowance, decimal OrdinaryBudget, decimal MaximumBudget, decimal EffectiveBudget,
    decimal? NominalExposure, decimal? StopLoss, decimal? OpeningCommissionUsd, decimal? ClosingCommissionUsd,
    decimal? SpreadCost, decimal? SlippageCost, decimal? RequiredMargin, decimal? TotalCosts, decimal KnownCostLowerBound,
    decimal? LossIncludingCostsAndGap, decimal? PotentialGrossProfit, decimal? PotentialNetProfit,
    decimal? BreakEvenPriceDistance, decimal? BreakEvenPips, string RiskGateReason,
    bool ExecutionAuthorized = false);

// Diagnostic companion to ExecutionFeasibilityAnalyzer. No order transport or policy changes.
public static class EconomicComparison
{
    public static EconomicComparisonResult Analyze(RiskPolicy policy, AccountState account,
        EconomicComparisonInput input, DateTimeOffset now)
    {
        policy.Validate();
        if (policy.AllocatedCapital != 100 || policy.CumulativeLossLimit != 20 || account.Capital is null ||
            account.Capital.InitialCapital != policy.AllocatedCapital || account.Capital.LossAllowance != policy.CumulativeLossLimit)
            throw new ArgumentException("ECONOMIC_ALLOCATION_REQUIRED");
        if (string.IsNullOrWhiteSpace(input.Instrument) || input.Quantity <= 0 || input.Multiplier <= 0 ||
            input.StopDistance <= 0 || input.TargetDistance <= 0 || input.ProposedRisk is <= 0 || input.ProposedRisk > policy.MaximumRisk)
            throw new ArgumentException("INVALID_ECONOMIC_SCENARIO");
        var facts = new[] {input.Price,input.QuoteToUsd,input.RoundTripSpread,input.RoundTripSlippage,input.AdverseGap,
            input.MarginRate,input.MinimumQuantity,input.QuantityStep,input.AccountPermitted,
            input.Opening.Amount,input.Opening.ToUsd,input.Closing.Amount,input.Closing.ToUsd};
        foreach (var fact in facts) fact.Validate();
        foreach (var commission in new[] {input.Opening,input.Closing})
            if (commission.Currency is not null && (commission.Currency.Length!=3 || commission.Currency.Any(c=>c is < 'A' or > 'Z')))
                throw new ArgumentException("INVALID_COMMISSION_CURRENCY");
        var q = input.Quantity;
        decimal? Known(EconomicEvidence e) => e.Known(q);
        if (Known(input.Price) is <= 0 || Known(input.QuoteToUsd) is <= 0 || Known(input.MinimumQuantity) is <= 0 ||
            Known(input.QuantityStep) is <= 0 || Known(input.MarginRate) is <= 0 or > 1 ||
            Known(input.AccountPermitted) is not (null or 0 or 1) || Known(input.Opening.ToUsd) is <= 0 || Known(input.Closing.ToUsd) is <= 0 ||
            input.Opening.Currency == "USD" && Known(input.Opening.ToUsd) is decimal openFx && openFx != 1 ||
            input.Closing.Currency == "USD" && Known(input.Closing.ToUsd) is decimal closeFx && closeFx != 1)
            throw new ArgumentException("INVALID_ECONOMIC_UNITS");
        var reasons = new List<string>();
        if (!facts.All(e => e.Verified(q,now)) || !input.Opening.Verified(q,now) || !input.Closing.Verified(q,now))
            reasons.Add("ESSENTIAL_EVIDENCE_UNVERIFIED");
        // Ask the existing risk engine for its effective room, with no executable facts.
        // Placeholder price is used only for that gate when price is unknown; never output as evidence.
        var gatePrice = Known(input.Price) ?? input.StopDistance + 1;
        if (gatePrice <= input.StopDistance) throw new ArgumentException("INVALID_ECONOMIC_STOP");
        var request = new RiskRequest(input.Instrument,"BUY",gatePrice,gatePrice,gatePrice-input.StopDistance,
            1,1,1,1,1,account.Equity,0,0,0,0,now,input.ProposedRisk);
        var risk = RiskEngine.Evaluate(policy,account,request,now);
        if (risk.Reason != "EXECUTION_DATA_INCOMPLETE") reasons.Add(risk.Reason);
        var fx = input.Multiplier * Known(input.QuoteToUsd);
        var exposure = q * Known(input.Price) * fx;
        var stop = q * input.StopDistance * fx;
        var gross = q * input.TargetDistance * fx;
        var open = input.Opening.Usd(q); var close = input.Closing.Usd(q);
        var spread = q * Known(input.RoundTripSpread) * fx;
        var slippage = q * Known(input.RoundTripSlippage) * fx;
        var costs = open + close + spread + slippage;
        // Unknown components stay null in totals. Only the explicitly named lower bound treats missing parts as zero.
        var lowerBound = (open??0)+(close??0)+(spread??0)+(slippage??0);
        var loss = stop + costs + q * Known(input.AdverseGap) * fx;
        var margin = exposure * Known(input.MarginRate);
        var positions = account.OpenPositions.Concat(account.PendingOrders).ToArray();
        var exposureRoom = account.Equity * policy.MaxLeverage * policy.Protection(account.Equity).ExposureFactor - positions.Sum(p=>p.Notional);
        var marginRoom = account.Equity - positions.Sum(p=>p.Margin) - policy.MinFreeMargin;
        if (Known(input.AccountPermitted) == 0) reasons.Add("ACCOUNT_NOT_PERMITTED");
        if (Known(input.MinimumQuantity) is decimal min && q < min) reasons.Add("BELOW_MINIMUM_QUANTITY");
        if (Known(input.MinimumQuantity) is decimal lattice && Known(input.QuantityStep) is decimal step && (q-lattice)%step != 0)
            reasons.Add("INVALID_QUANTITY_INCREMENT");
        if (exposure > exposureRoom) reasons.Add("VIRTUAL_CAPITAL_INSUFFICIENT");
        if (margin + costs > marginRoom) reasons.Add("VIRTUAL_MARGIN_INSUFFICIENT");
        if (lowerBound > risk.Budget) reasons.Add("COST_EXCEEDS_RISK_BUDGET");
        if (loss > risk.Budget) reasons.Add("LOSS_EXCEEDS_RISK_BUDGET");
        if (gross > 0 && gross - costs <= 0) reasons.Add("POSITIVE_GROSS_NONPOSITIVE_NET");
        var breakEven = costs / (q * fx);
        var unverified = reasons.Contains("ESSENTIAL_EVIDENCE_UNVERIFIED");
        return new(input.Instrument,q,unverified ? "UNVERIFIED" : reasons.Count > 0 ? "VERIFIED_MODEL_REJECTED" : "VERIFIED_MODEL_ONLY",
            reasons.Distinct().ToArray(),account.Equity,account.Capital.LossAllowance,account.Equity*policy.OrdinaryRisk,
            account.Equity*policy.MaximumRisk,risk.Budget,exposure,stop,open,close,spread,slippage,margin,costs,lowerBound,loss,gross,gross-costs,
            breakEven,input.Instrument=="EUR/USD" ? breakEven/.0001m : null,risk.Reason);
    }
}
