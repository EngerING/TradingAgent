using Npgsql;
using TradingAgent.Identity.Persistence;
using Xunit;

namespace TradingAgent.Identity.Tests;

[Collection("PostgreSQL")]
public sealed class ConcurrencyTests(DatabaseFixture fixture)
{
    private async Task<(Guid User, IdentityKey Identity, SessionReference Session, Guid Resource, Guid Grant, SessionReference Admin)> AuthorizedAsync(TimeSpan? grantLifetime = null)
    {
        var admin = await fixture.AdministratorAsync(); var user = await fixture.UserAsync(admin.Session); var resource = Guid.NewGuid();
        Assert.Equal(StoreOutcome.Success, (await fixture.Administration().GrantRoleAsync(admin.Session, user.User, PlatformRole.Viewer, DateTimeOffset.UtcNow.AddHours(1), CancellationToken.None)).Outcome);
        var grant = await fixture.Administration().GrantResourceAsync(admin.Session, user.User, ResourceKind.Account, resource, EnvironmentScope.Paper, Capability.Read, DateTimeOffset.UtcNow.Add(grantLifetime ?? TimeSpan.FromHours(1)), CancellationToken.None);
        Assert.Equal(StoreOutcome.Success, grant.Outcome);
        return (user.User, user.Identity, await fixture.IssueAsync(user.Identity), resource, grant.Id!.Value, admin.Session);
    }
    private Task<AuthorizationDecision> AuthorizeAsync(SessionReference session, Guid resource, CancellationToken token = default) => fixture.Sessions.AuthorizeAsync(session, ResourceKind.Account, resource, EnvironmentScope.Paper, Capability.Read, token);
    private async Task<int> WaitingAuthorizationAsync()
    {
        var deadline = DateTime.UtcNow.AddSeconds(2);
        while (DateTime.UtcNow < deadline)
        {
            var pid = await fixture.ScalarAsync("SELECT pid FROM pg_stat_activity WHERE datname=current_database() AND application_name='TradingAgent.M012.Disposable' AND wait_event_type='Lock' AND query LIKE 'SELECT allowed,as_of%' LIMIT 1");
            if (pid is int value) return value;
            await Task.Delay(20);
        }
        throw new InvalidOperationException("Expected authorization lock wait was not observed.");
    }
    [Theory]
    [InlineData("RevokeResource")] [InlineData("Status")]
    public async Task RevocationAndDisableCommittedDuringAuthorizationDenyAfterLockWait(string action)
    {
        var data = await AuthorizedAsync(); Assert.True((await AuthorizeAsync(data.Session, data.Resource)).Allowed);
        await using var owner = await fixture.OpenOwnerAsync(); await using var transaction = await owner.BeginTransactionAsync();
        await using (var mutation = new NpgsqlCommand("SELECT app_security.admin_change($1,$2,$3,$4,NULL,NULL,'Paper',NULL,NULL,NULL,NULL,NULL)", owner, transaction))
        {
            mutation.Parameters.AddWithValue(data.Admin.LookupHash()); mutation.Parameters.AddWithValue(action);
            mutation.Parameters.AddWithValue(action == "Status" ? data.User : data.Grant); mutation.Parameters.AddWithValue(action == "Status" ? "DISABLED" : "");
            Assert.Contains("Success", (string)(await mutation.ExecuteScalarAsync())!, StringComparison.Ordinal);
        }
        var authorization = AuthorizeAsync(data.Session, data.Resource); await WaitingAuthorizationAsync();
        await transaction.CommitAsync(); Assert.False((await authorization).Allowed);
        Assert.False((await AuthorizeAsync(data.Session, data.Resource)).Allowed);
        Assert.Equal(StoreOutcome.Denied, (await fixture.Sessions.TouchAsync(data.Session, 1, CancellationToken.None)).Outcome);
    }
    [Fact]
    public async Task GrantExpiringWhileBlockedUsesClockAfterLockAcquisition()
    {
        var data = await AuthorizedAsync(TimeSpan.FromSeconds(2));
        await using var owner = await fixture.OpenOwnerAsync(); await using var transaction = await owner.BeginTransactionAsync();
        await using (var locking = new NpgsqlCommand("SELECT app_user_id FROM app_security.app_users WHERE app_user_id=$1 FOR UPDATE", owner, transaction))
        { locking.Parameters.AddWithValue(data.User); await locking.ExecuteScalarAsync(); }
        var authorization = AuthorizeAsync(data.Session, data.Resource); await WaitingAuthorizationAsync();
        while (!(bool)(await fixture.ScalarAsync("SELECT clock_timestamp()>=expires_at FROM app_security.resource_grants WHERE grant_id=$1", data.Grant))!) await Task.Delay(25);
        await transaction.CommitAsync(); Assert.False((await authorization).Allowed);
    }
    [Fact]
    public async Task InterruptedAuthorizationConnectionReturnsUnavailableWithoutAccess()
    {
        var data = await AuthorizedAsync(); await using var owner = await fixture.OpenOwnerAsync(); await using var transaction = await owner.BeginTransactionAsync();
        await using (var locking = new NpgsqlCommand("SELECT app_user_id FROM app_security.app_users WHERE app_user_id=$1 FOR UPDATE", owner, transaction))
        { locking.Parameters.AddWithValue(data.User); await locking.ExecuteScalarAsync(); }
        var authorization = AuthorizeAsync(data.Session, data.Resource); var pid = await WaitingAuthorizationAsync();
        Assert.True((bool)(await fixture.ScalarAsync("SELECT pg_terminate_backend($1)", pid))!);
        var result = await authorization; Assert.False(result.Allowed); Assert.Equal(StoreOutcome.Unavailable, result.Outcome);
        await transaction.RollbackAsync();
    }
    [Fact]
    public async Task CancelledAuthorizationDoesNotReturnAllowed()
    {
        var data = await AuthorizedAsync(); using var cancellation = new CancellationTokenSource(); cancellation.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => AuthorizeAsync(data.Session, data.Resource, cancellation.Token));
    }
    [Fact]
    public async Task InterruptedRoleChangeRollsBackAuditVersionAndSessionRevocation()
    {
        var data = await AuthorizedAsync(); var before = await fixture.ScalarAsync("SELECT authz_version FROM app_security.app_users WHERE app_user_id=$1", data.User);
        var audits = await fixture.ScalarAsync("SELECT count(*) FROM app_security.security_audit_events WHERE actor_id=(SELECT app_user_id FROM app_security.web_sessions WHERE reference_hash=$1)", data.Admin.LookupHash());
        await using (var owner = await fixture.OpenOwnerAsync())
        {
            await using var transaction = await owner.BeginTransactionAsync();
            await using var mutation = new NpgsqlCommand("SELECT app_security.admin_change($1,'GrantRole',$2,'Researcher',NULL,NULL,'Paper',NULL,$3,NULL,NULL,NULL)", owner, transaction);
            mutation.Parameters.AddWithValue(data.Admin.LookupHash()); mutation.Parameters.AddWithValue(data.User); mutation.Parameters.AddWithValue(DateTimeOffset.UtcNow.AddHours(1));
            Assert.Contains("Success", (string)(await mutation.ExecuteScalarAsync())!, StringComparison.Ordinal);
            // Dispose without COMMIT models interruption of this explicit transaction.
        }
        Assert.Equal(before, await fixture.ScalarAsync("SELECT authz_version FROM app_security.app_users WHERE app_user_id=$1", data.User));
        Assert.Equal(audits, await fixture.ScalarAsync("SELECT count(*) FROM app_security.security_audit_events WHERE actor_id=(SELECT app_user_id FROM app_security.web_sessions WHERE reference_hash=$1)", data.Admin.LookupHash()));
        Assert.True((await AuthorizeAsync(data.Session, data.Resource)).Allowed);
    }
    [Fact]
    public async Task AuditInsertFailureRollsBackEntireAdministrativeChange()
    {
        var data = await AuthorizedAsync(); var before = await fixture.ScalarAsync("SELECT authz_version FROM app_security.app_users WHERE app_user_id=$1", data.User);
        await using var owner = await fixture.OpenOwnerAsync();
        await DatabaseFixture.ExecuteAsync(owner, "CREATE FUNCTION app_security.fixture_fail_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.action='GrantRole' THEN RAISE EXCEPTION 'FIXTURE_AUDIT_FAILURE'; END IF; RETURN NEW; END $$; CREATE TRIGGER fixture_failure BEFORE INSERT ON app_security.security_audit_events FOR EACH ROW EXECUTE FUNCTION app_security.fixture_fail_audit(); REVOKE EXECUTE ON FUNCTION app_security.fixture_fail_audit() FROM PUBLIC");
        try
        {
            Assert.Equal(StoreOutcome.Unavailable, (await fixture.Administration().GrantRoleAsync(data.Admin, data.User, PlatformRole.Researcher, DateTimeOffset.UtcNow.AddHours(1), CancellationToken.None)).Outcome);
            Assert.Equal(before, await fixture.ScalarAsync("SELECT authz_version FROM app_security.app_users WHERE app_user_id=$1", data.User));
            Assert.Equal(0L, await fixture.ScalarAsync("SELECT count(*) FROM app_security.user_roles WHERE app_user_id=$1 AND role_name='Researcher'", data.User));
            Assert.True((await AuthorizeAsync(data.Session, data.Resource)).Allowed);
        }
        finally { await DatabaseFixture.ExecuteAsync(owner, "DROP TRIGGER fixture_failure ON app_security.security_audit_events; DROP FUNCTION app_security.fixture_fail_audit()"); }
    }
    [Fact]
    public async Task ExpiredSessionsAndStaleAuthorizationVersionCannotBeReused()
    {
        var data = await AuthorizedAsync(); var shortSession = await fixture.IssueAsync(data.Identity, TimeSpan.FromMilliseconds(400));
        await Task.Delay(450); Assert.Null(await fixture.Sessions.FindSelfAsync(shortSession, CancellationToken.None));
        await fixture.ScalarAsync("UPDATE app_security.app_users SET authz_version=authz_version+1 WHERE app_user_id=$1", data.User);
        Assert.False((await AuthorizeAsync(data.Session, data.Resource)).Allowed);
    }
    [Fact]
    public async Task RevokedGrantCannotBeResurrectedAndHistoryRemains()
    {
        var data = await AuthorizedAsync(); Assert.Equal(StoreOutcome.Success, (await fixture.Administration().RevokeResourceAsync(data.Admin, data.Grant, CancellationToken.None)).Outcome);
        await using var owner = await fixture.OpenOwnerAsync();
        await using var command = new NpgsqlCommand("UPDATE app_security.resource_grants SET revoked_at=NULL,revoked_by=NULL WHERE grant_id=$1", owner); command.Parameters.AddWithValue(data.Grant);
        var error = await Assert.ThrowsAsync<PostgresException>(() => command.ExecuteNonQueryAsync()); Assert.Equal("23514", error.SqlState);
        Assert.Equal(1L, await fixture.ScalarAsync("SELECT count(*) FROM app_security.resource_grants WHERE grant_id=$1 AND revoked_at IS NOT NULL", data.Grant));
        Assert.False((await AuthorizeAsync(await fixture.IssueAsync(data.Identity), data.Resource)).Allowed);
    }
    [Fact]
    public async Task OwnerScopeRechecksAdministratorAfterWaitingForUserLock()
    {
        var admin = await fixture.AdministratorAsync(); await using var owner = await fixture.OpenOwnerAsync(); await using var transaction = await owner.BeginTransactionAsync();
        await using (var locking = new NpgsqlCommand("SELECT app_user_id FROM app_security.app_users WHERE app_user_id=$1 FOR UPDATE", owner, transaction))
        { locking.Parameters.AddWithValue(admin.User); await locking.ExecuteScalarAsync(); }
        await using (var revoke = new NpgsqlCommand("UPDATE app_security.user_roles SET revoked_at=clock_timestamp(),revoked_by=$1 WHERE app_user_id=$1 AND role_name='Administrator' AND revoked_at IS NULL", owner, transaction))
        { revoke.Parameters.AddWithValue(admin.User); await revoke.ExecuteNonQueryAsync(); }
        await using var contender = await fixture.OpenOwnerAsync();
        await using var scope = new NpgsqlCommand("SELECT app_security.owner_scope($1,'Live')", contender); scope.Parameters.AddWithValue(admin.User);
        var pending = scope.ExecuteScalarAsync(); var deadline = DateTime.UtcNow.AddSeconds(2);
        while (!(bool)(await fixture.ScalarAsync("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE pid=$1 AND wait_event_type='Lock')", contender.ProcessID))!)
        { Assert.True(DateTime.UtcNow < deadline); await Task.Delay(20); }
        await transaction.CommitAsync();
        Assert.Equal("42501", (await Assert.ThrowsAsync<PostgresException>(() => pending)).SqlState);
        Assert.Equal(0L, await fixture.ScalarAsync("SELECT count(*) FROM app_security.resource_grants WHERE app_user_id=$1 AND environment='Live'", admin.User));
    }
}
