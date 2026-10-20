using System.Security.Claims;
using System.Text.Encodings.Web;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using TradingAgent.Identity.Supabase;

namespace TradingAgent.Web.Auth;

public sealed class PilotAuthentication(IOptionsMonitor<AuthenticationSchemeOptions> options, ILoggerFactory logger, UrlEncoder encoder, PilotRuntime runtime)
    : AuthenticationHandler<AuthenticationSchemeOptions>(options, logger, encoder)
{
    protected override async Task<AuthenticateResult> HandleAuthenticateAsync()
    {
        // Anonymous identity routes include logout: provider outage must not prevent local revocation.
        // CSRF tokens deliberately use the anonymous browser-cookie binding before authentication.
        if (Context.GetEndpoint()?.Metadata.GetMetadata<IAllowAnonymous>() is not null) return AuthenticateResult.NoResult();
        var reference = HttpBoundary.Cookie(Request, HttpBoundary.SessionCookie);
        if (reference is null) return AuthenticateResult.NoResult();
        try
        {
            var user = await runtime.ValidateSessionAsync(reference, Context.RequestAborted).ConfigureAwait(false);
            var principal = new ClaimsPrincipal(new ClaimsIdentity([new Claim(ClaimTypes.NameIdentifier, user.ToString())], Scheme.Name));
            return AuthenticateResult.Success(new AuthenticationTicket(principal, Scheme.Name));
        }
        catch (AuthException error) when (error.Failure == AuthFailure.Invalid) { return AuthenticateResult.Fail("SESSION_INVALID"); }
    }
    protected override Task HandleChallengeAsync(AuthenticationProperties properties) => HttpBoundary.ErrorAsync(Context, 401);
    protected override Task HandleForbiddenAsync(AuthenticationProperties properties) => HttpBoundary.ErrorAsync(Context, 403);
}
