using System.Net;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text.Json;
using Npgsql;
using TradingAgent.Identity.Migrations;
using TradingAgent.Identity.Persistence;

namespace TradingAgent.React.BrowserFixture;

// Preparation only: no provider, identity bootstrap, application user or user grant.
public static class LocalPilotPreparation
{
    public static IReadOnlyList<DatabasePurpose> LoginPurposes { get; } =
        Array.AsReadOnly(new[] { DatabasePurpose.Migration, DatabasePurpose.Runtime, DatabasePurpose.SessionIssuer });

    public sealed record CertificateMaterial(X509Certificate2 Root, X509Certificate2 Leaf) : IDisposable
    {
        public void Dispose() { Leaf.Dispose(); Root.Dispose(); }
    }

    public static CertificateMaterial Certificate(bool extendedPreview = false)
    {
        using var rootKey = RSA.Create(3072);
        var rootRequest = new CertificateRequest("CN=TradingAgent owned local pilot " + Guid.NewGuid().ToString("N"), rootKey, HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1);
        rootRequest.CertificateExtensions.Add(new X509BasicConstraintsExtension(true, false, 0, true));
        rootRequest.CertificateExtensions.Add(new X509KeyUsageExtension(X509KeyUsageFlags.KeyCertSign, true));
        var now = DateTimeOffset.UtcNow;
        var root = rootRequest.CreateSelfSigned(now.AddMinutes(-1), now.AddHours(extendedPreview ? 11 : 4));
        try
        {
            using var key = RSA.Create(3072);
            var request = new CertificateRequest("CN=127.0.0.1", key, HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1);
            request.CertificateExtensions.Add(new X509BasicConstraintsExtension(false, false, 0, true));
            request.CertificateExtensions.Add(new X509KeyUsageExtension(X509KeyUsageFlags.DigitalSignature | X509KeyUsageFlags.KeyEncipherment, true));
            request.CertificateExtensions.Add(new X509EnhancedKeyUsageExtension(new OidCollection { new("1.3.6.1.5.5.7.3.1") }, true));
            var san = new SubjectAlternativeNameBuilder(); san.AddIpAddress(IPAddress.Loopback); request.CertificateExtensions.Add(san.Build());
            using var issued = request.Create(root, now.AddMinutes(-1), now.AddHours(extendedPreview ? 10 : 3), RandomNumberGenerator.GetBytes(16));
            var leaf = issued.CopyWithPrivateKey(key);
            return new(root, leaf);
        }
        catch { root.Dispose(); throw; }
    }

    // Custom trust is used ONLY for preparation tests. Hosted runner still requires OS trust.
    public static void ValidateCertificate(X509Certificate2 certificate, X509Certificate2 root)
    {
        var encoded = certificate.Extensions["2.5.29.17"];
        if (encoded is null || !certificate.HasPrivateKey) throw new InvalidOperationException("TLS_PROFILE_REJECTED");
        var san = new X509SubjectAlternativeNameExtension(); san.CopyFrom(encoded);
        if (!san.EnumerateIPAddresses().Contains(IPAddress.Loopback) ||
            certificate.Extensions.OfType<X509EnhancedKeyUsageExtension>().SingleOrDefault()?.EnhancedKeyUsages.Cast<Oid>().Any(o => o.Value == "1.3.6.1.5.5.7.3.1") != true)
            throw new InvalidOperationException("TLS_PROFILE_REJECTED");
        using var chain = new X509Chain();
        chain.ChainPolicy.TrustMode = X509ChainTrustMode.CustomRootTrust;
        chain.ChainPolicy.CustomTrustStore.Add(root);
        chain.ChainPolicy.ApplicationPolicy.Add(new Oid("1.3.6.1.5.5.7.3.1"));
        chain.ChainPolicy.RevocationMode = X509RevocationMode.NoCheck;
        if (!chain.Build(certificate)) throw new InvalidOperationException("TLS_CHAIN_REJECTED");
    }

