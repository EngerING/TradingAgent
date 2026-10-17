namespace TradingAgent.Core;

public sealed record RiskPolicy(
    string Version = "research-capital-v3", decimal OrdinaryRisk = .0025m, decimal MaximumRisk = .005m,
    decimal DailyLimit = .01m, decimal WeeklyLimit = .02m, decimal DrawdownLimit = .05m,
    int MaxPositions = 1, decimal PreventiveDrawdown = .02m, int PreventiveLossStreak = 3,
    decimal ReductionFactor = .5m, decimal MaxLeverage = 1m, decimal MinFreeMargin = 0m,
    decimal Buffer = 0m, int MaxDataAgeSeconds = 30,
    decimal AllocatedCapital = 100m, decimal CumulativeLossLimit = 20m,
    decimal ReviewEquity = 95m, decimal ReduceEquity = 90m, decimal RestrictEquity = 85m,
    decimal ReducedRiskFactor = .5m, decimal RestrictedRiskFactor = .25m)
{
    public void Validate()
        => ValidateCeiling(.005m);

    // Only the inactive Paper profile study may use this internal ceiling.
    internal void ValidatePaperExperimental() => ValidateCeiling(.10m);

    private void ValidateCeiling(decimal ceiling)
    {
        if (string.IsNullOrWhiteSpace(Version) || OrdinaryRisk <= 0 || OrdinaryRisk > MaximumRisk || MaximumRisk > ceiling ||
            DailyLimit <= 0 || DailyLimit >= 1 || WeeklyLimit <= 0 || WeeklyLimit >= 1 ||
            DrawdownLimit <= 0 || DrawdownLimit >= 1 || MaxPositions != 1 ||
            PreventiveDrawdown < 0 || PreventiveDrawdown >= DrawdownLimit || PreventiveLossStreak < 1 ||
            ReductionFactor <= 0 || ReductionFactor > 1 || MaxLeverage <= 0 || MinFreeMargin < 0 || Buffer < 0 || MaxDataAgeSeconds < 1 ||
            AllocatedCapital <= 0 || CumulativeLossLimit <= 0 || CumulativeLossLimit >= AllocatedCapital ||
            ReviewEquity > AllocatedCapital || ReviewEquity <= ReduceEquity || ReduceEquity <= RestrictEquity ||
            RestrictEquity <= AllocatedCapital - CumulativeLossLimit || ReducedRiskFactor <= 0 || ReducedRiskFactor > 1 ||
            RestrictedRiskFactor <= 0 || RestrictedRiskFactor > ReducedRiskFactor)
            throw new ArgumentException("Invalid risk policy or ceiling; one position required.");
    }
    public CapitalProtection Protection(decimal equity) => equity <= AllocatedCapital - CumulativeLossLimit
        ? new("SUSPENDED", 0, 0) : equity <= RestrictEquity
        ? new("RESTRICTED", RestrictedRiskFactor, RestrictedRiskFactor) : equity <= ReduceEquity
        ? new("REDUCED", ReducedRiskFactor, ReducedRiskFactor) : equity <= ReviewEquity
        ? new("REVIEW", 1, 1) : new("NORMAL", 1, 1);
}

