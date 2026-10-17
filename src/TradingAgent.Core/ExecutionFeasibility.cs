namespace TradingAgent.Core;

// These are research inputs, never an execution authorization or broker attestation.
public sealed record ExecutionFacts(
    string Source, string Environment, string Mode, DateTimeOffset At,
    decimal? OpeningCommission, decimal? ClosingCommission,
    bool CostsReliable = false, bool MarginReliable = false, bool ContractReliable = false,
    bool BrokerPermitsEntry = false, string QuoteStatus = "UNKNOWN", decimal? TakeProfit = null,
    RealAccountConstraints? EquivalentRealAccount = null);

public sealed record RealAccountConstraints(
    decimal? MinimumQuantity = null, decimal? QuantityStep = null, decimal? MarginRate = null,
    decimal? MaximumLeverage = null, bool? InstrumentPermitted = null,
    bool? ExecutionModePermitted = null, bool? AccountEligible = null)
{
    public bool Complete => MinimumQuantity is > 0 && QuantityStep is > 0 && MarginRate is > 0 and <= 1 &&
        MaximumLeverage is > 0 && InstrumentPermitted == true && ExecutionModePermitted == true && AccountEligible == true;
}

public enum ExecutionRejection
{
    None, ExcessiveCost, InsufficientCapital, InsufficientMargin, MinimumSize,
    ExcessiveRisk, IncompleteData, BrokerRestrictions
}

public sealed record ExecutionFeasibility(
    bool Allowed, string Reason, ExecutionRejection Rejection, decimal Budget,
    decimal Quantity = 0, decimal NominalExposure = 0, decimal RequiredMargin = 0,
    decimal StopDistance = 0, decimal StopLoss = 0, decimal SpreadCost = 0,
    decimal Commissions = 0, decimal SlippageCost = 0, decimal AdverseLoss = 0,
    decimal EstimatedLoss = 0, decimal? PotentialGrossProfit = null, decimal? PotentialNetProfit = null,
    string ProductionValidation = "UNVALIDATED_FOR_PRODUCTION");

public static class ExecutionFeasibilityAnalyzer
{
    public static ExecutionFeasibility Analyze(RiskPolicy policy, AccountState account, RiskRequest request,
        decimal budget, DateTimeOffset now)
    {
        policy.Validate();
        return AnalyzeValidated(policy,account,request,budget,now);
    }

