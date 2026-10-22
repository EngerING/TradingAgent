using System.Net;
using System.Security.Cryptography.X509Certificates;
using TradingAgent.Identity.Persistence;
using TradingAgent.Web.Auth;
using TradingAgent.Web.Browser;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;

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
        var encodedSan = certificate.Extensions["2.5.29.17"];
        if (encodedSan is null) throw new InvalidOperationException("Loopback IP SAN is required.");
        var san = new X509SubjectAlternativeNameExtension();
        san.CopyFrom(encodedSan);
        if (!certificate.HasPrivateKey || !san.EnumerateIPAddresses().Contains(IPAddress.Loopback) ||
            DateTime.UtcNow < certificate.NotBefore.ToUniversalTime() ||
            DateTime.UtcNow >= certificate.NotAfter.ToUniversalTime())
            throw new InvalidOperationException("Trusted, current loopback HTTPS certificate required.");
        using (var chain = new X509Chain())
        {
            // Local development authorities commonly have no OCSP. Chain and name
            // trust remain mandatory; no custom root or accept-all callback.
            chain.ChainPolicy.RevocationMode = X509RevocationMode.NoCheck;
            chain.ChainPolicy.ApplicationPolicy.Add(new System.Security.Cryptography.Oid("1.3.6.1.5.5.7.3.1"));
            if (certificate.Extensions.OfType<X509EnhancedKeyUsageExtension>().SingleOrDefault()?.EnhancedKeyUsages.Cast<System.Security.Cryptography.Oid>().Any(o => o.Value == "1.3.6.1.5.5.7.3.1") != true)
                throw new InvalidOperationException("Explicit serverAuth certificate required.");
            if (!chain.Build(certificate))
                throw new InvalidOperationException("Loopback certificate must chain to an already-trusted development CA.");
        }

        var reactRoot = Path.GetFullPath(Required("M014B_B2_REACT_DIST"));
        await using var app = BrowserHost.CreateHosted(settings, runtime, issuer, certificate, reactRoot);
        var loginAttempts = 0;
        app.Use(async (context, next) =>
        {
            if (context.Request.Path == "/bff/auth/login" && HttpMethods.IsPost(context.Request.Method) && Interlocked.Increment(ref loginAttempts) != 1)
            {
                context.Response.StatusCode = 409;
                await context.Response.WriteAsJsonAsync(new { code = "LOCAL_PILOT_ATTEMPT_CONSUMED", correlationId = Guid.NewGuid(), executionAuthorized = false });
                return;
            }
            await next(context);
        });
        if (Environment.GetEnvironmentVariable("M014B_B2_DIAGNOSTIC_FILE") is { } diagnosticFile)
            app.Services.GetRequiredService<ILoggerFactory>().AddProvider(new LocalPilotDiagnostic(diagnosticFile));
        using var stop = new CancellationTokenSource(TimeSpan.FromMinutes(20));
        Console.CancelKeyPress += (_, args) => { args.Cancel = true; stop.Cancel(); };
        await app.StartAsync(stop.Token);
        Console.WriteLine("B2_HOSTED_BROWSER_READY; development only; OFFLINE / NO_TRADE.");
        try {
            var stopFile = Environment.GetEnvironmentVariable("M014B_B2_STOP_FILE");
            while (!stop.IsCancellationRequested)
            {
                if (stopFile is not null && File.Exists(stopFile)) { stop.Cancel(); break; }
                await Task.Delay(500, stop.Token);
            }
        }
        catch (OperationCanceledException) when (stop.IsCancellationRequested) { }
        finally { await app.StopAsync(); }
    }
}
