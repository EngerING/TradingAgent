using System.Reflection;
using System.Reflection.Metadata;
using System.Reflection.PortableExecutable;
using TradingAgent.Identity.Migrations;
using TradingAgent.Identity.Persistence;
using Xunit;

namespace TradingAgent.Identity.Tests;

public sealed class IsolationTests
{
    private static readonly string[] DeniedTypes = ["System.Diagnostics.Process", "System.Net.Http.HttpClient", "System.Net.Http.IHttpClientFactory", "System.IO.File", "System.IO.FileStream"];
    [Fact]
    public void ProductAssembliesReferenceNoFinancialEngineOrExecutionMechanism()
    {
        foreach (var assembly in new[] { typeof(SessionRepository).Assembly, typeof(MigrationRunner).Assembly })
        {
            Assert.DoesNotContain(assembly.GetReferencedAssemblies(), x => x.Name!.StartsWith("TradingAgent.", StringComparison.Ordinal) && x.Name != "TradingAgent.Identity.Persistence");
            using var stream = File.OpenRead(assembly.Location); using var pe = new PEReader(stream); var metadata = pe.GetMetadataReader();
            foreach (var handle in metadata.TypeReferences)
            {
                var type = metadata.GetTypeReference(handle); var name = metadata.GetString(type.Namespace) + "." + metadata.GetString(type.Name);
                Assert.DoesNotContain(name, DeniedTypes);
                Assert.DoesNotContain("ibapi", name, StringComparison.OrdinalIgnoreCase); Assert.DoesNotContain("Python", name, StringComparison.OrdinalIgnoreCase);
            }
            foreach (var handle in metadata.MethodDefinitions)
                Assert.Equal((MethodAttributes)0, metadata.GetMethodDefinition(handle).Attributes & MethodAttributes.PinvokeImpl);
        }
    }
    [Fact]
    public void CredentialsCannotBeSubstitutedAcrossRepositoryInterfaces()
    {
        var target = new DisposableTarget("127.0.0.1", 39871, "m012_test_" + Guid.NewGuid().ToString("N"));
        var runtime = new SecurityDatabase(target, "fixture", "public-test-only", DatabasePurpose.Runtime);
        Assert.Throws<ArgumentException>(() => new SessionIssuer(runtime, new UnavailableIdentityVerifier()));
        Assert.Throws<ArgumentException>(() => new IdentityAdministration(runtime, EnvironmentScope.Paper));
        Assert.DoesNotContain("public-test-only", runtime.ToString(), StringComparison.Ordinal);
    }
}
