using Npgsql;
using TradingAgent.Identity.Migrations;
using TradingAgent.Identity.Persistence;
using Xunit;

namespace TradingAgent.Identity.Tests;

[Collection("PostgreSQL")]
public sealed class SecurityTests(DatabaseFixture fixture)
{
    [Theory]
    [InlineData(ResourceKind.Account)] [InlineData(ResourceKind.Study)] [InlineData(ResourceKind.Experiment)] [InlineData(ResourceKind.Strategy)]
    public async Task EachResourceIsExactAndExecutionAlwaysDisabled(ResourceKind kind)
    {
        var admin = await fixture.AdministratorAsync(); var user = await fixture.UserAsync(admin.Session); var resource = Guid.NewGuid();
        await fixture.Administration().GrantRoleAsync(admin.Session, user.User, PlatformRole.Researcher, DateTimeOffset.UtcNow.AddHours(1), CancellationToken.None);
        await fixture.Administration().GrantResourceAsync(admin.Session, user.User, kind, resource, EnvironmentScope.Paper, Capability.ManageResearch, DateTimeOffset.UtcNow.AddHours(1), CancellationToken.None);
        var decision = await fixture.Sessions.AuthorizeAsync(await fixture.IssueAsync(user.Identity), kind, resource, EnvironmentScope.Paper, Capability.ManageResearch, CancellationToken.None);
        Assert.True(decision.Allowed); Assert.False(decision.ExecutionAuthorized);
    }
    [Fact]
    public async Task LiveScopeNeedsSeparateOwnerCeremonyAndStillCannotExecute()
    {
        var admin = await fixture.AdministratorAsync(); var user = await fixture.UserAsync(admin.Session); var resource = Guid.NewGuid(); var end = DateTimeOffset.UtcNow.AddHours(1);
        await fixture.Administration().GrantRoleAsync(admin.Session, user.User, PlatformRole.Viewer, end, CancellationToken.None);
        Assert.Equal(StoreOutcome.Denied, (await fixture.Administration(EnvironmentScope.Live).GrantResourceAsync(admin.Session, user.User, ResourceKind.Account, resource, EnvironmentScope.Live, Capability.Read, end, CancellationToken.None)).Outcome);
        await fixture.ScalarAsync("SELECT app_security.owner_scope($1,'Live')", admin.User);
        Assert.Null(await fixture.Sessions.FindSelfAsync(admin.Session, CancellationToken.None));
        var newAdmin = await fixture.IssueAsync(admin.Identity);
        Assert.Equal(StoreOutcome.Success, (await fixture.Administration(EnvironmentScope.Live).GrantResourceAsync(newAdmin, user.User, ResourceKind.Account, resource, EnvironmentScope.Live, Capability.Read, end, CancellationToken.None)).Outcome);
        var session = await fixture.IssueAsync(user.Identity);
        var decision = await fixture.Sessions.AuthorizeAsync(session, ResourceKind.Account, resource, EnvironmentScope.Live, Capability.Read, CancellationToken.None);
        Assert.True(decision.Allowed); Assert.False(decision.ExecutionAuthorized);
        Assert.False((await fixture.Sessions.AuthorizeAsync(session, ResourceKind.Account, resource, EnvironmentScope.Paper, Capability.Read, CancellationToken.None)).Allowed);
    }
    [Fact]
    public async Task UnknownEnumsEmptyIdsAndUnavailableVerifierFailClosed()
    {
        var session = SessionReference.Generate();
        Assert.False((await fixture.Sessions.AuthorizeAsync(session, (ResourceKind)99, Guid.NewGuid(), EnvironmentScope.Paper, Capability.Read, CancellationToken.None)).Allowed);
        Assert.False((await fixture.Sessions.AuthorizeAsync(session, ResourceKind.Account, Guid.Empty, EnvironmentScope.Paper, Capability.Read, CancellationToken.None)).Allowed);
        Assert.False((await fixture.Sessions.AuthorizeAsync(session, ResourceKind.Account, Guid.NewGuid(), (EnvironmentScope)99, (Capability)99, CancellationToken.None)).Allowed);
        Assert.Equal(StoreOutcome.Denied, (await fixture.Administration().GrantRoleAsync(session, Guid.NewGuid(), (PlatformRole)99, DateTimeOffset.UtcNow, CancellationToken.None)).Outcome);
        Assert.Equal(StoreOutcome.Denied, (await fixture.Administration().ChangeStatusAsync(session, Guid.NewGuid(), (UserStatus)99, CancellationToken.None)).Outcome);
        Assert.Equal(StoreOutcome.Denied, (await new SessionIssuer(fixture.Database(DatabasePurpose.SessionIssuer), new UnavailableIdentityVerifier()).CreateAsync(ReadOnlyMemory<char>.Empty, CancellationToken.None)).Outcome);
    }
    [Fact]
    public async Task DisableRevokesAllSessionsAndPreventsIssuance()
    {
        var admin = await fixture.AdministratorAsync(); var user = await fixture.UserAsync(admin.Session);
        var one = await fixture.IssueAsync(user.Identity); var two = await fixture.IssueAsync(user.Identity);
        Assert.Equal(StoreOutcome.Success, (await fixture.Administration().ChangeStatusAsync(admin.Session, user.User, UserStatus.Disabled, CancellationToken.None)).Outcome);
        Assert.Null(await fixture.Sessions.FindSelfAsync(one, CancellationToken.None)); Assert.Null(await fixture.Sessions.FindSelfAsync(two, CancellationToken.None));
        Assert.Equal(0L, await fixture.ScalarAsync("SELECT count(*) FROM app_security.web_sessions WHERE app_user_id=$1 AND revoked_at IS NULL", user.User));
        Assert.Equal(StoreOutcome.Denied, (await fixture.TryIssueAsync(user.Identity)).Outcome);
    }
    [Fact]
    public async Task SessionCasRevocationAndOldVersionsAreEnforced()
    {
        var admin = await fixture.AdministratorAsync(); var user = await fixture.UserAsync(admin.Session); var session = await fixture.IssueAsync(user.Identity);
        var updates = await Task.WhenAll(fixture.Sessions.TouchAsync(session, 1, CancellationToken.None), fixture.Sessions.TouchAsync(session, 1, CancellationToken.None));
        Assert.Single(updates, x => x.Outcome == StoreOutcome.Success); Assert.Single(updates, x => x.Outcome == StoreOutcome.Conflict);
        Assert.Equal(StoreOutcome.Conflict, (await fixture.Sessions.TouchAsync(session, 1, CancellationToken.None)).Outcome);
        Assert.Equal(StoreOutcome.Success, (await fixture.Sessions.RevokeAsync(session, CancellationToken.None)).Outcome);
        Assert.Equal(StoreOutcome.Denied, (await fixture.Sessions.TouchAsync(session, 2, CancellationToken.None)).Outcome);
        Assert.Equal(StoreOutcome.Denied, (await fixture.Sessions.RevokeAsync(session, CancellationToken.None)).Outcome);
        Assert.Null(await fixture.Sessions.FindSelfAsync(session, CancellationToken.None));
    }
    [Fact]
    public async Task SessionSecretsAreHashedAndReservedTokenSlotsRemainEmpty()
    {
        var admin = await fixture.AdministratorAsync(); var session = admin.Session;
        Assert.Equal(session.LookupHash(), (byte[])(await fixture.ScalarAsync("SELECT reference_hash FROM app_security.web_sessions WHERE reference_hash=$1", session.LookupHash()))!);
        Assert.Equal(0L, await fixture.ScalarAsync("SELECT count(*) FROM app_security.web_sessions WHERE encrypted_access_token IS NOT NULL OR encrypted_refresh_token IS NOT NULL OR token_key_id IS NOT NULL"));
        var exported = (string)(await fixture.ScalarAsync("SELECT string_agg(row_to_json(s)::text,'') FROM app_security.web_sessions s"))!;
        Assert.DoesNotContain(session.ExportForCookie(), exported, StringComparison.Ordinal);
        Assert.DoesNotContain(session.ExportForCookie(), (string)(await fixture.ScalarAsync("SELECT string_agg(row_to_json(a)::text,'') FROM app_security.security_audit_events a"))!, StringComparison.Ordinal);
    }
    [Theory]
    [InlineData(DatabasePurpose.Runtime, "UPDATE app_security.resource_grants SET capability='ManageSecurity'")]
    [InlineData(DatabasePurpose.Runtime, "SELECT app_security.create_session(NULL,NULL,NULL,NULL,NULL,NULL,NULL)")]
    [InlineData(DatabasePurpose.Runtime, "SELECT app_security.admin_change(NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL)")]
    [InlineData(DatabasePurpose.SessionIssuer, "SELECT app_security.admin_change(NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL)")]
    [InlineData(DatabasePurpose.Administration, "INSERT INTO app_security.app_users VALUES(gen_random_uuid(),'x',gen_random_uuid(),'ACTIVE',1,NULL,now(),now())")]
    [InlineData(DatabasePurpose.Reader, "DELETE FROM app_security.role_permissions")]
    [InlineData(DatabasePurpose.Reader, "SELECT * FROM app_security.web_sessions")]
    [InlineData(DatabasePurpose.Runtime, "TRUNCATE app_security.security_audit_events")]
    [InlineData(DatabasePurpose.Administration, "UPDATE app_security.security_audit_events SET outcome='Success'")]
    [InlineData(DatabasePurpose.Runtime, "SELECT * FROM financial_fixture.sentinel")]
    [InlineData(DatabasePurpose.Runtime, "UPDATE financial_fixture.sentinel SET value='CHANGED'")]
    [InlineData(DatabasePurpose.Migration, "SELECT * FROM financial_fixture.sentinel")]
    public async Task SqlCredentialsCannotCrossTheirBoundary(DatabasePurpose purpose, string sql)
    {
        await using var connection = await fixture.Database(purpose).OpenAsync(CancellationToken.None);
        var error = await Assert.ThrowsAsync<PostgresException>(() => DatabaseFixture.ExecuteAsync(connection, sql)); Assert.Equal("42501", error.SqlState);
    }
    [Fact]
    public async Task LedgerTamperingIsRejectedByMigratorAndRuntime()
    {
        var original = SchemaManifest.Expected[1];
        try
        {
            await fixture.ScalarAsync("UPDATE app_security.migration_ledger SET checksum=repeat('0',64) WHERE version=1");
            await Assert.ThrowsAsync<InvalidOperationException>(() => MigrationRunner.ApplyAsync(fixture.Database(DatabasePurpose.Migration), CancellationToken.None));
            Assert.Equal(StoreOutcome.Unavailable, (await fixture.Sessions.AuthorizeAsync(SessionReference.Generate(), ResourceKind.Account, Guid.NewGuid(), EnvironmentScope.Paper, Capability.Read, CancellationToken.None)).Outcome);
        }
        finally { await fixture.ScalarAsync("UPDATE app_security.migration_ledger SET checksum=$1 WHERE version=1", original); }
    }
    [Fact]
    public async Task DatabaseConstraintsRejectIdentityReplacementUnknownRolesAndForeignKeys()
    {
        var admin = await fixture.AdministratorAsync();
        foreach (var sql in new[] {
            $"UPDATE app_security.app_users SET identity_subject=gen_random_uuid() WHERE app_user_id='{admin.User}'",
            $"INSERT INTO app_security.app_users(app_user_id,identity_issuer,identity_subject,status) SELECT gen_random_uuid(),identity_issuer,identity_subject,'ACTIVE' FROM app_security.app_users WHERE app_user_id='{admin.User}'",
            $"INSERT INTO app_security.user_roles VALUES(gen_random_uuid(),'{admin.User}','Unknown','{admin.User}',now(),now()+interval '1 hour',NULL,NULL)",
            $"INSERT INTO app_security.user_roles VALUES(gen_random_uuid(),gen_random_uuid(),'Viewer','{admin.User}',now(),now()+interval '1 hour',NULL,NULL)",
            "UPDATE app_security.security_audit_events SET outcome='Denied'", "DELETE FROM app_security.security_audit_events", "TRUNCATE app_security.security_audit_events" })
        {
            await using var owner = await fixture.OpenOwnerAsync(); await Assert.ThrowsAsync<PostgresException>(() => DatabaseFixture.ExecuteAsync(owner, sql));
        }
        Assert.Equal(StoreOutcome.Conflict, (await fixture.Administration().RegisterAsync(admin.Session, admin.Identity, null, CancellationToken.None)).Outcome);
    }
    [Fact]
    public async Task EffectiveLoginFlagsAndInheritedFinancialPrivilegesAreRejected()
    {
        await using var runtime = await fixture.Database(DatabasePurpose.Runtime).OpenAsync(CancellationToken.None);
        await using var who = new NpgsqlCommand("SELECT session_user", runtime); var login = (string)(await who.ExecuteScalarAsync())!;
        try
        {
            await using var owner = await fixture.OpenOwnerAsync(); await DatabaseFixture.ExecuteAsync(owner, $"ALTER ROLE {login} CREATEDB");
            await Assert.ThrowsAsync<InvalidOperationException>(() => fixture.Database(DatabasePurpose.Runtime).OpenAsync(CancellationToken.None));
            await DatabaseFixture.ExecuteAsync(owner, $"ALTER ROLE {login} NOCREATEDB; GRANT USAGE ON SCHEMA financial_fixture TO PUBLIC; GRANT SELECT ON financial_fixture.sentinel TO PUBLIC");
            await Assert.ThrowsAsync<InvalidOperationException>(() => fixture.Database(DatabasePurpose.Runtime).OpenAsync(CancellationToken.None));
        }
        finally
        {
            await using var owner = await fixture.OpenOwnerAsync(); await DatabaseFixture.ExecuteAsync(owner, $"ALTER ROLE {login} NOCREATEDB; REVOKE ALL ON SCHEMA financial_fixture FROM PUBLIC; REVOKE ALL ON financial_fixture.sentinel FROM PUBLIC");
        }
        Assert.Equal("UNCHANGED", await fixture.ScalarAsync("SELECT value FROM financial_fixture.sentinel WHERE id=1"));
    }
    [Fact]
    public async Task NullProofExpiryCannotBecomeTwelveHourSession()
    {
        var admin = await fixture.AdministratorAsync();
        await using var issuer = await fixture.Database(DatabasePurpose.SessionIssuer).OpenAsync(CancellationToken.None);
        await using var command = new NpgsqlCommand("SELECT app_security.create_session($1,$2,$3,$4,2,clock_timestamp(),NULL)", issuer);
        command.Parameters.AddWithValue(SessionReference.Generate().LookupHash()); command.Parameters.AddWithValue(admin.Identity.Issuer);
        command.Parameters.AddWithValue(admin.Identity.Subject); command.Parameters.AddWithValue(Guid.NewGuid());
        Assert.Contains("Denied", (string)(await command.ExecuteScalarAsync())!, StringComparison.Ordinal);
    }
    [Fact]
    public async Task PaperAdministratorCannotReactivateLatentLiveAuthority()
    {
        var paper = await fixture.AdministratorAsync(); var live = await fixture.AdministratorAsync();
        await fixture.ScalarAsync("SELECT app_security.owner_scope($1,'Live')", live.User);
        var liveSession = await fixture.IssueAsync(live.Identity); var target = await fixture.UserAsync(liveSession);
        await fixture.Administration(EnvironmentScope.Live).GrantResourceAsync(liveSession, target.User, ResourceKind.Account, Guid.NewGuid(), EnvironmentScope.Live, Capability.Read, DateTimeOffset.UtcNow.AddHours(1), CancellationToken.None);
        Assert.Equal(StoreOutcome.Denied, (await fixture.Administration().GrantRoleAsync(paper.Session, target.User, PlatformRole.Viewer, DateTimeOffset.UtcNow.AddHours(1), CancellationToken.None)).Outcome);
        Assert.Equal(StoreOutcome.Denied, (await fixture.Administration().ChangeStatusAsync(paper.Session, target.User, UserStatus.Active, CancellationToken.None)).Outcome);
        Assert.Equal(StoreOutcome.Success, (await fixture.Administration().GrantRoleAsync(liveSession, target.User, PlatformRole.Viewer, DateTimeOffset.UtcNow.AddHours(1), CancellationToken.None)).Outcome);
    }
    [Fact]
    public async Task AdministrativeIdentityMustRemainFreshAfterSessionIssuance()
    {
        var admin = await fixture.AdministratorAsync(); var reference = SessionReference.Generate();
        await using var issuer = await fixture.Database(DatabasePurpose.SessionIssuer).OpenAsync(CancellationToken.None);
        await using var command = new NpgsqlCommand("SELECT app_security.create_session($1,$2,$3,$4,2,clock_timestamp()-interval '299 seconds',clock_timestamp()+interval '1 hour')", issuer);
        command.Parameters.AddWithValue(reference.LookupHash()); command.Parameters.AddWithValue(admin.Identity.Issuer);
        command.Parameters.AddWithValue(admin.Identity.Subject); command.Parameters.AddWithValue(Guid.NewGuid());
        Assert.Contains("Success", (string)(await command.ExecuteScalarAsync())!, StringComparison.Ordinal);
        await Task.Delay(1100);
        Assert.NotNull(await fixture.Sessions.FindSelfAsync(reference, CancellationToken.None));
        Assert.Equal(StoreOutcome.Denied, (await fixture.Administration().RegisterAsync(reference, new("https://fixture.invalid", Guid.NewGuid()), null, CancellationToken.None)).Outcome);
    }
    [Theory]
    [InlineData("GRANT EXECUTE ON FUNCTION app_security.create_session(bytea,text,uuid,uuid,integer,timestamptz,timestamptz) TO web_security_runtime", "REVOKE EXECUTE ON FUNCTION app_security.create_session(bytea,text,uuid,uuid,integer,timestamptz,timestamptz) FROM web_security_runtime")]
    [InlineData("GRANT UPDATE ON app_security.app_users TO web_security_runtime", "REVOKE UPDATE ON app_security.app_users FROM web_security_runtime")]
    public async Task SecurityAclDriftIsRejectedBeforeRuntimeUse(string grant, string revoke)
    {
        await using var owner = await fixture.OpenOwnerAsync();
        try
        {
            await DatabaseFixture.ExecuteAsync(owner, grant);
            await Assert.ThrowsAsync<InvalidOperationException>(() => fixture.Database(DatabasePurpose.Runtime).OpenAsync(CancellationToken.None));
        }
        finally { await DatabaseFixture.ExecuteAsync(owner, revoke); }
    }
    [Fact]
    public async Task UnknownMigrationVersionIsRejected()
    {
        try
        {
            await fixture.ScalarAsync("INSERT INTO app_security.migration_ledger VALUES(99,repeat('a',64),clock_timestamp())");
            await Assert.ThrowsAsync<InvalidOperationException>(() => MigrationRunner.ApplyAsync(fixture.Database(DatabasePurpose.Migration), CancellationToken.None));
        }
        finally { await fixture.ScalarAsync("DELETE FROM app_security.migration_ledger WHERE version=99"); }
    }
    [Fact]
    public async Task AuditReaderIsBoundedAndRequiresBothAdministrationScopes()
    {
        var admin = await fixture.AdministratorAsync(); var reader = new SecurityAuditReader(fixture.Database(DatabasePurpose.Administration));
        Assert.Equal(StoreOutcome.Denied, (await reader.ReadAsync(admin.Session, 10, CancellationToken.None)).Outcome);
        await fixture.ScalarAsync("SELECT app_security.owner_scope($1,'Live')", admin.User);
        var session = await fixture.IssueAsync(admin.Identity);
        var page = await reader.ReadAsync(session, 3, CancellationToken.None);
        Assert.Equal(StoreOutcome.Success, page.Outcome); Assert.Equal(3, page.Events.Count); Assert.All(page.Events, e => Assert.Equal(1, e.PolicyVersion));
        Assert.Equal(StoreOutcome.Denied, (await reader.ReadAsync(session, 101, CancellationToken.None)).Outcome);
        Assert.Equal(StoreOutcome.Success, (await fixture.Sessions.RevokeAsync(session, CancellationToken.None)).Outcome);
        Assert.Equal(StoreOutcome.Denied, (await reader.ReadAsync(session, 3, CancellationToken.None)).Outcome);
    }
    [Fact]
    public async Task RoleRevocationRemovesAuthorityFromNewAndExistingSessions()
    {
        var admin = await fixture.AdministratorAsync(); var user = await fixture.UserAsync(admin.Session); var resource = Guid.NewGuid(); var expiry = DateTimeOffset.UtcNow.AddHours(1);
        var role = await fixture.Administration().GrantRoleAsync(admin.Session, user.User, PlatformRole.Viewer, expiry, CancellationToken.None);
        await fixture.Administration().GrantResourceAsync(admin.Session, user.User, ResourceKind.Study, resource, EnvironmentScope.Paper, Capability.Read, expiry, CancellationToken.None);
        var session = await fixture.IssueAsync(user.Identity);
        Assert.Equal(StoreOutcome.Success, (await fixture.Administration().RevokeRoleAsync(admin.Session, role.Id!.Value, CancellationToken.None)).Outcome);
        foreach (var reference in new[] { session, await fixture.IssueAsync(user.Identity) })
            Assert.False((await fixture.Sessions.AuthorizeAsync(reference, ResourceKind.Study, resource, EnvironmentScope.Paper, Capability.Read, CancellationToken.None)).Allowed);
    }
    [Fact]
    public async Task ExpiredRoleIsDeniedEvenWhenGrantAndSessionRemainValid()
    {
        var admin = await fixture.AdministratorAsync(); var user = await fixture.UserAsync(admin.Session); var resource = Guid.NewGuid();
        await fixture.Administration().GrantResourceAsync(admin.Session, user.User, ResourceKind.Study, resource, EnvironmentScope.Paper, Capability.Read, DateTimeOffset.UtcNow.AddHours(1), CancellationToken.None);
        var role = await fixture.Administration().GrantRoleAsync(admin.Session, user.User, PlatformRole.Viewer, DateTimeOffset.UtcNow.AddSeconds(1), CancellationToken.None);
        Assert.Equal(StoreOutcome.Success, role.Outcome); var session = await fixture.IssueAsync(user.Identity);
        while (!(bool)(await fixture.ScalarAsync("SELECT clock_timestamp()>=expires_at FROM app_security.user_roles WHERE grant_id=$1", role.Id!.Value))!) await Task.Delay(25);
        Assert.False((await fixture.Sessions.AuthorizeAsync(session, ResourceKind.Study, resource, EnvironmentScope.Paper, Capability.Read, CancellationToken.None)).Allowed);
    }
    [Fact]
    public async Task BootstrapCannotRepeatAndFutureFinancialReaderHasNoRights()
    {
        await fixture.AdministratorAsync();
        await using var owner = await fixture.OpenOwnerAsync();
        await using var command = new NpgsqlCommand("SELECT app_security.bootstrap('https://fixture.invalid',$1)", owner); command.Parameters.AddWithValue(Guid.NewGuid());
        Assert.Equal("42501", (await Assert.ThrowsAsync<PostgresException>(() => command.ExecuteScalarAsync())).SqlState);
        Assert.False((bool)(await fixture.ScalarAsync("SELECT has_schema_privilege('web_financial_reader','app_security','USAGE') OR has_table_privilege('web_financial_reader','financial_fixture.sentinel','SELECT,INSERT,UPDATE,DELETE')"))!);
    }
    [Fact]
    public async Task FinancialColumnPrivilegeIsRejectedBeforeConnectionIsExposed()
    {
        await using var owner = await fixture.OpenOwnerAsync();
        try
        {
            await DatabaseFixture.ExecuteAsync(owner, "GRANT USAGE ON SCHEMA financial_fixture TO web_security_runtime; GRANT UPDATE(value) ON financial_fixture.sentinel TO web_security_runtime");
            Assert.False((bool)(await fixture.ScalarAsync("SELECT has_table_privilege('web_security_runtime','financial_fixture.sentinel','UPDATE')"))!);
            Assert.True((bool)(await fixture.ScalarAsync("SELECT has_any_column_privilege('web_security_runtime','financial_fixture.sentinel','UPDATE')"))!);
            await Assert.ThrowsAsync<InvalidOperationException>(() => fixture.Database(DatabasePurpose.Runtime).OpenAsync(CancellationToken.None));
            Assert.Equal("UNCHANGED", await fixture.ScalarAsync("SELECT value FROM financial_fixture.sentinel WHERE id=1"));
        }
        finally { await DatabaseFixture.ExecuteAsync(owner, "REVOKE UPDATE(value) ON financial_fixture.sentinel FROM web_security_runtime; REVOKE USAGE ON SCHEMA financial_fixture FROM web_security_runtime"); }
    }
}
