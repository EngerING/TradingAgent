using System.Text.Json;
using System.Net;
using System.Security.Cryptography.X509Certificates;
using Microsoft.AspNetCore.Antiforgery;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Authorization.Policy;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using TradingAgent.Identity.Persistence;
using TradingAgent.Identity.Supabase;

namespace TradingAgent.Web.Auth;

public static class IntegratedHostFactory
{
    public static WebApplication CreateSyntheticPilot(AuthConfiguration configuration, SecurityDatabase runtime, SecurityDatabase issuer, Action<WebApplicationBuilder> configureTestHost)
    {
        ArgumentNullException.ThrowIfNull(configuration); ArgumentNullException.ThrowIfNull(configureTestHost);
        if (!configuration.Simulation || runtime.Purpose != DatabasePurpose.Runtime || issuer.Purpose != DatabasePurpose.SessionIssuer) throw new InvalidOperationException("M01.3A supports only explicit synthetic composition.");
        return Create(configuration, runtime, issuer, new Uri("https://tradingagent.test"), configureTestHost);
    }
    public static WebApplication CreateHostedDevelopmentPilot(HostedPilotSettings settings, SecurityDatabase runtime, SecurityDatabase issuer, X509Certificate2 certificate)
    {
        ArgumentNullException.ThrowIfNull(settings); ArgumentNullException.ThrowIfNull(certificate);
        if (!certificate.HasPrivateKey || certificate.NotBefore.ToUniversalTime() > DateTime.UtcNow || certificate.NotAfter.ToUniversalTime() <= DateTime.UtcNow) throw new ArgumentException("Valid externally supplied development TLS certificate required.", nameof(certificate));
        return Create(settings.Authentication, runtime, issuer, settings.BrowserOrigin, builder =>
            builder.WebHost.UseKestrel(options => options.Listen(IPAddress.Loopback, settings.BrowserOrigin.Port, listener => listener.UseHttps(certificate))));
    }
    private static WebApplication Create(AuthConfiguration configuration, SecurityDatabase runtime, SecurityDatabase issuer, Uri browserOrigin, Action<WebApplicationBuilder> configureHost)
    {
        if (runtime.Purpose != DatabasePurpose.Runtime || issuer.Purpose != DatabasePurpose.SessionIssuer) throw new ArgumentException("Separate disposable runtime and issuer credentials required.");
        var builder = WebApplication.CreateEmptyBuilder(new WebApplicationOptions { ApplicationName = typeof(IntegratedHostFactory).Assembly.GetName().Name, EnvironmentName = "Development" });
        builder.Logging.ClearProviders(); builder.Services.AddRouting();
        builder.Services.AddSupabaseAuth(configuration);
        builder.Services.AddSingleton<TemporarySessions>();
        builder.Services.AddSingleton<PilotRequestBudgets>();
        builder.Services.AddSingleton(sp => new PilotRuntime(runtime, issuer, sp.GetRequiredService<JwtVerifier>(), sp.GetRequiredService<SupabaseAuthClient>(), sp.GetRequiredService<TemporarySessions>(), sp.GetRequiredService<TimeProvider>()));
        builder.Services.AddAuthenticationCore(o => { o.DefaultAuthenticateScheme = "PilotSession"; o.DefaultChallengeScheme = "PilotSession"; o.DefaultForbidScheme = "PilotSession"; });
        builder.Services.AddAuthentication().AddScheme<AuthenticationSchemeOptions, PilotAuthentication>("PilotSession", _ => { });
        var deny = new AuthorizationPolicyBuilder().RequireAssertion(_ => false).Build();
        builder.Services.AddAuthorizationBuilder().SetDefaultPolicy(deny).SetFallbackPolicy(deny).AddPolicy("PilotSession", policy => policy.RequireAuthenticatedUser());
        builder.Services.AddSingleton<IAuthorizationMiddlewareResultHandler, RoutingAuthorizationResultHandler>();
        builder.Services.AddAntiforgery(o => { o.HeaderName = "X-CSRF-TOKEN"; o.Cookie.Name = "__Host-TradingAgent.Csrf"; o.Cookie.SecurePolicy = CookieSecurePolicy.Always; o.Cookie.HttpOnly = true; o.Cookie.SameSite = SameSiteMode.Strict; o.Cookie.Path = "/"; });
        builder.Services.AddSingleton<IDataProtectionProvider>(new EphemeralDataProtectionProvider());
        configureHost(builder);
        if (builder.Environment.EnvironmentName != "Development") throw new InvalidOperationException("Pilot environment must remain Development.");
        var app = builder.Build();
        var boundaryLogger = app.Services.GetRequiredService<ILoggerFactory>().CreateLogger("TradingAgent.Web.Auth.Boundary");
        app.Use(async (context, next) =>
        {
            context.Response.Headers.CacheControl = "no-store"; context.Response.Headers.Pragma = "no-cache";
            context.Response.Headers.XContentTypeOptions = "nosniff"; context.Response.Headers.ContentSecurityPolicy = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'";
            context.Response.Headers["Referrer-Policy"] = "no-referrer"; context.Response.Headers["Strict-Transport-Security"] = "max-age=31536000";
            using var timeout = CancellationTokenSource.CreateLinkedTokenSource(context.RequestAborted); timeout.CancelAfter(TimeSpan.FromSeconds(15));
            context.RequestAborted = timeout.Token;
            try
            {
                if (!context.Request.IsHttps || context.Request.Host.Value != browserOrigin.Authority || context.Request.Headers["Sec-Fetch-Site"] is var site && site.Count != 0 && site != "same-origin" && site != "none") { await HttpBoundary.ErrorAsync(context, 403); return; }
                if (HttpMethods.IsPost(context.Request.Method))
                {
                    if (context.Request.ContentLength > 4096) { await HttpBoundary.ErrorAsync(context, 413); return; }
                    if (context.Request.Headers.Origin != browserOrigin.GetLeftPart(UriPartial.Authority)) { await HttpBoundary.ErrorAsync(context, 403); return; }
                    await context.RequestServices.GetRequiredService<IAntiforgery>().ValidateRequestAsync(context);
                }
                await next(context);
            }
            catch (AuthException error) when (!context.Response.HasStarted) { await HttpBoundary.ErrorAsync(context, error.Failure switch { AuthFailure.Invalid => 401, AuthFailure.Conflict => 409, AuthFailure.RateLimited => 429, _ => 503 }); }
            catch (ProbeDeniedException) when (!context.Response.HasStarted) { await HttpBoundary.ErrorAsync(context, 403); }
            catch (AntiforgeryValidationException) when (!context.Response.HasStarted) { await HttpBoundary.ErrorAsync(context, 403); }
            catch (BadHttpRequestException error) when (!context.Response.HasStarted) { await HttpBoundary.ErrorAsync(context, error.StatusCode == 413 ? 413 : 400); }
            catch (Exception error) when (!context.Response.HasStarted && error is JsonException or ArgumentException or KeyNotFoundException or InvalidOperationException or FormatException) { await HttpBoundary.ErrorAsync(context, 400); }
            catch (OperationCanceledException) when (!context.Response.HasStarted) { context.Response.StatusCode = 503; }
            catch (Exception) when (!context.Response.HasStarted) { await HttpBoundary.ErrorAsync(context, 500); }
            finally
            {
                var operation = context.Request.Path.StartsWithSegments("/bff/auth") ? "AUTH" : context.Request.Path.StartsWithSegments("/bff/session") ? "SESSION" : context.Request.Path.StartsWithSegments("/bff/probe") ? "SYNTHETIC_PROBE" : "OTHER";
                BoundaryLog.Completed(boundaryLogger, operation, context.Response.StatusCode);
            }
        });
        app.UseStatusCodePages(async status => await HttpBoundary.ErrorAsync(status.HttpContext, status.HttpContext.Response.StatusCode));
        app.UseRouting();
        app.Use(async (context, next) =>
        {
            var operation = context.GetEndpoint()?.Metadata.GetMetadata<PilotOperationMetadata>()?.Operation ?? PilotOperation.Session;
            if (HttpMethods.IsPost(context.Request.Method) && operation != PilotOperation.Login && !context.RequestServices.GetRequiredService<PilotRequestBudgets>().TryAdmit(operation, context.Connection.RemoteIpAddress)) throw new AuthException(AuthFailure.RateLimited);
            await next(context);
        });
        app.UseAuthentication(); app.UseAuthorization();
        app.MapGet("/health", () => Results.Json(new { status = "ok" })).AllowAnonymous();
        app.MapGet("/bff/csrf", (HttpContext context, IAntiforgery antiforgery) => Results.Json(new { token = antiforgery.GetAndStoreTokens(context).RequestToken })).AllowAnonymous();
        PilotEndpoints.Map(app);
        return app;
    }
    private sealed class RoutingAuthorizationResultHandler : IAuthorizationMiddlewareResultHandler
    {
        private readonly AuthorizationMiddlewareResultHandler handler = new();
        public Task HandleAsync(RequestDelegate next, HttpContext context, AuthorizationPolicy policy, PolicyAuthorizationResult authorizeResult) =>
            context.GetEndpoint() is not RouteEndpoint ? next(context) : handler.HandleAsync(next, context, policy, authorizeResult);
    }
}
