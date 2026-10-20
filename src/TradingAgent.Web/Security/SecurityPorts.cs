namespace TradingAgent.Web.Security;

public enum IdentityVerificationStatus { Unavailable }
public enum AccessDecision { Denied }
public enum WebCapability { ResearchRead }

public interface IExternalIdentityVerifier
{
    // No claim decoding, token retention or provider connection exists in M01.1.
    ValueTask<IdentityVerificationStatus> VerifyAsync(ReadOnlyMemory<char> credential, CancellationToken cancellationToken);
}

public interface IWebSessionReader
{
    ValueTask<SessionView> GetCurrentAsync(CancellationToken cancellationToken);
}

public interface IWebAuthorizer
{
    // Session/resource references must eventually be resolved by server-side stores, never trusted as grants.
    ValueTask<AccessDecision> CheckAsync(Guid sessionReference, WebCapability capability, Guid resourceReference,
        CancellationToken cancellationToken);
}

/// <summary>Explicitly unavailable ports; these are not a mock identity provider or a session store.</summary>
public sealed class UnconfiguredSecurity : IExternalIdentityVerifier, IWebSessionReader, IWebAuthorizer
{
    public ValueTask<IdentityVerificationStatus> VerifyAsync(ReadOnlyMemory<char> credential, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        return ValueTask.FromResult(IdentityVerificationStatus.Unavailable);
    }

    public ValueTask<SessionView> GetCurrentAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        return ValueTask.FromResult(SessionView.Unavailable);
    }

    public ValueTask<AccessDecision> CheckAsync(Guid sessionReference, WebCapability capability, Guid resourceReference,
        CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        return ValueTask.FromResult(AccessDecision.Denied);
    }
}
