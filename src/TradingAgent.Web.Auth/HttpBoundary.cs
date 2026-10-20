using System.Text.Json;
using Microsoft.AspNetCore.Http;
using TradingAgent.Identity.Persistence;

namespace TradingAgent.Web.Auth;

internal static class HttpBoundary
{
    internal const string SessionCookie = "__Host-TradingAgent.Session";
    internal const string PreauthCookie = "__Host-TradingAgent.PreAuth";
    internal static SessionReference? Cookie(HttpRequest request, string name)
    {
        if (!request.Cookies.TryGetValue(name, out var value)) return null;
        try { return SessionReference.Parse(value); } catch (ArgumentException) { return null; }
    }
    internal static CookieOptions CookieOptions(DateTimeOffset expires) => new() { Secure = true, HttpOnly = true, SameSite = SameSiteMode.Strict, Path = "/", Expires = expires, IsEssential = true };
    internal static Task ErrorAsync(HttpContext context, int status)
    {
        context.Response.StatusCode = status;
        var code = status switch { 400 => "INVALID_REQUEST", 401 => "SESSION_INVALID", 403 => "ACCESS_DENIED", 404 => "NOT_FOUND", 405 => "METHOD_NOT_ALLOWED", 409 => "SESSION_CONFLICT", 413 => "REQUEST_TOO_LARGE", 429 => "TRY_LATER", 503 => "DEPENDENCY_UNAVAILABLE", _ => "INTERNAL_ERROR" };
        return context.Response.WriteAsJsonAsync(new { code, correlationId = Guid.NewGuid(), executionAuthorized = false }, context.RequestAborted);
    }
    internal static async Task<JsonDocument> BodyAsync(HttpContext context)
    {
        if (context.Request.ContentType?.Split(';')[0] != "application/json") throw new JsonException("JSON required.");
        using var memory = new MemoryStream(); var buffer = new byte[1024];
        while (true)
        {
            var count = await context.Request.Body.ReadAsync(buffer, context.RequestAborted).ConfigureAwait(false); if (count == 0) break;
            if (memory.Length + count > 4096) throw new BadHttpRequestException("Request too large.", 413);
            memory.Write(buffer, 0, count);
        }
        var document = JsonDocument.Parse(memory.ToArray(), new JsonDocumentOptions { MaxDepth = 4 });
        var names = new HashSet<string>(StringComparer.Ordinal);
        foreach (var property in document.RootElement.EnumerateObject()) if (!names.Add(property.Name)) { document.Dispose(); throw new JsonException("Duplicate property."); }
        return document;
    }
}
