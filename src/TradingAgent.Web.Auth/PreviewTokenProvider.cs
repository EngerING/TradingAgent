using System.Text.Json;
using TradingAgent.Identity.Supabase;

namespace TradingAgent.Web.Auth;

/// <summary>Rotating provider tokens remain strictly server-side in the disposable preview.</summary>
public sealed record PreviewTokenPair(AccessCredential Credential, string RefreshToken)
{
    public override string ToString() => "[REDACTED_PREVIEW_TOKEN_PAIR]";
}

public interface IPreviewTokenProvider
{
    Task<PreviewTokenPair> PasswordAsync(string email, string password, CancellationToken cancellationToken);
    Task<PreviewTokenPair> RefreshAsync(string refreshToken, CancellationToken cancellationToken);
    Task CheckAsync(AccessCredential credential, CancellationToken cancellationToken);
    Task LogoutAsync(AccessCredential credential, CancellationToken cancellationToken);
}

public sealed class PreviewTokenProvider(AuthTransport transport, JwtVerifier verifier, SupabaseAuthClient provider) : IPreviewTokenProvider
{
    public async Task<PreviewTokenPair> PasswordAsync(string email, string password, CancellationToken ct)
    {
        using var response = await transport.SendAsync(HttpMethod.Post, "/auth/v1/token?grant_type=password",
            new { email, password }, null, ct).ConfigureAwait(false);
        return await ParseAsync(response, ct).ConfigureAwait(false);
    }
    public async Task<PreviewTokenPair> RefreshAsync(string refreshToken, CancellationToken ct)
    {
        if (string.IsNullOrWhiteSpace(refreshToken) || refreshToken.Length > 4096)
            throw new AuthException(AuthFailure.Invalid);
        using var response = await transport.SendAsync(HttpMethod.Post, "/auth/v1/token?grant_type=refresh_token",
            new { refresh_token = refreshToken }, null, ct).ConfigureAwait(false);
        return await ParseAsync(response, ct).ConfigureAwait(false);
    }
    private async Task<PreviewTokenPair> ParseAsync(JsonDocument response, CancellationToken ct)
    {
        try
        {
            var root = response.RootElement;
            if (root.GetProperty("token_type").GetString() != "bearer") throw new AuthException(AuthFailure.Invalid);
            var accessToken = root.GetProperty("access_token").GetString();
            var refreshToken = root.GetProperty("refresh_token").GetString();
            if (string.IsNullOrEmpty(accessToken) || string.IsNullOrWhiteSpace(refreshToken) ||
                refreshToken.Length is < 8 or > 4096) throw new AuthException(AuthFailure.Invalid);
            var identity = await verifier.ValidateAsync(accessToken, ct).ConfigureAwait(false);
            if (identity.Aal is < 1 or > 2) throw new AuthException(AuthFailure.Invalid);
            var access = new AccessCredential(accessToken, identity);
            await provider.CheckUserAsync(access, ct).ConfigureAwait(false);
            return new(access, refreshToken);
        }
        catch (Exception ex) when (ex is KeyNotFoundException or InvalidOperationException or FormatException)
        { throw new AuthException(AuthFailure.Unavailable); }
    }
    public async Task CheckAsync(AccessCredential credential, CancellationToken ct)
    {
        var validated = await verifier.ValidateAsync(credential.Token, ct).ConfigureAwait(false);
        if (validated != credential.Identity || validated.Aal is < 1 or > 2)
            throw new AuthException(AuthFailure.Invalid);
        await provider.CheckUserAsync(credential, ct).ConfigureAwait(false);
    }
    public Task LogoutAsync(AccessCredential credential, CancellationToken ct) => provider.LogoutAsync(credential, ct);
}
