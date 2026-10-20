namespace TradingAgent.Web.Security;

/// <summary>A provider identity reference, never evidence of verification or application permissions.</summary>
public sealed record ExternalIdentity
{
    public ExternalIdentity(Uri issuer, Guid subject)
    {
        ArgumentNullException.ThrowIfNull(issuer);
        if (!issuer.IsAbsoluteUri || issuer.Scheme != Uri.UriSchemeHttps ||
            issuer.UserInfo.Length != 0 || issuer.Query.Length != 0 || issuer.Fragment.Length != 0)
        {
            throw new ArgumentException("An absolute HTTPS issuer without credentials, query or fragment is required.", nameof(issuer));
        }

        if (subject == Guid.Empty)
        {
            throw new ArgumentException("A nonempty subject is required.", nameof(subject));
        }

        Issuer = issuer;
        Subject = subject;
    }

    public Uri Issuer { get; }
    public Guid Subject { get; }
}
