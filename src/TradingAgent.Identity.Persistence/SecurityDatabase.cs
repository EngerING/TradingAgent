using System.Collections.Frozen;
using System.Reflection;
using System.Text.Json;
using Npgsql;

namespace TradingAgent.Identity.Persistence;

/// <summary>This milestone has no connection mode for an operational database.</summary>
public sealed class SecurityDatabase
{
    private static readonly string[] ReaderTables = ["migration_ledger", "role_permissions"];
    private static readonly string[] ServiceTables = ["migration_ledger"];
    private readonly string connectionString;
    private readonly DisposableTarget target;
    public DatabasePurpose Purpose { get; }
    public SecurityDatabase(DisposableTarget target, string username, string password, DatabasePurpose purpose)
    {
        ArgumentNullException.ThrowIfNull(target);
        ArgumentException.ThrowIfNullOrWhiteSpace(username);
        ArgumentException.ThrowIfNullOrWhiteSpace(password);
        if (!Enum.IsDefined(purpose)) throw new ArgumentOutOfRangeException(nameof(purpose));
        this.target = target; Purpose = purpose;
        connectionString = new NpgsqlConnectionStringBuilder
        {
            Host = target.Host, Port = target.Port, Database = target.Database, Username = username, Password = password,
            Pooling = false, Timeout = 3, CommandTimeout = 5, SslMode = SslMode.Disable, GssEncryptionMode = GssEncryptionMode.Disable,
            IncludeErrorDetail = false, ApplicationName = "TradingAgent.M012.Disposable", Options = "-c statement_timeout=5000 -c lock_timeout=3000"
        }.ConnectionString;
    }
    public override string ToString() => "[REDACTED_SECURITY_DATABASE]";
    public async Task<NpgsqlConnection> OpenAsync(CancellationToken cancellationToken, bool requireSchema = true)
    {
        var connection = new NpgsqlConnection(connectionString);
        try
        {
            await connection.OpenAsync(cancellationToken).ConfigureAwait(false);
            await using var guard = new NpgsqlCommand("""
                SELECT shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database();
                SELECT rolname,rolsuper OR rolbypassrls OR rolcreatedb OR rolcreaterole OR rolreplication
                FROM pg_roles WHERE oid IN (
                  WITH RECURSIVE reachable(oid) AS (
                    SELECT oid FROM pg_roles WHERE rolname=session_user
                    UNION SELECT m.roleid FROM pg_auth_members m JOIN reachable r ON m.member=r.oid
                  ) SELECT oid FROM reachable);
                SELECT has_database_privilege(current_database(),'CREATE') OR has_database_privilege(current_database(),'TEMP');
                SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname NOT IN ('pg_catalog','information_schema','app_security')
                  AND nspname NOT LIKE 'pg_%' AND has_schema_privilege(oid,'CREATE'))
                  OR EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                  WHERE n.nspname NOT IN ('pg_catalog','information_schema','app_security') AND n.nspname NOT LIKE 'pg_toast%'
                  AND n.nspname NOT LIKE 'pg_temp_%' AND has_schema_privilege(n.oid,'USAGE')
                  AND ((c.relkind IN ('r','p','v','m','f') AND (has_table_privilege(c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') OR has_any_column_privilege(c.oid,'SELECT,INSERT,UPDATE,REFERENCES')))
                    OR (c.relkind='S' AND has_sequence_privilege(c.oid,'USAGE,SELECT,UPDATE'))))
                  OR EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
                  WHERE n.nspname NOT IN ('pg_catalog','information_schema','app_security') AND n.nspname NOT LIKE 'pg_toast%'
                  AND has_schema_privilege(n.oid,'USAGE') AND has_function_privilege(p.oid,'EXECUTE'));
                """, connection);
            await using (var reader = await guard.ExecuteReaderAsync(cancellationToken).ConfigureAwait(false))
            {
                if (!await reader.ReadAsync(cancellationToken).ConfigureAwait(false) || reader.IsDBNull(0) || reader.GetString(0) != target.Marker)
                    throw new InvalidOperationException("Disposable database marker rejected.");
                await reader.NextResultAsync(cancellationToken).ConfigureAwait(false);
                var group = Purpose switch
                {
                    DatabasePurpose.Runtime => "web_security_runtime", DatabasePurpose.SessionIssuer => "identity_session_issuer",
                    DatabasePurpose.Administration => "identity_access_admin", DatabasePurpose.Reader => "identity_security_reader",
                    DatabasePurpose.Migration => "identity_migration_owner", _ => throw new InvalidOperationException("Unknown purpose.")
                };
                var groups = new HashSet<string>(StringComparer.Ordinal);
                while (await reader.ReadAsync(cancellationToken).ConfigureAwait(false))
                {
                    if (reader.GetBoolean(1)) throw new InvalidOperationException("Privileged login rejected.");
                    groups.Add(reader.GetString(0));
                }
                if (groups.Count != 2 || !groups.Contains(group)) throw new InvalidOperationException("Role membership rejected.");
                await reader.NextResultAsync(cancellationToken).ConfigureAwait(false);
                await reader.ReadAsync(cancellationToken).ConfigureAwait(false);
                if (reader.GetBoolean(0)) throw new InvalidOperationException("Database DDL privilege rejected.");
                await reader.NextResultAsync(cancellationToken).ConfigureAwait(false);
                await reader.ReadAsync(cancellationToken).ConfigureAwait(false);
                if (reader.GetBoolean(0)) throw new InvalidOperationException("Non-security privileges rejected.");
            }
            if (Purpose == DatabasePurpose.Migration)
            {
                await using var setRole = new NpgsqlCommand("SET ROLE identity_migration_owner", connection);
                await setRole.ExecuteNonQueryAsync(cancellationToken).ConfigureAwait(false);
            }
            if (requireSchema)
            {
                await SchemaManifest.VerifyAsync(connection, cancellationToken).ConfigureAwait(false);
                if (Purpose != DatabasePurpose.Migration) await VerifyPrivilegesAsync(connection, cancellationToken).ConfigureAwait(false);
            }
            return connection;
        }
        catch { await connection.DisposeAsync().ConfigureAwait(false); throw; }
    }
    private async Task VerifyPrivilegesAsync(NpgsqlConnection connection, CancellationToken cancellationToken)
    {
        string[] functions = Purpose switch
        {
            DatabasePurpose.Runtime => ["app_security.authorize(bytea,text,uuid,text,text)", "app_security.self_user(bytea)", "app_security.session_change(bytea,text,bigint)"],
            DatabasePurpose.SessionIssuer => ["app_security.create_session(bytea,text,uuid,uuid,integer,timestamptz,timestamptz)"],
            DatabasePurpose.Administration => ["app_security.admin_change(bytea,text,uuid,text,uuid,text,text,text,timestamptz,text,uuid,text)", "app_security.read_audit(bytea,integer)"],
            _ => []
        };
        await using var command = new NpgsqlCommand("""
            SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='app_security' AND
              (pg_get_userbyid(nspowner)<>'identity_migration_owner' OR has_schema_privilege(oid,'CREATE')))
            OR EXISTS(SELECT 1 FROM pg_class c WHERE c.relnamespace='app_security'::regnamespace AND c.relkind IN ('r','p','v','m','f')
              AND (has_table_privilege(c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') OR has_any_column_privilege(c.oid,'INSERT,UPDATE,REFERENCES')
              OR (c.relname<>ALL($1) AND (has_table_privilege(c.oid,'SELECT') OR has_any_column_privilege(c.oid,'SELECT')))))
            OR EXISTS(SELECT 1 FROM pg_proc p WHERE p.pronamespace='app_security'::regnamespace AND has_function_privilege(p.oid,'EXECUTE')
              AND NOT EXISTS(SELECT 1 FROM unnest($2::text[]) f WHERE to_regprocedure(f)=p.oid))
              OR EXISTS(SELECT 1 FROM unnest($2::text[]) f WHERE to_regprocedure(f) IS NULL OR NOT has_function_privilege(to_regprocedure(f),'EXECUTE'));
            """, connection);
        command.Parameters.AddWithValue(Purpose == DatabasePurpose.Reader ? ReaderTables : ServiceTables);
        command.Parameters.AddWithValue(functions);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken).ConfigureAwait(false);
        do
        {
            if (!await reader.ReadAsync(cancellationToken).ConfigureAwait(false) || reader.GetBoolean(0)) throw new InvalidOperationException("Security schema privileges rejected.");
        } while (await reader.NextResultAsync(cancellationToken).ConfigureAwait(false));
    }
}

public static class SchemaManifest
{
    public static IReadOnlyDictionary<int, string> Expected { get; } = ReadManifest();
    private static FrozenDictionary<int, string> ReadManifest()
    {
        using var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("identity.manifest.json")!;
        return (JsonSerializer.Deserialize<Dictionary<int, string>>(stream) ?? throw new InvalidOperationException("Missing migration manifest.")).ToFrozenDictionary();
    }
    public static async Task VerifyAsync(NpgsqlConnection connection, CancellationToken cancellationToken)
    {
        await using var command = new NpgsqlCommand("SELECT version,checksum FROM app_security.migration_ledger ORDER BY version", connection);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken).ConfigureAwait(false);
        var count = 0;
        while (await reader.ReadAsync(cancellationToken).ConfigureAwait(false))
        {
            if (!Expected.TryGetValue(reader.GetInt32(0), out var hash) || hash != reader.GetString(1)) throw new InvalidOperationException("Migration ledger rejected.");
            count++;
        }
        if (count != Expected.Count || count == 0) throw new InvalidOperationException("Incomplete migration ledger.");
    }
}
