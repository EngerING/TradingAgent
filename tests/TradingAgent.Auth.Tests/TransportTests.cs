using System.Net;
using System.Text;
using TradingAgent.Identity.Supabase;
using Xunit;

namespace TradingAgent.Auth.Tests;

public sealed class TransportTests
{
    [Theory]
    [InlineData(302, "application/json", "{}")]
    [InlineData(500, "text/html", "PRIVATE_ERROR")]
    [InlineData(200, "application/json", "{\"x\":1,\"x\":2}")]
    [InlineData(200, "text/html", "<script>private</script>")]
    public async Task RedirectErrorsDuplicateJsonAndWrongContentTypeAreRejected(int status, string type, string body)
    {
        using var handler = new ResponseHandler(status, type, body); using var client = new HttpClient(handler);
        var transport = new AuthTransport(client, AuthConfiguration.ForSimulation(new Uri("http://127.0.0.1:39873")));
        var error = await Assert.ThrowsAsync<AuthException>(() => transport.SendAsync(HttpMethod.Get, "/auth/v1/user", null, "private-fixture", CancellationToken.None));
        Assert.DoesNotContain("PRIVATE_ERROR", error.Message, StringComparison.Ordinal);
    }
    [Fact]
    public async Task OversizedResponseIsBoundedAndProviderRateLimitIsExplicit()
    {
        using var handler = new ResponseHandler(200, "application/json", new string('x', 65537)); using var client = new HttpClient(handler);
        await Assert.ThrowsAsync<AuthException>(() => new AuthTransport(client, AuthConfiguration.ForSimulation(new Uri("http://127.0.0.1:39873"))).SendAsync(HttpMethod.Get, "/auth/v1/user", null, null, CancellationToken.None));
        using var throttled = new ResponseHandler(429, "application/json", "{}"); using var other = new HttpClient(throttled);
        var error = await Assert.ThrowsAsync<AuthException>(() => new AuthTransport(other, AuthConfiguration.ForSimulation(new Uri("http://127.0.0.1:39873"))).SendAsync(HttpMethod.Get, "/auth/v1/user", null, null, CancellationToken.None));
        Assert.Equal(AuthFailure.RateLimited, error.Failure);
    }
    private sealed class ResponseHandler(int status, string type, string body) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken) => Task.FromResult(new HttpResponseMessage((HttpStatusCode)status) { RequestMessage = request, Content = new StringContent(body, Encoding.UTF8, type) });
    }
}
