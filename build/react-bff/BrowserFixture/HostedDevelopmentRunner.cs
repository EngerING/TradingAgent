using System.Net;
using System.Security.Cryptography.X509Certificates;
using System.Security.Cryptography;
using System.Text.Json;
using TradingAgent.Identity.Tests;
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
    internal static async Task RunAsync(bool localChecksOnly = false)
    {
        using var observer = localChecksOnly ? new ConnectionObserver() : null;
        static string Required(string key)
        {
            var value = Environment.GetEnvironmentVariable(key);
            return string.IsNullOrWhiteSpace(value)
                ? throw new InvalidOperationException("Required B2 development configuration missing.")
                : value;
        }

        if (Required("M014B_B2_INTERACTIVE_APPROVAL") != (localChecksOnly ? "LOCAL_STARTUP_CHECKS_ONLY" : "APPROVED_HOSTED_AUTH_DEV_NO_TRADE"))
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
            chain.ChainPolicy.ApplicationPolicy.Add(new Oid("1.3.6.1.5.5.7.3.1"));
            if (certificate.Extensions.OfType<X509EnhancedKeyUsageExtension>().SingleOrDefault()?.EnhancedKeyUsages.Cast<Oid>().Any(o => o.Value == "1.3.6.1.5.5.7.3.1") != true)
                throw new InvalidOperationException("TLS_SERVER_AUTH_REQUIRED");
            if (!chain.Build(certificate))
                throw new InvalidOperationException("Loopback certificate must chain to an already-trusted development CA.");
        }

        var reactRoot = Path.GetFullPath(Required("M014B_B2_REACT_DIST"));
        await using var app = BrowserHost.CreateHosted(settings, runtime, issuer, certificate, reactRoot, localChecksOnly);
        // Hosted login is separately approved and single-attempt. Diagnostic output is closed/redacted.
        // Local-checks mode skips all auth paths and never installs this login middleware.
        if (!localChecksOnly)
        {
            var loginAttempts = 0;
            app.Use(async (context, next) =>
            {
                if (context.Request.Path == "/bff/auth/login" && HttpMethods.IsPost(context.Request.Method) &&
                    Interlocked.Increment(ref loginAttempts) != 1)
                {
                    context.Response.StatusCode = 409;
                    await context.Response.WriteAsJsonAsync(new { code = "LOCAL_PILOT_ATTEMPT_CONSUMED", correlationId = Guid.NewGuid(), executionAuthorized = false });
                    return;
                }
                await next(context);
            });
            if (Environment.GetEnvironmentVariable("M014B_B2_DIAGNOSTIC_FILE") is { } diagnosticFile)
                app.Services.GetRequiredService<ILoggerFactory>().AddProvider(new LocalPilotDiagnostic(diagnosticFile));
        }
        // Local-only diagnostic server stays active until an owned Stop signal.
        // The separately approved hosted login runner has a 20-minute safety deadline.
        using var stop = localChecksOnly ? new CancellationTokenSource() : new CancellationTokenSource(TimeSpan.FromMinutes(20));
        Console.CancelKeyPress += (_, args) => { args.Cancel = true; stop.Cancel(); };
        await app.StartAsync(stop.Token);
        var stateFile = localChecksOnly ? Required("M014B_B2_STATE_FILE") : null;
        using var process = System.Diagnostics.Process.GetCurrentProcess();
        var expectedSqlAddress = new IPEndPoint(IPAddress.Loopback, port).Serialize().ToString();
        async Task StateAsync(string state) {
            if (stateFile is not null) {
                var unexpectedConnections = observer!.Addresses.Count(a => a != expectedSqlAddress);
                var temporary = stateFile + ".tmp";
                await File.WriteAllTextAsync(temporary, JsonSerializer.Serialize(new { pid = Environment.ProcessId, startedAtUtc = process.StartTime.ToUniversalTime(), state, localChecksOnly, unexpectedConnections, sqlConnectionAttempts = observer.Addresses.Count, origin = settings.BrowserOrigin.AbsoluteUri, mode = "OFFLINE", decision = "NO_TRADE" }));
                File.Move(temporary, stateFile, overwrite: true);
                if (unexpectedConnections != 0) throw new InvalidOperationException("LOCAL_NETWORK_BOUNDARY_REJECTED");
            }
        }
        await StateAsync("READY");
        Console.WriteLine($"URL={settings.BrowserOrigin.AbsoluteUri} PID={Environment.ProcessId} STATE=READY {(localChecksOnly ? "LOGIN_DISABLED" : "HOSTED_DEVELOPMENT")} OFFLINE / NO_TRADE");
        try {
            var stopFile = localChecksOnly ? Required("M014B_B2_STOP_FILE") : Environment.GetEnvironmentVariable("M014B_B2_STOP_FILE");
            while (!stop.IsCancellationRequested) {
                if (stopFile is not null && File.Exists(stopFile)) { stop.Cancel(); break; }
                await Task.Delay(500, stop.Token);
            }
        }
        catch (OperationCanceledException) when (stop.IsCancellationRequested) { }
        finally { await app.StopAsync(); await StateAsync("STOPPED"); Console.WriteLine("STATE=STOPPED; LOCAL_RESOURCES_RELEASED"); }
    }
}
