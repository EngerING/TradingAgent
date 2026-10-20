using System.Text.Json;
using TradingAgent.Identity.Persistence;
using Xunit;

namespace TradingAgent.Identity.Tests;

public sealed class ContractTests
{
    [Theory]
    [InlineData("http://id.invalid/auth")]
    [InlineData("https://user:example@id.invalid/auth")]
    [InlineData("https://id.invalid/auth?x=1")]
    [InlineData("https://id.invalid/auth#x")]
    [InlineData("not-a-uri")]
    public void InvalidIssuersAreRejected(string issuer) =>
        Assert.Throws<ArgumentException>(() => new IdentityKey(issuer, Guid.NewGuid()));

    [Fact]
    public void SubjectsAndProofTimesMustBeValid()
    {
        Assert.Throws<ArgumentException>(() => new IdentityKey("https://id.invalid/auth", Guid.Empty));
        var key = new IdentityKey("https://id.invalid/auth", Guid.NewGuid());
        Assert.NotEqual(key, new IdentityKey("https://other.invalid/auth", key.Subject));
        Assert.Throws<ArgumentException>(() => new IdentityProof(key, Guid.Empty, 2, DateTimeOffset.UtcNow, DateTimeOffset.UtcNow.AddHours(1)));
        Assert.Throws<ArgumentException>(() => new IdentityProof(key, Guid.NewGuid(), 3, DateTimeOffset.UtcNow, DateTimeOffset.UtcNow.AddHours(1)));
    }

    [Fact]
    public void SessionReferencesAreRandomRedactedAndNotJsonSecrets()
    {
        var first = SessionReference.Generate(); var second = SessionReference.Generate();
        Assert.NotEqual(first.ExportForCookie(), second.ExportForCookie());
        Assert.Equal(43, first.ExportForCookie().Length);
        Assert.Equal(first.LookupHash(), SessionReference.Parse(first.ExportForCookie()).LookupHash());
        Assert.DoesNotContain(first.ExportForCookie(), first.ToString(), StringComparison.Ordinal);
        Assert.DoesNotContain(first.ExportForCookie(), JsonSerializer.Serialize(first), StringComparison.Ordinal);
        Assert.Throws<ArgumentException>(() => SessionReference.Parse("client-selected"));
        Assert.Throws<ArgumentException>(() => SessionReference.Parse(new string('=', 43)));
    }

    [Fact]
    public async Task UnconfiguredVerifierCannotIssueProof()
    {
        Assert.Null(await new UnavailableIdentityVerifier().VerifyAsync("invalid".AsMemory(), CancellationToken.None));
        using var cancel = new CancellationTokenSource(); await cancel.CancelAsync();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(async () =>
            await new UnavailableIdentityVerifier().VerifyAsync(ReadOnlyMemory<char>.Empty, cancel.Token));
    }

    [Theory]
    [InlineData("localhost", 44000, "m012_test_0123456789abcdef0123456789abcdef")]
    [InlineData("127.0.0.1", 5432, "m012_test_0123456789abcdef0123456789abcdef")]
    [InlineData("127.0.0.1", 44000, "postgres")]
    public void NonDisposableTargetsFailBeforeConnecting(string host, int port, string database) =>
        Assert.Throws<ArgumentException>(() => new DisposableTarget(host, port, database));

    [Fact]
    public void DecisionsCannotAuthorizeExecution()
    {
        var d = AuthorizationDecision.Denied();
        Assert.False(d.ExecutionAuthorized); Assert.Equal("OFFLINE", d.Mode); Assert.Equal("NO_TRADE", d.Decision);
        Assert.False(d.Allowed);
    }
}