public sealed record PositionRisk(decimal RemainingLoss, decimal Notional, decimal Margin);
public sealed record AccountState
{
    public required string AccountId { get; init; }
    public required decimal Equity { get; init; }
    public required decimal Units { get; init; }
    public decimal Nav => Units > 0 ? Equity / Units : 0;
    public required decimal DayNav { get; init; }
    public required decimal WeekNav { get; init; }
    public required decimal HighNav { get; init; }
    public required DateTimeOffset At { get; init; }
    public int LossStreak { get; init; }
    public string PolicyVersion { get; init; } = "";
    public string[] Halts { get; init; } = [];
    public string? ReservationId { get; init; }
    public PositionRisk[] OpenPositions { get; init; } = [];
    public PositionRisk[] PendingOrders { get; init; } = [];
    // Nullable solely to deserialize old snapshots. Missing allocation blocks entries.
    public VirtualCapital? Capital { get; init; }
    public PaperContinuation? PaperContinuation { get; init; }
    public decimal DailyLoss => DayNav > 0 ? Math.Max(0, 1 - Nav / DayNav) : 1;
    public decimal WeeklyLoss => WeekNav > 0 ? Math.Max(0, 1 - Nav / WeekNav) : 1;
    public decimal Drawdown => HighNav > 0 ? Math.Max(0, 1 - Nav / HighNav) : 1;
    public static AccountState Initial(string id, decimal equity, DateTimeOffset at, decimal lossAllowance = 20m)
    {
        if (string.IsNullOrWhiteSpace(id) || equity <= 0) throw new ArgumentException("Invalid account/equity");
        var capital = new VirtualCapital(equity, lossAllowance);
        capital.Validate();
        return new() { AccountId = id, Equity = equity, Units = equity / 100m, Capital = capital,
            DayNav = 100, WeekNav = 100, HighNav = 100, At = at.ToUniversalTime() };
    }
    public AccountState Halt(string reason) => this with { Halts = Halts.Append(reason).Distinct().ToArray() };
    public AccountState Mark(decimal equity, DateTimeOffset at, RiskPolicy policy)
    {
        if (at < At) throw new ArgumentException("Out of order equity event");
        // Phase 2 uses simulation events. Carry last known NAV into the new period,
        // so overnight losses remain charged; no historical loss is silently dropped.
        var day = at.UtcDateTime.Date;
        static DateTime Monday(DateTime d) => d.AddDays(-(((int)d.DayOfWeek + 6) % 7));
        var next = this with { Equity = equity, At = at.ToUniversalTime(),
            Capital = Capital?.Mark(equity, Capital.OpenCosts),
            DayNav = day != At.UtcDateTime.Date ? Nav : DayNav,
            WeekNav = Monday(day) != Monday(At.UtcDateTime.Date) ? Nav : WeekNav,
            HighNav = Math.Max(HighNav, equity / Units) };
        if (equity <= 0) return next.Halt("CAPITAL_DEPLETED");
        if (next.Capital is { RemainingLoss: <= 0 }) next = next.Halt("CUMULATIVE_LOSS_LIMIT");
        if (next.DailyLoss >= policy.DailyLimit) next = next.Halt("DAILY_LIMIT");
        if (next.WeeklyLoss >= policy.WeeklyLimit) next = next.Halt("WEEKLY_LIMIT");
        if (next.Drawdown >= policy.DrawdownLimit) next = next.Halt("DRAWDOWN_LIMIT");
        return next;
    }
    public AccountState CashFlow(decimal amount)
    {
        if (Capital is not null) throw new InvalidOperationException("EXTERNAL_CAPITAL_NOT_ALLOCATED");
        if (Equity + amount <= 0 || Nav <= 0) throw new ArgumentException("Invalid cash flow");
        return this with { Equity = Equity + amount, Units = Units + amount / Nav };
    }
    public AccountState Settle(decimal netPnl, decimal costs, DateTimeOffset at, RiskPolicy policy)
    {
        var capital = (Capital ?? throw new InvalidOperationException("VIRTUAL_CAPITAL_REQUIRED")).Settle(netPnl, costs);
        return (this with { Capital = capital, ReservationId = null, OpenPositions = [], PendingOrders = [],
            LossStreak = netPnl < 0 ? LossStreak + 1 : 0 }).Mark(capital.Equity, at, policy);
    }
    public AccountState ValuePosition(decimal unrealizedNetPnl, decimal openCosts, decimal remainingRisk,
        DateTimeOffset at, RiskPolicy policy)
    {
        if (Capital is null || ReservationId is null || OpenPositions.Length != 1 || PendingOrders.Length != 0 ||
            openCosts < 0 || remainingRisk < 0) throw new ArgumentException("INVALID_SIMULATED_POSITION_VALUATION");
        var capital = Capital.Mark(Capital.InitialCapital + Capital.RealizedNetPnl + unrealizedNetPnl, openCosts);
        return (this with {Capital = capital, OpenPositions = [OpenPositions[0] with {RemainingLoss = remainingRisk} ]})
            .Mark(capital.Equity,at,policy);
    }
}

