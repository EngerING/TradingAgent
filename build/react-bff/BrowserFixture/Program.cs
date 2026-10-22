using System.Net;
using System.Net.Sockets;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using TradingAgent.Identity.Persistence;
using TradingAgent.Identity.Tests;
using TradingAgent.React.BrowserFixture;
using TradingAgent.Web.Browser;

if (args.Length == 1 && args[0] == "--hosted-local-checks")
{
    try { await HostedDevelopmentRunner.RunAsync(localChecksOnly: true); }
    catch (Exception) { Console.WriteLine("LOCAL_STARTUP_PREFLIGHT_FAILED; NO_SENSITIVE_DETAILS"); Environment.ExitCode = 1; }
    return;
}
if (args.Length == 1 && args[0] == "--hosted-development")
{
    // Isolated B2 entrypoint: no fixture Auth, grants, migrations, synthetic tokens or SQL bootstrap.
    await HostedDevelopmentRunner.RunAsync();
    return;
}
if (Environment.GetEnvironmentVariable("M014B_SYNTHETIC_BROWSER_FIXTURE") != "YES") throw new InvalidOperationException("Explicit synthetic fixture opt-in required.");
var root = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "../../../../../.."));
// Runtime argument is the repository root; validated marker prevents using an arbitrary assets path.
root = Path.GetFullPath(args.Single());
if (!File.Exists(Path.Combine(root, "build/react-bff/BrowserFixture/BrowserFixture.csproj"))) throw new InvalidOperationException("Fixture repository required.");
var ready = Path.Combine(root, "tmp/m014b/browser"); Directory.CreateDirectory(ready);
static int Port() { var listener = new TcpListener(IPAddress.Loopback, 0); listener.Start(); var port = ((IPEndPoint)listener.LocalEndpoint).Port; listener.Stop(); return port; }
var authPort = Port(); var webPort = Port(); var origin = new Uri($"https://localhost:{webPort}");
using var caKey = RSA.Create(3072);
var now = DateTimeOffset.UtcNow;
var caRequest = new CertificateRequest("CN=TradingAgent ephemeral synthetic CI root", caKey, HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1);
caRequest.CertificateExtensions.Add(new X509BasicConstraintsExtension(true, false, 0, true));
caRequest.CertificateExtensions.Add(new X509KeyUsageExtension(X509KeyUsageFlags.KeyCertSign, true));
using var ca = caRequest.CreateSelfSigned(now.AddMinutes(-1), now.AddHours(1));
using var leafKey = RSA.Create(3072);
var request = new CertificateRequest("CN=localhost", leafKey, HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1);
request.CertificateExtensions.Add(new X509BasicConstraintsExtension(false, false, 0, true));
request.CertificateExtensions.Add(new X509KeyUsageExtension(X509KeyUsageFlags.DigitalSignature | X509KeyUsageFlags.KeyEncipherment, true));
request.CertificateExtensions.Add(new X509EnhancedKeyUsageExtension(new OidCollection { new("1.3.6.1.5.5.7.3.1") }, true));
var san = new SubjectAlternativeNameBuilder(); san.AddDnsName("localhost"); san.AddIpAddress(IPAddress.Loopback); request.CertificateExtensions.Add(san.Build());
using var issued = request.Create(ca, now.AddMinutes(-1), now.AddMinutes(45), RandomNumberGenerator.GetBytes(16));
using var issuedWithKey = issued.CopyWithPrivateKey(leafKey);
static X509Certificate2 TlsCertificate(X509Certificate2 source)
{
    if (!OperatingSystem.IsWindows()) return new X509Certificate2(source);
    // Schannel needs a temporary platform key container, removed when the imported certificate is disposed.
    // No trust-store mutation or exported private-key file; the PFX buffer is wiped after import.
    var bytes = source.Export(X509ContentType.Pkcs12);
    try { return X509CertificateLoader.LoadPkcs12(bytes, null, X509KeyStorageFlags.DefaultKeySet); }
    finally { CryptographicOperations.ZeroMemory(bytes); }
}
using var certificate = TlsCertificate(issuedWithKey);
await File.WriteAllTextAsync(Path.Combine(ready, "root.crt"), ca.ExportCertificatePem()); // Public root only. Private keys stay in memory.
using var database = new BrowserDatabaseFixture(); await database.InitializeAsync();
await using var provider = new HttpAuthFixture(authPort);
database.AdditionalAllowedAddresses.Add(new IPEndPoint(IPAddress.Loopback, authPort).Serialize().ToString()!);
database.AdditionalAllowedAddresses.Add(new IPEndPoint(IPAddress.Loopback.MapToIPv6(), authPort).Serialize().ToString()!);
var admin = (await database.AdministratorAsync()).Session;
var resource = Guid.NewGuid();
var users = new Dictionary<string, Guid>(StringComparer.Ordinal);
foreach (var name in new[] { "viewer", "enroll", "orphan", "ambiguous", "no-role", "no-grant", "disabled", "other" })
{
    var subject = Guid.NewGuid(); provider.Users[name + "@fixture.invalid"] = subject;
    var created = await database.Administration().RegisterAsync(admin, new(provider.Configuration.Issuer, subject), null, CancellationToken.None);
    if (created.Outcome != StoreOutcome.Success) throw new InvalidOperationException("Fixture registration failed.");
    var user = created.Id!.Value; users[name] = user;
    if ((await database.Administration().ChangeStatusAsync(admin, user, UserStatus.Active, CancellationToken.None)).Outcome != StoreOutcome.Success) throw new InvalidOperationException("Fixture activation failed.");
    if (name != "no-role") await database.Administration().GrantRoleAsync(admin, user, PlatformRole.Viewer, now.AddHours(1), CancellationToken.None);
    if (name != "no-grant") await database.Administration().GrantResourceAsync(admin, user, ResourceKind.Study, resource, EnvironmentScope.Paper, Capability.Read, now.AddHours(1), CancellationToken.None);
    if (name == "disabled") await database.Administration().ChangeStatusAsync(admin, user, UserStatus.Disabled, CancellationToken.None);
    if (name != "enroll") { var f = Guid.NewGuid(); provider.Factors[f] = subject; if (name != "orphan") provider.VerifiedFactors[f] = true; }
    if (name == "ambiguous") { var f = Guid.NewGuid(); provider.Factors[f] = subject; provider.VerifiedFactors[f] = true; }
}
await using var controlConnection = await database.OpenClusterAsync();
provider.Control = async command =>
{
    if (command == "disable-viewer") await database.Administration().ChangeStatusAsync(admin, users["viewer"], UserStatus.Disabled, CancellationToken.None);
    else if (command == "enable-viewer") await database.Administration().ChangeStatusAsync(admin, users["viewer"], UserStatus.Active, CancellationToken.None);
    else if (command == "db-down") await BrowserDatabaseFixture.ExecuteAsync(controlConnection, $"ALTER DATABASE {database.Target.Database} ALLOW_CONNECTIONS false");
    else if (command == "db-up") await BrowserDatabaseFixture.ExecuteAsync(controlConnection, $"ALTER DATABASE {database.Target.Database} ALLOW_CONNECTIONS true");
    else throw new InvalidOperationException("Unknown fixture command.");
};
await provider.StartAsync();
await using var app = BrowserHost.CreateSynthetic(provider.Configuration, database.Database(DatabasePurpose.Runtime), database.Database(DatabasePurpose.SessionIssuer), origin, certificate, Path.Combine(root, "frontend-react/dist"), builder => builder.Services.Replace(ServiceDescriptor.Singleton<TimeProvider>(provider.Clock)));
await app.StartAsync();
database.AdditionalAllowedAddresses.Add(new IPEndPoint(IPAddress.Loopback, webPort).Serialize().ToString()!);
database.AdditionalAllowedAddresses.Add(new IPEndPoint(IPAddress.IPv6Loopback, webPort).Serialize().ToString()!);
database.AdditionalAllowedAddresses.Add(new IPEndPoint(IPAddress.Loopback.MapToIPv6(), webPort).Serialize().ToString()!);
await File.WriteAllTextAsync(Path.Combine(ready, "ready.json"), JsonSerializer.Serialize(new { origin = origin.GetLeftPart(UriPartial.Authority), authOrigin = $"http://127.0.0.1:{authPort}", resource, mode = "OFFLINE", decision = "NO_TRADE" }));
Console.WriteLine("M014B_SYNTHETIC_HTTPS_READY");
try {
    if (Environment.GetEnvironmentVariable("M014B_LOCAL_TLS_SMOKE") == "YES") await LocalTlsSmoke.RunAsync(origin, provider.Configuration.Project, ca, resource, Environment.GetEnvironmentVariable("M012_RESULTS_DIRECTORY")!);
    else { var deadline = DateTimeOffset.UtcNow.AddMinutes(12); while (!File.Exists(Path.Combine(ready, "stop")) && DateTimeOffset.UtcNow < deadline) await Task.Delay(250); }
}
catch (Exception error) { await File.WriteAllTextAsync(Path.Combine(ready, "failure.json"), JsonSerializer.Serialize(new { code = error.GetType().Name, http = error is HttpRequestException http ? http.HttpRequestError.ToString() : "NOT_HTTP" })); throw new InvalidOperationException("SYNTHETIC_FIXTURE_FAILED"); }
finally { await File.WriteAllTextAsync(Path.Combine(Environment.GetEnvironmentVariable("M012_RESULTS_DIRECTORY")!, "auth-metrics.json"), JsonSerializer.Serialize(provider.RedactedMetrics)); await app.StopAsync(); await controlConnection.DisposeAsync(); await database.DisposeAsync(); }
