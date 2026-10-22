using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using TradingAgent.Identity.Supabase;

namespace TradingAgent.Web.Auth;

/// <summary>Explicitly isolated AAL1 preview; no operational endpoints.</summary>
internal static class PasswordPreviewEndpoints
{
    private const string CookieName = "__Host-TradingAgent.Preview";
    internal static void Map(WebApplication app)
    {
        app.MapPost("/bff/preview/login", async (HttpContext ctx, PasswordPreviewSessions preview, PilotRequestBudgets budget) =>
        {
            using var body = await HttpBoundary.BodyAsync(ctx);
            var p = body.RootElement;
            var email = p.GetProperty("email").GetString();
            var pass = p.GetProperty("password").GetString();
            if (email is null || email.Length is < 3 or > 320 || !email.Contains('@') ||
                pass is null || pass.Length is < 1 or > 1024) return Results.StatusCode(400);
            if (!budget.TryAdmit(PilotOperation.Login, ctx.Connection.RemoteIpAddress, email)) throw new AuthException(AuthFailure.RateLimited);
            if (ctx.Request.Cookies.ContainsKey(HttpBoundary.SessionCookie)) throw new AuthException(AuthFailure.Conflict);
            var created = await preview.LoginAsync(email, pass, ctx.RequestAborted);
            ctx.Response.Cookies.Append(CookieName, created.Reference.ExportForCookie(), HttpBoundary.CookieOptions(created.Expires));
            return Results.Json(new { status = "PASSWORD_PREVIEW", authenticated = true, aal = "aal1",
                profile = "PASSWORD_ONLY_DEV_PREVIEW", expiresAt = created.Expires, renewable = false,
                executionAuthorized = false, mode = "OFFLINE", decision = "NO_TRADE" });
        }).WithMetadata(new PilotOperationMetadata(PilotOperation.Login)).AllowAnonymous();

        app.MapGet("/bff/preview/session", async (HttpContext ctx, PasswordPreviewSessions preview) =>
            Results.Json(await preview.SessionAsync(HttpBoundary.Cookie(ctx.Request, CookieName), ctx.RequestAborted)))
            .AllowAnonymous();

        app.MapPost("/bff/preview/logout", async (HttpContext ctx, PasswordPreviewSessions preview) =>
        {
            try { await preview.LogoutAsync(HttpBoundary.Cookie(ctx.Request, CookieName), ctx.RequestAborted); }
            finally { ctx.Response.Cookies.Delete(CookieName, HttpBoundary.CookieOptions(DateTimeOffset.UnixEpoch)); }
            return Results.StatusCode(204);
        }).WithMetadata(new PilotOperationMetadata(PilotOperation.Logout)).AllowAnonymous();
    }
}
