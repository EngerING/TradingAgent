using System.Reflection;
using System.Reflection.Metadata;
using System.Reflection.PortableExecutable;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Routing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;
using TradingAgent.Identity.Persistence;
using TradingAgent.Identity.Supabase;
using TradingAgent.Identity.Tests;
using TradingAgent.Web.Auth;
using Xunit;

namespace TradingAgent.Auth.Tests;

[Collection("PostgreSQL")]
public sealed class IsolationTests(DatabaseFixture fixture)
{
    private static readonly string[] ForbiddenTypes = ["System.Diagnostics.Process", "System.IO.File", "System.IO.FileStream", "System.Runtime.InteropServices.NativeLibrary"];
    [Fact]
    public async Task IntegratedCompositionHasNoFinancialRoutesWorkersOrPersistentKeyStore()
    {
        await using var harness = new BrowserHarness(); await harness.StartAsync(fixture);
        Assert.IsType<EphemeralDataProtectionProvider>(harness.App.Services.GetRequiredService<IDataProtectionProvider>());
        var routes = harness.App.Services.GetServices<EndpointDataSource>().SelectMany(s => s.Endpoints).OfType<RouteEndpoint>().Select(e => e.RoutePattern.RawText).ToArray();
        Assert.DoesNotContain(routes, r => r!.Contains("orders", StringComparison.OrdinalIgnoreCase) || r.Contains("dashboard", StringComparison.OrdinalIgnoreCase) || r.Contains("admin", StringComparison.OrdinalIgnoreCase) || r.Contains("proxy", StringComparison.OrdinalIgnoreCase));
        foreach (var assembly in new[] { typeof(JwtVerifier).Assembly, typeof(PilotRuntime).Assembly })
        {
            Assert.DoesNotContain(assembly.GetReferencedAssemblies(), a => a.Name!.StartsWith("TradingAgent.", StringComparison.Ordinal) && a.Name is not ("TradingAgent.Identity.Persistence" or "TradingAgent.Identity.Supabase"));
            using var stream = File.OpenRead(assembly.Location); using var pe = new PEReader(stream); var metadata = pe.GetMetadataReader();
            foreach (var handle in metadata.TypeReferences)
            {
                var type = metadata.GetTypeReference(handle); var name = metadata.GetString(type.Namespace) + "." + metadata.GetString(type.Name);
                Assert.DoesNotContain(name, ForbiddenTypes); Assert.DoesNotContain("Python", name, StringComparison.OrdinalIgnoreCase); Assert.DoesNotContain("ibapi", name, StringComparison.OrdinalIgnoreCase);
            }
            foreach (var handle in metadata.MethodDefinitions) Assert.Equal((MethodAttributes)0, metadata.GetMethodDefinition(handle).Attributes & MethodAttributes.PinvokeImpl);
        }
    }
    [Fact]
    public async Task AliceBobSessionBindingsDoNotGrantCrossUserResourceAccess()
    {
        await using var alice = new BrowserHarness(); await alice.StartAsync(fixture); await alice.SignInAsync();
        await using var bob = new BrowserHarness(); await bob.StartAsync(fixture); await bob.SignInAsync();
        using var response = await bob.Browser.GetAsync($"/bff/probe/{alice.Resource}/Paper"); Assert.Equal(403, (int)response.StatusCode);
        // A cookie copied between independently composed vaults has no matching local capability.
        bob.Browser.Cookies["__Host-TradingAgent.Session"] = alice.Browser.Cookies["__Host-TradingAgent.Session"];
        using var copied = await bob.Browser.GetAsync("/bff/session"); Assert.Equal(401, (int)copied.StatusCode);
    }
    [Theory]
    [InlineData("http://tradingagent.test")]
    [InlineData("https://attacker.invalid")]
    public async Task NonHttpsOrWrongHostIsRejected(string origin)
    {
        await using var harness = new BrowserHarness(); await harness.StartAsync(fixture);
        using var client = harness.App.GetTestClient(); using var response = await client.GetAsync(origin + "/bff/csrf"); Assert.Equal(403, (int)response.StatusCode);
    }
    [Fact]
    public async Task LogoutWithUnavailableStorageRemovesLocalCapabilityWithoutClaimingCommit()
    {
        await using var harness = new BrowserHarness(); await harness.StartAsync(fixture); await harness.SignInAsync();
        var old = harness.Browser.Cookies["__Host-TradingAgent.Session"];
        await using var connection = await fixture.Database(DatabasePurpose.Runtime).OpenAsync(CancellationToken.None);
        await using var query = new Npgsql.NpgsqlCommand("SELECT session_user", connection); var login = (string)(await query.ExecuteScalarAsync())!;
        try
        {
            await using var owner = await fixture.OpenOwnerAsync(); await DatabaseFixture.ExecuteAsync(owner, $"ALTER ROLE {login} NOLOGIN");
            using var logout = await harness.Browser.PostAsync("/bff/auth/logout", new { }); Assert.Equal(503, (int)logout.StatusCode);
            Assert.False(harness.Browser.Cookies.ContainsKey("__Host-TradingAgent.Session"));
        }
        finally { await using var owner = await fixture.OpenOwnerAsync(); await DatabaseFixture.ExecuteAsync(owner, $"ALTER ROLE {login} LOGIN"); }
        harness.Browser.Cookies["__Host-TradingAgent.Session"] = old;
        using var stale = await harness.Browser.GetAsync("/bff/session"); Assert.Equal(401, (int)stale.StatusCode);
    }
}
