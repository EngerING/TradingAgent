using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;

namespace TradingAgent.Identity.Persistence;

public enum PlatformRole { Viewer, Researcher, Operator, Administrator }
public enum ResourceKind { Account, Study, Experiment, Strategy, Platform }
public enum EnvironmentScope { Paper, Live }
public enum Capability { Read, ManageResearch, Supervise, ManageSecurity }
public enum UserStatus { Invited, Active, Disabled }
public enum StoreOutcome { Success, Denied, Conflict, Unavailable }
public enum DatabasePurpose { Runtime, SessionIssuer, Administration, Reader, Migration }

public sealed record IdentityKey
{
    public IdentityKey(string issuer, Guid subject)
    {
        if (issuer is null || issuer.Length > 2048 || !Uri.TryCreate(issuer, UriKind.Absolute, out var uri) ||
            uri.Scheme != Uri.UriSchemeHttps || uri.UserInfo.Length != 0 || uri.Query.Length != 0 || uri.Fragment.Length != 0 ||
            issuer.Any(char.IsWhiteSpace) || subject == Guid.Empty)
            throw new ArgumentException("Invalid external identity.");
        Issuer = issuer; Subject = subject;
    }
    public string Issuer { get; }
    public Guid Subject { get; }
}

/// <summary>Only a trusted verifier implementation may attest these fields; constructing a DTO confers no access.</summary>
public sealed record IdentityProof
{
    public IdentityProof(IdentityKey identity, Guid providerSessionId, int assuranceLevel, DateTimeOffset verifiedAt, DateTimeOffset expiresAt)
    {
        ArgumentNullException.ThrowIfNull(identity);
        if (providerSessionId == Guid.Empty || assuranceLevel is not (1 or 2) || verifiedAt.Offset != TimeSpan.Zero ||
            expiresAt.Offset != TimeSpan.Zero || expiresAt <= verifiedAt)
            throw new ArgumentException("Invalid identity proof.");
        Identity = identity; ProviderSessionId = providerSessionId; AssuranceLevel = assuranceLevel;
        VerifiedAt = verifiedAt; ExpiresAt = expiresAt;
    }
    public IdentityKey Identity { get; }
    public Guid ProviderSessionId { get; }
    public int AssuranceLevel { get; }
    public DateTimeOffset VerifiedAt { get; }
    public DateTimeOffset ExpiresAt { get; }
}

public interface IIdentityEvidenceVerifier
{
    ValueTask<IdentityProof?> VerifyAsync(ReadOnlyMemory<char> evidence, CancellationToken cancellationToken);
}
public sealed class UnavailableIdentityVerifier : IIdentityEvidenceVerifier
{
    public ValueTask<IdentityProof?> VerifyAsync(ReadOnlyMemory<char> evidence, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested(); return ValueTask.FromResult<IdentityProof?>(null);
    }
}

