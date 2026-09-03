using Ai00.Connector.Contracts;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class AdapterManifestTests
{
    [Fact]
    public void ManifestRequiresExactOperationContractHash()
    {
        var manifest = new AdapterManifest(
            "ai00.vismockup", 1, "siemens.vismockup", "14.2.0",
            [new AdapterOperationContract("vismockup.application.probe@1", "sha256:" + new string('a', 64))]);

        Assert.True(manifest.Supports("vismockup.application.probe@1", "sha256:" + new string('a', 64)));
        Assert.False(manifest.Supports("vismockup.application.probe@1", "sha256:" + new string('b', 64)));
        Assert.False(manifest.Supports("vismockup.raw.com@1", "sha256:" + new string('a', 64)));
    }

    [Fact]
    public void BuiltInManifestIsLoadedOnlyAfterTrustVerification()
    {
        var verifier = new RecordingVerifier();
        var loader = new AdapterManifestLoader(verifier, []);
        var manifest = loader.LoadBuiltIn(typeof(AdapterManifestTests).Assembly, "Ai00.Connector.Tests.vismockup.adapter.json");

        Assert.Equal("ai00.vismockup", manifest.AdapterId);
        Assert.True(verifier.Called);
    }

    private sealed class RecordingVerifier : IAdapterSignatureVerifier
    {
        public bool Called { get; private set; }
        public void RequireTrusted(AdapterManifest manifest, string assemblyPath) => Called = true;
    }
}
