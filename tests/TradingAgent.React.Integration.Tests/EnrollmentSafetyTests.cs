using System.Net;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.DependencyInjection;
using TradingAgent.Auth.Tests;
using TradingAgent.Identity.Persistence;
using TradingAgent.Identity.Supabase;
using TradingAgent.Web.Auth;
using Xunit;

namespace TradingAgent.React.Integration.Tests;

public sealed class EnrollmentSafetyTests
{
    [Fact]
    public async Task HostedBrowserRequiresExplicitLoopbackSanAndPublishesClosedConfig()
    {
        using var rsa = RSA.Create(2048);
        var request = new CertificateRequest("CN=127.0.0.1", rsa, HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1);
        var alt = new SubjectAlternativeNameBuilder();
        alt.AddIpAddress(IPAddress.Loopback);
        request.CertificateExtensions.Add(alt.Build());
        using var valid = request.CreateSelfSigned(DateTimeOffset.UtcNow.AddMinutes(-1), DateTimeOffset.UtcNow.AddMinutes(15));
        var origin = new Uri("https://127.0.0.1:29997/");
        var settings = HostedPilotSettings.FromExternalValues(
            "Development", "ocwabwmzhpedyxlkjpje",
            new Uri("https://ocwabwmzhpedyxlkjpje.supabase.co/"),
            "sb_publishable_testonly_localfixture", origin);
        var target = new DisposableTarget("127.0.0.1", 29999, "m012_test_" + Guid.NewGuid().ToString("N"));
        var runtime = new SecurityDatabase(target, "test_runtime", "PUBLIC_TEST_ONLY", DatabasePurpose.Runtime);
        var issuer = new SecurityDatabase(target, "test_issuer", "PUBLIC_TEST_ONLY", DatabasePurpose.SessionIssuer);
        await using (var app = IntegratedHostFactory.CreateHostedBrowserPilot(settings, runtime, issuer, valid))
        {
            var mapped = ((IEndpointRouteBuilder)app).DataSources.SelectMany(d => d.Endpoints).OfType<RouteEndpoint>();
            Assert.Contains(mapped, route => route.RoutePattern.RawText == "/bff/config");
            Assert.Contains(mapped, route => route.RoutePattern.RawText == "/bff/auth/login");
        }
        using var otherKey = RSA.Create(2048);
        var wrongRequest = new CertificateRequest("CN=127.0.0.1", otherKey, HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1);
        using var missingSan = wrongRequest.CreateSelfSigned(DateTimeOffset.UtcNow.AddMinutes(-1), DateTimeOffset.UtcNow.AddMinutes(15));
        Assert.Throws<ArgumentException>(() => IntegratedHostFactory.CreateHostedBrowserPilot(settings, runtime, issuer, missingSan));
        Assert.Throws<ArgumentException>(() => HostedPilotSettings.FromExternalValues(
            "Development", "ocwabwmzhpedyxlkjpje",
            new Uri("https://ocwabwmzhpedyxlkjpje.supabase.co/"),
            "sb_publishable_testonly_localfixture", new Uri("https://localhost:29997/")));
    }
    [Theory]
    [InlineData(1, false)]
    [InlineData(2, false)]
    [InlineData(1, true)]
    [InlineData(2, true)]
    public async Task ExistingOwnFactorsBlockEnrollmentWithoutDeletingOrReplacing(int count, bool verified)
    {
        await using var flow = await EnrollmentFlow.CreateAsync();
        var factors = Enumerable.Range(0, count).Select(_ => flow.AddFactor(verified)).ToArray();
        var reference = await flow.LoginAsync();

        var error = await Assert.ThrowsAsync<AuthException>(() => flow.Runtime.EnrollAsync(reference, CancellationToken.None));

        Assert.Equal(AuthFailure.Conflict, error.Failure);
        Assert.Equal(factors.Order(), flow.Provider.Factors.Keys.Order());
        Assert.Equal(verified ? count : 0, flow.Provider.VerifiedFactors.Count);
    }

    [Fact]
    public async Task RepeatedEnrollmentPreservesFirstUnverifiedFactorAndCanStillChallengeIt()
    {
        await using var flow = await EnrollmentFlow.CreateAsync(); var reference = await flow.LoginAsync();
        var enrollment = await flow.Runtime.EnrollAsync(reference, CancellationToken.None);

        var error = await Assert.ThrowsAsync<AuthException>(() => flow.Runtime.EnrollAsync(reference, CancellationToken.None));

        Assert.Equal(AuthFailure.Conflict, error.Failure);
        Assert.Equal(enrollment.FactorId, Assert.Single(flow.Provider.Factors).Key);
        var challenge = await flow.Runtime.ChallengeAsync(reference, enrollment.FactorId, CancellationToken.None);
        Assert.NotEqual(Guid.Empty, challenge.Id); Assert.Equal(0, flow.Provider.VerifyRequests);
    }