public sealed record RiskRequest(
    string Instrument, string Side, decimal Bid, decimal Ask, decimal Stop,
    decimal QuoteToAccountFx, decimal Multiplier, decimal MinQuantity, decimal QuantityStep,
    decimal MarginRate, decimal AvailableMargin, decimal CommissionFixedRoundTrip,
    decimal CommissionPerUnitRoundTrip, decimal SlippagePerUnit, decimal AdverseGapPerUnit,
    DateTimeOffset MarketAt, decimal? ProposedRisk = null, ExecutionFacts? Execution = null,
    decimal? MaximumQuantity = null);

public sealed record RiskEvaluation(
    string Decision, string Reason, string PolicyVersion, decimal Equity, decimal RiskFraction,
    decimal Budget, decimal Quantity, decimal NominalExposure, decimal RequiredMargin,
    decimal StopDistance, decimal SpreadCost, decimal Commissions, decimal SlippageCost,
    decimal AdverseLoss, decimal EstimatedLoss, decimal OpenRisk,
    decimal DailyLoss, decimal WeeklyLoss, decimal Drawdown)
{
    public bool Allowed => Decision == "ALLOW_SIMULATION";
    public string CapitalLevel { get; init; } = "UNKNOWN";
    public decimal ConsumedLoss { get; init; }
    public decimal RemainingLoss { get; init; }
    public ExecutionFeasibility? Feasibility { get; init; }
}

public static partial class RiskEngine
{
    public static RiskEvaluation Evaluate(RiskPolicy p, AccountState a, RiskRequest r, DateTimeOffset now)
    {
        p.Validate();
        return EvaluateValidated(p,a,r,now);
    }

