using System.Text.Json;
using TradingAgent.Web.Security;
using Xunit;

namespace TradingAgent.Web.Tests;

public sealed class ContractTests
{
    [Fact]
    public void ExternalIdentityIsIssuerAndSubjectRatherThanEmailOrAuthority()
    {
        var subject = Guid.NewGuid();
        var identity = new ExternalIdentity(new Uri("https://identity.invalid/auth/v1"), subject);
        Assert.Equal(subject, identity.Subject);
        Assert.NotEqual(identity, new ExternalIdentity(new Uri("https://other.invalid/auth/v1"), subject));
        Assert.Throws<ArgumentException>(() => new ExternalIdentity(new Uri("http://identity.invalid"), subject));
        Assert.Throws<ArgumentException>(() => new ExternalIdentity(new Uri("https://user:password@identity.invalid"), subject));
        Assert.Throws<ArgumentException>(() => new ExternalIdentity(new Uri("https://identity.invalid?key=example"), subject));
        Assert.Throws<ArgumentException>(() => new ExternalIdentity(new Uri("https://identity.invalid/#fragment"), subject));
        Assert.Throws<ArgumentException>(() => new ExternalIdentity(new Uri("https://identity.invalid"), Guid.Empty));
    }

    [Fact]
    public void SessionViewCannotPresentAnActiveSessionOrExecutionPermission()
    {
        using var json = JsonDocument.Parse(JsonSerializer.Serialize(SessionView.Unavailable, JsonSerializerOptions.Web));
        Assert.Equal(1, json.RootElement.GetProperty("schemaVersion").GetInt32());
        Assert.Equal("UNAVAILABLE", json.RootElement.GetProperty("sessionState").GetString());
        Assert.Equal("OFFLINE", json.RootElement.GetProperty("mode").GetString());
        Assert.Equal("NO_TRADE", json.RootElement.GetProperty("decision").GetString());
        Assert.False(json.RootElement.GetProperty("executionAuthorized").GetBoolean());
        Assert.Empty(json.RootElement.GetProperty("capabilities").EnumerateArray());
        Assert.Empty(json.RootElement.GetProperty("accessibleEnvironments").EnumerateArray());
        Assert.Equal(JsonValueKind.Null, json.RootElement.GetProperty("userId").ValueKind);
        Assert.All(typeof(SessionView).GetProperties(), property => Assert.Null(property.SetMethod));
        Assert.Empty(typeof(SessionView).GetConstructors());
    }

    [Fact]
    public async Task UnconfiguredPortsNeverVerifyAnIdentityOrGrantAccess()
    {
        var ports = new UnconfiguredSecurity();
        var verification = await ports.VerifyAsync("untrusted-input".AsMemory(), CancellationToken.None);
        Assert.Equal(IdentityVerificationStatus.Unavailable, verification.Status);
        Assert.Null(verification.Identity);
        Assert.Same(SessionView.Unavailable, await ports.GetCurrentAsync(CancellationToken.None));
        Assert.Equal(AccessDecision.Denied,
            await ports.CheckAsync(Guid.NewGuid(), WebCapability.ResearchRead, Guid.NewGuid(), CancellationToken.None));
        Assert.Equal(AccessDecision.Denied,
            await ports.CheckAsync(Guid.Empty, (WebCapability)999, Guid.Empty, CancellationToken.None));
    }

    [Fact]
    public async Task PortsRespectCancellationInsteadOfContinuingWork()
    {
        var ports = new UnconfiguredSecurity();
        using var canceled = new CancellationTokenSource();
        await canceled.CancelAsync();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(
            async () => await ports.VerifyAsync(ReadOnlyMemory<char>.Empty, canceled.Token));
        await Assert.ThrowsAnyAsync<OperationCanceledException>(
            async () => await ports.GetCurrentAsync(canceled.Token));
        await Assert.ThrowsAnyAsync<OperationCanceledException>(
            async () => await ports.CheckAsync(Guid.Empty, WebCapability.ResearchRead, Guid.Empty, canceled.Token));
    }

    [Fact]
    public void ErrorsUseClosedCodesAndServerGeneratedCorrelationWithoutDetails()
    {
        var first = WebError.Create(WebErrorCode.ServiceUnavailable);
        var second = WebError.Create(WebErrorCode.ServiceUnavailable);
        Assert.NotEqual(first.CorrelationId, second.CorrelationId);
        Assert.NotEqual(Guid.Empty, first.CorrelationId);
        using var json = JsonDocument.Parse(JsonSerializer.Serialize(first, JsonSerializerOptions.Web));
        Assert.Equal("SERVICE_UNAVAILABLE", json.RootElement.GetProperty("code").GetString());
        Assert.Equal(2, json.RootElement.EnumerateObject().Count());
        Assert.Throws<ArgumentOutOfRangeException>(() => WebError.Create((WebErrorCode)999));
    }
}
