namespace TradingAgent.Identity.Supabase;

public sealed class AuthConfiguration
{
    private AuthConfiguration(Uri project, string publicKey, bool simulation)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(publicKey);
        if (!publicKey.StartsWith("sb_publishable_", StringComparison.Ordinal) || publicKey.Length > 256) throw new ArgumentException("Publishable application key required.", nameof(publicKey));
        Project = project; PublicKey = publicKey; Simulation = simulation;
        Issuer = simulation ? "https://synthetic.supabase.invalid/auth/v1" : new Uri(project, "/auth/v1").AbsoluteUri;
        Jwks = new Uri(project, "/auth/v1/.well-known/jwks.json");
    }
    public Uri Project { get; }
    public string Issuer { get; }
    public Uri Jwks { get; }
    public string PublicKey { get; }
    public bool Simulation { get; }
    public static AuthConfiguration ForProject(Uri project, string publicKey)
    {
        ArgumentNullException.ThrowIfNull(project);
        if (!project.IsAbsoluteUri || project.Scheme != "https" || !project.IsDefaultPort || project.UserInfo.Length != 0 || project.Query.Length != 0 || project.Fragment.Length != 0 || project.AbsolutePath != "/" ||
            !System.Text.RegularExpressions.Regex.IsMatch(project.Host, "\\A[a-z0-9-]+\\.supabase\\.co\\z", System.Text.RegularExpressions.RegexOptions.CultureInvariant)) throw new ArgumentException("Untrusted project origin.", nameof(project));
        return new(project, publicKey, false);
    }
    public static AuthConfiguration ForSimulation(Uri project)
    {
        ArgumentNullException.ThrowIfNull(project);
        if (!project.IsAbsoluteUri || project.Scheme != "http" || project.Host != "127.0.0.1" || project.UserInfo.Length != 0 || project.AbsolutePath != "/" || project.Query.Length != 0 || project.Fragment.Length != 0) throw new ArgumentException("Loopback fixture required.", nameof(project));
        return new(project, "sb_publishable_syntheticfixture", true);
    }
}

public enum AuthFailure { Invalid, Unavailable, RateLimited, Conflict }
// Closed internal categories only. Never attach claim values or library exception text.
public enum AuthDiagnostic
{
    Unspecified, ResponseTooLarge, UnexpectedContentType, InvalidJson, DeadlineExceeded, TransportUnavailable, EnrollmentContractInvalid,
    JwtStructureInvalid, JwtHeaderInvalid, JwtAlgorithmInvalid, JwtTypeInvalid, JwtRemoteKeyHintRejected, JwtKeyIdInvalid,
    JwksProfileInvalid, JwksKeyNotFound, JwksUnavailable, JwksResponseRejected,
    JwtValidationFailed, JwtSignatureInvalid, JwtIssuerInvalid, JwtAudienceInvalid,
    JwtExpirationMissing, JwtExpired, JwtNotYetValid, JwtLifetimeInvalid,
    JwtPayloadInvalid, JwtSubjectInvalid, JwtSessionInvalid, JwtIssuedAtInvalid, JwtExpirationInvalid,
    JwtAalInvalid, JwtRoleInvalid, JwtAnonymousRejected, JwtRefRejected, JwtIssuedAtFuture, JwtLifetimeTooLong,
    JwtAmrInvalid, JwtAmrTimestampInvalid, JwtAmrMethodInvalid
}
public sealed class AuthException(AuthFailure failure, AuthDiagnostic diagnostic = AuthDiagnostic.Unspecified) : Exception("AUTH_REQUEST_REJECTED")
{
    public AuthFailure Failure { get; } = failure;
    public AuthDiagnostic Diagnostic { get; } = diagnostic;
}