    internal static RiskEvaluation EvaluateValidated(RiskPolicy p, AccountState a, RiskRequest r, DateTimeOffset now,
        bool paperExperimental = false)
    {
        if (paperExperimental) PaperRiskProfile.ValidateScope(p,a);
        decimal fraction = r.ProposedRisk ?? p.OrdinaryRisk;
        var existing = a.OpenPositions.Concat(a.PendingOrders).ToArray();
        var openRisk = existing.Sum(x => x.RemainingLoss);
        RiskEvaluation Deny(string reason, string decision = "DENY") => new(decision, reason, p.Version,
            a.Equity, fraction, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, openRisk, a.DailyLoss, a.WeeklyLoss, a.Drawdown)
            { CapitalLevel = PaperRiskProfile.Protection(p,a.Equity,paperExperimental).Level, ConsumedLoss = a.Capital?.ConsumedLoss ?? 0,
                RemainingLoss = a.Capital?.RemainingLoss ?? 0 };
        if (a.Capital is null) return Deny("VIRTUAL_CAPITAL_REQUIRED");
        a.Capital.Validate();
        if (a.Capital.InitialCapital != p.AllocatedCapital || a.Capital.LossAllowance != p.CumulativeLossLimit)
            return Deny("ALLOCATION_POLICY_MISMATCH");
        if (a.Equity != a.Capital.Equity || a.Units <= 0 || a.DayNav <= 0 || a.WeekNav <= 0 || a.HighNav <= 0)
            return Deny("VIRTUAL_CAPITAL_MISMATCH");
        if (existing.Any(x => x.RemainingLoss < 0 || x.Notional < 0 || x.Margin < 0)) return Deny("INVALID_INPUT");
        var lossRoom = Math.Min(a.Capital.RemainingLoss, p.CumulativeLossLimit - a.Capital.ConsumedLoss);
        if (lossRoom <= 0 || a.Equity <= p.AllocatedCapital - p.CumulativeLossLimit)
            return Deny("CUMULATIVE_LOSS_LIMIT", "HALT");
        if (paperExperimental && PaperRiskProfile.EntryBlock(a,now) is string block) return Deny(block,"HALT");
        if (a.Halts.Length > 0) return Deny(string.Join(",", a.Halts), "HALT");
        if (a.Equity <= 0 || !paperExperimental && (a.DailyLoss >= p.DailyLimit || a.WeeklyLoss >= p.WeeklyLimit || a.Drawdown >= p.DrawdownLimit))
            return Deny("LOSS_LIMIT", "HALT");
        if (a.At > now || r.MarketAt > now || now - a.At > TimeSpan.FromSeconds(p.MaxDataAgeSeconds) ||
            now - r.MarketAt > TimeSpan.FromSeconds(p.MaxDataAgeSeconds)) return Deny("DATA_STALE");
        if (fraction <= 0 || fraction > p.MaximumRisk) return Deny("RISK_EXCEEDS_POLICY");
        if (openRisk + p.Buffer >= lossRoom) return Deny("CUMULATIVE_LOSS_RESERVED");
        if (a.ReservationId != null || existing.Length >= p.MaxPositions) return Deny("POSITION_LIMIT");
        if (string.IsNullOrWhiteSpace(r.Instrument) || r.Side is not ("BUY" or "SELL") ||
            r.Bid <= 0 || r.Ask < r.Bid || r.Stop <= 0 || r.QuoteToAccountFx <= 0 || r.Multiplier <= 0 ||
            r.MinQuantity <= 0 || r.QuantityStep <= 0 || r.MarginRate <= 0 || r.MarginRate > 1 || r.AvailableMargin < 0 ||
            r.CommissionFixedRoundTrip < 0 || r.CommissionPerUnitRoundTrip < 0 || r.SlippagePerUnit < 0 || r.AdverseGapPerUnit < 0 ||
            a.OpenPositions.Any(x => x.RemainingLoss < 0 || x.Notional < 0 || x.Margin < 0)) return Deny("INVALID_INPUT");
        if ((r.Side == "BUY" && r.Stop >= r.Bid) || (r.Side == "SELL" && r.Stop <= r.Ask)) return Deny("INVALID_STOP");
        if (!paperExperimental && (a.Drawdown >= p.PreventiveDrawdown || a.LossStreak >= p.PreventiveLossStreak)) fraction *= p.ReductionFactor;
        var protection = PaperRiskProfile.Protection(p,a.Equity,paperExperimental);
        fraction *= protection.RiskFactor;
        var room = paperExperimental ? 10m : new[] { a.Units * (a.Nav - (1-p.DailyLimit)*a.DayNav),
            a.Units * (a.Nav - (1-p.WeeklyLimit)*a.WeekNav), a.Units * (a.Nav - (1-p.DrawdownLimit)*a.HighNav) }.Min();
        var budget = Math.Max(0, Math.Min(a.Equity * fraction, Math.Min(room, lossRoom) - openRisk - p.Buffer));
        var execution = ExecutionFeasibilityAnalyzer.AnalyzeValidated(p,a,r,budget,now,paperExperimental);
        if (!execution.Allowed) return Deny(execution.Reason) with { Budget = budget, Feasibility = execution };
        return new("ALLOW_SIMULATION", "WITHIN_RESEARCH_POLICY", p.Version, a.Equity, fraction, budget, execution.Quantity,
            execution.NominalExposure, execution.RequiredMargin, execution.StopDistance, execution.SpreadCost,
            execution.Commissions, execution.SlippageCost, execution.AdverseLoss, execution.EstimatedLoss,
            openRisk, a.DailyLoss, a.WeeklyLoss, a.Drawdown)
            { CapitalLevel = protection.Level, ConsumedLoss = a.Capital.ConsumedLoss, RemainingLoss = lossRoom, Feasibility = execution };
    }
}
