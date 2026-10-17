namespace TradingAgent.Core;

// Design-time readiness only; never an execution grant. The read-only identity attestation is NOT an order authorization.
public sealed record PaperPreparationChecks(string Environment, bool LiveEnabled, bool ReadOnlyAttested,
    bool PaperAttested, DateTimeOffset AttestedAt, DateTimeOffset ExpiresAt, bool Connected,
    bool Reconciled, bool EmergencyStopped, bool IndependentExecutionAuthorization,
    bool ExecutionCostsVerified, bool VirtualRiskApproved, bool ProtectiveOrdersVerified);
public sealed record PaperPreparationResult(bool IdentityMatches, string[] Blockers,
    bool TransmissionEnabled = false, bool LiveEnabled = false);

// Correlation and event contracts for a future separate Paper execution service.
// No IB order ID is allocated, no order is staged, and no persistence/transport is activated in E.0.
public sealed record PaperIntentReference(string InternalAccountKey, string StrategyVersion, string SignalKey,
    int ContractId, string Side)
{
    public string IdempotencyKey
    {
        get
        {
            if (!System.Text.RegularExpressions.Regex.IsMatch(InternalAccountKey,"^PAPER-[a-f0-9]{16}$") ||
                string.IsNullOrWhiteSpace(StrategyVersion) || string.IsNullOrWhiteSpace(SignalKey) || ContractId <= 0 ||
                Side is not ("BUY" or "SELL")) throw new ArgumentException("INVALID_PAPER_INTENT_REFERENCE");
            // Length-delimited JSON avoids ambiguity from delimiters inside strategy/signal keys.
            return Evidence.Hash(System.Text.Json.JsonSerializer.Serialize(new {schema=1,environment="PAPER_TRADING",
                InternalAccountKey,StrategyVersion,SignalKey,ContractId,Side}));
        }
    }
}
public sealed record PaperFillObservation(string IntentKey, string ExecutionId, int BrokerOrderId, long PermanentId,
    decimal Quantity, decimal Price, DateTimeOffset ExecutedAt);
public sealed record PaperCommissionObservation(string ExecutionId, decimal Amount, string Currency, DateTimeOffset ReceivedAt);

public static class PaperExecutionPreparation
{
    public static PaperPreparationResult Check(string configuredIdentity, IReadOnlyCollection<string> managedIdentities,
        PaperPreparationChecks checks, DateTimeOffset now)
    {
        // Identity values stay in memory and never appear in the returned report or exceptions.
        var exact = !string.IsNullOrWhiteSpace(configuredIdentity) && managedIdentities.Count == 1 &&
            string.Equals(configuredIdentity,managedIdentities.Single(),StringComparison.Ordinal);
        var blockers = new List<string> {"E0_EXECUTION_DISABLED"};
        if (!exact) blockers.Add("EXACT_IDENTITY_MISMATCH");
        if (checks.LiveEnabled || checks.Environment != "PAPER_TRADING") blockers.Add("LIVE_DISABLED");
        if (!checks.PaperAttested || !checks.ReadOnlyAttested || checks.AttestedAt > now || checks.ExpiresAt <= now ||
            checks.ExpiresAt > checks.AttestedAt.AddHours(24)) blockers.Add("READ_ONLY_PAPER_ATTESTATION_INVALID");
        if (!checks.Connected) blockers.Add("BROKER_DISCONNECTED");
        if (!checks.Reconciled) blockers.Add("RECONCILIATION_REQUIRED");
        if (checks.EmergencyStopped) blockers.Add("EMERGENCY_STOP");
        if (!checks.IndependentExecutionAuthorization) blockers.Add("SEPARATE_MANUAL_EXECUTION_AUTHORIZATION_REQUIRED");
        if (!checks.ExecutionCostsVerified) blockers.Add("EXECUTION_EVIDENCE_REQUIRED");
        if (!checks.VirtualRiskApproved) blockers.Add("VIRTUAL_RISK_REJECTED");
        if (!checks.ProtectiveOrdersVerified) blockers.Add("POSITION_PROTECTION_REQUIRED");
        return new(exact,blockers.ToArray());
    }
}
