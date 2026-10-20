using System.Text.Json;
using Npgsql;
using NpgsqlTypes;

namespace TradingAgent.Identity.Persistence;

internal static class Calls
{
    internal static NpgsqlParameter Parameter(object? value, NpgsqlDbType type) => new() { Value = value ?? DBNull.Value, NpgsqlDbType = type };
    internal static bool StorageFailure(Exception error) => error is NpgsqlException or InvalidOperationException or TimeoutException;
    internal static async Task<JsonDocument> JsonAsync(SecurityDatabase database, string sql, CancellationToken cancellationToken, params NpgsqlParameter[] parameters)
    {
        await using var connection = await database.OpenAsync(cancellationToken).ConfigureAwait(false);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken).ConfigureAwait(false);
        await using var command = new NpgsqlCommand(sql, connection, transaction);
        command.Parameters.AddRange(parameters);
        var value = (string)(await command.ExecuteScalarAsync(cancellationToken).ConfigureAwait(false))!;
        await transaction.CommitAsync(cancellationToken).ConfigureAwait(false);
        return JsonDocument.Parse(value);
    }
    internal static MutationResult Mutation(JsonDocument document)
    {
        var root = document.RootElement;
        var outcome = Enum.TryParse<StoreOutcome>(root.GetProperty("outcome").GetString(), out var parsed) && Enum.IsDefined(parsed) ? parsed : StoreOutcome.Denied;
        return new(outcome, root.TryGetProperty("id", out var id) && id.ValueKind == JsonValueKind.String ? id.GetGuid() : null);
    }
    internal static void RequirePurpose(SecurityDatabase database, DatabasePurpose purpose)
    {
        ArgumentNullException.ThrowIfNull(database);
        if (database.Purpose != purpose) throw new ArgumentException("Separate database credential required.", nameof(database));
    }
}

public sealed class SessionIssuer : ISessionIssuer
{
    private readonly SecurityDatabase database;
    private readonly IIdentityEvidenceVerifier verifier;
    public SessionIssuer(SecurityDatabase database, IIdentityEvidenceVerifier verifier)
    {
        Calls.RequirePurpose(database, DatabasePurpose.SessionIssuer); ArgumentNullException.ThrowIfNull(verifier);
        this.database = database; this.verifier = verifier;
    }
    public async Task<SessionCreation> CreateAsync(ReadOnlyMemory<char> evidence, CancellationToken cancellationToken)
    {
        try
        {
            var proof = await verifier.VerifyAsync(evidence, cancellationToken).ConfigureAwait(false);
            if (proof is null) return new(StoreOutcome.Denied);
            var reference = SessionReference.Generate();
            using var result = await Calls.JsonAsync(database, "SELECT app_security.create_session($1,$2,$3,$4,$5,$6,$7)", cancellationToken,
                Calls.Parameter(reference.LookupHash(), NpgsqlDbType.Bytea), Calls.Parameter(proof.Identity.Issuer, NpgsqlDbType.Text),
                Calls.Parameter(proof.Identity.Subject, NpgsqlDbType.Uuid), Calls.Parameter(proof.ProviderSessionId, NpgsqlDbType.Uuid),
                Calls.Parameter(proof.AssuranceLevel, NpgsqlDbType.Integer), Calls.Parameter(proof.VerifiedAt, NpgsqlDbType.TimestampTz), Calls.Parameter(proof.ExpiresAt, NpgsqlDbType.TimestampTz)).ConfigureAwait(false);
            var mutation = Calls.Mutation(result);
            if (mutation.Outcome != StoreOutcome.Success) return new(mutation.Outcome);
            var root = result.RootElement;
            return new(StoreOutcome.Success, reference, new(root.GetProperty("id").GetGuid(), root.GetProperty("user").GetGuid(), root.GetProperty("version").GetInt64(), root.GetProperty("expires").GetDateTimeOffset(), root.GetProperty("idle").GetDateTimeOffset()));
        }
        catch (Exception error) when (Calls.StorageFailure(error)) { return new(StoreOutcome.Unavailable); }
    }
}

