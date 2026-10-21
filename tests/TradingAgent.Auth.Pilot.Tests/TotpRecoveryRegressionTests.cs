using Microsoft.Extensions.DependencyInjection;
using TradingAgent.Auth.Tests;
using TradingAgent.HostedPilot;
using TradingAgent.Identity.Persistence;
using TradingAgent.Identity.Supabase;
using Xunit;

namespace TradingAgent.Auth.Pilot.Tests;

public sealed class TotpRecoveryRegressionTests
{
    [Fact]
    public async Task ConfirmedExactOwnUnverifiedFactorIsRemovedAndOtherUserRemainsIntact()
    {
        await using var f = await RecoveryFixture.CreateAsync();
        var other = Guid.NewGuid(); f.Remote.Factors[other] = Guid.NewGuid(); f.Remote.VerifiedFactors[other] = true;
        var prompts = 0;
        await f.Recover(target => { prompts++; Assert.Equal(f.Target, target); return true; });
        Assert.Equal(1, prompts); Assert.False(f.Remote.Factors.ContainsKey(f.Factor));
        Assert.True(f.Remote.Factors.ContainsKey(other)); Assert.True(f.Remote.VerifiedFactors.ContainsKey(other));
        Assert.Single(f.Remote.Factors); // No automatic enrollment inside recovery.
    }
    [Fact]
    public async Task RefusingConfirmationPreservesFactor()
    {
        await using var f = await RecoveryFixture.CreateAsync();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => f.Recover(_ => false));
        Assert.True(f.Remote.Factors.ContainsKey(f.Factor));
    }
    [Fact]
    public async Task VerifiedFactorNeverPromptsOrDeletes()
    {
        await using var f = await RecoveryFixture.CreateAsync(); f.Remote.VerifiedFactors[f.Factor] = true;
        await Assert.ThrowsAsync<AuthException>(() => f.Recover(_ => throw new InvalidOperationException("Must not prompt")));
        Assert.True(f.Remote.Factors.ContainsKey(f.Factor));
    }
    [Fact]
    public async Task FactorVerifiedDuringConfirmationIsPreserved()
    {
        await using var f = await RecoveryFixture.CreateAsync();
        await Assert.ThrowsAsync<AuthException>(() => f.Recover(_ => { f.Remote.VerifiedFactors[f.Factor] = true; return true; }));
        Assert.True(f.Remote.Factors.ContainsKey(f.Factor));
    }
    [Fact]
    public async Task ChangedCandidateAfterConfirmationIsNotReplacedByAnotherTarget()
    {
        await using var f = await RecoveryFixture.CreateAsync(); var replacement = Guid.NewGuid();
        await Assert.ThrowsAsync<AuthException>(() => f.Recover(candidate => { f.Remote.Factors.TryRemove(f.Factor, out _); f.Remote.Factors[replacement] = f.Credential.Identity.Identity.Subject; return true; }));
        Assert.True(f.Remote.Factors.ContainsKey(replacement));
    }
    [Fact]
    public async Task ForeignFactorIsRejectedWithoutPrompt()
    {
        await using var f = await RecoveryFixture.CreateAsync(); var foreign = Guid.NewGuid(); f.Remote.Factors[foreign] = Guid.NewGuid();
        var target = f.Target with { FactorId = foreign };
        await Assert.ThrowsAsync<AuthException>(() => IncompleteTotpRecovery.RecoverAsync(f.Auth, f.Verifier, f.Credential, target, _ => throw new InvalidOperationException("Must not prompt"), f.Remote.Clock, CancellationToken.None));
        Assert.True(f.Remote.Factors.ContainsKey(foreign));
    }
    [Fact]
    public async Task DifferentIdentityCannotAuthorizeRecovery()
    {
        await using var f = await RecoveryFixture.CreateAsync();
        var target = f.Target with { Identity = new IdentityKey(f.Target.Identity.Issuer, Guid.NewGuid()) };
        await Assert.ThrowsAsync<AuthException>(() => IncompleteTotpRecovery.RecoverAsync(f.Auth, f.Verifier, f.Credential, target, _ => throw new InvalidOperationException("Must not prompt"), f.Remote.Clock, CancellationToken.None));
        Assert.True(f.Remote.Factors.ContainsKey(f.Factor));
    }
    [Fact]
    public async Task MultipleOwnCandidatesAreRejectedWithoutPrompt()
    {
        await using var f = await RecoveryFixture.CreateAsync(); f.Remote.Factors[Guid.NewGuid()] = f.Credential.Identity.Identity.Subject;
        await Assert.ThrowsAsync<AuthException>(() => f.Recover(_ => throw new InvalidOperationException("Must not prompt")));
        Assert.Equal(2, f.Remote.Factors.Count);
    }
    [Fact]
    public async Task ExpiredConfirmationDoesNotMutate()
    {
        await using var f = await RecoveryFixture.CreateAsync();
        await Assert.ThrowsAsync<AuthException>(() => f.Recover(_ => { f.Remote.Clock.Advance(TimeSpan.FromMinutes(2)); return true; }));
        Assert.True(f.Remote.Factors.ContainsKey(f.Factor));
    }
    [Fact]
    public async Task CancellationAfterConfirmationDoesNotMutate()
    {
        await using var f = await RecoveryFixture.CreateAsync(); using var cancellation = new CancellationTokenSource();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => f.Recover(_ => { cancellation.Cancel(); return true; }, cancellation.Token));
        Assert.True(f.Remote.Factors.ContainsKey(f.Factor));
    }
    [Fact]
    public async Task ExpiryDuringFinalOwnershipReadPreventsDeleteDispatch()
    {
        await using var f = await RecoveryFixture.CreateAsync();
        f.Hook.AfterThirdUserRead = () => f.Remote.Clock.Advance(TimeSpan.FromMinutes(2));
        await Assert.ThrowsAsync<AuthException>(() => f.Recover(_ => true));
        Assert.Equal(0, f.Hook.DeleteRequests); Assert.True(f.Remote.Factors.ContainsKey(f.Factor));
    }
    [Fact]
    public async Task ProviderRejectsVerifiedFactorRaceAfterFinalReadInFixture()
    {
        await using var f = await RecoveryFixture.CreateAsync();
        f.Hook.AfterThirdUserRead = () => f.Remote.VerifiedFactors[f.Factor] = true;
        await Assert.ThrowsAsync<AuthException>(() => f.Recover(_ => true));
        Assert.Equal(1, f.Hook.DeleteRequests); Assert.True(f.Remote.VerifiedFactors.ContainsKey(f.Factor));
        Assert.True(f.Remote.Factors.ContainsKey(f.Factor)); // Provider-fixture guard; not an atomic client guarantee.
    }
    [Fact]
    public async Task InvalidJwtNeverPromptsOrDeletes()
    {
        await using var f = await RecoveryFixture.CreateAsync(); var invalid = new AccessCredential("INVALID_PUBLIC_FIXTURE", f.Credential.Identity);
        await Assert.ThrowsAsync<AuthException>(() => IncompleteTotpRecovery.RecoverAsync(f.Auth, f.Verifier, invalid, f.Target, _ => throw new InvalidOperationException("Must not prompt"), f.Remote.Clock, CancellationToken.None));
        Assert.True(f.Remote.Factors.ContainsKey(f.Factor));
    }
    [Fact]
    public async Task Aal2CredentialCannotUseIncompleteEnrollmentRecovery()
    {
        await using var f = await RecoveryFixture.CreateAsync();
        var challenge = await f.Auth.ChallengeAsync(f.Credential, f.Factor, CancellationToken.None);
        var elevated = await f.Auth.VerifyAsync(f.Credential, f.Factor, challenge.Id, "123456", CancellationToken.None);
        f.Remote.VerifiedFactors.TryRemove(f.Factor, out _); // Remote fixture state only: guard must reject AAL2 itself.
        await Assert.ThrowsAsync<AuthException>(() => IncompleteTotpRecovery.RecoverAsync(f.Auth, f.Verifier, elevated, f.Target, _ => throw new InvalidOperationException("Must not prompt"), f.Remote.Clock, CancellationToken.None));
        Assert.True(f.Remote.Factors.ContainsKey(f.Factor));
    }

    private sealed class RecoveryFixture : IAsyncDisposable
    {
        internal SimulatedAuth Remote { get; } = new();
        private ServiceProvider services = null!;
        internal UserReadHook Hook { get; } = new();
        internal Guid Factor { get; } = Guid.NewGuid();
        internal SupabaseAuthClient Auth => services.GetRequiredService<SupabaseAuthClient>();
        internal JwtVerifier Verifier => services.GetRequiredService<JwtVerifier>();
        internal AccessCredential Credential { get; private set; } = null!;
        internal TotpRecoveryTarget Target => new(Credential.Identity.Identity, Factor);
        internal static async Task<RecoveryFixture> CreateAsync()
        {
            var f = new RecoveryFixture(); var user = Guid.NewGuid(); f.Remote.Users["fixture@fixture.invalid"] = user; f.Remote.Factors[f.Factor] = user;
            await f.Remote.StartAsync();
            var registrations = new ServiceCollection(); f.Remote.Configure(registrations);
            registrations.AddHttpClient<AuthTransport>().AddHttpMessageHandler(() => f.Hook);
            f.services = registrations.BuildServiceProvider();
            f.Credential = await f.Auth.PasswordAsync("fixture@fixture.invalid", "fixture-password", CancellationToken.None); return f;
        }
        internal Task Recover(Func<TotpRecoveryTarget, bool> confirm, CancellationToken token = default) => IncompleteTotpRecovery.RecoverAsync(Auth, Verifier, Credential, Target, confirm, Remote.Clock, token);
        public async ValueTask DisposeAsync() { await services.DisposeAsync(); await Remote.DisposeAsync(); }
    }
    private sealed class UserReadHook : DelegatingHandler
    {
        private int reads;
        internal Action? AfterThirdUserRead { get; set; }
        internal int DeleteRequests { get; private set; }
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            if (request.Method == HttpMethod.Delete) DeleteRequests++;
            var response = await base.SendAsync(request, cancellationToken);
            if (request.RequestUri!.AbsolutePath == "/auth/v1/user" && ++reads == 3)
            {
                await response.Content.LoadIntoBufferAsync(65536, cancellationToken);
                AfterThirdUserRead?.Invoke();
            }
            return response;
        }
    }
}
