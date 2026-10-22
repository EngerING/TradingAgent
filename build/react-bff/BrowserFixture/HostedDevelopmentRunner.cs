using System.Net;
using System.Security.Cryptography.X509Certificates;
using TradingAgent.Identity.Persistence;
using TradingAgent.Web.Auth;
using TradingAgent.Web.Browser;

namespace TradingAgent.React.BrowserFixture;

/// <summary>
/// Manual B2 hosted browser entrypoint. Does not create users, MFA factors, roles,
/// grants, SQL migrations, tokens, or privileged database accounts.
/// </summary>
internal static class HostedDevelopmentRunner
{
    internal static async Task RunAsync()
    {
        static string Required(string key)
        {
            var value = Environment.GetEnvironmentVariable(key);
            return string.IsNullOrWhiteSpace(value)
                ? throw new InvalidOperationException("Required B2 development configuration missing.")
                : value;
        }

        if (Required("M014B_B2_INTERACTIVE_APPROVAL") != "APPROVED_HOSTED_AUTH_DEV_NO_TRADE")
            throw new InvalidOperationException("Hosted authentication requires explicit local approval.");
        if (Required("M014B_B2_PROJECT_REF") != "ocwabwmzhpedyxlkjpje")
            throw new InvalidOperationException("Only the confirmed Supabase Auth Dev project is allowed.");
        var settings = HostedPilotSettings.FromExternalValues(
            "Development", Required("M014B_B2_PROJECT_REF"),
            new Uri(Required("M014B_B2_PROJECT_URL"), UriKind.Absolute),
            Required("M014B_B2_PUBLISHABLE_KEY"),
            new Uri(Required("M014B_B2_ORIGIN"), UriKind.Absolute));

        // DisposableTarget and SecurityDatabase independently verify the target marker,
        // migration ledger, exact role memberships and the absence of non-security grants.
        var port = int.Parse(Required("M014B_B2_SQL_PORT"), System.Globalization.CultureInfo.InvariantCulture);
        var target = new DisposableTarget("127.0.0.1", port, Required("M014B_B2_SQL_DATABASE"));
        var runtime = new SecurityDatabase(target,
            Required("M014B_B2_RUNTIME_USER"), Required("M014B_B2_RUNTIME_PASSWORD"), DatabasePurpose.Runtime);
        var issuer = new SecurityDatabase(target,
            Required("M014B_B2_ISSUER_USER"), Required("M014B_B2_ISSUER_PASSWORD"), DatabasePurpose.SessionIssuer);
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(20));
        await using (var connection = await runtime.OpenAsync(deadline.Token)) { }
        await using (var connection = await issuer.OpenAsync(deadline.Token)) { }

        // PFX is supplied outside Git and must already be trusted by the OS/browser.
        // The launcher never installs a trust root or disables certificate checking.
        var flags = OperatingSystem.IsWindows() ? X509KeyStorageFlags.DefaultKeySet : X509KeyStorageFlags.EphemeralKeySet;
        using var certificate = X509CertificateLoader.LoadPkcs12FromFile(
            Required("M014B_B2_TLS_PFX"), Required("M014B_B2_TLS_PASSWORD"), flags);
        var ips = certificate.Extensions.OfType<X509SubjectAlternativeNameExtension>()
            .SelectMany(extension => extension.EnumerateIPAddresses());
        if (!certificate.HasPrivateKey || !ips.Contains(IPAddress.Loopback) ||
            DateTime.UtcNow < certificate.NotBefore.ToUniversalTime() ||
            DateTime.UtcNow >= certificate.NotAfter.ToUniversalTime())
            throw new InvalidOperationException("Trusted, current loopback HTTPS certificate required.");
        using (var chain = new X509Chain())
        {
            // Local development authorities commonly have no OCSP. Chain and name
            // trust remain mandatory; no custom root or accept-all callback.
            chain.ChainPolicy.RevocationMode = X509RevocationMode.NoCheck;
            if (!chain.Build(certificate))
                throw new InvalidOperationException("Loopback certificate must chain to an already-trusted development CA.");
        }

        var reactRoot = Path.GetFullPath(Required("M014B_B2_REACT_DIST"));
        await using var app = BrowserHost.CreateHosted(settings, runtime, issuer, certificate, reactRoot);
        using var stop = new CancellationTokenSource();
        Console.CancelKeyPress += (_, args) => { args.Cancel = true; stop.Cancel(); };
        await app.StartAsync(stop.Token);
        Console.WriteLine("B2_HOSTED_BROWSER_READY; development only; OFFLINE / NO_TRADE.");
        try { await Task.Delay(Timeout.InfiniteTimeSpan, stop.Token); }
        catch (OperationCanceledException) when (stop.IsCancellationRequested) { }
        finally { await app.StopAsync(); }
    }
}
