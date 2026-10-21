using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.IdentityModel.Tokens;

namespace TradingAgent.HostedPilot;

internal static class ObserverSelfTest
{
    internal static async Task RunAsync()
    {
        HostedRun.UseDiagnosticSelfTestOutput();
        var privateMarker = Guid.NewGuid().ToString("N");
        var now = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
        var token = Base64UrlEncoder.Encode(JsonSerializer.Serialize(new { alg = "ES256", typ = "JWT", kid = privateMarker })) + "." +
            Base64UrlEncoder.Encode(JsonSerializer.Serialize(new { iss = "https://private-project.invalid/auth/v1", aud = "authenticated", sub = Guid.NewGuid(), session_id = Guid.NewGuid(), aal = "aal1", role = "authenticated", is_anonymous = false, iat = now, exp = now + 300, email = privateMarker, user_metadata = new { privateMarker } })) + ".UNSIGNED_FIXTURE_NOT_AUTHORITY";
        using var observer = new RedactedAuthObserver("https://private-project.invalid/auth/v1") { InnerHandler = new FixtureResponse(token, privateMarker) };
        using var client = new HttpClient(observer);
        using var result = await client.PostAsync("https://public-fixture.invalid/auth/v1/token", new StringContent("{}"));
        using var request = new HttpRequestMessage(HttpMethod.Post, "https://public-fixture.invalid/auth/v1/factors");
        using var mfa = await client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead);
        var text = await File.ReadAllTextAsync("tmp/m013b/hosted-observer-self-test.json");
        if (text.Contains(privateMarker, StringComparison.Ordinal) || text.Contains(token, StringComparison.Ordinal) || text.Contains("private-project", StringComparison.Ordinal)) throw new PilotFailure("DIAGNOSTIC_DISCLOSURE");
        using var report = JsonDocument.Parse(text);
        if (report.RootElement.GetProperty("http_PASSWORD").GetInt32() != 200 || !report.RootElement.GetProperty("UNTRUSTED_PASSWORD_JWT_COMPATIBILITY_NOT_VALIDATION").GetProperty("issuer_matches").GetBoolean()) throw new PilotFailure("DIAGNOSTIC_MISSING");
        if (!report.RootElement.GetProperty("attempted_MFA_ENROLL").GetBoolean() ||
            !report.RootElement.GetProperty("response_profile_MFA_ENROLL").GetProperty("declared_body_exceeds_64k").GetBoolean())
            throw new PilotFailure("MFA_HEADER_DIAGNOSTIC_MISSING");
        // Invalid-signature input may produce shape diagnostics, but no authenticated or PASS result.
        if (report.RootElement.TryGetProperty("status", out _) ||
            report.RootElement.TryGetProperty("authenticated", out _) ||
            report.RootElement.TryGetProperty("executionAuthorized", out _) ||
            report.RootElement.EnumerateObject().Any(field => field.Value.ValueKind == JsonValueKind.String && field.Value.GetString() == "PASS"))
            throw new PilotFailure("UNTRUSTED_SHAPE_GRANTED_AUTHORITY");
        File.WriteAllText("tmp/m013b/hosted-observer-self-test-verdict.json", "{\"result\":\"PASS\",\"checks\":[\"NO_PRIVATE_MARKER_OR_TOKEN_OR_ISSUER\",\"UNSIGNED_SHAPE_NEVER_AUTHORIZES\",\"HTTP_STATUS_PRESERVED\",\"MFA_PHASE_AND_BOUNDED_HEADER_PROFILE\"],\"network_requests\":0}");
    }
    private sealed class FixtureResponse(string token, string marker) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            HttpContent content = request.RequestUri!.AbsolutePath == "/auth/v1/token" ?
                JsonContent.Create(new { access_token = token, refresh_token = marker }) : new ByteArrayContent(new byte[70000]);
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { RequestMessage = request, Content = content });
        }
    }
}
