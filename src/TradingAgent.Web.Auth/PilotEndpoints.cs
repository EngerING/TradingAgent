using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using TradingAgent.Identity.Persistence;
using TradingAgent.Identity.Supabase;

namespace TradingAgent.Web.Auth;

internal static class PilotEndpoints
{
    internal static void Map(WebApplication app)
    {
        app.MapPost("/bff/auth/login", async (HttpContext context, PilotRuntime runtime) =>
        {
            if (HttpBoundary.Cookie(context.Request, HttpBoundary.SessionCookie) is not null) throw new AuthException(AuthFailure.Conflict);
            using var body = await HttpBoundary.BodyAsync(context); var p = body.RootElement;
            var email = p.GetProperty("email").GetString(); var password = p.GetProperty("password").GetString();
            if (email is null || email.Length is < 3 or > 320 || !email.Contains('@', StringComparison.Ordinal) || password is null || password.Length is < 1 or > 1024) return Results.StatusCode(400);
            if (HttpBoundary.Cookie(context.Request, HttpBoundary.PreauthCookie) is { } old) await runtime.LogoutAsync(null, old, context.RequestAborted);
            var pending = await runtime.LoginAsync(email, password, context.RequestAborted);
            context.Response.Cookies.Append(HttpBoundary.PreauthCookie, pending.Reference.ExportForCookie(), HttpBoundary.CookieOptions(pending.Expires));
            return Results.Json(new { status = "MFA_REQUIRED", factors = pending.Factors, executionAuthorized = false });
        }).AllowAnonymous();
        app.MapPost("/bff/auth/mfa/enroll", async (HttpContext context, PilotRuntime runtime) =>
            Results.Json(await runtime.EnrollAsync(Preauth(context), context.RequestAborted))).AllowAnonymous();
        app.MapPost("/bff/auth/mfa/challenge", async (HttpContext context, PilotRuntime runtime) =>
        {
            using var body = await HttpBoundary.BodyAsync(context);
            return Results.Json(await runtime.ChallengeAsync(Preauth(context), body.RootElement.GetProperty("factorId").GetGuid(), context.RequestAborted));
        }).AllowAnonymous();
        app.MapPost("/bff/auth/mfa/verify", async (HttpContext context, PilotRuntime runtime) =>
        {
            using var body = await HttpBoundary.BodyAsync(context); var p = body.RootElement;
            var code = p.GetProperty("code").GetString();
            if (code is null || code.Length != 6 || code.Any(c => c is < '0' or > '9')) return Results.StatusCode(400);
            var session = await runtime.VerifyAsync(Preauth(context), p.GetProperty("challengeId").GetGuid(), code, context.RequestAborted);
            context.Response.Cookies.Delete(HttpBoundary.PreauthCookie, HttpBoundary.CookieOptions(DateTimeOffset.UnixEpoch));
            context.Response.Cookies.Append(HttpBoundary.SessionCookie, session.Reference.ExportForCookie(), HttpBoundary.CookieOptions(session.Expires));
            return Results.Json(new { status = "SIGNED_IN", expiresAt = session.Expires, renewable = false, executionAuthorized = false });
        }).AllowAnonymous();
        app.MapGet("/bff/session", async (HttpContext context, PilotRuntime runtime) => Results.Json(await runtime.SessionAsync(Session(context), context.RequestAborted))).RequireAuthorization("PilotSession");
        app.MapGet("/bff/probe/{resource:guid}/{environment}", async (HttpContext context, PilotRuntime runtime, Guid resource, string environment) =>
        {
            if (!Enum.TryParse<EnvironmentScope>(environment, out var scope) || !Enum.IsDefined(scope)) return Results.StatusCode(400);
            return Results.Json(await runtime.ProbeAsync(Session(context), resource, scope, context.RequestAborted));
        }).RequireAuthorization("PilotSession");
        app.MapPost("/bff/session/touch", async (HttpContext context, PilotRuntime runtime) =>
        {
            using var body = await HttpBoundary.BodyAsync(context); var version = body.RootElement.GetProperty("rowVersion").GetInt64();
            var result = await runtime.TouchAsync(Session(context), version, context.RequestAborted);
            return Results.StatusCode(result switch { StoreOutcome.Success => 204, StoreOutcome.Conflict => 409, StoreOutcome.Unavailable => 503, _ => 401 });
        }).RequireAuthorization("PilotSession");
        app.MapPost("/bff/auth/logout", async (HttpContext context, PilotRuntime runtime) =>
        {
            var success = await runtime.LogoutAsync(HttpBoundary.Cookie(context.Request, HttpBoundary.SessionCookie), HttpBoundary.Cookie(context.Request, HttpBoundary.PreauthCookie), context.RequestAborted);
            context.Response.Cookies.Delete(HttpBoundary.SessionCookie, HttpBoundary.CookieOptions(DateTimeOffset.UnixEpoch));
            context.Response.Cookies.Delete(HttpBoundary.PreauthCookie, HttpBoundary.CookieOptions(DateTimeOffset.UnixEpoch));
            return Results.StatusCode(success ? 204 : 503);
        }).AllowAnonymous();
    }
    private static SessionReference Preauth(HttpContext context) => HttpBoundary.Cookie(context.Request, HttpBoundary.PreauthCookie) ?? throw new AuthException(AuthFailure.Invalid);
    private static SessionReference Session(HttpContext context) => HttpBoundary.Cookie(context.Request, HttpBoundary.SessionCookie) ?? throw new AuthException(AuthFailure.Invalid);
}
