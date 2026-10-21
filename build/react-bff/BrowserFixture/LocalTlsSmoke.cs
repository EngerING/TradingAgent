using System.Net;
using System.Net.Http.Json;
using System.Net.Security;
using System.Security.Cryptography.X509Certificates;
using System.Text.Json;

namespace TradingAgent.React.BrowserFixture;

internal static class LocalTlsSmoke
{
    public static async Task RunAsync(Uri origin, Uri authOrigin, X509Certificate2 root, Guid resource, string results)
    {
        // Standard platform TLS chain/name verification with an explicit private test trust root.
        // No validation callback, insecure switch, or modification of the user's certificate stores.
        var policy = new X509ChainPolicy { TrustMode = X509ChainTrustMode.CustomRootTrust, RevocationMode = X509RevocationMode.NoCheck };
        policy.CustomTrustStore.Add(root);
        using var handler = new SocketsHttpHandler { SslOptions = new SslClientAuthenticationOptions { CertificateChainPolicy = policy }, CookieContainer = new CookieContainer(), UseCookies = true, UseProxy = false, AllowAutoRedirect = false };
        using var client = new HttpClient(handler) { BaseAddress = origin, Timeout = TimeSpan.FromSeconds(10) };
        static void Require(bool value) { if (!value) throw new InvalidOperationException("LOCAL_TLS_SMOKE_REJECTED"); }
        async Task<JsonElement> ReadAsync(string path) { using var response = await client.GetAsync(path); Require(response.StatusCode == HttpStatusCode.OK); using var doc = JsonDocument.Parse(await response.Content.ReadAsStringAsync()); return doc.RootElement.Clone(); }
        async Task<JsonElement> PostAsync(string path, object body, HttpStatusCode status = HttpStatusCode.OK)
        {
            var csrf = await ReadAsync("/bff/csrf");
            using var request = new HttpRequestMessage(HttpMethod.Post, path) { Content = JsonContent.Create(body) };
            request.Headers.Add("Origin", origin.GetLeftPart(UriPartial.Authority)); request.Headers.Add("X-CSRF-TOKEN", csrf.GetProperty("token").GetString());
            using var response = await client.SendAsync(request); Require(response.StatusCode == status);
            if (status == HttpStatusCode.NoContent) return default;
            using var doc = JsonDocument.Parse(await response.Content.ReadAsStringAsync()); return doc.RootElement.Clone();
        }
        var profile = await ReadAsync("/bff/config"); Require(profile.GetProperty("profile").GetString() == "SYNTHETIC_HTTP_FIXTURE");
        using (var html = await client.GetAsync("/")) Require(html.StatusCode == HttpStatusCode.OK && html.Content.Headers.ContentType?.MediaType == "text/html");
        var login = await PostAsync("/bff/auth/login", new { email = "viewer@fixture.invalid", password = "fixture-password" });
        var factor = login.GetProperty("factors")[0].GetProperty("id").GetGuid();
        using (var aal1 = await client.GetAsync("/bff/session")) Require(aal1.StatusCode == HttpStatusCode.Unauthorized);
        var challenge = await PostAsync("/bff/auth/mfa/challenge", new { factorId = factor });
        await PostAsync("/bff/auth/mfa/verify", new { challengeId = challenge.GetProperty("id").GetGuid(), code = "123456" });
        var session = await ReadAsync("/bff/session"); Require(session.GetProperty("aal").GetString() == "aal2" && !session.GetProperty("executionAuthorized").GetBoolean());
        var probe = await ReadAsync($"/bff/probe/{resource}/Paper"); Require(probe.GetProperty("synthetic").GetBoolean());
        async Task ControlAsync(string command)
        {
            using var request = new HttpRequestMessage(HttpMethod.Post, new Uri(authOrigin, "/fixture/control/" + command));
            request.Headers.Add("X-Fixture-Control", "public-synthetic-only");
            using var response = await client.SendAsync(request); Require(response.StatusCode == HttpStatusCode.NoContent);
        }
        await ControlAsync("db-down");
        try { using var down = await client.GetAsync("/bff/session"); Require(down.StatusCode == HttpStatusCode.ServiceUnavailable); }
        finally { await ControlAsync("db-up"); }
        await ReadAsync("/bff/session");
        await PostAsync("/bff/auth/logout", new { }, HttpStatusCode.NoContent);
        using (var ended = await client.GetAsync("/bff/session")) Require(ended.StatusCode == HttpStatusCode.Unauthorized);
        await File.WriteAllTextAsync(Path.Combine(results, "local-tls-smoke.json"), JsonSerializer.Serialize(new { result = "PASS", tls = "CustomRootTrust with normal chain and hostname verification; no user store modified", password = "PASS", aal1_denied = true, aal2 = "PASS", postgres_resource = "PASS", postgres_connection_refusal = "PASS", logout = "PASS", mode = "OFFLINE", decision = "NO_TRADE" }));
    }
}
