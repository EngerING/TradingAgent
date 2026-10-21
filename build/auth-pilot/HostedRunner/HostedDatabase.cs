using System.Security.Cryptography;
using Npgsql;
using TradingAgent.Identity.Migrations;
using TradingAgent.Identity.Persistence;
namespace TradingAgent.HostedPilot;
internal sealed class HostedDatabase : IAsyncDisposable
{
    private string bootstrap = "";
    private readonly Dictionary<DatabasePurpose, (string User, string Password)> credentials = [];
    private DisposableTarget Target { get; set; } = null!;
    internal SecurityDatabase Database(DatabasePurpose purpose) => new(Target, credentials[purpose].User, credentials[purpose].Password, purpose);
    internal async Task InitializeAsync(CancellationToken token)
    {
        var port = int.Parse(Environment.GetEnvironmentVariable("M012_TEST_PORT") ?? throw new InvalidOperationException("Disposable PostgreSQL required; SQL tests never skip."), System.Globalization.CultureInfo.InvariantCulture);
        Target = new("127.0.0.1", port, "m012_test_" + Guid.NewGuid().ToString("N"));
        var builder = new NpgsqlConnectionStringBuilder { Host = Target.Host, Port = port, Database = "postgres", Username = "postgres",
            Password = Environment.GetEnvironmentVariable("M012_BOOTSTRAP_PASSWORD") ?? throw new InvalidOperationException("Fixture password missing."),
            Pooling = false, Timeout = 3, CommandTimeout = 10, SslMode = SslMode.Disable, GssEncryptionMode = GssEncryptionMode.Disable };
        await using (var cluster = new NpgsqlConnection(builder.ConnectionString))
        {
            await cluster.OpenAsync(token);
            await using var check = new NpgsqlCommand("SHOW cluster_name", cluster);
            var marker = Environment.GetEnvironmentVariable("M012_CLUSTER_MARKER");
            if (marker is null || !marker.StartsWith("m012_disposable_", StringComparison.Ordinal) || (string)(await check.ExecuteScalarAsync(token))! != marker)
                throw new InvalidOperationException("Disposable cluster marker rejected before DDL.");
            await using var create = new NpgsqlCommand($"CREATE DATABASE {Target.Database}", cluster); await create.ExecuteNonQueryAsync(token);
        }
        builder.Database = Target.Database; bootstrap = builder.ConnectionString;
        await using (var connection = await OpenOwnerAsync(token))
        {
            await ExecuteAsync(connection, $"COMMENT ON DATABASE {Target.Database} IS '{Target.Marker}'; REVOKE CREATE,TEMP ON DATABASE {Target.Database} FROM PUBLIC; REVOKE ALL ON SCHEMA public FROM PUBLIC", token);
            var roles = new Dictionary<DatabasePurpose, string>
            {
                [DatabasePurpose.Migration] = "identity_migration_owner", [DatabasePurpose.Runtime] = "web_security_runtime",
                [DatabasePurpose.SessionIssuer] = "identity_session_issuer", [DatabasePurpose.Administration] = "identity_access_admin", [DatabasePurpose.Reader] = "identity_security_reader"
            };
            foreach (var (purpose, group) in roles)
            {
                await using var exists = new NpgsqlCommand("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=$1)", connection); exists.Parameters.AddWithValue(group);
                if (!(bool)(await exists.ExecuteScalarAsync(token))!) await ExecuteAsync(connection, $"CREATE ROLE {group} NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION", token);
                var login = "m012_" + Guid.NewGuid().ToString("N"); var password = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
                await ExecuteAsync(connection, $"CREATE ROLE {login} LOGIN PASSWORD '{password}' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION; GRANT {group} TO {login}", token);
                credentials.Add(purpose, (login, password));
            }
            await using (var exists = new NpgsqlCommand("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='web_financial_reader')", connection))
                if (!(bool)(await exists.ExecuteScalarAsync(token))!) await ExecuteAsync(connection, "CREATE ROLE web_financial_reader NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION", token);
            await ExecuteAsync(connection, "CREATE SCHEMA app_security AUTHORIZATION identity_migration_owner; CREATE SCHEMA financial_fixture; REVOKE ALL ON SCHEMA financial_fixture FROM PUBLIC; CREATE TABLE financial_fixture.sentinel(id integer PRIMARY KEY,value text); INSERT INTO financial_fixture.sentinel VALUES(1,'UNCHANGED')", token);
        }
        await MigrationRunner.ApplyAsync(Database(DatabasePurpose.Migration), token);
    }
    internal Guid Resource { get; } = Guid.NewGuid();
    internal async Task SeedAsync(IdentityKey realIdentity, CancellationToken token)
    {
        var fakeOwner = new IdentityKey("https://bootstrap.invalid/hosted-pilot", Guid.NewGuid());
        await using (var owner = await OpenOwnerAsync(token))
        {
            await using var command = new NpgsqlCommand("SELECT app_security.bootstrap($1,$2)", owner);
            command.Parameters.AddWithValue(fakeOwner.Issuer); command.Parameters.AddWithValue(fakeOwner.Subject); await command.ExecuteScalarAsync(token);
        }
        var proof = new IdentityProof(fakeOwner, Guid.NewGuid(), 2, DateTimeOffset.UtcNow.AddSeconds(-1), DateTimeOffset.UtcNow.AddMinutes(10));
        var admin = await new SessionIssuer(Database(DatabasePurpose.SessionIssuer), new FixtureAdminVerifier(proof)).CreateAsync("DISPOSABLE_OWNER_FIXTURE".AsMemory(), token);
        if (admin.Reference is null) throw new PilotFailure("FIXTURE_ADMIN_DENIED");
        var administration = new IdentityAdministration(Database(DatabasePurpose.Administration), EnvironmentScope.Paper);
        var user = await administration.RegisterAsync(admin.Reference, realIdentity, null, token);
        if (user.Outcome != StoreOutcome.Success || user.Id is null) throw new PilotFailure("FIXTURE_USER_DENIED");
        var active = await administration.ChangeStatusAsync(admin.Reference, user.Id.Value, UserStatus.Active, token);
        var role = await administration.GrantRoleAsync(admin.Reference, user.Id.Value, PlatformRole.Viewer, DateTimeOffset.UtcNow.AddMinutes(15), token);
        var grant = await administration.GrantResourceAsync(admin.Reference, user.Id.Value, ResourceKind.Study, Resource, EnvironmentScope.Paper, Capability.Read, DateTimeOffset.UtcNow.AddMinutes(15), token);
        if (new[] { active, role, grant }.Any(r => r.Outcome != StoreOutcome.Success)) throw new PilotFailure("FIXTURE_GRANT_DENIED");
    }
    internal async Task<bool> SentinelAsync(CancellationToken token)
    {
        await using var owner = await OpenOwnerAsync(token); await using var query = new NpgsqlCommand("SELECT value FROM financial_fixture.sentinel WHERE id=1", owner);
        return (string?)await query.ExecuteScalarAsync(token) == "UNCHANGED";
    }
    private async Task<NpgsqlConnection> OpenOwnerAsync(CancellationToken token = default) { var connection = new NpgsqlConnection(bootstrap); await connection.OpenAsync(token); return connection; }
    private static async Task ExecuteAsync(NpgsqlConnection connection, string sql, CancellationToken token = default) { await using var command = new NpgsqlCommand(sql, connection); await command.ExecuteNonQueryAsync(token); }
    public async ValueTask DisposeAsync()
    {
        if (bootstrap.Length == 0) return;
        var builder = new NpgsqlConnectionStringBuilder(bootstrap) { Database = "postgres" };
        await using var cluster = new NpgsqlConnection(builder.ConnectionString); await cluster.OpenAsync();
        // Only the random, validated DB created by this fixture in the marked throwaway cluster.
        await ExecuteAsync(cluster, $"DROP DATABASE {Target.Database} WITH (FORCE)");
        foreach (var value in credentials.Values) await ExecuteAsync(cluster, $"DROP ROLE {value.User}");
    }
    private sealed class FixtureAdminVerifier(IdentityProof proof) : IIdentityEvidenceVerifier
    {
        public ValueTask<IdentityProof?> VerifyAsync(ReadOnlyMemory<char> evidence, CancellationToken cancellationToken) => ValueTask.FromResult<IdentityProof?>(proof);
    }
}