    internal static ExecutionFeasibility AnalyzeValidated(RiskPolicy policy, AccountState account, RiskRequest request,
        decimal budget, DateTimeOffset now, bool paperExperimental = false)
    {
        if (paperExperimental) PaperRiskProfile.ValidateScope(policy,account);
        ExecutionFeasibility Deny(string reason, ExecutionRejection category) => new(false, reason, category, budget);
        var f = request.Execution;
        if (account.Capital is null || account.Capital.Equity != account.Equity)
            return Deny("VIRTUAL_CAPITAL_REQUIRED", ExecutionRejection.IncompleteData);
        account.Capital.Validate();
        if(account.Capital.InitialCapital!=policy.AllocatedCapital || account.Capital.LossAllowance!=policy.CumulativeLossLimit)
            return Deny("ALLOCATION_POLICY_MISMATCH", ExecutionRejection.IncompleteData);
        if (account.Halts.Length > 0 || account.Capital.RemainingLoss <= 0)
            return Deny("ACCOUNT_HALTED", ExecutionRejection.ExcessiveRisk);
        if (f is null || string.IsNullOrWhiteSpace(f.Source) || f.Environment != account.Capital.Environment ||
            f.Mode is not ("STANDARD" or "ODD_LOT" or "SIMULATED") ||
            !f.CostsReliable || !f.MarginReliable || !f.ContractReliable ||
            f.OpeningCommission is null || f.ClosingCommission is null)
            return Deny("EXECUTION_DATA_INCOMPLETE", ExecutionRejection.IncompleteData);
        if (account.At > now || now-account.At > TimeSpan.FromSeconds(policy.MaxDataAgeSeconds) ||
            f.At > now || now - f.At > TimeSpan.FromSeconds(policy.MaxDataAgeSeconds) ||
            request.MarketAt > now || now - request.MarketAt > TimeSpan.FromSeconds(policy.MaxDataAgeSeconds) ||
            f.QuoteStatus != (f.Environment == "SIMULATION" ? "SIMULATED" : "LIVE"))
            return Deny("MARKET_DATA_UNUSABLE", ExecutionRejection.IncompleteData);
        if (!f.BrokerPermitsEntry) return Deny("BROKER_RESTRICTION", ExecutionRejection.BrokerRestrictions);
        if (budget <= 0) return Deny("RISK_BUDGET_EXHAUSTED", ExecutionRejection.ExcessiveRisk);
        if (budget > account.Equity * policy.MaximumRisk || budget > account.Capital.RemainingLoss ||
            paperExperimental && budget > 10)
            return Deny("RISK_EXCEEDS_POLICY", ExecutionRejection.ExcessiveRisk);
        if (request.Side is not ("BUY" or "SELL") || string.IsNullOrWhiteSpace(request.Instrument) ||
            request.Bid <= 0 || request.Ask < request.Bid || request.Stop <= 0 ||
            request.Multiplier <= 0 || request.QuoteToAccountFx <= 0 || request.MinQuantity <= 0 || request.QuantityStep <= 0 ||
            request.MarginRate <= 0 || request.MarginRate > 1 || request.AvailableMargin < 0 ||
            request.CommissionFixedRoundTrip < 0 || request.CommissionPerUnitRoundTrip < 0 ||
            request.SlippagePerUnit < 0 || request.AdverseGapPerUnit < 0 || f.OpeningCommission < 0 || f.ClosingCommission < 0 ||
            f.OpeningCommission + f.ClosingCommission != request.CommissionFixedRoundTrip)
            return Deny("EXECUTION_DATA_INVALID", ExecutionRejection.IncompleteData);
        var positions = account.OpenPositions.Concat(account.PendingOrders).ToArray();
        if (positions.Any(p => p.RemainingLoss < 0 || p.Notional < 0 || p.Margin < 0))
            return Deny("EXECUTION_DATA_INVALID", ExecutionRejection.IncompleteData);
        var real = f.EquivalentRealAccount;
        if (real is not null && (real.InstrumentPermitted == false || real.ExecutionModePermitted == false || real.AccountEligible == false))
            return Deny("REAL_ACCOUNT_RESTRICTION", ExecutionRejection.BrokerRestrictions);
        if (real is not null && (real.MinimumQuantity is <= 0 || real.QuantityStep is <= 0 ||
            real.MarginRate is <= 0 or > 1 || real.MaximumLeverage is <= 0))
            return Deny("REAL_ACCOUNT_DATA_INVALID", ExecutionRejection.IncompleteData);
        var mid = (request.Ask + request.Bid) / 2;
        if ((request.Side == "BUY" && request.Stop >= request.Bid) || (request.Side == "SELL" && request.Stop <= request.Ask))
            return Deny("INVALID_STOP", ExecutionRejection.ExcessiveRisk);
        if (f.TakeProfit is decimal tp && ((request.Side == "BUY" && tp <= request.Ask) || (request.Side == "SELL" && tp >= request.Bid)))
            return Deny("INVALID_TAKE_PROFIT", ExecutionRejection.IncompleteData);
        var fx = request.Multiplier * request.QuoteToAccountFx;
        var distance = Math.Abs(mid - request.Stop);
        var spread = (request.Ask - request.Bid) * fx;
        var unitCosts = spread + request.SlippagePerUnit * fx + request.CommissionPerUnitRoundTrip;
        var unitRisk = distance * fx + unitCosts + request.AdverseGapPerUnit * fx;
        var unitNotional = request.Ask * fx;
        var marginRate = Math.Max(request.MarginRate, real?.MarginRate ?? request.MarginRate);
        var unitMargin = unitNotional * marginRate;
        var marginRoom = Math.Min(request.AvailableMargin, account.Equity - positions.Sum(p => p.Margin));
        var exposureRoom = account.Equity * Math.Min(policy.MaxLeverage, real?.MaximumLeverage ?? policy.MaxLeverage) *
            PaperRiskProfile.Protection(policy,account.Equity,paperExperimental).ExposureFactor - positions.Sum(p => p.Notional);
        var minimum = Math.Max(request.MinQuantity, real?.MinimumQuantity ?? request.MinQuantity);
        // Align a known real minimum to the Paper contract's quantity lattice, never silently round up the budget.
        minimum = request.MinQuantity + decimal.Ceiling((minimum - request.MinQuantity) / request.QuantityStep) * request.QuantityStep;
        var fixedFees = request.CommissionFixedRoundTrip;
        if (fixedFees + minimum * unitCosts >= budget)
            return Deny("COST_EXCEEDS_RISK_BUDGET", ExecutionRejection.ExcessiveCost);
        if (fixedFees + minimum * unitRisk > budget)
            return Deny("MIN_SIZE_EXCEEDS_BUDGET", ExecutionRejection.MinimumSize);
        if (minimum * (unitMargin + unitCosts) + fixedFees + policy.MinFreeMargin > marginRoom)
            return Deny("VIRTUAL_MARGIN_INSUFFICIENT", ExecutionRejection.InsufficientMargin);
        if (minimum * unitNotional > exposureRoom)
            return Deny("VIRTUAL_CAPITAL_INSUFFICIENT", ExecutionRejection.InsufficientCapital);
        var riskCap = (budget - fixedFees) / unitRisk;
        var marginCap = (marginRoom - policy.MinFreeMargin - fixedFees) / (unitMargin + unitCosts);
        var exposureCap = exposureRoom / unitNotional;
        if(request.MaximumQuantity is <= 0) return Deny("INVALID_QUANTITY_CAP",ExecutionRejection.IncompleteData);
        var cap = Math.Min(request.MaximumQuantity ?? decimal.MaxValue,Math.Min(riskCap, Math.Min(marginCap, exposureCap)));
        var quantity = request.MinQuantity + decimal.Floor((cap - request.MinQuantity) / request.QuantityStep) * request.QuantityStep;
        if (quantity < minimum) return Deny("MIN_SIZE_EXCEEDS_BUDGET", ExecutionRejection.MinimumSize);
        if (real?.QuantityStep is decimal step && (quantity - (real.MinimumQuantity ?? request.MinQuantity)) % step != 0)
            return Deny("REAL_ACCOUNT_QUANTITY_INCREMENT", ExecutionRejection.BrokerRestrictions);
        var commissions = fixedFees + quantity * request.CommissionPerUnitRoundTrip;
        var costs = fixedFees + quantity * unitCosts;
        var estimatedLoss = fixedFees + quantity * unitRisk;
        if (estimatedLoss > budget || estimatedLoss + positions.Sum(p => p.RemainingLoss) + policy.Buffer >
            Math.Min(account.Capital.RemainingLoss,policy.CumulativeLossLimit-account.Capital.ConsumedLoss))
            return Deny("RISK_EXCEEDS_BUDGET", ExecutionRejection.ExcessiveRisk);
        decimal? grossProfit = f.TakeProfit is decimal target ? quantity * Math.Abs(target - mid) * fx : null;
        if (grossProfit is decimal gross && gross <= costs)
            return Deny("COST_EXCEEDS_POTENTIAL_PROFIT", ExecutionRejection.ExcessiveCost);
        return new(true, "ECONOMICALLY_FEASIBLE_FOR_SIMULATION", ExecutionRejection.None, budget, quantity,
            quantity * unitNotional, quantity * unitMargin, distance, quantity * distance * fx, quantity * spread,
            commissions, quantity * request.SlippagePerUnit * fx, quantity * request.AdverseGapPerUnit * fx,
            estimatedLoss, grossProfit, grossProfit - costs,
            real?.Complete == true ? "KNOWN_REAL_RESTRICTIONS_CHECKED_LIVE_DISABLED" : "UNVALIDATED_FOR_PRODUCTION");
    }
}
