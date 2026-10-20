using System.Net;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Authorization.Policy;
using TradingAgent.Web.Security;

namespace TradingAgent.Web;

public static class WebHostFactory
{
    // The callback is a trusted composition seam for TestServer, not a remote configuration surface.
    public static WebApplication Create(Action<WebApplicationBuilder>? configureHost = null)
    {
        var builder = WebApplication.CreateEmptyBuilder(new WebApplicationOptions
        {
            ApplicationName = typeof(WebHostFactory).Assembly.GetName().Name,
            EnvironmentName = Environments.Production
        });
        builder.WebHost.UseKestrel(options =>
        {
            options.AddServerHeader = false;
            options.Listen(IPAddress.Loopback, 5185);
            options.Limits.MaxRequestBodySize = 4096;
            options.Limits.RequestHeadersTimeout = TimeSpan.FromSeconds(10);
            options.Limits.KeepAliveTimeout = TimeSpan.FromSeconds(15);
        });
        builder.Services.AddRouting();
        // No scheme/handler, cookie, JWT or default identity provider is installed.
        builder.Services.AddAuthentication();
        builder.Services.AddAuthorizationBuilder().SetFallbackPolicy(
            new AuthorizationPolicyBuilder().RequireAssertion(_ => false).Build());
        builder.Services.AddSingleton<IAuthorizationMiddlewareResultHandler, UnavailableAuthorizationHandler>();
        builder.Services.AddSingleton<IExternalIdentityVerifier, UnconfiguredSecurity>();
        builder.Services.AddSingleton<IWebSessionReader, UnconfiguredSecurity>();
        builder.Services.AddSingleton<IWebAuthorizer, UnconfiguredSecurity>();
        configureHost?.Invoke(builder);

        var app = builder.Build();
        app.Use(async (context, next) =>
        {
            context.Response.Headers.CacheControl = "no-store";
            context.Response.Headers.XContentTypeOptions = "nosniff";
            context.Response.Headers.ContentSecurityPolicy = "default-src 'none'; frame-ancestors 'none'";
            try
            {
                await next(context);
            }
            catch (Exception) when (!context.Response.HasStarted && !context.RequestAborted.IsCancellationRequested)
            {
                context.Response.StatusCode = StatusCodes.Status500InternalServerError;
                await context.Response.WriteAsJsonAsync(WebError.Create(WebErrorCode.InternalError), context.RequestAborted);
            }
        });
        app.UseRouting();
        app.UseAuthentication();
        app.UseAuthorization();
        app.MapGet("/health", () => Results.Json(new { status = "ok" })).AllowAnonymous();
        return app;
    }

    private sealed class UnavailableAuthorizationHandler : IAuthorizationMiddlewareResultHandler
    {
        public async Task HandleAsync(RequestDelegate next, HttpContext context, AuthorizationPolicy policy,
            PolicyAuthorizationResult authorizeResult)
        {
            if (authorizeResult.Succeeded)
            {
                await next(context);
                return;
            }

            // Unknown routes remain 404; a mapped future protected route fails closed with 503.
            var status = context.GetEndpoint() is null ? 404 : context.Response.StatusCode == 405 ? 405 : 503;
            context.Response.StatusCode = status;
            var code = status switch
            {
                404 => WebErrorCode.NotFound,
                405 => WebErrorCode.MethodNotAllowed,
                _ => WebErrorCode.ServiceUnavailable
            };
            await context.Response.WriteAsJsonAsync(WebError.Create(code), context.RequestAborted);
        }
    }
}
