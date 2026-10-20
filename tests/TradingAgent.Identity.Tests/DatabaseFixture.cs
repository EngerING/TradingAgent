using System.Security.Cryptography;
using Npgsql;
using TradingAgent.Identity.Migrations;
using TradingAgent.Identity.Persistence;
using Xunit;

[assembly: CollectionBehavior(DisableTestParallelization = true)]
namespace TradingAgent.Identity.Tests;

public sealed class DatabaseFixture : IAsyncLifetime, IDisposable
{
    private string bootstrap = "";
    private readonly ConnectionObserver connections = new();
    public void Dispose() { connections.Dispose(); GC.SuppressFinalize(this); }
    private readonly Dictionary<DatabasePurpose, (string User, string Password)> credentials = [];
    public DisposableTarget Target { get; private set; } = null!;
    public SecurityDatabase Database(DatabasePurpose purpose) => new(Target, credentials[purpose].User, credentials[purpose].Password, purpose);
    public SessionRepository Sessions => new(Database(DatabasePurpose.Runtime));
    public IdentityAdministration Administration(EnvironmentScope scope = EnvironmentScope.Paper) => new(Database(DatabasePurpose.Administration), scope);
    public async Task InitializeAsync()
    {
        var port = int.Parse(Environment.GetEnvironmentVariable("M012_TEST_PORT") ?? throw new InvalidOperationException("Disposable PostgreSQL required; SQL tests never skip."), System.Globalization.CultureInfo.InvariantCulture);
        Target = new("127.0.0.1", port, "m012_test_" + Guid.NewGuid().ToString("N"));
        var builder = new NpgsqlConnectionStringBuilder { Host = Target.Host, Port = port, Database = "postgres", Username = "postgres",
            Password = Environment.GetEnvironmentVariable("M012_BOOTSTRAP_PASSWORD") ?? throw new InvalidOperationException("Fixture password missing."),
            Pooling = false, Timeout = 3, CommandTimeout = 10, SslMode = SslMode.Disable, GssEncryptionMode = GssEncryptionMode.Disable };
        await using (var cluster = new NpgsqlConnection(builder.ConnectionString))
        {
            await cluster.OpenAsync();
            await using var check = new NpgsqlCommand("SHOW cluster_name", cluster);
            var marker = Environment.GetEnvironmentVariable("M012_CLUSTER_MARKER");
            if (marker is null || !marker.StartsWith("m012_disposable_", StringComparison.Ordinal) || (string)(await check.ExecuteScalarAsync())! != marker)
                throw new InvalidOperationException("Disposable cluster marker rejected before DDL.");
            await using var create = new NpgsqlCommand($"CREATE DATABASE {Target.Database}", cluster); await create.ExecuteNonQueryAsync();
        }
        builder.Database = Target.Database; bootstrap = builder.ConnectionString;
        await using (var connection = await OpenOwnerAsync())
        {
            await ExecuteAsync(connection, $"COMMENT ON DATABASE {Target.Database} IS '{Target.Marker}'; REVOKE CREATE,TEMP ON DATABASE {Target.Database} FROM PUBLIC; REVOKE ALL ON SCHEMA public FROM PUBLIC");
            var roles = new Dictionary<DatabasePurpose, string>
            {
                [DatabasePurpose.Migration] = "identity_migration_owner", [DatabasePurpose.Runtime] = "web_security_runtime",
                [DatabasePurpose.SessionIssuer] = "identity_session_issuer", [DatabasePurpose.Administration] = "identity_access_admin", [DatabasePurpose.Reader] = "identity_security_reader"
            };
            foreach (var (purpose, group) in roles)
            {
                await using var exists = new NpgsqlCommand("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=$1)", connection); exists.Parameters.AddWithValue(group);
                if (!(bool)(await exists.ExecuteScalarAsync())!) await ExecuteAsync(connection, $"CREATE ROLE {group} NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION");
                var login = "m012_" + Guid.NewGuid().ToString("N"); var password = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
                await ExecuteAsync(connection, $"CREATE ROLE {login} LOGIN PASSWORD '{password}' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION; GRANT {group} TO {login}");
                credentials.Add(purpose, (login, password));
            }
            await using (var exists = new NpgsqlCommand("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='web_financial_reader')", connection))
                if (!(bool)(await exists.ExecuteScalarAsync())!) await ExecuteAsync(connection, "CREATE ROLE web_financial_reader NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION");
            await ExecuteAsync(connection, "CREATE SCHEMA app_security AUTHORIZATION identity_migration_owner; CREATE SCHEMA financial_fixture; REVOKE ALL ON SCHEMA financial_fixture FROM PUBLIC; CREATE TABLE financial_fixture.sentinel(id integer PRIMARY KEY,value text); INSERT INTO financial_fixture.sentinel VALUES(1,'UNCHANGED')");
        }
        await MigrationRunner.ApplyAsync(Database(DatabasePurpose.Migration), CancellationToken.None);
    }
    public async Task DisposeAsync()
    {
        if (bootstrap.Length == 0) return;
        var builder = new NpgsqlConnectionStringBuilder(bootstrap) { Database = "postgres" };
        await using var cluster = new NpgsqlConnection(builder.ConnectionString); await cluster.OpenAsync();
        // Target name was generated and validated by DisposableTarget; never drop any caller-selected database.
        await ExecuteAsync(cluster, $"DROP DATABASE {Target.Database} WITH (FORCE)");
        foreach (var item in credentials.Values) await ExecuteAsync(cluster, $"DROP ROLE {item.User}");
        connections.Dispose();
        var addresses = connections.Addresses.ToArray();
        var expected = new System.Net.IPEndPoint(System.Net.IPAddress.Loopback, Target.Port).Serialize().ToString();
        Assert.NotEmpty(addresses); Assert.All(addresses, address => Assert.Equal(expected, address));
        var results = Environment.GetEnvironmentVariable("M012_RESULTS_DIRECTORY");
        if (!string.IsNullOrEmpty(results))
        {
            Directory.CreateDirectory(results);
            await File.WriteAllTextAsync(Path.Combine(results, "isolation.json"), System.Text.Json.JsonSerializer.Serialize(new
            {
                mode = "OFFLINE", decision = "NO_TRADE", socket_connect_starts = addresses.Length,
                connections_outside_disposable_postgres = 0, scope = "SQL fixture lifecycle; tooling excluded",
                postgres_version = await VersionAsync(cluster)
            }));
        }
    }
    private static async Task<string> VersionAsync(NpgsqlConnection connection)
    {
        await using var command = new NpgsqlCommand("SHOW server_version", connection); return (string)(await command.ExecuteScalarAsync())!;
    }
    public async Task<NpgsqlConnection> OpenOwnerAsync()
    {
        var connection = new NpgsqlConnection(bootstrap); await connection.OpenAsync(); return connection;
    }
    public static async Task ExecuteAsync(NpgsqlConnection connection, string sql)
    {
        await using var command = new NpgsqlCommand(sql, connection); await command.ExecuteNonQueryAsync();
    }
    public async Task<object?> ScalarAsync(string sql, params object[] parameters)
    {
        await using var connection = await OpenOwnerAsync(); await using var command = new NpgsqlCommand(sql, connection);
        foreach (var parameter in parameters) command.Parameters.AddWithValue(parameter);
        return await command.ExecuteScalarAsync();
    }
    public async Task<(Guid User, IdentityKey Identity, SessionReference Session)> AdministratorAsync()
    {
        var identity = new IdentityKey("https://fixture.invalid/" + Guid.NewGuid().ToString("N"), Guid.NewGuid());
        // Bootstrap is intentionally one-shot. Additional isolated administrators are provisioned out of band by the fixture owner.
        Guid user;
        if (!(bool)(await ScalarAsync("SELECT bootstrapped FROM app_security.settings"))!)
            user = (Guid)(await ScalarAsync("SELECT app_security.bootstrap($1,$2)", identity.Issuer, identity.Subject))!;
        else
        {
            user = Guid.NewGuid();
            await using var owner = await OpenOwnerAsync();
            await using var transaction = await owner.BeginTransactionAsync();
            await using (var command = new NpgsqlCommand("INSERT INTO app_security.app_users(app_user_id,identity_issuer,identity_subject,status) VALUES($1,$2,$3,'ACTIVE')", owner, transaction))
            {
                command.Parameters.AddWithValue(user); command.Parameters.AddWithValue(identity.Issuer); command.Parameters.AddWithValue(identity.Subject); await command.ExecuteNonQueryAsync();
            }
            await using (var command = new NpgsqlCommand("INSERT INTO app_security.user_roles VALUES(gen_random_uuid(),$1,'Administrator',$1,clock_timestamp(),clock_timestamp()+interval '1 day',NULL,NULL)", owner, transaction))
            { command.Parameters.AddWithValue(user); await command.ExecuteNonQueryAsync(); }
            await using (var command = new NpgsqlCommand("SELECT app_security.owner_scope($1,'Paper')", owner, transaction))
            { command.Parameters.AddWithValue(user); await command.ExecuteNonQueryAsync(); }
            await transaction.CommitAsync();
        }
        return (user, identity, await IssueAsync(identity));
    }
    public async Task<SessionReference> IssueAsync(IdentityKey identity, TimeSpan? lifetime = null)
    {
        var creation = await TryIssueAsync(identity, lifetime);
        Assert.Equal(StoreOutcome.Success, creation.Outcome); return Assert.IsType<SessionReference>(creation.Reference);
    }
    public async Task<SessionCreation> TryIssueAsync(IdentityKey identity, TimeSpan? lifetime = null)
    {
        var proof = new IdentityProof(identity, Guid.NewGuid(), 2, DateTimeOffset.UtcNow.AddSeconds(-1), DateTimeOffset.UtcNow.Add(lifetime ?? TimeSpan.FromHours(1)));
        return await new SessionIssuer(Database(DatabasePurpose.SessionIssuer), new FixtureVerifier(proof)).CreateAsync("SYNTHETIC_TEST_FIXTURE".AsMemory(), CancellationToken.None);
    }
    public async Task<(Guid User, IdentityKey Identity)> UserAsync(SessionReference administrator)
    {
        var identity = new IdentityKey("https://fixture.invalid", Guid.NewGuid());
        var registration = await Administration().RegisterAsync(administrator, identity, null, CancellationToken.None); Assert.Equal(StoreOutcome.Success, registration.Outcome);
        var user = registration.Id!.Value;
        Assert.Equal(StoreOutcome.Success, (await Administration().ChangeStatusAsync(administrator, user, UserStatus.Active, CancellationToken.None)).Outcome);
        return (user, identity);
    }
    private sealed class FixtureVerifier(IdentityProof proof) : IIdentityEvidenceVerifier
    {
        public ValueTask<IdentityProof?> VerifyAsync(ReadOnlyMemory<char> evidence, CancellationToken cancellationToken) { cancellationToken.ThrowIfCancellationRequested(); return ValueTask.FromResult<IdentityProof?>(proof); }
    }
}

[CollectionDefinition("PostgreSQL")]
public sealed class DatabaseGroup : ICollectionFixture<DatabaseFixture>;
