using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Ai00.Connector.AppHost;
using Ai00.Connector.Contracts.V2;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class AppArtifactMaterializerTests : IDisposable
{
    private readonly string root = Path.Combine(Path.GetTempPath(), "ai00-v2-artifact-" + Guid.NewGuid().ToString("N"));

    [Fact]
    public async Task DownloadsVerifiesAndProjectsOnlyAConnectorLocalPath()
    {
        var bytes = Encoding.UTF8.GetBytes("<PLMXML xmlns=\"http://www.plmxml.org/Schemas/PLMXMLSchema\"/>");
        var hash = Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
        var artifact = new JsonObject
        {
            ["artifact_id"] = "artifact_fixture_1", ["media_type"] = "application/plmxml+xml",
            ["sha256"] = hash, ["byte_size"] = bytes.Length, ["version"] = 1,
        };
        var step = Step("vismockup.model.open@1", new JsonObject { ["artifact_ref"] = artifact.DeepClone() });
        var handler = new ArtifactHandler(artifact, bytes);
        var materializer = new AppArtifactMaterializer(
            new RuntimeTransport(new HttpClient(handler), new Uri("https://gateway.example.com/")), root);

        var payload = await materializer.MaterializeAsync(
            "plan-002", "lease-002", step, OutcomeUnknownRecoveryTests.Session(), CancellationToken.None);

        var local = payload.GetProperty("local_artifact_path").GetString()!;
        Assert.StartsWith(Path.GetFullPath(root), local, StringComparison.OrdinalIgnoreCase);
        Assert.Equal(bytes, await File.ReadAllBytesAsync(local));
        Assert.False(payload.TryGetProperty("file_path", out _));
        Assert.Equal(1, handler.DownloadCount);

        await materializer.MaterializeAsync("plan-002", "lease-002", step, OutcomeUnknownRecoveryTests.Session(), CancellationToken.None);
        Assert.Equal(1, handler.DownloadCount);
    }

    [Fact]
    public async Task HashMismatchNeverPublishesThePartialFile()
    {
        var expected = Encoding.UTF8.GetBytes("expected");
        var artifact = new JsonObject
        {
            ["artifact_id"] = "artifact_fixture_2", ["media_type"] = "model/vnd.jt",
            ["sha256"] = Convert.ToHexString(SHA256.HashData(expected)).ToLowerInvariant(),
            ["byte_size"] = expected.Length, ["version"] = 1,
        };
        var materializer = new AppArtifactMaterializer(
            new RuntimeTransport(new HttpClient(new ArtifactHandler(artifact, Encoding.UTF8.GetBytes("tampered"))), new Uri("https://gateway.example.com/")), root);

        var error = await Assert.ThrowsAsync<Ai00.Connector.Contracts.ConnectorNoEffectException>(() =>
            materializer.MaterializeAsync("plan-002", "lease-002", Step("vismockup.model.insert@1", new JsonObject { ["artifact_ref"] = artifact.DeepClone() }), OutcomeUnknownRecoveryTests.Session(), CancellationToken.None));

        Assert.Equal("artifact_integrity_failed", error.Code);
        Assert.Empty(Directory.GetFiles(root));
    }

    [Fact]
    public async Task FrozenEnvironmentStagesDependenciesBesideOneGeneratedTopLevelDocument()
    {
        var topBytes = Encoding.UTF8.GetBytes("<PLMXML><ExternalFile location=\"dependencies/0001-tool.jt\"/></PLMXML>");
        var jtBytes = Encoding.UTF8.GetBytes("jt-data");
        JsonObject Ref(string id, string media, byte[] bytes) => new()
        {
            ["artifact_id"] = id, ["media_type"] = media,
            ["sha256"] = Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant(),
            ["byte_size"] = bytes.Length, ["version"] = 1,
        };
        var top = Ref("artifact_top", "application/plmxml+xml", topBytes);
        var dependency = Ref("artifact_tool", "model/vnd.jt", jtBytes);
        var payload = new JsonObject
        {
            ["artifact_ref"] = top.DeepClone(),
            ["package_dependencies"] = new JsonArray(new JsonObject
            {
                ["package_path"] = "dependencies/0001-tool.jt", ["artifact_ref"] = dependency.DeepClone(),
            }),
        };
        var handler = new MultiArtifactHandler(new Dictionary<string, (JsonObject Ref, byte[] Bytes)>
        {
            ["artifact_top"] = (top, topBytes), ["artifact_tool"] = (dependency, jtBytes),
        });
        var materializer = new AppArtifactMaterializer(
            new RuntimeTransport(new HttpClient(handler), new Uri("https://gateway.example.com/")), root);

        var result = await materializer.MaterializeAsync("plan-package", "lease-package",
            Step("vismockup.model.open@1", payload), OutcomeUnknownRecoveryTests.Session(), CancellationToken.None);

        var topPath = result.GetProperty("local_artifact_path").GetString()!;
        Assert.Equal(topBytes, await File.ReadAllBytesAsync(topPath));
        Assert.Equal(jtBytes, await File.ReadAllBytesAsync(Path.Combine(Path.GetDirectoryName(topPath)!, "dependencies", "0001-tool.jt")));
        Assert.False(result.TryGetProperty("package_dependencies", out _));
    }

    private static ConnectorStepV2 Step(string operation, JsonObject payload)
    {
        var plan = ProtocolV2VectorTests.Vector["plan"]!.DeepClone().AsObject();
        plan["steps"]![0]!["operation_id"] = operation;
        plan["steps"]![0]!["payload"] = payload;
        plan["steps"]![0]!["payload_hash"] = CanonicalJsonV2.Hash(JsonSerializer.SerializeToElement(payload));
        using var cloud = ProtocolV2VectorTests.TestKey("plan");
        ProtocolV2VectorTests.SignPlan(plan, cloud);
        return ExecutionPlanV2.ParseAndVerify(plan.ToJsonString(), ProtocolV2VectorTests.Vector["plan_public_jwk"]!.ToJsonString()).Steps[0];
    }

    private sealed class ArtifactHandler(JsonObject artifact, byte[] content) : HttpMessageHandler
    {
        public int DownloadCount { get; private set; }
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            if (request.RequestUri!.AbsolutePath.EndsWith("/content", StringComparison.Ordinal))
            {
                DownloadCount++;
                return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new ByteArrayContent(content) });
            }
            var body = new JsonObject { ["success"] = true, ["data"] = new JsonObject
            {
                ["artifact_ref"] = artifact.DeepClone(), ["download_url"] = "/artifact/content",
            }};
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(body.ToJsonString()) });
        }
    }

    private sealed class MultiArtifactHandler(Dictionary<string, (JsonObject Ref, byte[] Bytes)> artifacts) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            var parts = request.RequestUri!.AbsolutePath.Split('/', StringSplitOptions.RemoveEmptyEntries);
            var id = parts[^1] == "content" ? parts[^2] : parts[^1];
            var item = artifacts[id];
            if (parts[^1] == "content")
                return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new ByteArrayContent(item.Bytes) });
            var body = new JsonObject { ["success"] = true, ["data"] = new JsonObject
            {
                ["artifact_ref"] = item.Ref.DeepClone(), ["download_url"] = $"/artifact/{id}/content",
            }};
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(body.ToJsonString()) });
        }
    }

    public void Dispose() { if (Directory.Exists(root)) Directory.Delete(root, true); }
}