    private static string Required(string name) => Environment.GetEnvironmentVariable(name) ?? throw new InvalidOperationException("LOCAL_CONFIGURATION_MISSING");
    public static async Task PrepareAsync()
    {
        var directory = Path.GetFullPath(Required("M014B_LOCAL_PILOT_RUN_DIRECTORY"));
        if (!File.Exists(Path.Combine(directory, "owner.json")) || File.Exists(Path.Combine(directory, "prepared.json"))) throw new InvalidOperationException("OWNED_NEW_RUN_REQUIRED");
        var port = int.Parse(Required("M012_TEST_PORT"), System.Globalization.CultureInfo.InvariantCulture);
        var target = new DisposableTarget("127.0.0.1", port, "m012_test_" + Guid.NewGuid().ToString("N"));
        var builder = new NpgsqlConnectionStringBuilder { Host = target.Host, Port = port, Database = "postgres", Username = "postgres", Password = Required("M012_BOOTSTRAP_PASSWORD"), Pooling = false, Timeout = 3, CommandTimeout = 10, SslMode = SslMode.Disable, GssEncryptionMode = GssEncryptionMode.Disable, IncludeErrorDetail = false };
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(60));
        await using (var cluster = new NpgsqlConnection(builder.ConnectionString))
        {
            await cluster.OpenAsync(deadline.Token);
            await using var check = new NpgsqlCommand("SHOW cluster_name", cluster);
            var marker = Required("M012_CLUSTER_MARKER");
            if (!marker.StartsWith("m012_disposable_", StringComparison.Ordinal) || (string)(await check.ExecuteScalarAsync(deadline.Token))! != marker) throw new InvalidOperationException("CLUSTER_MARKER_REJECTED");
            await ExecuteAsync(cluster, $"CREATE DATABASE {target.Database}", deadline.Token);
        }
        builder.Database = target.Database;
        var credentials = new Dictionary<DatabasePurpose, (string User, string Password)>();
        await using (var owner = new NpgsqlConnection(builder.ConnectionString))
        {
            await owner.OpenAsync(deadline.Token);
            await ExecuteAsync(owner, $"COMMENT ON DATABASE {target.Database} IS '{target.Marker}'; REVOKE CREATE,TEMP ON DATABASE {target.Database} FROM PUBLIC; REVOKE ALL ON SCHEMA public FROM PUBLIC", deadline.Token);
            foreach (var group in new[] { "identity_migration_owner", "web_security_runtime", "identity_session_issuer", "identity_access_admin", "identity_security_reader" })
                await ExecuteAsync(owner, $"CREATE ROLE {group} NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION", deadline.Token);
            foreach (var purpose in LoginPurposes)
            {
                var prefix = purpose switch { DatabasePurpose.Migration => "MIGRATION", DatabasePurpose.Runtime => "RUNTIME", _ => "ISSUER" };
                var group = purpose switch { DatabasePurpose.Migration => "identity_migration_owner", DatabasePurpose.Runtime => "web_security_runtime", _ => "identity_session_issuer" };
                var login = "m012_" + Guid.NewGuid().ToString("N");
                var password = Required("M014B_LOCAL_" + prefix + "_PASSWORD");
                // Generated hexadecimal only; never interpolate external configuration into DDL.
                if (password.Length != 64 || password.Any(c => !Uri.IsHexDigit(c))) throw new InvalidOperationException("GENERATED_PASSWORD_REQUIRED");
                await ExecuteAsync(owner, $"CREATE ROLE {login} LOGIN PASSWORD '{password}' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION; GRANT {group} TO {login}", deadline.Token);
                credentials.Add(purpose, (login, password));
            }
            await ExecuteAsync(owner, "CREATE SCHEMA app_security AUTHORIZATION identity_migration_owner", deadline.Token);
        }
        SecurityDatabase Database(DatabasePurpose purpose) => new(target, credentials[purpose].User, credentials[purpose].Password, purpose);
        await MigrationRunner.ApplyAsync(Database(DatabasePurpose.Migration), deadline.Token);
        foreach (var purpose in new[] { DatabasePurpose.Runtime, DatabasePurpose.SessionIssuer })
            await using (var connection = await Database(purpose).OpenAsync(deadline.Token)) { }
        await using (var owner = new NpgsqlConnection(builder.ConnectionString))
        {
            await owner.OpenAsync(deadline.Token);
            await using var count = new NpgsqlCommand("SELECT (SELECT count(*) FROM app_security.app_users)+(SELECT count(*) FROM app_security.user_roles)+(SELECT count(*) FROM app_security.resource_grants)", owner);
            if (Convert.ToInt64(await count.ExecuteScalarAsync(deadline.Token), System.Globalization.CultureInfo.InvariantCulture) != 0) throw new InvalidOperationException("APPLICATION_AUTHORIZATION_MUST_REMAIN_EMPTY");
        }
        var certificateProfile = Environment.GetEnvironmentVariable("M014B_LOCAL_PREVIEW_CERTIFICATE");
        if (certificateProfile is not null && certificateProfile != "EXPLICIT_EXTENDED_PREVIEW_CERTIFICATE")
            throw new InvalidOperationException("INVALID_CERTIFICATE_PROFILE");
        using var material = Certificate(certificateProfile is not null);
        ValidateCertificate(material.Leaf, material.Root);
        await File.WriteAllBytesAsync(Path.Combine(directory, "root.cer"), material.Root.Export(X509ContentType.Cert), deadline.Token);
        var pfx = material.Leaf.Export(X509ContentType.Pkcs12, Required("M014B_LOCAL_TLS_PASSWORD"));
        try { await File.WriteAllBytesAsync(Path.Combine(directory, "loopback.pfx"), pfx, deadline.Token); }
        finally { CryptographicOperations.ZeroMemory(pfx); }
        await File.WriteAllTextAsync(Path.Combine(directory, "prepared.json"), JsonSerializer.Serialize(new {
            database = target.Database, runtimeUser = credentials[DatabasePurpose.Runtime].User, issuerUser = credentials[DatabasePurpose.SessionIssuer].User,
            rootThumbprint = material.Root.Thumbprint, leafThumbprint = material.Leaf.Thumbprint, expiresAt = material.Leaf.NotAfter.ToUniversalTime(),
            appUsers = 0, userRoles = 0, resourceGrants = 0, sqlRolesValidated = true, certificateProfileValidated = true, extendedPreviewCertificate = certificateProfile is not null,
            osTrustInstalled = false, hostedRequests = 0, mode = "OFFLINE", decision = "NO_TRADE" }), deadline.Token);
        Console.WriteLine("LOCAL_PREPARATION_PASS; EMPTY_APPLICATION_AUTHORIZATION; NO_HOSTED_REQUESTS");
    }
    private static async Task ExecuteAsync(NpgsqlConnection connection, string sql, CancellationToken token)
    { await using var command = new NpgsqlCommand(sql, connection); await command.ExecuteNonQueryAsync(token); }
}
