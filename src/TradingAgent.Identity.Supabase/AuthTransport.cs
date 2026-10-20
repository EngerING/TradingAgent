using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;

namespace TradingAgent.Identity.Supabase;

public sealed class AuthTransport(HttpClient client, AuthConfiguration configuration)
{
    public async Task<JsonDocument> SendAsync(HttpMethod method, string path, object? body, string? token, CancellationToken cancellationToken)
    {
        // Paths are internal fixed grammar. Never accept a URI or discovery hint from a JWT/browser.
        if (!path.StartsWith("/auth/v1/", StringComparison.Ordinal) || path.Contains("..", StringComparison.Ordinal) || path.Contains('#', StringComparison.Ordinal)) throw new InvalidOperationException("Closed Auth path required.");
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken); deadline.CancelAfter(TimeSpan.FromSeconds(3));
        using var request = new HttpRequestMessage(method, new Uri(configuration.Project, path));
        request.Headers.Add("apikey", configuration.PublicKey);
        if (token is not null) request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);
        if (body is not null) request.Content = JsonContent.Create(body);
        try
        {
            using var response = await client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, deadline.Token).ConfigureAwait(false);
            if ((int)response.StatusCode == 429) throw new AuthException(AuthFailure.RateLimited);
            if (response.StatusCode is HttpStatusCode.BadRequest or HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden or HttpStatusCode.UnprocessableEntity) throw new AuthException(AuthFailure.Invalid);
            if (!response.IsSuccessStatusCode || response.RequestMessage?.RequestUri?.GetLeftPart(UriPartial.Authority) != configuration.Project.GetLeftPart(UriPartial.Authority)) throw new AuthException(AuthFailure.Unavailable);
            if (path.StartsWith("/auth/v1/logout", StringComparison.Ordinal)) return JsonDocument.Parse("{}");
            if (response.Content.Headers.ContentLength > 65536 || response.Content.Headers.ContentType?.MediaType != "application/json") throw new AuthException(AuthFailure.Unavailable);
            await using var stream = await response.Content.ReadAsStreamAsync(deadline.Token).ConfigureAwait(false);
            using var memory = new MemoryStream(); var buffer = new byte[4096];
            while (true)
            {
                var count = await stream.ReadAsync(buffer, deadline.Token).ConfigureAwait(false); if (count == 0) break;
                if (memory.Length + count > 65536) throw new AuthException(AuthFailure.Unavailable);
                memory.Write(buffer, 0, count);
            }
            var document = JsonDocument.Parse(memory.ToArray(), new JsonDocumentOptions { MaxDepth = 16 });
            EnsureUnique(document.RootElement); return document;
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested) { throw new AuthException(AuthFailure.Unavailable); }
        catch (HttpRequestException) { throw new AuthException(AuthFailure.Unavailable); }
        catch (JsonException) { throw new AuthException(AuthFailure.Unavailable); }
    }
    internal static void EnsureUnique(JsonElement element)
    {
        if (element.ValueKind == JsonValueKind.Object)
        {
            var keys = new HashSet<string>(StringComparer.Ordinal);
            foreach (var property in element.EnumerateObject()) { if (!keys.Add(property.Name)) throw new JsonException("Duplicate property."); EnsureUnique(property.Value); }
        }
        else if (element.ValueKind == JsonValueKind.Array) foreach (var item in element.EnumerateArray()) EnsureUnique(item);
    }
}
public static class AuthServices
{
    public static IHttpClientBuilder AddSupabaseAuth(this IServiceCollection services, AuthConfiguration configuration)
    {
        ArgumentNullException.ThrowIfNull(services); ArgumentNullException.ThrowIfNull(configuration);
        services.AddSingleton(configuration); services.AddSingleton(TimeProvider.System); services.AddSingleton<JwksCache>(); services.AddSingleton<JwtVerifier>();
        services.AddTransient<SupabaseAuthClient>();
        return services.AddHttpClient<AuthTransport>(client => client.Timeout = TimeSpan.FromSeconds(4)).RemoveAllLoggers()
            .ConfigurePrimaryHttpMessageHandler(() => new SocketsHttpHandler { AllowAutoRedirect = false, UseCookies = false, UseProxy = false, MaxConnectionsPerServer = 8, ConnectTimeout = TimeSpan.FromSeconds(2), MaxResponseHeadersLength = 16 });
    }
}
