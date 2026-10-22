using TradingAgent.Web.Auth;
using TradingAgent.Identity.Persistence;
using TradingAgent.Identity.Supabase;
using Xunit;

namespace TradingAgent.React.Integration.Tests;

/// <summary>No hosted requests or real credentials. Exercises bounded in-memory auth state.</summary>
public sealed class PreviewSessionLifecycleTests
{
    private sealed class ManualClock : TimeProvider
    {
        private DateTimeOffset now = new(2026, 10, 22, 12, 0, 0, TimeSpan.Zero);
        public override DateTimeOffset GetUtcNow() => now;
        public void Advance(TimeSpan delta) => now += delta;
    }
    private sealed class FakeTokenProvider(ManualClock clock) : IPreviewTokenProvider
    {
        private readonly Guid user = Guid.NewGuid();
        private readonly Guid session = Guid.NewGuid();
        internal bool ChangeSession { get; set; }
        internal bool RejectRefresh { get; set; }
        internal bool FailLogout { get; set; }
        internal bool FailCheck { get; set; }
        internal int TokenAal { get; set; } = 1;
        internal int Refreshed { get; private set; }
        private PreviewTokenPair Token(int number, Guid? sessionOverride = null) => new(
            new AccessCredential("PUBLIC_SYNTHETIC_TEST_TOKEN_" + number,
                new VerifiedIdentity(new IdentityKey("https://fixture.invalid/auth/v1", user),
                    sessionOverride ?? session, TokenAal, clock.GetUtcNow(), clock.GetUtcNow().AddHours(1), null)),
            "public-synthetic-refresh-" + number);
        public Task<PreviewTokenPair> PasswordAsync(string email, string password, CancellationToken ct)
        {
            Assert.Equal("fixture@fixture.invalid", email); Assert.Equal("public-fixture-password", password);
            return Task.FromResult(Token(0));
        }
        public Task<PreviewTokenPair> RefreshAsync(string refreshToken, CancellationToken ct)
        {
            Refreshed++;
            if (RejectRefresh) throw new AuthException(AuthFailure.Unavailable);
            return Task.FromResult(Token(Refreshed, ChangeSession ? Guid.NewGuid() : null));
        }
        public Task CheckAsync(AccessCredential credential, CancellationToken ct)
        {
            if (FailCheck) throw new AuthException(AuthFailure.Unavailable);
            if (credential.Identity.ExpiresAt <= clock.GetUtcNow()) throw new AuthException(AuthFailure.Invalid);
            return Task.CompletedTask;
        }
        public Task LogoutAsync(AccessCredential credential, CancellationToken ct)
        {
            if (FailLogout) throw new AuthException(AuthFailure.Unavailable);
            return Task.CompletedTask;
        }
    }
    private static async Task<(PasswordPreviewSessions Sessions, FakeTokenProvider Provider, ManualClock Clock, SessionReference Cookie)> Begin()
    {
        var clock = new ManualClock(); var provider = new FakeTokenProvider(clock);
        var sessions = new PasswordPreviewSessions(provider, clock, "fixture@fixture.invalid");
        var result = await sessions.LoginAsync("fixture@fixture.invalid", "public-fixture-password", CancellationToken.None);
        return (sessions, provider, clock, result.Reference);
    }

    [Fact]
    public async Task PassiveSessionChecksDoNotExtendThirtyMinuteInactivity()
    {
        var (sessions, _, clock, cookie) = await Begin();
        clock.Advance(TimeSpan.FromMinutes(20));
        _ = await sessions.SessionAsync(cookie, false, CancellationToken.None);
        clock.Advance(TimeSpan.FromMinutes(10));
        await Assert.ThrowsAsync<AuthException>(() => sessions.SessionAsync(cookie, false, CancellationToken.None));
    }

    [Fact]
    public async Task ExplicitActivityRenewsIdleAndRotatesProviderRefresh()
    {
        var (sessions, provider, clock, cookie) = await Begin();
        clock.Advance(TimeSpan.FromMinutes(20));
        var before = await sessions.SessionAsync(cookie, true, CancellationToken.None);
        clock.Advance(TimeSpan.FromMinutes(20));
        var after = await sessions.SessionAsync(cookie, true, CancellationToken.None);
        Assert.True(after.IdleExpiresAt > before.IdleExpiresAt);
        clock.Advance(TimeSpan.FromMinutes(19));
        _ = await sessions.SessionAsync(cookie, true, CancellationToken.None);
        Assert.Equal(1, provider.Refreshed);
        _ = await sessions.SessionAsync(cookie, false, CancellationToken.None);
        Assert.Equal(1, provider.Refreshed);
    }

