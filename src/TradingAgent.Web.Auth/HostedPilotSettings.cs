using TradingAgent.Identity.Supabase;

namespace TradingAgent.Web.Auth;

/// <summary>Explicit human-confirmed development target. No ambient configuration or production activation flag.</summary>
public sealed class HostedPilotSettings
{
    private HostedPilotSettings(AuthConfiguration authentication, Uri browserOrigin)
    { Authentication = authentication; BrowserOrigin = browserOrigin; }
    public AuthConfiguration Authentication { get; }
    public Uri BrowserOrigin { get; }
    public static HostedPilotSettings FromExternalValues(string environment, string confirmedDevelopmentReference, Uri project, string publishableKey, Uri browserOrigin)
    {
        ArgumentNullException.ThrowIfNull(project); ArgumentNullException.ThrowIfNull(browserOrigin);
        if (environment != "Development" || confirmedDevelopmentReference is null ||
            !System.Text.RegularExpressions.Regex.IsMatch(confirmedDevelopmentReference, "\\A[a-z0-9]{20}\\z", System.Text.RegularExpressions.RegexOptions.CultureInvariant) ||
            project.Host != confirmedDevelopmentReference + ".supabase.co") throw new ArgumentException("Exact development project confirmation required.");
        if (!browserOrigin.IsAbsoluteUri || browserOrigin.Scheme != "https" || browserOrigin.Host != "127.0.0.1" ||
            browserOrigin.Port < 20000 || browserOrigin.Port > 65535 || browserOrigin.UserInfo.Length != 0 || browserOrigin.AbsolutePath != "/" ||
            browserOrigin.Query.Length != 0 || browserOrigin.Fragment.Length != 0) throw new ArgumentException("Explicit loopback HTTPS development origin required.");
        return new(AuthConfiguration.ForProject(project, publishableKey), browserOrigin);
    }
    public override string ToString() => "[EXPLICIT_DEVELOPMENT_PILOT_SETTINGS]";
}
