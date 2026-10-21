using System.Net;
using TradingAgent.Auth.Tests;
using TradingAgent.Web.Auth;
using Xunit;

namespace TradingAgent.Auth.Pilot.Tests;

public sealed class RequestBudgetTests
{
    [Fact]
    public void ExhaustedSourceCannotConsumeAnotherSourcesLoginCapacity()
    {
        var budgets = new PilotRequestBudgets(new TestClock()); var attacker = IPAddress.Parse("192.0.2.1");
        for (var i = 0; i < 20; i++) Assert.True(budgets.TryAdmit(PilotOperation.Login, attacker, $"user{i}@fixture.invalid"));
        for (var i = 0; i < 3000; i++) Assert.False(budgets.TryAdmit(PilotOperation.Login, attacker, $"rejected{i}@fixture.invalid"));
        Assert.True(budgets.TryAdmit(PilotOperation.Login, IPAddress.Parse("192.0.2.2"), "healthy@fixture.invalid"));
    }
    [Fact]
    public void AccountQuotaSurvivesChangingDirectAddressesAndEmailCase()
    {
        var b = new PilotRequestBudgets(new TestClock());
        for (var i = 1; i <= 20; i++) Assert.True(b.TryAdmit(PilotOperation.Login, IPAddress.Parse($"192.0.2.{i}"), i % 2 == 0 ? "ALICE@fixture.invalid" : "alice@fixture.invalid"));
        Assert.False(b.TryAdmit(PilotOperation.Login, IPAddress.Parse("198.51.100.1"), "alice@fixture.invalid"));
        Assert.True(b.TryAdmit(PilotOperation.Login, IPAddress.Parse("198.51.100.1"), "bob@fixture.invalid"));
    }
    [Fact]
    public void RejectedAccountDoesNotChargeSourcesOrGlobalBudget()
    {
        var b = new PilotRequestBudgets(new TestClock());
        for (var i = 0; i < 20; i++) Assert.True(b.TryAdmit(PilotOperation.Login, IPAddress.Parse("192.0.2.1"), "alice@fixture.invalid"));
        var healthy = IPAddress.Parse("192.0.2.2");
        for (var i = 0; i < 1000; i++) Assert.False(b.TryAdmit(PilotOperation.Login, healthy, "alice@fixture.invalid"));
        for (var i = 0; i < 20; i++) Assert.True(b.TryAdmit(PilotOperation.Login, healthy, "bob@fixture.invalid"));
    }
    [Theory]
    [InlineData(PilotOperation.Login,20)] [InlineData(PilotOperation.Mfa,40)] [InlineData(PilotOperation.Logout,20)] [InlineData(PilotOperation.Session,20)]
    public void ConcurrentAdmissionCannotOverspendSourceBudget(PilotOperation operation, int expected)
    {
        var b = new PilotRequestBudgets(new TestClock()); var successes = 0;
        Parallel.For(0, 200, _ => { if (b.TryAdmit(operation, IPAddress.Loopback, "fixture@fixture.invalid")) Interlocked.Increment(ref successes); });
        Assert.Equal(expected, successes);
    }
    [Fact]
    public void LoginExhaustionCannotBlockMfaOrLogout()
    {
        var b = new PilotRequestBudgets(new TestClock());
        for (var i = 0; i < 20; i++) Assert.True(b.TryAdmit(PilotOperation.Login, IPAddress.Loopback, "alice@fixture.invalid"));
        Assert.False(b.TryAdmit(PilotOperation.Login, IPAddress.Loopback, "alice@fixture.invalid"));
        Assert.True(b.TryAdmit(PilotOperation.Mfa, IPAddress.Loopback));
        Assert.True(b.TryAdmit(PilotOperation.Logout, IPAddress.Loopback));
    }
    [Fact]
    public void GlobalSafetyLimitStillBoundsDistributedTrafficAndLogoutHasReserve()
    {
        var b = new PilotRequestBudgets(new TestClock());
        for (var i = 1; i <= 200; i++) Assert.True(b.TryAdmit(PilotOperation.Login, IPAddress.Parse($"192.0.2.{i}"), $"user{i}@fixture.invalid"));
        Assert.False(b.TryAdmit(PilotOperation.Login, IPAddress.Parse("198.51.100.1"), "new@fixture.invalid"));
        Assert.True(b.TryAdmit(PilotOperation.Logout, IPAddress.Parse("198.51.100.1")));
    }
    [Fact]
    public void ExpiredWindowsRecoverCapacity()
    {
        var clock = new TestClock(); var b = new PilotRequestBudgets(clock);
        for (var i = 0; i < 20; i++) Assert.True(b.TryAdmit(PilotOperation.Login, null, "alice@fixture.invalid"));
        Assert.False(b.TryAdmit(PilotOperation.Login, null, "alice@fixture.invalid"));
        clock.Advance(TimeSpan.FromSeconds(61)); Assert.True(b.TryAdmit(PilotOperation.Login, null, "alice@fixture.invalid"));
    }
    [Fact]
    public void MappedIpv4DoesNotBypassSourceQuota()
    {
        var b = new PilotRequestBudgets(new TestClock());
        for (var i = 0; i < 20; i++) Assert.True(b.TryAdmit(PilotOperation.Login, IPAddress.Loopback, "alice@fixture.invalid"));
        Assert.False(b.TryAdmit(PilotOperation.Login, IPAddress.Loopback.MapToIPv6(), "alice@fixture.invalid"));
    }
}
