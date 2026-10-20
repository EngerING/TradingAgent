using System.Collections.Immutable;

namespace TradingAgent.Web.Security;

/// <summary>M01.1 exposes no authenticated state. Future session issuance needs a separately approved implementation.</summary>
public sealed class SessionView
{
    private SessionView() { }

    public static SessionView Unavailable { get; } = new();
    public int SchemaVersion => 1;
    public Guid? UserId => null;
    public string? DisplayName => null;
    public string SessionState => "UNAVAILABLE";
    public DateTimeOffset? ExpiresAt => null;
    public string AssuranceLevel => "NONE";
    public ImmutableArray<string> Capabilities => [];
    public string? RequestedEnvironment => null;
    public ImmutableArray<string> AccessibleEnvironments => [];
    public bool ExecutionAuthorized => false;
    public string Mode => "OFFLINE";
    public string Decision => "NO_TRADE";
}