public sealed class SessionRepository : ISessionOperations, IUserReader, IResourceAuthorizer
{
    private readonly SecurityDatabase database;
    public SessionRepository(SecurityDatabase database) { Calls.RequirePurpose(database, DatabasePurpose.Runtime); this.database = database; }
    public async Task<AuthorizationDecision> AuthorizeAsync(SessionReference session, ResourceKind kind, Guid resourceId, EnvironmentScope environment, Capability capability, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(session);
        if (!Enum.IsDefined(kind) || !Enum.IsDefined(environment) || !Enum.IsDefined(capability) || resourceId == Guid.Empty) return AuthorizationDecision.Denied();
        try
        {
            await using var connection = await database.OpenAsync(cancellationToken).ConfigureAwait(false);
            await using var transaction = await connection.BeginTransactionAsync(cancellationToken).ConfigureAwait(false);
            await using var command = new NpgsqlCommand("SELECT allowed,as_of FROM app_security.authorize($1,$2,$3,$4,$5)", connection, transaction);
            command.Parameters.AddWithValue(session.LookupHash()); command.Parameters.AddWithValue(kind.ToString()); command.Parameters.AddWithValue(resourceId);
            command.Parameters.AddWithValue(environment.ToString()); command.Parameters.AddWithValue(capability.ToString());
            AuthorizationDecision decision;
            await using (var reader = await command.ExecuteReaderAsync(cancellationToken).ConfigureAwait(false))
            {
                if (!await reader.ReadAsync(cancellationToken).ConfigureAwait(false)) return AuthorizationDecision.Denied();
                decision = new(reader.GetBoolean(0), reader.GetBoolean(0) ? StoreOutcome.Success : StoreOutcome.Denied, reader.GetFieldValue<DateTimeOffset>(1));
            }
            await transaction.CommitAsync(cancellationToken).ConfigureAwait(false); return decision;
        }
        catch (Exception error) when (Calls.StorageFailure(error)) { return new(false, StoreOutcome.Unavailable); }
    }
    public async Task<UserView?> FindSelfAsync(SessionReference session, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(session);
        try
        {
            await using var connection = await database.OpenAsync(cancellationToken).ConfigureAwait(false);
            await using var command = new NpgsqlCommand("SELECT * FROM app_security.self_user($1)", connection); command.Parameters.AddWithValue(session.LookupHash());
            await using var reader = await command.ExecuteReaderAsync(cancellationToken).ConfigureAwait(false);
            if (!await reader.ReadAsync(cancellationToken).ConfigureAwait(false) || !Enum.TryParse<UserStatus>(reader.GetString(3), true, out var status) || !Enum.IsDefined(status)) return null;
            return new(reader.GetGuid(0), new(reader.GetString(1), reader.GetGuid(2)), status, reader.GetInt64(4));
        }
        catch (Exception error) when (Calls.StorageFailure(error)) { return null; }
    }
    public Task<MutationResult> TouchAsync(SessionReference session, long rowVersion, CancellationToken cancellationToken) => ChangeAsync(session, "SessionTouch", rowVersion, cancellationToken);
    public Task<MutationResult> RevokeAsync(SessionReference session, CancellationToken cancellationToken) => ChangeAsync(session, "SessionRevoke", null, cancellationToken);
    private async Task<MutationResult> ChangeAsync(SessionReference session, string action, long? version, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(session);
        try
        {
            using var result = await Calls.JsonAsync(database, "SELECT app_security.session_change($1,$2,$3)", cancellationToken,
                Calls.Parameter(session.LookupHash(), NpgsqlDbType.Bytea), Calls.Parameter(action, NpgsqlDbType.Text), Calls.Parameter(version, NpgsqlDbType.Bigint)).ConfigureAwait(false);
            return Calls.Mutation(result);
        }
        catch (Exception error) when (Calls.StorageFailure(error)) { return new(StoreOutcome.Unavailable); }
    }
}

