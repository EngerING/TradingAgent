namespace TradingAgent.Core;

// Persisted with the allocation, never with a broker session or process.
public sealed record PaperTradeResult(string Id, decimal Net, decimal Fees, DateOnly Day);
public sealed record PaperContinuation(DateOnly Day, int ClosedTrades = 0, decimal? LastNet = null,
    bool FirstLossStopped = false, string? PendingId = null, bool ResultPending = false,
    PaperTradeResult[]? Results = null, string[]? CancelledIds = null);

// An offline candidate, not a broker permission or execution authorization.
// The normal RiskPolicy.Validate and every running service retain the 0.50% ceiling.
public sealed record PaperRiskProfileStudy(string Profile, RiskPolicy Policy, decimal OperationCeiling,
    RiskEvaluation Evaluation)
{
    public bool Active => false;
    public bool ExecutionAuthorized => false;
    public bool LiveEnabled => false;
    public string? ContinuationPolicy => Profile == PaperRiskProfile.Experimental ? PaperRiskProfile.ContinuationPolicy : null;
}

public static class PaperRiskProfile
{
    public const string Experimental = "PAPER_EXPERIMENTAL_10_PERCENT";
    public const string Conservative = "PAPER_CONSERVATIVE";
    public const string ContinuationPolicy = "WIN_TO_CONTINUE / FIRST_LOSS_STOPS_DAY";

    internal static void ValidateScope(RiskPolicy p, AccountState a)
    {
        p.ValidatePaperExperimental();
        if (p.Version != Experimental || p.AllocatedCapital != 100 || p.CumulativeLossLimit != 20 ||
            p.MaxLeverage > 1 || a.Capital?.Environment != "PAPER_TRADING" ||
            a.Capital.InitialCapital != 100 || a.Capital.LossAllowance != 20)
            throw new ArgumentException("STRATEGY_IBKR_PAPER_ONLY");
    }

    internal static CapitalProtection Protection(RiskPolicy p, decimal equity, bool experimental)
        => experimental ? new(equity <= 80 ? "SUSPENDED" : "NORMAL", equity <= 80 ? 0 : 1,
            equity <= 80 ? 0 : 1) : p.Protection(equity);

    private static DateOnly Day(DateTimeOffset at) => DateOnly.FromDateTime(at.UtcDateTime);

    private static PaperContinuation? Continuation(AccountState a)
        => a.PaperContinuation ?? (a.Capital is { RealizedCosts: 0, RealizedGrossPnl: 0,
            CumulativeRealizedLoss: 0, UnrealizedGrossPnl: 0, OpenCosts: 0 } && a.Halts.Length == 0 &&
            a.ReservationId is null && a.OpenPositions.Length == 0 && a.PendingOrders.Length == 0
            ? new(Day(a.At)) : null);

    internal static string? EntryBlock(AccountState a, DateTimeOffset now)
    {
        var c = Continuation(a);
        if (c is null) return a.ReservationId is not null || a.OpenPositions.Length + a.PendingOrders.Length > 0
            ? "POSITION_LIMIT" : "PAPER_CONTINUATION_HISTORY_REQUIRED";
        if (a.PaperContinuation is not null && !HistoryConsistent(a)) return "PAPER_CONTINUATION_HISTORY_INVALID";
        if (c.PendingId is not null || c.ResultPending) return "PAPER_RESULT_UNRESOLVED";
        if (Day(now) < c.Day) return "PAPER_TRADING_DAY_OUT_OF_ORDER";
        if (Day(now) != c.Day) return null;
        if (c.FirstLossStopped) return "DAILY_FIRST_LOSS_STOP";
        if (c.ClosedTrades > 0 && c.LastNet is not > 0) return "DAILY_WIN_REQUIRED";
        return null;
    }

