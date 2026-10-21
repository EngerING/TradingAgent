using Microsoft.Extensions.DependencyInjection;
using Microsoft.IdentityModel.Tokens;

namespace TradingAgent.Identity.Supabase;

public sealed class JwksCache(IServiceScopeFactory scopes, TimeProvider clock) : IDisposable
{
    private readonly SemaphoreSlim gate = new(1, 1);
    private SecurityKey[] keys = [];
    private DateTimeOffset fetched = DateTimeOffset.MinValue;
    private DateTimeOffset attempted = DateTimeOffset.MinValue;
    public async Task<SecurityKey[]> ResolveAsync(string kid, CancellationToken cancellationToken)
    {
        await gate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            var now = clock.GetUtcNow();
            var match = keys.Where(k => k.KeyId == kid).ToArray();
            if (now - fetched < TimeSpan.FromMinutes(5) && match.Length == 1) return match;
            if (now - attempted >= TimeSpan.FromSeconds(30))
            {
                attempted = now;
                using var scope = scopes.CreateScope(); var transport = scope.ServiceProvider.GetRequiredService<AuthTransport>();
                try
                {
                    using var document = await transport.SendAsync(HttpMethod.Get, "/auth/v1/.well-known/jwks.json", null, null, cancellationToken).ConfigureAwait(false);
                    var set = new JsonWebKeySet(document.RootElement.GetRawText());
                    if (set.Keys.Count is < 1 or > 10 || set.Keys.Select(k => k.Kid).Distinct(StringComparer.Ordinal).Count() != set.Keys.Count ||
                        set.Keys.Any(k => k.Kty != "EC" || k.Crv != "P-256" || k.Use != "sig" || k.Alg != "ES256" || string.IsNullOrWhiteSpace(k.Kid) || k.Kid.Length > 128 || !string.IsNullOrEmpty(k.D)))
                        throw new AuthException(AuthFailure.Unavailable, AuthDiagnostic.JwksProfileInvalid);
                    var candidate = set.GetSigningKeys().ToArray(); if (candidate.Length != set.Keys.Count) throw new AuthException(AuthFailure.Unavailable, AuthDiagnostic.JwksProfileInvalid);
                    keys = candidate;
                    fetched = now;
                }
                catch (AuthException) when (now - fetched < TimeSpan.FromMinutes(10) && match.Length == 1) { return match; }
            }
            match = keys.Where(k => k.KeyId == kid).ToArray();
            if (now - fetched >= TimeSpan.FromMinutes(10)) throw new AuthException(AuthFailure.Unavailable, AuthDiagnostic.JwksUnavailable);
            if (match.Length != 1) throw new AuthException(AuthFailure.Invalid, AuthDiagnostic.JwksKeyNotFound);
            return match;
        }
        finally { gate.Release(); }
    }
    public void Dispose() { gate.Dispose(); GC.SuppressFinalize(this); }
}