public sealed class IdentityAdministration : IIdentityAdministration
{
    private readonly SecurityDatabase database;
    private readonly EnvironmentScope scope;
    public IdentityAdministration(SecurityDatabase database, EnvironmentScope scope)
    {
        Calls.RequirePurpose(database, DatabasePurpose.Administration);
        if (!Enum.IsDefined(scope)) throw new ArgumentOutOfRangeException(nameof(scope)); this.database = database; this.scope = scope;
    }
    public Task<MutationResult> RegisterAsync(SessionReference actor, IdentityKey identity, string? contactEmail, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(identity);
        if (contactEmail?.Length > 320) return Task.FromResult(new MutationResult(StoreOutcome.Denied));
        return ChangeAsync(actor, "Register", null, null, null, null, null, null, identity, contactEmail, cancellationToken);
    }
    public Task<MutationResult> ChangeStatusAsync(SessionReference actor, Guid user, UserStatus status, CancellationToken cancellationToken) =>
        Enum.IsDefined(status) ? ChangeAsync(actor, "Status", user, status.ToString().ToUpperInvariant(), null, null, null, null, null, null, cancellationToken) : Task.FromResult(new MutationResult(StoreOutcome.Denied));
    public Task<MutationResult> GrantRoleAsync(SessionReference actor, Guid user, PlatformRole role, DateTimeOffset expiresAt, CancellationToken cancellationToken) =>
        Enum.IsDefined(role) ? ChangeAsync(actor, "GrantRole", user, role.ToString(), null, null, null, expiresAt, null, null, cancellationToken) : Task.FromResult(new MutationResult(StoreOutcome.Denied));
    public Task<MutationResult> GrantResourceAsync(SessionReference actor, Guid user, ResourceKind kind, Guid resourceId, EnvironmentScope environment, Capability capability, DateTimeOffset expiresAt, CancellationToken cancellationToken) =>
        Enum.IsDefined(kind) && Enum.IsDefined(capability) && environment == scope && resourceId != Guid.Empty ?
        ChangeAsync(actor, "GrantResource", user, null, resourceId, kind.ToString(), capability.ToString(), expiresAt, null, null, cancellationToken) : Task.FromResult(new MutationResult(StoreOutcome.Denied));
    public Task<MutationResult> RevokeRoleAsync(SessionReference actor, Guid grantId, CancellationToken cancellationToken) => ChangeAsync(actor, "RevokeRole", grantId, null, null, null, null, null, null, null, cancellationToken);
    public Task<MutationResult> RevokeResourceAsync(SessionReference actor, Guid grantId, CancellationToken cancellationToken) => ChangeAsync(actor, "RevokeResource", grantId, null, null, null, null, null, null, null, cancellationToken);
    private async Task<MutationResult> ChangeAsync(SessionReference actor, string action, Guid? target, string? value, Guid? resource, string? kind, string? capability, DateTimeOffset? expiry, IdentityKey? identity, string? email, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(actor);
        if (target == Guid.Empty || expiry?.Offset != null && expiry.Value.Offset != TimeSpan.Zero) return new(StoreOutcome.Denied);
        try
        {
            using var result = await Calls.JsonAsync(database, "SELECT app_security.admin_change($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)", cancellationToken,
                Calls.Parameter(actor.LookupHash(), NpgsqlDbType.Bytea), Calls.Parameter(action, NpgsqlDbType.Text), Calls.Parameter(target, NpgsqlDbType.Uuid),
                Calls.Parameter(value, NpgsqlDbType.Text), Calls.Parameter(resource, NpgsqlDbType.Uuid), Calls.Parameter(kind, NpgsqlDbType.Text),
                Calls.Parameter(scope.ToString(), NpgsqlDbType.Text), Calls.Parameter(capability, NpgsqlDbType.Text), Calls.Parameter(expiry, NpgsqlDbType.TimestampTz),
                Calls.Parameter(identity?.Issuer, NpgsqlDbType.Text), Calls.Parameter(identity?.Subject, NpgsqlDbType.Uuid), Calls.Parameter(email, NpgsqlDbType.Text)).ConfigureAwait(false);
            return Calls.Mutation(result);
        }
        catch (PostgresException error) when (error.SqlState is "23505" or "23514" or "23503" or "23502") { return new(StoreOutcome.Conflict); }
        catch (Exception error) when (Calls.StorageFailure(error)) { return new(StoreOutcome.Unavailable); }
    }
}
