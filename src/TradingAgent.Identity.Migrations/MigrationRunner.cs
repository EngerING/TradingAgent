using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using Npgsql;
using TradingAgent.Identity.Persistence;

namespace TradingAgent.Identity.Migrations;

public static class MigrationRunner
{
    public static async Task ApplyAsync(SecurityDatabase database, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(database);
        if (database.Purpose != DatabasePurpose.Migration) throw new InvalidOperationException("Migration credential required.");
        var scripts = Assembly.GetExecutingAssembly().GetManifestResourceNames().Where(n => n.EndsWith(".sql", StringComparison.Ordinal)).Order(StringComparer.Ordinal).ToArray();
        if (scripts.Length != SchemaManifest.Expected.Count || scripts.Length == 0) throw new InvalidOperationException("Migration manifest mismatch.");
        var documents = new List<(int Version, string Hash, string Sql)>();
        for (var i = 0; i < scripts.Length; i++)
        {
            using var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream(scripts[i])!;
            using var memory = new MemoryStream(); await stream.CopyToAsync(memory, cancellationToken).ConfigureAwait(false);
            var bytes = memory.ToArray(); var hash = Convert.ToHexStringLower(SHA256.HashData(bytes));
            if (!SchemaManifest.Expected.TryGetValue(i + 1, out var expected) || hash != expected || !scripts[i].Contains($"V{i + 1:000}__", StringComparison.Ordinal)) throw new InvalidOperationException("Altered migration rejected.");
            documents.Add((i + 1, hash, Encoding.UTF8.GetString(bytes)));
        }
        await using var connection = await database.OpenAsync(cancellationToken, requireSchema: false).ConfigureAwait(false);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken).ConfigureAwait(false);
        await ExecuteAsync(connection, "SELECT pg_advisory_xact_lock(70112026); SET LOCAL statement_timeout='10s'; SET LOCAL lock_timeout='3s'", cancellationToken).ConfigureAwait(false);
        await using var inspection = new NpgsqlCommand("SELECT pg_get_userbyid(nspowner)='identity_migration_owner' FROM pg_namespace WHERE nspname='app_security'; SELECT to_regclass('app_security.migration_ledger') IS NOT NULL", connection);
        bool existing;
        await using (var reader = await inspection.ExecuteReaderAsync(cancellationToken).ConfigureAwait(false))
        {
            if (!await reader.ReadAsync(cancellationToken).ConfigureAwait(false) || !reader.GetBoolean(0)) throw new InvalidOperationException("Precreated private schema required.");
            await reader.NextResultAsync(cancellationToken).ConfigureAwait(false); await reader.ReadAsync(cancellationToken).ConfigureAwait(false); existing = reader.GetBoolean(0);
        }
        if (existing) await SchemaManifest.VerifyAsync(connection, cancellationToken).ConfigureAwait(false);
        else
        {
            await using var empty = new NpgsqlCommand("SELECT (SELECT count(*) FROM pg_class WHERE relnamespace='app_security'::regnamespace)+(SELECT count(*) FROM pg_proc WHERE pronamespace='app_security'::regnamespace)", connection);
            if ((long)(await empty.ExecuteScalarAsync(cancellationToken).ConfigureAwait(false))! != 0) throw new InvalidOperationException("Incompatible schema rejected.");
            await ExecuteAsync(connection, "CREATE TABLE app_security.migration_ledger(version integer PRIMARY KEY,checksum text NOT NULL CHECK(length(checksum)=64),applied_at timestamptz NOT NULL DEFAULT clock_timestamp()); REVOKE ALL ON app_security.migration_ledger FROM PUBLIC; GRANT SELECT ON app_security.migration_ledger TO web_security_runtime,identity_session_issuer,identity_access_admin,identity_security_reader", cancellationToken).ConfigureAwait(false);
            foreach (var document in documents)
            {
                await ExecuteAsync(connection, document.Sql, cancellationToken).ConfigureAwait(false);
                await using var insert = new NpgsqlCommand("INSERT INTO app_security.migration_ledger(version,checksum) VALUES($1,$2)", connection);
                insert.Parameters.AddWithValue(document.Version); insert.Parameters.AddWithValue(document.Hash);
                await insert.ExecuteNonQueryAsync(cancellationToken).ConfigureAwait(false);
            }
        }
        await transaction.CommitAsync(cancellationToken).ConfigureAwait(false);
    }
    private static async Task ExecuteAsync(NpgsqlConnection connection, string sql, CancellationToken cancellationToken)
    {
        await using var command = new NpgsqlCommand(sql, connection); await command.ExecuteNonQueryAsync(cancellationToken).ConfigureAwait(false);
    }
}