    [Fact]
    public async Task EightHourAbsoluteExpiryWinsEvenWithUserActivity()
    {
        var (sessions, _, clock, cookie) = await Begin();
        for (var i = 0; i < 23; i++)
        {
            clock.Advance(TimeSpan.FromMinutes(20));
            var result = await sessions.SessionAsync(cookie, true, CancellationToken.None);
            Assert.True(result.IdleExpiresAt <= result.ExpiresAt);
        }
        clock.Advance(TimeSpan.FromMinutes(20)); // Exactly 8 hours, irrespective of recent activity.
        await Assert.ThrowsAsync<AuthException>(() => sessions.SessionAsync(cookie, true, CancellationToken.None));
    }

    [Fact]
    public async Task RefreshSessionSubstitutionFailsClosedAndCannotBeReplayed()
    {
        var (sessions, provider, clock, cookie) = await Begin();
        clock.Advance(TimeSpan.FromMinutes(20));
        _ = await sessions.SessionAsync(cookie, true, CancellationToken.None);
        clock.Advance(TimeSpan.FromMinutes(20));
        _ = await sessions.SessionAsync(cookie, true, CancellationToken.None);
        provider.ChangeSession = true;
        clock.Advance(TimeSpan.FromMinutes(19));
        await Assert.ThrowsAsync<AuthException>(() => sessions.SessionAsync(cookie, true, CancellationToken.None));
        await Assert.ThrowsAsync<AuthException>(() => sessions.SessionAsync(cookie, false, CancellationToken.None));
        Assert.Equal(1, provider.Refreshed);
    }

    [Fact]
    public async Task ProviderUnavailabilityRevokesAnOtherwiseValidPreview()
    {
        var (sessions, provider, clock, cookie) = await Begin();
        clock.Advance(TimeSpan.FromMinutes(1));
        provider.FailCheck = true;
        await Assert.ThrowsAsync<AuthException>(() => sessions.SessionAsync(cookie, false, CancellationToken.None));
        provider.FailCheck = false;
        await Assert.ThrowsAsync<AuthException>(() => sessions.SessionAsync(cookie, false, CancellationToken.None));
    }

    [Fact]
    public async Task PasswordOnlyPreviewRejectsAal2Identity()
    {
        var clock = new ManualClock();
        var provider = new FakeTokenProvider(clock) { TokenAal = 2 };
        using var sessions = new PasswordPreviewSessions(provider, clock, "fixture@fixture.invalid");
        await Assert.ThrowsAsync<AuthException>(() => sessions.LoginAsync("fixture@fixture.invalid", "public-fixture-password", CancellationToken.None));
    }

    [Fact]
    public async Task RefreshWithChangedAssuranceFailsClosed()
    {
        var (sessions, provider, clock, cookie) = await Begin();
        clock.Advance(TimeSpan.FromMinutes(20));
        _ = await sessions.SessionAsync(cookie, true, CancellationToken.None);
        clock.Advance(TimeSpan.FromMinutes(20));
        _ = await sessions.SessionAsync(cookie, true, CancellationToken.None);
        provider.TokenAal = 2;
        clock.Advance(TimeSpan.FromMinutes(19));
        await Assert.ThrowsAsync<AuthException>(() => sessions.SessionAsync(cookie, true, CancellationToken.None));
        await Assert.ThrowsAsync<AuthException>(() => sessions.SessionAsync(cookie, false, CancellationToken.None));
    }

    [Fact]
    public async Task RemoteLogoutFailureStillInvalidatesLocalPreviewCapability()
    {
        var (sessions, provider, _, cookie) = await Begin();
        provider.FailLogout = true;
        await Assert.ThrowsAsync<AuthException>(() => sessions.LogoutAsync(cookie, CancellationToken.None));
        await Assert.ThrowsAsync<AuthException>(() => sessions.SessionAsync(cookie, false, CancellationToken.None));
    }
}
