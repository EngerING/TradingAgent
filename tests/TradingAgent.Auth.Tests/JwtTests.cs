using Microsoft.Extensions.DependencyInjection;
using TradingAgent.Identity.Supabase;
using Xunit;

namespace TradingAgent.Auth.Tests;

public sealed class JwtTests
{
    [Theory]
    [InlineData("expired")] [InlineData("issuer")] [InlineData("audience")] [InlineData("service")] [InlineData("anonymous")]
    [InlineData("subject")] [InlineData("session")] [InlineData("future")] [InlineData("nbf")] [InlineData("aal")] [InlineData("none")]
    public async Task InvalidJwtIsDenied(string variant)
    {
        await using var provider = new SimulatedAuth(); await provider.StartAsync();
        await Assert.ThrowsAsync<AuthException>(() => provider.Services.GetRequiredService<JwtVerifier>().ValidateAsync(provider.Token(Guid.NewGuid(), Guid.NewGuid(), variant: variant), CancellationToken.None));
    }
    [Fact]
    public async Task ValidJwtAndSignedMfaTimestampProduceBoundProof()
    {
        await using var provider = new SimulatedAuth(); await provider.StartAsync(); var user = Guid.NewGuid(); var session = Guid.NewGuid();
        var proof = await provider.Services.GetRequiredService<JwtVerifier>().VerifyAsync(provider.Token(user, session).AsMemory(), CancellationToken.None);
        Assert.NotNull(proof); Assert.Equal(user, proof.Identity.Subject); Assert.Equal(session, proof.ProviderSessionId); Assert.Equal(2, proof.AssuranceLevel);
    }
    [Fact]
    public async Task AalOneAndMissingMfaEvidenceCannotIssueSession()
    {
        await using var provider = new SimulatedAuth(); await provider.StartAsync(); var verifier = provider.Services.GetRequiredService<JwtVerifier>();
        Assert.Null(await verifier.VerifyAsync(provider.Token(Guid.NewGuid(), Guid.NewGuid(), 1).AsMemory(), CancellationToken.None));
        Assert.Null(await verifier.VerifyAsync(provider.Token(Guid.NewGuid(), Guid.NewGuid(), variant: "nomfa").AsMemory(), CancellationToken.None));
    }
    [Fact]
    public async Task RotationIsCoordinatedAndRandomKidsCannotForceUnboundedDownloads()
    {
        await using var provider = new SimulatedAuth(); await provider.StartAsync(); var verifier = provider.Services.GetRequiredService<JwtVerifier>();
        await verifier.ValidateAsync(provider.Token(Guid.NewGuid(), Guid.NewGuid()), CancellationToken.None);
        for (var i = 0; i < 20; i++) await Assert.ThrowsAsync<AuthException>(() => verifier.ValidateAsync(provider.Token(Guid.NewGuid(), Guid.NewGuid(), variant: "unknownkid"), CancellationToken.None));
        Assert.Equal(1, provider.JwksRequests);
        provider.Rotated = true; provider.Clock.Advance(TimeSpan.FromSeconds(31));
        await Task.WhenAll(Enumerable.Range(0, 8).Select(_ => verifier.ValidateAsync(provider.Token(Guid.NewGuid(), Guid.NewGuid()), CancellationToken.None)));
        Assert.Equal(2, provider.JwksRequests);
    }
    [Fact]
    public async Task MissingOrStaleJwksFailsClosedAndSignatureTamperingFails()
    {
        await using var provider = new SimulatedAuth(); await provider.StartAsync(); var verifier = provider.Services.GetRequiredService<JwtVerifier>();
        var token = provider.Token(Guid.NewGuid(), Guid.NewGuid());
        var broken = token[..^5] + "AAAAA"; await Assert.ThrowsAsync<AuthException>(() => verifier.ValidateAsync(broken, CancellationToken.None));
        provider.Unavailable = true; provider.Clock.Advance(TimeSpan.FromMinutes(11));
        await Assert.ThrowsAsync<AuthException>(() => verifier.ValidateAsync(provider.Token(Guid.NewGuid(), Guid.NewGuid()), CancellationToken.None));
    }
}