    [Fact]
    public async Task OtherUsersFactorIsNeverDeletedByEnrollment()
    {
        await using var flow = await EnrollmentFlow.CreateAsync();
        var foreign = Guid.NewGuid(); flow.Provider.Factors[foreign] = Guid.NewGuid();
        var reference = await flow.LoginAsync();

        var enrollment = await flow.Runtime.EnrollAsync(reference, CancellationToken.None);

        Assert.Contains(foreign, flow.Provider.Factors.Keys);
        Assert.NotEqual(foreign, enrollment.FactorId); Assert.Equal(2, flow.Provider.Factors.Count);
    }

    [Fact]
    public async Task SuccessfulEnrollmentCannotBeRepeatedWhenProviderListTemporarilyOmitsIt()
    {
        await using var flow = await EnrollmentFlow.CreateAsync(); var reference = await flow.LoginAsync();
        var enrollment = await flow.Runtime.EnrollAsync(reference, CancellationToken.None);
        Assert.True(flow.Provider.Factors.TryRemove(enrollment.FactorId, out _));

        var error = await Assert.ThrowsAsync<AuthException>(() => flow.Runtime.EnrollAsync(reference, CancellationToken.None));

        Assert.Equal(AuthFailure.Conflict, error.Failure); Assert.Empty(flow.Provider.Factors);
    }

    [Fact]
    public async Task ExistingVerifiedFactorCanBeChallengedWithoutEnrollmentOrDeletion()
    {
        await using var flow = await EnrollmentFlow.CreateAsync(); var factor = flow.AddFactor(true);
        var reference = await flow.LoginAsync();

        var challenge = await flow.Runtime.ChallengeAsync(reference, factor, CancellationToken.None);

        Assert.NotEqual(Guid.Empty, challenge.Id); Assert.Equal(factor, Assert.Single(flow.Provider.Factors).Key);
        Assert.True(flow.Provider.VerifiedFactors[factor]);
    }

    [Fact]
    public async Task OrphanFromAnotherLoginCannotBeChallengedOrReplaced()
    {
        await using var flow = await EnrollmentFlow.CreateAsync();
        var first = await flow.LoginAsync(); var enrollment = await flow.Runtime.EnrollAsync(first, CancellationToken.None);
        var second = await flow.LoginAsync();

        var challengeError = await Assert.ThrowsAsync<AuthException>(() => flow.Runtime.ChallengeAsync(second, enrollment.FactorId, CancellationToken.None));
        var enrollError = await Assert.ThrowsAsync<AuthException>(() => flow.Runtime.EnrollAsync(second, CancellationToken.None));

        Assert.Equal(AuthFailure.Invalid, challengeError.Failure); Assert.Equal(AuthFailure.Conflict, enrollError.Failure);
        Assert.Equal(enrollment.FactorId, Assert.Single(flow.Provider.Factors).Key); Assert.Empty(flow.Provider.VerifiedFactors);
    }

    [Fact]
    public async Task RejectedCurrentIdentityCannotMutateExistingEnrollment()
    {
        await using var flow = await EnrollmentFlow.CreateAsync(); var factor = flow.AddFactor(false);
        var reference = await flow.LoginAsync(); flow.Provider.RejectUser = true;

        var error = await Assert.ThrowsAsync<AuthException>(() => flow.Runtime.EnrollAsync(reference, CancellationToken.None));

        Assert.Equal(AuthFailure.Invalid, error.Failure); Assert.Equal(factor, Assert.Single(flow.Provider.Factors).Key);
    }

    [Fact]
    public async Task UncertainEnrollmentResponseCannotBeAutomaticallyRetried()
    {
        var failure = new EnrollmentFailureHandler();
        await using var flow = await EnrollmentFlow.CreateAsync(failure); var reference = await flow.LoginAsync();
        var first = await Assert.ThrowsAsync<AuthException>(() => flow.Runtime.EnrollAsync(reference, CancellationToken.None));
        Assert.Equal(AuthFailure.Unavailable, first.Failure); failure.FailEnrollment = false;

        var second = await Assert.ThrowsAsync<AuthException>(() => flow.Runtime.EnrollAsync(reference, CancellationToken.None));

        Assert.Equal(AuthFailure.Conflict, second.Failure); Assert.Equal(1, failure.Attempts); Assert.Empty(flow.Provider.Factors);
    }