    public static bool HistoryConsistent(AccountState a)
    {
        var c = a.PaperContinuation;
        if (c is null || a.Capital is null || c.Day != Day(a.At) || a.Equity != a.Capital.Equity ||
            c.PendingId is null && (a.Capital.UnrealizedGrossPnl != 0 || a.Capital.OpenCosts != 0)) return false;
        var results = c.Results ?? [];
        var cancelled = c.CancelledIds ?? [];
        var today = results.Where(x => x.Day == c.Day).ToArray();
        return cancelled.All(x=>!string.IsNullOrWhiteSpace(x) && x!=c.PendingId && results.All(r=>r.Id!=x)) &&
            cancelled.Distinct().Count()==cancelled.Length &&
            results.All(x => !string.IsNullOrWhiteSpace(x.Id) && x.Fees >= 0 && x.Day <= c.Day) &&
            results.Select(x => x.Id).Distinct().Count() == results.Length &&
            a.Capital.CumulativeRealizedLoss == results.Sum(x => Math.Max(0,-x.Net)) &&
            a.Capital.RealizedNetPnl == results.Sum(x => x.Net) && a.Capital.RealizedCosts == results.Sum(x => x.Fees) &&
            c.ClosedTrades == today.Length && c.LastNet == today.LastOrDefault()?.Net &&
            c.FirstLossStopped == today.Any(x => x.Net < 0) &&
            c.ResultPending == (c.PendingId is not null) && c.PendingId == a.ReservationId &&
            (c.PendingId is null ? a.OpenPositions.Length + a.PendingOrders.Length == 0 :
                a.OpenPositions.Length + a.PendingOrders.Length == 1 && results.All(x => x.Id != c.PendingId));
    }

    // Offline lifecycle. These methods grant no execution permission and perform no I/O.
    public static AccountState Mark(AccountState a, DateTimeOffset at, RiskPolicy conservative)
    {
        var p = Candidate(conservative); ValidateScope(p,a); a.Capital!.Validate();
        if (at < a.At) throw new ArgumentException("Out of order equity event");
        if (a.Equity != a.Capital.Equity || a.Units <= 0 ||
            a.PaperContinuation is not null && !HistoryConsistent(a))
            throw new InvalidOperationException("PAPER_CONTINUATION_HISTORY_INVALID");
        var c = Continuation(a) ?? throw new InvalidOperationException("PAPER_CONTINUATION_HISTORY_REQUIRED");
        if (Day(at) != c.Day) c = c with { Day = Day(at), ClosedTrades = 0, LastNet = null, FirstLossStopped = false };
        var marked = a with { At = at.ToUniversalTime(), PolicyVersion = Experimental, PaperContinuation = c,
            Equity = a.Capital.Equity, DayNav = Day(at) != Day(a.At) ? a.Nav : a.DayNav,
            HighNav = Math.Max(a.HighNav,a.Capital.Equity/a.Units) };
        return a.Capital.RemainingLoss <= 0 ? marked.Halt("CUMULATIVE_LOSS_LIMIT") : marked;
    }

    public static AccountState Reserve(AccountState a, RiskRequest request, string id, DateTimeOffset at,
        RiskPolicy conservative)
    {
        if (string.IsNullOrWhiteSpace(id)) throw new ArgumentException("PAPER_INTENT_REQUIRED");
        var c = Continuation(a);
        if (c?.PendingId == id || c?.Results?.Any(x => x.Id == id) == true || c?.CancelledIds?.Contains(id)==true)
            throw new InvalidOperationException("PAPER_INTENT_ALREADY_USED");
        a = Mark(a,at,conservative);
        var risk = Study(Experimental,conservative,a,request,at,"IBKR","StrategyPaper",false).Evaluation;
        if (!risk.Allowed) throw new InvalidOperationException(risk.Reason);
        return a with { ReservationId = id, PendingOrders = [new(risk.EstimatedLoss,risk.NominalExposure,risk.RequiredMargin)],
            PaperContinuation = a.PaperContinuation! with { PendingId = id, ResultPending = true } };
    }

    public static AccountState ReleaseUnfilled(AccountState a,string id,DateTimeOffset at,RiskPolicy conservative)
    {
        a=Mark(a,at,conservative);var c=a.PaperContinuation!;
        if(c.CancelledIds?.Contains(id)==true)return a;
        if(c.PendingId!=id || a.ReservationId!=id)throw new InvalidOperationException("PAPER_RESERVATION_REQUIRED");
        return a with {ReservationId=null,PendingOrders=[],OpenPositions=[],PaperContinuation=c with {
            PendingId=null,ResultPending=false,CancelledIds=(c.CancelledIds??[]).Append(id).ToArray()}};
    }

