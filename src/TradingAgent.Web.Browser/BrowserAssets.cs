using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.StaticFiles;

namespace TradingAgent.Web.Browser;

// Fixed build-time file map: no request-controlled filesystem traversal or directory browsing.
internal static class BrowserAssets
{
    public static void Map(WebApplication app, string root)
    {
        var directory = Path.GetFullPath(root);
        if (!Directory.Exists(directory) || !File.Exists(Path.Combine(directory, "index.html"))) throw new ArgumentException("Compiled React directory required.", nameof(root));
        var types = new FileExtensionContentTypeProvider();
        foreach (var file in Directory.EnumerateFiles(directory, "*", SearchOption.AllDirectories))
        {
            if ((File.GetAttributes(file) & FileAttributes.ReparsePoint) != 0) throw new ArgumentException("Linked assets rejected.", nameof(root));
            var relative = Path.GetRelativePath(directory, file).Replace('\\', '/');
            if (relative == "index.html") continue;
            if (!relative.StartsWith("assets/", StringComparison.Ordinal) && relative != "mark.svg") throw new ArgumentException("Unexpected build asset.", nameof(root));
            if (Path.GetExtension(file) is not (".js" or ".css" or ".svg" or ".woff" or ".woff2") || !types.TryGetContentType(file, out var contentType)) throw new ArgumentException("Unexpected asset type.", nameof(root));
            app.MapGet("/" + relative, () => Results.File(file, contentType, enableRangeProcessing: false)).AllowAnonymous();
        }
        foreach (var route in new[] { "/", "/login", "/forgot-password", "/reset-password", "/invitation", "/mfa/enroll", "/mfa/verify", "/session/expired", "/session/denied", "/session/unavailable", "/session/progress", "/session/complete" })
            app.MapGet(route, () => Results.File(Path.Combine(directory, "index.html"), "text/html", enableRangeProcessing: false)).AllowAnonymous();
    }
}
