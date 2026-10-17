using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace TradingAgent.Core;

public static class Evidence
{
    public static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web)
        { UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow };
    public static string Hash(string text) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(text))).ToLowerInvariant();
}

// Strings containing conditions are specifications, never executable generated code.
public sealed record StrategyVersion(string StrategyId, string Name, int Version, string Instrument,
    string Timeframes, string EntryRule, string ExitRule, decimal StopDistance, decimal TakeProfitDistance,
    decimal MaxExposure, string ExecutionRequirements, string ParametersJson)
{
    [JsonIgnore]
    public string Hash => Evidence.Hash(JsonSerializer.Serialize(this));
    public void Validate()
    {
        if (string.IsNullOrWhiteSpace(StrategyId) || string.IsNullOrWhiteSpace(Name) || Version < 1 ||
            string.IsNullOrWhiteSpace(Instrument) || string.IsNullOrWhiteSpace(EntryRule) || string.IsNullOrWhiteSpace(ExitRule) ||
            StopDistance <= 0 || TakeProfitDistance <= 0 || MaxExposure <= 0) throw new ArgumentException("Invalid strategy");
        using var _ = JsonDocument.Parse(ParametersJson);
    }
}
public sealed record StrategyApproval(string StrategyHash, string PolicyVersion, string Environment,
    string Owner, DateTimeOffset At, DateTimeOffset ExpiresAt)
{
    public bool Matches(StrategyVersion version, RiskPolicy policy, DateTimeOffset now) =>
        Environment == "PAPER_TRADING" && StrategyHash == version.Hash && PolicyVersion == policy.Version &&
        !string.IsNullOrWhiteSpace(Owner) && At <= now && now < ExpiresAt;
}

// Evidence and lifecycle are separate append-only records: adding results never changes a strategy hash.
public sealed record StrategyReview(string StrategyHash, string State, string? HistoricalRunId,
    string? OutOfSampleRunId, string? PaperRunId, string[] SuspensionReasons, DateTimeOffset At)
{
    public void Validate()
    {
        if(string.IsNullOrWhiteSpace(StrategyHash) || State is not ("CANDIDATE" or "BACKTESTED" or "OOS_VALIDATED" or "PAPER_PASSED" or "SUSPENDED") || SuspensionReasons is null)
            throw new ArgumentException("Invalid research lifecycle state; LIVE approval is unavailable");
        if(State=="SUSPENDED" && SuspensionReasons.Length==0)throw new ArgumentException("Suspension reason required");
        if(State is "BACKTESTED" or "OOS_VALIDATED" or "PAPER_PASSED" && string.IsNullOrWhiteSpace(HistoricalRunId))throw new ArgumentException("Backtest evidence required");
        if(State is "OOS_VALIDATED" or "PAPER_PASSED" && string.IsNullOrWhiteSpace(OutOfSampleRunId))throw new ArgumentException("Out of sample evidence required");
        if(State=="PAPER_PASSED" && string.IsNullOrWhiteSpace(PaperRunId))throw new ArgumentException("Paper evidence required");
    }
}

public sealed record Experience(string Id, string AccountId, string Instrument, DateTimeOffset At,
    string Session, string StrategyHash, decimal ProposedRisk, string Reason, bool Rejected,
    Dictionary<string, decimal> Features, string MarketBeforeJson, decimal EstimatedCosts,
    decimal? SimulatedPnl = null, decimal? ObservedCosts = null, string? MarketAfterJson = null,
    string? BehaviorChange = null);

public static class ExperienceSimilarity
{
    // Scales must be fixed on development data. Only episodes available before cutoff qualify.
    public static IEnumerable<(Experience Episode, double Distance)> Find(
        Dictionary<string, decimal> query, IEnumerable<Experience> history,
        Dictionary<string, decimal> scales, string instrument, DateTimeOffset cutoff, int count = 5)
    {
        if (query.Count == 0 || query.Keys.Any(k => !scales.ContainsKey(k) || scales[k] <= 0))
            throw new ArgumentException("Positive feature scales required");
        return history.Where(e=>e.At < cutoff && e.Instrument==instrument && query.Keys.All(e.Features.ContainsKey))
            .Select(e=>(Episode:e, Distance:Math.Sqrt(query.Sum(kv=>Math.Pow((double)((kv.Value-e.Features[kv.Key])/scales[kv.Key]),2)))))
            .OrderBy(e=>e.Distance).ThenBy(e=>e.Episode.Id).Take(Math.Clamp(count,1,100));
    }
}

public sealed record AiContext(string MarketSummary, Dictionary<string, decimal> Indicators,
    string StrategyResults, Experience[] Experiences, RiskPolicy ReadOnlyRiskPolicy);
public sealed record AiProposal(string Hypothesis, string Explanation, string StrategyHash,
    decimal ProposedRisk, string[] EvidenceIds);
public interface IResearchAi { Task<AiProposal> ProposeAsync(AiContext context, CancellationToken ct); }
public sealed class DisabledResearchAi : IResearchAi
{
    public Task<AiProposal> ProposeAsync(AiContext context, CancellationToken ct) =>
        Task.FromException<AiProposal>(new InvalidOperationException("OPENAI_DISABLED"));
}
public static class ProposalValidator
{
    public static AiProposal Parse(string json, RiskPolicy policy)
    {
        var p = JsonSerializer.Deserialize<AiProposal>(json, Evidence.Json) ?? throw new ArgumentException("Empty proposal");
        if (string.IsNullOrWhiteSpace(p.Hypothesis) || string.IsNullOrWhiteSpace(p.Explanation) ||
            string.IsNullOrWhiteSpace(p.StrategyHash) || p.ProposedRisk <= 0 || p.ProposedRisk > policy.MaximumRisk || p.EvidenceIds is null)
            throw new ArgumentException("Invalid research proposal");
        return p;
    }
}
