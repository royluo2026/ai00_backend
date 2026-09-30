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

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task CacheDependenciesUseBoundedParallelDownloadsAndStillAuthorizeCachedFiles(bool failDependency)
    {
        JsonObject Ref(string id,byte[] bytes)=>new(){["artifact_id"]=id,["media_type"]="model/jt",["sha256"]=Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant(),["byte_size"]=bytes.Length,["version"]=1};
        var artifacts=Enumerable.Range(0,9).ToDictionary(i=>"file"+i,i=>{var bytes=Encoding.UTF8.GetBytes("verified-file"+i);return(Ref("file"+i,bytes),bytes);});
        var dependencies=new JsonArray(Enumerable.Range(1,8).Select(i=>(JsonNode)new JsonObject{["package_path"]=$"dependencies/file{i}.jt",["artifact_ref"]=artifacts["file"+i].Item1.DeepClone()}).ToArray());
        var payload=new JsonObject{["artifact_ref"]=artifacts["file0"].Item1.DeepClone(),["package_dependencies"]=dependencies};
        var handler=new MultiArtifactHandler(artifacts){DelayMs=50,FailDependency=failDependency};
        var materializer=new AppArtifactMaterializer(new RuntimeTransport(new HttpClient(handler),new Uri("https://gateway.example.com/")),root);
        var step=Step("vismockup.model.open@2",payload);
        if(failDependency)
        {
            await Assert.ThrowsAnyAsync<Exception>(()=>materializer.MaterializeAsync("parallel","lease",step,OutcomeUnknownRecoveryTests.Session(),default));
            Assert.InRange(handler.MaximumConcurrent,2,4);Assert.True(handler.Cancelled>0);Assert.Equal(0,handler.Active);
            Assert.Empty(Directory.GetFiles(root,"*.partial-*",SearchOption.AllDirectories));return;
        }
        await materializer.MaterializeAsync("parallel","lease",step,OutcomeUnknownRecoveryTests.Session(),default);
        Assert.InRange(handler.MaximumConcurrent,2,4);Assert.Equal(9,handler.Downloads);
        await materializer.MaterializeAsync("parallel","lease",step,OutcomeUnknownRecoveryTests.Session(),default);
        Assert.Equal(9,handler.Downloads);Assert.Equal(18,handler.Grants);
    }

    [Theory]
    [InlineData(false,false)]
    [InlineData(true,false)]
    [InlineData(false,true)]
    public async Task NewCachePlansReuseVerifiedBytesAfterFreshGrantsAndRepairTampering(bool tamper,bool rejectGrant)
    {
        var bytes=Encoding.UTF8.GetBytes("shared-verified-bytes");
        JsonObject Ref(string id,string media)=>new(){["artifact_id"]=id,["media_type"]=media,["sha256"]=Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant(),["byte_size"]=bytes.Length,["version"]=1};
        var artifacts=Enumerable.Range(0,9).ToDictionary(i=>"file"+i,i=>(Ref("file"+i,i==0?"model/plmxml":"model/jt"),bytes));
        var dependencies=new JsonArray(Enumerable.Range(1,8).Select(i=>(JsonNode)new JsonObject{["package_path"]=$"dependencies/file{i}.jt",["artifact_ref"]=artifacts["file"+i].Item1.DeepClone()}).ToArray());
        var step=Step("vismockup.model.open@2",new JsonObject{["artifact_ref"]=artifacts["file0"].Item1.DeepClone(),["package_dependencies"]=dependencies});
        var handler=new MultiArtifactHandler(artifacts){DelayMs=30};
        AppArtifactMaterializer Materializer()=>new(new RuntimeTransport(new HttpClient(handler),new Uri("https://gateway.example.com/")),root);
        await Materializer().MaterializeAsync("first-plan","lease-a",step,OutcomeUnknownRecoveryTests.Session(),default);
        Assert.Equal(2,handler.Downloads);
        if(rejectGrant)
        {
            handler.RejectGrants=true;
            await Assert.ThrowsAnyAsync<Exception>(()=>Materializer().MaterializeAsync("second-plan","lease-b",step,OutcomeUnknownRecoveryTests.Session(),default));
            Assert.Equal(2,handler.Downloads);Assert.Equal(10,handler.Grants);
            Assert.Empty(Directory.GetFiles(Path.Combine(root,"second-plan"),"*",SearchOption.AllDirectories));return;
        }
        if(tamper)File.WriteAllText(Directory.GetFiles(Path.Combine(root,"shared-cache"),"*.jt").Single(),"tampered");
        var result=await Materializer().MaterializeAsync("second-plan","lease-b",step,OutcomeUnknownRecoveryTests.Session(),default);
        Assert.Equal(tamper?3:2,handler.Downloads);Assert.Equal(18,handler.Grants);
        var package=Path.GetDirectoryName(result.GetProperty("local_artifact_path").GetString())!;
        foreach(var file in Directory.GetFiles(Path.Combine(package,"dependencies")))Assert.Equal(bytes,await File.ReadAllBytesAsync(file));
        Assert.Empty(Directory.GetFiles(root,"*.partial-*",SearchOption.AllDirectories));
    }

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

    [Theory]
    [InlineData("vismockup.model.open@1")]
    [InlineData("vismockup.model.open@2")]
    public async Task FrozenEnvironmentStagesDependenciesBesideOneGeneratedTopLevelDocument(string operation)
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
            Step(operation, payload), OutcomeUnknownRecoveryTests.Session(), CancellationToken.None);

        var topPath = result.GetProperty("local_artifact_path").GetString()!;
        Assert.Equal(topBytes, await File.ReadAllBytesAsync(topPath));
        Assert.Equal(jtBytes, await File.ReadAllBytesAsync(Path.Combine(Path.GetDirectoryName(topPath)!, "dependencies", "0001-tool.jt")));
        Assert.Equal(operation=="vismockup.model.open@2",result.TryGetProperty("package_dependencies", out _));
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
        public int DelayMs,MaximumConcurrent,Downloads,Grants,Cancelled;
        public bool FailDependency,RejectGrants;
        public int Active=>active;
        private int active;
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            var parts = request.RequestUri!.AbsolutePath.Split('/', StringSplitOptions.RemoveEmptyEntries);
            var id = parts[^1] == "content" ? parts[^2] : parts[^1];
            var item = artifacts[id];
            if (parts[^1] == "content")
            {
                lock(this){active++;Downloads++;MaximumConcurrent=Math.Max(MaximumConcurrent,active);}
                try
                {
                    if(DelayMs>0)await Task.Delay(FailDependency && id is not ("file0" or "file1")?5000:DelayMs,cancellationToken);
                    if(FailDependency && id=="file1")throw new HttpRequestException("dependency_download_failed");
                    return new HttpResponseMessage(HttpStatusCode.OK) { Content = new ByteArrayContent(item.Bytes) };
                }
                catch(OperationCanceledException){Interlocked.Increment(ref Cancelled);throw;}
                finally{lock(this)active--;}
            }
            Interlocked.Increment(ref Grants);
            if(RejectGrants)return new HttpResponseMessage(HttpStatusCode.Forbidden){Content=new StringContent("{\"detail\":{\"code\":\"lease_rejected\"}}")};
            var body = new JsonObject { ["success"] = true, ["data"] = new JsonObject
            {
                ["artifact_ref"] = item.Ref.DeepClone(), ["download_url"] = $"/artifact/{id}/content",
            }};
            return new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(body.ToJsonString()) };
        }
    }

    public void Dispose() { if (Directory.Exists(root)) Directory.Delete(root, true); }
}
