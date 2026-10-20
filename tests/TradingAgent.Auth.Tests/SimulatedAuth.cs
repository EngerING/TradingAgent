using System.Collections.Concurrent;
using System.Security.Cryptography;
using System.Text.Json;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Logging;
using Microsoft.IdentityModel.JsonWebTokens;
using Microsoft.IdentityModel.Tokens;
using TradingAgent.Identity.Supabase;

namespace TradingAgent.Auth.Tests;

public sealed class TestClock : TimeProvider
{
    private long offsetTicks;
    public override DateTimeOffset GetUtcNow() => DateTimeOffset.UtcNow.AddTicks(Interlocked.Read(ref offsetTicks));
    public void Advance(TimeSpan value) => Interlocked.Add(ref offsetTicks, value.Ticks);
}
public sealed class SimulatedAuth : IAsyncDisposable
{
    private readonly ECDsa key = ECDsa.Create(ECCurve.NamedCurves.nistP256);
    private readonly ECDsa nextKey = ECDsa.Create(ECCurve.NamedCurves.nistP256);
    private WebApplication app = null!;
    private readonly ConcurrentDictionary<Guid, Guid> sessions = new();
    private readonly ConcurrentDictionary<Guid, (Guid User, Guid Factor)> challenges = new();
    public ConcurrentDictionary<string, Guid> Users { get; } = new(StringComparer.Ordinal);
    public ConcurrentDictionary<Guid, Guid> Factors { get; } = new();
    public ConcurrentDictionary<Guid, bool> VerifiedFactors { get; } = new();
    public TestClock Clock { get; } = new();
    public bool Rotated { get; set; }
    public bool Unavailable { get; set; }
    public bool RejectUser { get; set; }
    public bool IgnoreRemoteLogout { get; set; }
    public bool ChangeVerifySubject { get; set; }
    public bool ChangeVerifySession { get; set; }
    public bool StaleMfa { get; set; }
    public TaskCompletionSource? VerifyEntered { get; set; }
    public TaskCompletionSource? ReleaseVerify { get; set; }
    private int jwksRequests;
    private int verifyRequests;
    private int passwordRequests;
    public int JwksRequests => Volatile.Read(ref jwksRequests);
    public int VerifyRequests => Volatile.Read(ref verifyRequests);
    public int PasswordRequests => Volatile.Read(ref passwordRequests);
    public ServiceProvider Services { get; private set; } = null!;
    public AuthConfiguration Configuration { get; } = AuthConfiguration.ForSimulation(new Uri("http://127.0.0.1:39873"));
    public async Task StartAsync()
    {
        var builder = WebApplication.CreateEmptyBuilder(new WebApplicationOptions { ApplicationName = typeof(SimulatedAuth).Assembly.FullName });
        builder.WebHost.UseTestServer(); builder.Services.AddRouting(); builder.Logging.ClearProviders(); app = builder.Build();
        app.Use(async (context, next) => { if (Unavailable) { context.Response.StatusCode = 503; return; } await next(context); });
        app.MapGet("/auth/v1/.well-known/jwks.json", () =>
        {
            Interlocked.Increment(ref jwksRequests);
            var parameters = (Rotated ? nextKey : key).ExportParameters(false);
            return Results.Json(new { keys = new[] { new { kty = "EC", crv = "P-256", use = "sig", alg = "ES256", kid = Rotated ? "next" : "first", x = Base64UrlEncoder.Encode(parameters.Q.X!), y = Base64UrlEncoder.Encode(parameters.Q.Y!) } } });
        });
        app.MapPost("/auth/v1/token", async (HttpContext context) =>
        {
            Interlocked.Increment(ref passwordRequests); using var body = await JsonDocument.ParseAsync(context.Request.Body);
            var p = body.RootElement;
            if (context.Request.Query["grant_type"] != "password" || p.GetProperty("password").GetString() != "fixture-password" || !Users.TryGetValue(p.GetProperty("email").GetString()!, out var user)) return Results.Json(new { msg = "PRIVATE_PROVIDER_ERROR" }, statusCode: 400);
            var session = Guid.NewGuid(); sessions[session] = user; return Tokens(user, session, 1);
        });
        app.MapGet("/auth/v1/user", (HttpContext context) =>
        {
            var (user, session) = ReadIdentity(context);
            if (RejectUser || !sessions.TryGetValue(session, out var bound) || bound != user) return Results.Unauthorized();
            return Results.Json(new { id = user, is_anonymous = false, factors = Factors.Where(f => f.Value == user).Select(f => new { id = f.Key, factor_type = "totp", status = VerifiedFactors.ContainsKey(f.Key) ? "verified" : "unverified" }) });
        });
        app.MapPost("/auth/v1/factors", (HttpContext context) =>
        {
            var (user, _) = ReadIdentity(context); var factor = Guid.NewGuid(); Factors[factor] = user;
            return Results.Json(new { id = factor, type = "totp", totp = new { secret = "PUBLICSYNTHETICTOTPONLY", uri = "otpauth://totp/TradingAgent:fixture?secret=PUBLICSYNTHETICTOTPONLY", qr_code = "<svg onload='danger'></svg>" } });
        });
        app.MapDelete("/auth/v1/factors/{factor:guid}", (HttpContext context, Guid factor) =>
        {
            var (user, _) = ReadIdentity(context);
            if (!Factors.TryGetValue(factor, out var bound) || bound != user || VerifiedFactors.ContainsKey(factor)) return Results.BadRequest();
            Factors.TryRemove(factor, out _); return Results.Json(new { id = factor });
        });
        app.MapPost("/auth/v1/factors/{factor:guid}/challenge", (HttpContext context, Guid factor) =>
        {
            var (user, _) = ReadIdentity(context); if (!Factors.TryGetValue(factor, out var bound) || bound != user) return Results.BadRequest();
            var challenge = Guid.NewGuid(); challenges[challenge] = (user, factor);
            return Results.Json(new { id = challenge, expires_at = Clock.GetUtcNow().AddSeconds(60).ToUnixTimeSeconds() });
        });
        app.MapPost("/auth/v1/factors/{factor:guid}/verify", async (HttpContext context, Guid factor) =>
        {
            Interlocked.Increment(ref verifyRequests); var (user, session) = ReadIdentity(context);
            using var body = await JsonDocument.ParseAsync(context.Request.Body); var p = body.RootElement;
            if (!challenges.TryRemove(p.GetProperty("challenge_id").GetGuid(), out var challenge) || challenge.User != user || challenge.Factor != factor || p.GetProperty("code").GetString() != "123456") return Results.BadRequest();
            VerifyEntered?.TrySetResult();
            if (ReleaseVerify is not null) await ReleaseVerify.Task.WaitAsync(context.RequestAborted);
            VerifiedFactors[factor] = true;
            return Tokens(ChangeVerifySubject ? Guid.NewGuid() : user, ChangeVerifySession ? Guid.NewGuid() : session, 2);
        });
        app.MapPost("/auth/v1/logout", (HttpContext context) => { var (_, session) = ReadIdentity(context); if (!IgnoreRemoteLogout) sessions.TryRemove(session, out _); return Results.NoContent(); });
        await app.StartAsync();
        var services = new ServiceCollection(); Configure(services); Services = services.BuildServiceProvider();
    }
    public void Configure(IServiceCollection services)
    {
        services.AddSupabaseAuth(Configuration).ConfigurePrimaryHttpMessageHandler(() => app.GetTestServer().CreateHandler());
        services.Replace(ServiceDescriptor.Singleton<TimeProvider>(Clock));
    }
    public void ConfigureTransport(IServiceCollection services)
    {
        services.AddHttpClient<AuthTransport>().ConfigurePrimaryHttpMessageHandler(() => app.GetTestServer().CreateHandler());
        services.Replace(ServiceDescriptor.Singleton<TimeProvider>(Clock));
    }
    private IResult Tokens(Guid user, Guid session, int aal) => Results.Json(new { token_type = "bearer", access_token = Token(user, session, aal), refresh_token = "PUBLIC_FIXTURE_REFRESH_DISCARD", expires_in = 300 });
    private static (Guid User, Guid Session) ReadIdentity(HttpContext context)
    {
        var token = new JsonWebTokenHandler().ReadJsonWebToken(context.Request.Headers.Authorization.ToString()[7..]);
        return (Guid.Parse(token.Subject), Guid.Parse(token.GetClaim("session_id").Value));
    }
    public string Token(Guid user, Guid session, int aal = 2, string variant = "valid")
    {
        var now = Clock.GetUtcNow().ToUnixTimeSeconds();
        var payload = new Dictionary<string, object?>
        {
            ["iss"] = Configuration.Issuer, ["aud"] = "authenticated", ["sub"] = user.ToString(), ["session_id"] = session.ToString(),
            ["iat"] = now, ["exp"] = now + 300, ["nbf"] = now - 1, ["aal"] = "aal" + aal, ["role"] = "authenticated", ["is_anonymous"] = false,
            ["amr"] = new[] { new { method = aal == 2 ? variant == "legacytotp" ? "totp" : "mfa/totp" : "password", timestamp = StaleMfa ? now - 600 : now } }
        };
        switch (variant)
        {
            case "expired": payload["exp"] = now - 1; break;
            case "issuer": payload["iss"] = "https://other.invalid/auth/v1"; break;
            case "audience": payload["aud"] = "anon"; break;
            case "service": payload["role"] = "service_role"; break;
            case "anonymous": payload["is_anonymous"] = true; break;
            case "subject": payload["sub"] = "not-uuid"; break;
            case "session": payload.Remove("session_id"); break;
            case "future": payload["iat"] = now + 30; break;
            case "nbf": payload["nbf"] = now + 30; break;
            case "aal": payload["aal"] = "aal9"; break;
            case "nomfa": payload.Remove("amr"); break;
            case "longlife": payload["exp"] = now + 7200; break;
            case "missingiat": payload.Remove("iat"); break;
            case "missingexp": payload.Remove("exp"); break;
        }
        var signing = new ECDsaSecurityKey(Rotated ? nextKey : key) { KeyId = Rotated ? "next" : "first" };
        if (variant == "unknownkid") signing.KeyId = Guid.NewGuid().ToString("N");
        var handler = new JsonWebTokenHandler { SetDefaultTimesOnTokenCreation = false };
        if (variant == "none") return Base64UrlEncoder.Encode("{\"alg\":\"none\",\"typ\":\"JWT\",\"kid\":\"first\"}") + "." + Base64UrlEncoder.Encode(JsonSerializer.Serialize(payload)) + ".";
        var json = JsonSerializer.Serialize(payload);
        if (variant == "hs256") return handler.CreateToken(json, new SigningCredentials(new SymmetricSecurityKey(RandomNumberGenerator.GetBytes(32)) { KeyId = "first" }, "HS256"));
        if (variant == "duplicate") json = json[..^1] + ",\"iss\":\"" + Configuration.Issuer + "\"}";
        if (variant == "jku") return handler.CreateToken(json, new SigningCredentials(signing, "ES256"), new Dictionary<string, object> { ["jku"] = "https://attacker.invalid/jwks" });
        return handler.CreateToken(json, new SigningCredentials(signing, "ES256"));
    }
    public async ValueTask DisposeAsync()
    {
        if (Services is not null) await Services.DisposeAsync();
        if (app is not null) await app.DisposeAsync(); key.Dispose(); nextKey.Dispose(); GC.SuppressFinalize(this);
    }
}
