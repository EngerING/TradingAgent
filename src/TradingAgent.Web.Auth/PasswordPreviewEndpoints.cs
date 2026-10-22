using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using TradingAgent.Identity.Supabase;

namespace TradingAgent.Web.Auth;

/// <summary>Only password-based development identity; isolated from protected application routes.</summary>
internal static class PasswordPreviewEndpoints
{
    private const string CookieName = "__Host-TradingAgent.Preview";
    private static object Response(PreviewSessionSnapshot snapshot, bool login) =>
        login
        ? new { status = "PASSWORD_PREVIEW", authenticated = true, aal = "aal1", profile = "PASSWORD_ONLY_DEV_PREVIEW",
            expiresAt = snapshot.ExpiresAt, idleExpiresAt = snapshot.IdleExpiresAt, renewable = true, executionAuthorized = false,
            mode = "OFFLINE", decision = "NO_TRADE" }
        : new { status = "PASSWORD_PREVIEW", authenticated = true, aal = "aal1", profile = "PASSWORD_ONLY_DEV_PREVIEW",
            expiresAt = snapshot.ExpiresAt, idleExpiresAt = snapshot.IdleExpiresAt, renewable = true, executionAuthorized = false,
            mode = "OFFLINE", decision = "NO_TRADE" };

    internal static void Map(WebApplication app)
    {
        app.MapPost("/bff/preview/login", async (HttpContext ctx, PasswordPreviewSessions preview, PilotRequestBudgets budget) =>
        {
            using var body = await HttpBoundary.BodyAsync(ctx); var p = body.RootElement;
            var email = p.GetProperty("email").GetString(); var pass = p.GetProperty("password").GetString();
            if (email is null || email.Length is < 3 or > 320 || !email.Contains('@') ||
                pass is null || pass.Length is < 1 or > 1024) return Results.StatusCode(400);
            if (!budget.TryAdmit(PilotOperation.Login, ctx.Connection.RemoteIpAddress, email))
                throw new AuthException(AuthFailure.RateLimited);
            if (ctx.Request.Cookies.ContainsKey(HttpBoundary.SessionCookie)) throw new AuthException(AuthFailure.Conflict);
            var issued = await preview.LoginAsync(email, pass, ctx.RequestAborted);
            ctx.Response.Cookies.Append(CookieName, issued.Reference.ExportForCookie(), HttpBoundary.CookieOptions(issued.Session.ExpiresAt));
            return Results.Json(Response(issued.Session, login: true));
        }).WithMetadata(new PilotOperationMetadata(PilotOperation.Login)).AllowAnonymous();

        app.MapGet("/bff/preview/session", async (HttpContext ctx, PasswordPreviewSessions preview) =>
            Results.Json(Response(await preview.SessionAsync(HttpBoundary.Cookie(ctx.Request, CookieName), false, ctx.RequestAborted), login: false)))
            .AllowAnonymous();

        app.MapPost("/bff/preview/activity", async (HttpContext ctx, PasswordPreviewSessions preview) =>
        {
            using var body = await HttpBoundary.BodyAsync(ctx);
            if (body.RootElement.ValueKind != System.Text.Json.JsonValueKind.Object ||
                body.RootElement.EnumerateObject().Any()) return Results.StatusCode(400);
            return Results.Json(Response(await preview.SessionAsync(HttpBoundary.Cookie(ctx.Request, CookieName), true, ctx.RequestAborted), login: false));
        }).WithMetadata(new PilotOperationMetadata(PilotOperation.Session)).AllowAnonymous();

        app.MapPost("/bff/preview/logout", async (HttpContext ctx, PasswordPreviewSessions preview) =>
        {
            try { await preview.LogoutAsync(HttpBoundary.Cookie(ctx.Request, CookieName), ctx.RequestAborted); }
            finally { ctx.Response.Cookies.Delete(CookieName, HttpBoundary.CookieOptions(DateTimeOffset.UnixEpoch)); }
            return Results.StatusCode(204);
        }).WithMetadata(new PilotOperationMetadata(PilotOperation.Logout)).AllowAnonymous();
    }
}
