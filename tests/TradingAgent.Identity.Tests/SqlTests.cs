using TradingAgent.Identity.Migrations;
using TradingAgent.Identity.Persistence;
using Xunit;

namespace TradingAgent.Identity.Tests;

[Collection("PostgreSQL")]
public sealed class SqlTests(DatabaseFixture fixture)
{
    [Fact]
    public async Task MigrationsAreIdempotentAndRealPostgresIsRequired()
    {
        await MigrationRunner.ApplyAsync(fixture.Database(DatabasePurpose.Migration), CancellationToken.None);
        Assert.Equal(2L, await fixture.ScalarAsync("SELECT count(*) FROM app_security.migration_ledger"));
        Assert.StartsWith("17.", (string)(await fixture.ScalarAsync("SHOW server_version"))!);
    }
    [Fact]
    public async Task AliceBobAdministratorNeedRoleAndExactResourceAndEnvironment()
    {
        var admin = await fixture.AdministratorAsync(); var alice = await fixture.UserAsync(admin.Session); var bob = await fixture.UserAsync(admin.Session);
        var resource = Guid.NewGuid(); var expiry = DateTimeOffset.UtcNow.AddHours(1);
        Assert.Equal(StoreOutcome.Success, (await fixture.Administration().GrantRoleAsync(admin.Session, alice.User, PlatformRole.Viewer, expiry, CancellationToken.None)).Outcome);
        var aliceSession = await fixture.IssueAsync(alice.Identity);
        Assert.False((await fixture.Sessions.AuthorizeAsync(aliceSession, ResourceKind.Account, resource, EnvironmentScope.Paper, Capability.Read, CancellationToken.None)).Allowed);
        Assert.Equal(StoreOutcome.Success, (await fixture.Administration().GrantResourceAsync(admin.Session, alice.User, ResourceKind.Account, resource, EnvironmentScope.Paper, Capability.Read, expiry, CancellationToken.None)).Outcome);
        aliceSession = await fixture.IssueAsync(alice.Identity); var bobSession = await fixture.IssueAsync(bob.Identity);
        Assert.True((await fixture.Sessions.AuthorizeAsync(aliceSession, ResourceKind.Account, resource, EnvironmentScope.Paper, Capability.Read, CancellationToken.None)).Allowed);
        foreach (var denied in new[] { (bobSession, resource, EnvironmentScope.Paper, Capability.Read), (admin.Session, resource, EnvironmentScope.Paper, Capability.Read), (aliceSession, Guid.NewGuid(), EnvironmentScope.Paper, Capability.Read), (aliceSession, resource, EnvironmentScope.Live, Capability.Read), (aliceSession, resource, EnvironmentScope.Paper, Capability.Supervise) })
            Assert.False((await fixture.Sessions.AuthorizeAsync(denied.Item1, ResourceKind.Account, denied.Item2, denied.Item3, denied.Item4, CancellationToken.None)).Allowed);
        Assert.Equal(StoreOutcome.Success, (await fixture.Administration().GrantResourceAsync(admin.Session, bob.User, ResourceKind.Account, resource, EnvironmentScope.Paper, Capability.Read, expiry, CancellationToken.None)).Outcome);
        Assert.False((await fixture.Sessions.AuthorizeAsync(await fixture.IssueAsync(bob.Identity), ResourceKind.Account, resource, EnvironmentScope.Paper, Capability.Read, CancellationToken.None)).Allowed);
    }
}