public sealed partial class SessionReference
{
    private readonly string encoded;
    private SessionReference(string value) => encoded = value;
    public static SessionReference Generate() => new(Convert.ToBase64String(RandomNumberGenerator.GetBytes(32)).TrimEnd('=').Replace('+', '-').Replace('/', '_'));
    public static SessionReference Parse(string value)
    {
        if (value is null || !ReferencePattern().IsMatch(value)) throw new ArgumentException("Invalid session reference.", nameof(value));
        var bytes = Convert.FromBase64String(value.Replace('-', '+').Replace('_', '/') + "=");
        if (Convert.ToBase64String(bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_') != value)
            throw new ArgumentException("Noncanonical session reference.", nameof(value));
        return new(value);
    }
    public string ExportForCookie() => encoded;
    public byte[] LookupHash() => SHA256.HashData(Encoding.ASCII.GetBytes("TradingAgent.M012.session.v1:" + encoded));
    public override string ToString() => "[REDACTED_SESSION_REFERENCE]";
    [GeneratedRegex("\\A[A-Za-z0-9_-]{43}\\z", RegexOptions.CultureInvariant)] private static partial Regex ReferencePattern();
}

public sealed partial record DisposableTarget
{
    public DisposableTarget(string host, int port, string database)
    {
        if (host != "127.0.0.1" || port is < 20000 or > 65535 or 55433 or 55434 ||
            database is null || !NamePattern().IsMatch(database))
            throw new ArgumentException("Only an explicitly marked disposable PostgreSQL target is supported.");
        Host = host; Port = port; Database = database;
    }
    public string Host { get; }
    public int Port { get; }
    public string Database { get; }
    public string Marker => "TradingAgent.M012.DISPOSABLE:" + Database;
    [GeneratedRegex("\\Am012_test_[a-f0-9]{32}\\z", RegexOptions.CultureInvariant)] private static partial Regex NamePattern();
}

public sealed record AuthorizationDecision(bool Allowed, StoreOutcome Outcome, DateTimeOffset? AsOf = null)
{
    public bool ExecutionAuthorized { get; }
    public string Mode { get; } = "OFFLINE";
    public string Decision { get; } = "NO_TRADE";
    public static AuthorizationDecision Denied() => new(false, StoreOutcome.Denied);
}
public sealed record UserView(Guid Id, IdentityKey Identity, UserStatus Status, long AuthorizationVersion);
public sealed record SessionView(Guid AuditReference, Guid UserId, long RowVersion, DateTimeOffset ExpiresAt, DateTimeOffset IdleUntil);
public sealed record SessionCreation(StoreOutcome Outcome, SessionReference? Reference = null, SessionView? Session = null);
public sealed record MutationResult(StoreOutcome Outcome, Guid? Id = null);
public sealed record SecurityAuditEvent(Guid EventId, string Action, string Outcome, DateTimeOffset OccurredAt, Guid CorrelationId, int PolicyVersion, Guid? SessionAuditId);
public sealed record AuditPage(StoreOutcome Outcome, IReadOnlyList<SecurityAuditEvent> Events);
public interface ISecurityAuditReader
{
    Task<AuditPage> ReadAsync(SessionReference actor, int limit, CancellationToken cancellationToken);
}

public interface IUserReader { Task<UserView?> FindSelfAsync(SessionReference session, CancellationToken cancellationToken); }
public interface IResourceAuthorizer
{
    Task<AuthorizationDecision> AuthorizeAsync(SessionReference session, ResourceKind kind, Guid resourceId, EnvironmentScope environment,
        Capability capability, CancellationToken cancellationToken);
}
public interface ISessionIssuer { Task<SessionCreation> CreateAsync(ReadOnlyMemory<char> evidence, CancellationToken cancellationToken); }
public interface ISessionOperations
{
    Task<MutationResult> TouchAsync(SessionReference session, long rowVersion, CancellationToken cancellationToken);
    Task<MutationResult> RevokeAsync(SessionReference session, CancellationToken cancellationToken);
}
public interface IIdentityAdministration
{
    Task<MutationResult> RegisterAsync(SessionReference actor, IdentityKey identity, string? contactEmail, CancellationToken cancellationToken);
    Task<MutationResult> ChangeStatusAsync(SessionReference actor, Guid user, UserStatus status, CancellationToken cancellationToken);
    Task<MutationResult> GrantRoleAsync(SessionReference actor, Guid user, PlatformRole role, DateTimeOffset expiresAt, CancellationToken cancellationToken);
    Task<MutationResult> GrantResourceAsync(SessionReference actor, Guid user, ResourceKind kind, Guid resourceId, EnvironmentScope environment,
        Capability capability, DateTimeOffset expiresAt, CancellationToken cancellationToken);
    Task<MutationResult> RevokeRoleAsync(SessionReference actor, Guid grantId, CancellationToken cancellationToken);
    Task<MutationResult> RevokeResourceAsync(SessionReference actor, Guid grantId, CancellationToken cancellationToken);
}