    // Net already includes ALL observed costs. Null/uncertain results retain the reservation across days/restarts.
    public static AccountState Settle(AccountState a, string id, decimal? net, decimal? fees,
        bool resultCertain, DateTimeOffset at, RiskPolicy conservative)
    {
        ValidateScope(Candidate(conservative),a);
        if (a.PaperContinuation is not null && !HistoryConsistent(a))
            throw new InvalidOperationException("PAPER_CONTINUATION_HISTORY_INVALID");
        var c = Continuation(a) ?? throw new InvalidOperationException("PAPER_CONTINUATION_HISTORY_REQUIRED");
        var previous = c.Results?.SingleOrDefault(x => x.Id == id);
        if (previous is not null)
        {
            if (!resultCertain || previous.Net != net || previous.Fees != fees)
                throw new InvalidOperationException("PAPER_RESULT_CONFLICT");
            return a; // Durable deduplication; replay cannot consume losses twice or clear the stop.
        }
        if (c.PendingId != id || a.ReservationId != id) throw new InvalidOperationException("PAPER_RESERVATION_REQUIRED");
        a = Mark(a,at,conservative); c = a.PaperContinuation!;
        if (fees < 0) throw new ArgumentException("Negative costs");
        if (!resultCertain || net is null || fees is null) return a;
        var capital = a.Capital!.Settle(net.Value,fees.Value);
        c = c with { ClosedTrades = c.ClosedTrades + 1, LastNet = net,
            FirstLossStopped = c.FirstLossStopped || net < 0, PendingId = null, ResultPending = false,
            Results = (c.Results ?? []).Append(new(id,net.Value,fees.Value,Day(at))).ToArray() };
        a = a with { Capital = capital, Equity = capital.Equity, ReservationId = null,
            OpenPositions = [], PendingOrders = [], PaperContinuation = c,
            LossStreak = net < 0 ? a.LossStreak + 1 : 0, HighNav = Math.Max(a.HighNav,capital.Equity/a.Units) };
        return capital.RemainingLoss <= 0 ? a.Halt("CUMULATIVE_LOSS_LIMIT") : a;
    }

    public static RiskPolicy Candidate(RiskPolicy conservative)
    {
        conservative.Validate();
        if (conservative.AllocatedCapital != 100 || conservative.CumulativeLossLimit != 20 ||
            conservative.MaxLeverage > 1)
            throw new ArgumentException("PAPER_PROFILE_ALLOCATION_REQUIRED");
        var candidate = conservative with {Version = Experimental, OrdinaryRisk = .10m, MaximumRisk = .10m};
        candidate.ValidatePaperExperimental();
        return candidate;
    }

    public static PaperRiskProfileStudy Study(string profile, RiskPolicy conservative, AccountState account,
        RiskRequest request, DateTimeOffset now, string broker, string mode, bool liveEnabled)
    {
        if (broker != "IBKR" || mode != "StrategyPaper" || liveEnabled ||
            account.Capital?.Environment != "PAPER_TRADING" || request.Execution?.Environment != "PAPER_TRADING")
            throw new ArgumentException("STRATEGY_IBKR_PAPER_ONLY");
        var candidate = Candidate(conservative);
        var policy = profile switch {
            Experimental => candidate, Conservative => conservative,
            _ => throw new ArgumentException("UNKNOWN_PAPER_RISK_PROFILE")
        };
        if (request.Execution.Mode is not ("STANDARD" or "ODD_LOT") ||
            request.Execution.EquivalentRealAccount?.Complete != true)
            throw new ArgumentException("STRATEGY_PAPER_EVIDENCE_REQUIRED");
        var evaluation = RiskEngine.EvaluateValidated(policy,account,request,now,profile == Experimental);
        return new(profile,policy,profile == Experimental ? Math.Min(10,account.Equity * policy.MaximumRisk)
            : account.Equity * policy.MaximumRisk,evaluation);
    }
}
