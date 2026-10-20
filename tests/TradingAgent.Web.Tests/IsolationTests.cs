using System.Collections.Concurrent;
using System.Diagnostics.Tracing;
using System.Reflection.Metadata;
using System.Reflection.PortableExecutable;
using System.Security.Claims;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Options;
using TradingAgent.Web.Security;
using Xunit;
using Xunit.Abstractions;

[assembly: CollectionBehavior(DisableTestParallelization = true)]

namespace TradingAgent.Web.Tests;

public sealed class IsolationTests(ITestOutputHelper output)
{
    [Fact]
    public async Task InMemoryHostAndUnavailablePortsMakeZeroSocketConnectionsOrDnsRequests()
    {
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(30));
        using var network = new NetworkActivity();
        await using (var app = WebHostFactory.Create(builder => builder.WebHost.UseTestServer()))
        {
            await app.StartAsync(deadline.Token);
            using var client = app.GetTestClient();
            using var health = await client.GetAsync("/health", deadline.Token);
            using var denied = await client.PostAsync("/api/orders", null, deadline.Token);
            Assert.Equal(200, (int)health.StatusCode);
            Assert.Equal(404, (int)denied.StatusCode);
            var verification = await app.Services.GetRequiredService<IExternalIdentityVerifier>()
                .VerifyAsync("invalid-public-fixture".AsMemory(), deadline.Token);
            Assert.Equal(IdentityVerificationStatus.Unavailable, verification.Status);
            Assert.Null(verification.Identity);
            Assert.Same(SessionView.Unavailable, await app.Services.GetRequiredService<IWebSessionReader>().GetCurrentAsync(deadline.Token));
            Assert.Equal(AccessDecision.Denied, await app.Services.GetRequiredService<IWebAuthorizer>()
                .CheckAsync(Guid.NewGuid(), WebCapability.ResearchRead, Guid.NewGuid(), deadline.Token));
            await app.StopAsync(deadline.Token);
        }
        Assert.Empty(network.Events);
        output.WriteLine("OUTBOUND_SOCKET_CONNECT_STARTS:0; DNS_RESOLUTION_STARTS:0 (in-memory host lifecycle only)");
    }

    [Fact]
    public async Task ContainerHasNoProviderSchemeBusinessWorkerOrOutboundClient()
    {
        ServiceDescriptor[] descriptors = [];
        string[] configurationSources = [];
        await using var app = WebHostFactory.Create(builder =>
        {
            descriptors = builder.Services.ToArray();
            configurationSources = builder.Configuration.Sources.Select(source => source.GetType().FullName!).ToArray();
            builder.WebHost.UseTestServer();
        });
        var schemes = await app.Services.GetRequiredService<IAuthenticationSchemeProvider>().GetAllSchemesAsync();
        Assert.Empty(schemes);
        Assert.Null(app.Services.GetService<IHttpClientFactory>());
        Assert.Null(app.Services.GetService<IDataProtectionProvider>());
        Assert.All(app.Services.GetServices<IHostedService>(), service =>
            Assert.Equal("Microsoft.AspNetCore.Hosting.GenericWebHostService", service.GetType().FullName));
        var forbidden = new[] { "Npgsql", "Supabase", "IBKR", "PaperFeed", "DashboardBroadcaster", "TradingAgent.Api",
            "TradingAgent.Infrastructure", "TradingAgent.Core", "Python", "OpenAI", "Kronos" };
        var registrations = descriptors.Select(descriptor => descriptor.ServiceType.FullName + " " + descriptor.ImplementationType?.FullName);
        foreach (var registration in registrations)
        {
            Assert.All(forbidden, name => Assert.DoesNotContain(name, registration, StringComparison.OrdinalIgnoreCase));
        }
        Assert.DoesNotContain(configurationSources, source => source.Contains("EnvironmentVariables", StringComparison.Ordinal));
        Assert.DoesNotContain(configurationSources, source => source.Contains("Json", StringComparison.Ordinal));
    }

    [Fact]
    public async Task DefaultAndFallbackPoliciesDenyEvenAnAuthenticatedPrincipal()
    {
        await using var app = WebHostFactory.Create(builder => builder.WebHost.UseTestServer());
        var policies = app.Services.GetRequiredService<IOptions<AuthorizationOptions>>().Value;
        var authorizer = app.Services.GetRequiredService<IAuthorizationService>();
        var principal = new ClaimsPrincipal(new ClaimsIdentity([new Claim(ClaimTypes.NameIdentifier, "public-fixture")], "fixture"));
        Assert.NotNull(policies.FallbackPolicy);
        Assert.False((await authorizer.AuthorizeAsync(principal, null, policies.FallbackPolicy)).Succeeded);
        Assert.False((await authorizer.AuthorizeAsync(principal, null, policies.DefaultPolicy)).Succeeded);
    }

    [Fact]
    public void CompiledHostHasNoOperationalOrOutboundOrFileWriteCapabilities()
    {
        // Inspect the shipped assembly, including compiler-generated endpoint delegates, not a source-text search.
        using var file = File.OpenRead(typeof(WebHostFactory).Assembly.Location);
        using var pe = new PEReader(file);
        var metadata = pe.GetMetadataReader();
        var references = metadata.AssemblyReferences.Select(handle => metadata.GetString(metadata.GetAssemblyReference(handle).Name));
        Assert.DoesNotContain(references, name => name.StartsWith("TradingAgent.", StringComparison.Ordinal));
        var forbidden = new[] { "System.Net.Sockets.", "System.Net.Http.HttpClient", "System.Net.Http.HttpMessageInvoker",
            "System.Diagnostics.Process", "System.IO.File", "System.IO.Directory", "System.IO.StreamWriter",
            "System.Runtime.InteropServices.NativeLibrary", "Microsoft.AspNetCore.SignalR.",
            "Microsoft.Extensions.Hosting.BackgroundService", "Npgsql.", "Supabase.", "Microsoft.EntityFrameworkCore." };
        foreach (var handle in metadata.TypeReferences)
        {
            var type = metadata.GetTypeReference(handle);
            var fullName = metadata.GetString(type.Namespace) + "." + metadata.GetString(type.Name);
            Assert.All(forbidden, prefix => Assert.False(fullName.StartsWith(prefix, StringComparison.Ordinal), fullName));
        }
        foreach (var handle in metadata.MemberReferences)
        {
            var member = metadata.GetMemberReference(handle);
            if (member.Parent.Kind != HandleKind.TypeReference) continue;
            var type = metadata.GetTypeReference((TypeReferenceHandle)member.Parent);
            var fullName = metadata.GetString(type.Namespace) + "." + metadata.GetString(type.Name);
            var method = metadata.GetString(member.Name);
            Assert.False(fullName == "System.Reflection.Assembly" && method.StartsWith("Load", StringComparison.Ordinal));
            Assert.False(fullName == "System.Reflection.MethodBase" && method == "Invoke");
            Assert.False(fullName == "System.Activator" && method == "CreateInstance");
        }
        Assert.All(metadata.MethodDefinitions, handle =>
            Assert.Equal(0, (int)(metadata.GetMethodDefinition(handle).Attributes & System.Reflection.MethodAttributes.PinvokeImpl)));
    }

    private sealed class NetworkActivity : EventListener
    {
        public ConcurrentQueue<string> Events { get; } = new();

        protected override void OnEventSourceCreated(EventSource eventSource)
        {
            if (eventSource.Name is "System.Net.Sockets" or "System.Net.NameResolution")
                EnableEvents(eventSource, EventLevel.LogAlways, EventKeywords.All);
        }

        protected override void OnEventWritten(EventWrittenEventArgs eventData)
        {
            if (eventData.EventName is "ConnectStart" or "ResolutionStart")
                Events.Enqueue(eventData.EventSource.Name + ":" + eventData.EventName);
        }
    }
}
