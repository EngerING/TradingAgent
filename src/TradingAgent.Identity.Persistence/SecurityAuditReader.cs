using NpgsqlTypes;

namespace TradingAgent.Identity.Persistence;

public sealed class SecurityAuditReader : ISecurityAuditReader
{
    private readonly SecurityDatabase database;
    public SecurityAuditReader(SecurityDatabase database) { Calls.RequirePurpose(database, DatabasePurpose.Administration); this.database = database; }
    public async Task<AuditPage> ReadAsync(SessionReference actor, int limit, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(actor);
        if (limit is < 1 or > 100) return new(StoreOutcome.Denied, []);
        try
        {
            using var document = await Calls.JsonAsync(database, "SELECT app_security.read_audit($1,$2)", cancellationToken,
                Calls.Parameter(actor.LookupHash(), NpgsqlDbType.Bytea), Calls.Parameter(limit, NpgsqlDbType.Integer)).ConfigureAwait(false);
            var outcome = Calls.Mutation(document).Outcome;
            if (outcome != StoreOutcome.Success) return new(outcome, []);
            var events = document.RootElement.GetProperty("events").EnumerateArray().Select(e => new SecurityAuditEvent(
                e.GetProperty("event_id").GetGuid(), e.GetProperty("action").GetString()!, e.GetProperty("outcome").GetString()!,
                e.GetProperty("occurred_at").GetDateTimeOffset(), e.GetProperty("correlation_id").GetGuid(), e.GetProperty("policy_version").GetInt32(),
                e.GetProperty("session_audit_id").ValueKind == System.Text.Json.JsonValueKind.String ? e.GetProperty("session_audit_id").GetGuid() : null)).ToArray();
            return new(StoreOutcome.Success, events);
        }
        catch (Exception error) when (Calls.StorageFailure(error)) { return new(StoreOutcome.Unavailable, []); }
    }
}