    [Fact]
    public async Task AnotherLoginCannotRetryAnEnrollmentWhoseResponseWasLost()
    {
        var failure = new EnrollmentFailureHandler();
        await using var flow = await EnrollmentFlow.CreateAsync(failure);
        var first = await flow.LoginAsync(); var second = await flow.LoginAsync();
        await Assert.ThrowsAsync<AuthException>(() => flow.Runtime.EnrollAsync(first, CancellationToken.None));
        failure.FailEnrollment = false;
        var rejected = await Assert.ThrowsAsync<AuthException>(() => flow.Runtime.EnrollAsync(second, CancellationToken.None));
        Assert.Equal(AuthFailure.Conflict, rejected.Failure); Assert.Equal(1, failure.Attempts); Assert.Empty(flow.Provider.Factors);
    }
    [Fact]
    public async Task ASecondFactorAppearingConcurrentlyStopsChallengeWithoutMutation()
    {
        await using var flow = await EnrollmentFlow.CreateAsync(); var reference = await flow.LoginAsync();
        var enrollment = await flow.Runtime.EnrollAsync(reference, CancellationToken.None); flow.AddFactor(false);
        var error = await Assert.ThrowsAsync<AuthException>(() => flow.Runtime.ChallengeAsync(reference, enrollment.FactorId, CancellationToken.None));
        Assert.Equal(AuthFailure.Conflict, error.Failure); Assert.Equal(2, flow.Provider.Factors.Count); Assert.Empty(flow.Provider.VerifiedFactors);
    }

    [Fact]
    public async Task FactorAmbiguityObservedAfterVerifyStopsBeforeSqlIssuance()
    {
        await using var flow = await EnrollmentFlow.CreateAsync(); var factor = flow.AddFactor(true); var reference = await flow.LoginAsync();
        var challenge = await flow.Runtime.ChallengeAsync(reference, factor, CancellationToken.None);
        flow.Provider.VerifyEntered = new(TaskCreationOptions.RunContinuationsAsynchronously);
        flow.Provider.ReleaseVerify = new(TaskCreationOptions.RunContinuationsAsynchronously);
        var verification = flow.Runtime.VerifyAsync(reference, challenge.Id, "123456", CancellationToken.None);
        await flow.Provider.VerifyEntered.Task.WaitAsync(TimeSpan.FromSeconds(3));
        flow.AddFactor(false); flow.Provider.ReleaseVerify.TrySetResult();
        var error = await Assert.ThrowsAsync<AuthException>(() => verification);
        Assert.Equal(AuthFailure.Conflict, error.Failure); Assert.Equal(2, flow.Provider.Factors.Count);
    }

    private sealed class EnrollmentFailureHandler : DelegatingHandler
    {
        internal bool FailEnrollment { get; set; } = true;
        internal int Attempts { get; private set; }
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            if (request.Method == HttpMethod.Post && request.RequestUri?.AbsolutePath == "/auth/v1/factors")
            {
                Attempts++;
                if (FailEnrollment) return Task.FromResult(new HttpResponseMessage(System.Net.HttpStatusCode.ServiceUnavailable) { RequestMessage = request });
            }
            return base.SendAsync(request, cancellationToken);
        }
    }

    private sealed class EnrollmentFlow : IAsyncDisposable
    {
        private const string Email = "enrollment@fixture.invalid";
        internal SimulatedAuth Provider { get; } = new();
        internal Guid Subject { get; } = Guid.NewGuid();
        internal PilotRuntime Runtime { get; private set; } = null!;
        private ServiceProvider? transportServices;
        internal static async Task<EnrollmentFlow> CreateAsync(EnrollmentFailureHandler? failure = null)
        {
            var flow = new EnrollmentFlow(); await flow.Provider.StartAsync(); flow.Provider.Users[Email] = flow.Subject;
            // These tested paths must never open SQL. A nonexistent marked disposable target fails if they do.
            var target = new DisposableTarget("127.0.0.1", 29999, "m012_test_" + Guid.NewGuid().ToString("N"));
            var runtime = new SecurityDatabase(target, "unused_fixture_runtime", "PUBLIC_UNUSED_FIXTURE", DatabasePurpose.Runtime);
            var issuer = new SecurityDatabase(target, "unused_fixture_issuer", "PUBLIC_UNUSED_FIXTURE", DatabasePurpose.SessionIssuer);
            var services = flow.Provider.Services;
            if (failure is not null)
            {
                var registration = new ServiceCollection(); flow.Provider.Configure(registration);
                registration.AddHttpClient<AuthTransport>().AddHttpMessageHandler(() => failure);
                flow.transportServices = registration.BuildServiceProvider(); services = flow.transportServices;
            }
            flow.Runtime = new(runtime, issuer, services.GetRequiredService<JwtVerifier>(), services.GetRequiredService<SupabaseAuthClient>(), new TemporarySessions(flow.Provider.Clock), flow.Provider.Clock);
            return flow;
        }
        internal Guid AddFactor(bool verified)
        {
            var factor = Guid.NewGuid(); Provider.Factors[factor] = Subject;
            if (verified) Provider.VerifiedFactors[factor] = true;
            return factor;
        }
        internal async Task<SessionReference> LoginAsync() => (await Runtime.LoginAsync(Email, "fixture-password", CancellationToken.None)).Reference;
        public async ValueTask DisposeAsync()
        {
            if (transportServices is not null) await transportServices.DisposeAsync();
            await Provider.DisposeAsync(); GC.SuppressFinalize(this);
        }
    }
}
