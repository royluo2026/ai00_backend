using System.Text.Json;
using System.Text.Json.Nodes;
using System.Reflection;
using Ai00.Connector.Adapters.VisMockup;
using Ai00.Connector.AppHost;
using Ai00.Connector.Contracts;
using Ai00.Connector.Contracts.V2;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class CacheBatchPlanExecutionTests : IDisposable
{
    private static readonly DateTimeOffset Now=DateTimeOffset.Parse("2026-09-07T01:03:00Z");
    private readonly string root=Path.Combine(Path.GetTempPath(),"ai00-cache-batch-plan-"+Guid.NewGuid().ToString("N"));

    [Fact]
    public async Task DefiniteFailureOfOneFileDoesNotStopLaterBatchMembers()
    {
        using var key=TestDeviceKey();
        var adapter=new BatchAdapter(failFirstFile:true,oversize:false);
        var journal=new AppPlanJournal(Path.Combine(root,"journal"));
        var worker=Worker(journal,adapter,key);
        var outcome=await worker.ExecuteAsync(Lease(BatchPlan()),Session(),CancellationToken.None);

        Assert.Equal("failed_without_effect",outcome.OverallStatus);
        Assert.Equal(new[]{"step-00001","step-00002","step-00003"},adapter.Seen.Select(item=>item.StepId));
        Assert.Equal(new[]{"succeeded","failed_without_effect","succeeded"},outcome.Steps.EnumerateArray().Select(item=>item.GetProperty("status").GetString()));
        Assert.False(worker.ExecutionQuarantined);
    }

    [Fact]
    public async Task OversizePreflightRetainsSizesAndNeverInvokesFileFetch()
    {
        using var key=TestDeviceKey();
        var adapter=new BatchAdapter(failFirstFile:false,oversize:true);
        var outcome=await Worker(new AppPlanJournal(Path.Combine(root,"journal")),adapter,key)
            .ExecuteAsync(Lease(BatchPlan()),Session(),CancellationToken.None);

        Assert.Equal("failed_without_effect",outcome.OverallStatus);
        var preflight=Assert.Single(outcome.Steps.EnumerateArray());
        Assert.Equal("failed_without_effect",preflight.GetProperty("status").GetString());
        Assert.Equal("cache_file_batch_size_exceeded",preflight.GetProperty("error_code").GetString());
        Assert.Equal(100*1024*1024+1,preflight.GetProperty("result").GetProperty("total_byte_length").GetInt64());
        Assert.Single(adapter.Seen);
    }

    private static PlanExecutionWorker Worker(AppPlanJournal journal,BatchAdapter adapter,DeviceSigningKey key)=>new(
        journal,adapter,key,"device-key-001",
        new Dictionary<string,TrustedPlanKey>{{"cloud-plan-key-2026-09",new(ProtocolV2VectorTests.Vector["plan_public_jwk"]!.ToJsonString(),Now.AddDays(-1),Now.AddDays(1),false)}},
        ()=>Now,captureUploader:new FakeUploader());

    private static RuntimeSession Session()=>new("device-001","tenant-001",7,"runtime-instance-001","session-secret",Now.AddMinutes(3));
    private static LeasedPlan Lease(JsonObject plan)=>new("lease-002",Now.AddMinutes(2),plan.ToJsonString());
    private static DeviceSigningKey TestDeviceKey()
    {
        var constructor=typeof(DeviceSigningKey).GetConstructors(BindingFlags.Instance|BindingFlags.NonPublic).Single();
        return (DeviceSigningKey)constructor.Invoke([ProtocolV2VectorTests.TestKey("device")]);
    }

    private static JsonObject BatchPlan()
    {
        var plan=ProtocolV2VectorTests.Vector["plan"]!.DeepClone().AsObject();
        plan["capability_id"]="simulation.model_cache.file.fetch.batch.request";
        var template=plan["steps"]![0]!.AsObject();
        JsonObject Step(string id,string operation,string hash,JsonNode payload,JsonArray dependencies)
        {
            var step=template.DeepClone().AsObject();
            step["step_id"]=id;step["operation_id"]=operation;step["contract_hash"]=hash;
            step["depends_on"]=dependencies;step["payload"]=payload;
            step["payload_hash"]="sha256:"+Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(CanonicalJsonV2.Serialize(JsonSerializer.Serialize(payload)))).ToLowerInvariant();
            step["side_effect_classification"]="read";step["post_condition_probe_id"]=null;
            return step;
        }
        var identity=JsonNode.Parse("""{"batch_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","generation":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","snapshot_hash":null,"schema_version":1}""")!;
        var source=JsonNode.Parse("""{"endpoint_id":"tc-production","object_uid":"item","item_revision_uid":"revision","bom_view_uid":"","revision_rule":"Latest Working","configuration_date":"2026-09-28T00:00:00Z"}""")!;
        var files=new JsonArray();
        for(var index=2;index<=3;index++)files.Add(new JsonObject
        {
            ["step_id"]=$"step-{index:00000}",["node_key"]=$"node-{index}",["item_revision_uid"]=$"revision-{index}",
            ["file_ref"]=new JsonObject{{"dataset_uid", $"dataset-{index}"},{"file_uid", $"file-{index}"},{"file_name", $"file-{index}.jt"},{"relation_type","IMAN_Rendering"}}
        });
        var steps=new JsonArray
        {
            Step("step-00001","teamcenter.model_files.size.preflight@1","sha256:ed99a125e673f46071a961e1a6a63eadc4b0268a88a9584b9484dee13cfcefa1",
                new JsonObject{{"identity",identity},{"source_selector",source},{"files",files}},new JsonArray()),
            Step("step-00002","teamcenter.model_file.fetch@1","sha256:5b41a02106977a8e06cbc4c052e9097057b385bce1d7b96f46e490196d29d1b7",
                JsonNode.Parse("""{"batch_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","generation":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","snapshot_hash":null,"schema_version":1,"node_key":"node-2","item_revision_uid":"revision-2","source_selector":{"endpoint_id":"tc-production","object_uid":"item","item_revision_uid":"revision","bom_view_uid":"","revision_rule":"Latest Working","configuration_date":"2026-09-28T00:00:00Z"},"file_ref":{"dataset_uid":"dataset-2","file_uid":"file-2","file_name":"file-2.jt","relation_type":"IMAN_Rendering"},"expected_content_hash":null,"artifact_resource_refs":["simulation://model-cache/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]}""")!,new JsonArray("step-00001")),
            Step("step-00003","teamcenter.model_file.fetch@1","sha256:5b41a02106977a8e06cbc4c052e9097057b385bce1d7b96f46e490196d29d1b7",
                JsonNode.Parse("""{"batch_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","generation":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","snapshot_hash":null,"schema_version":1,"node_key":"node-3","item_revision_uid":"revision-3","source_selector":{"endpoint_id":"tc-production","object_uid":"item","item_revision_uid":"revision","bom_view_uid":"","revision_rule":"Latest Working","configuration_date":"2026-09-28T00:00:00Z"},"file_ref":{"dataset_uid":"dataset-3","file_uid":"file-3","file_name":"file-3.jt","relation_type":"IMAN_Rendering"},"expected_content_hash":null,"artifact_resource_refs":["simulation://model-cache/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]}""")!,new JsonArray("step-00001")),
        };
        plan["steps"]=steps;
        using var cloud=ProtocolV2VectorTests.TestKey("plan");ProtocolV2VectorTests.SignPlan(plan,cloud);
        return plan;
    }

    private sealed class BatchAdapter(bool failFirstFile,bool oversize):IConnectorAdapter
    {
        private const string PreflightHash="sha256:ed99a125e673f46071a961e1a6a63eadc4b0268a88a9584b9484dee13cfcefa1";
        private const string FetchHash="sha256:5b41a02106977a8e06cbc4c052e9097057b385bce1d7b96f46e490196d29d1b7";
        internal List<AdapterOperation> Seen{get;}=[];
        public AdapterManifest Manifest{get;}=new("ai00.vismockup",1,"siemens.vismockup","14.2.0",[new("teamcenter.model_files.size.preflight@1",PreflightHash),new("teamcenter.model_file.fetch@1",FetchHash)]);
        public Task<AdapterHealth> ProbeAsync(CancellationToken ct)=>Task.FromResult(new AdapterHealth(true,"ready",true,true,"14.2.0"));
        public Task<AdapterResult> ExecuteAsync(AdapterOperation operation,CancellationToken ct)
        {
            Seen.Add(operation);
            if(operation.OperationId=="teamcenter.model_files.size.preflight@1")
            {
                var sizeA=oversize?50L*1024*1024:32L;var sizeB=oversize?50L*1024*1024+1:32L;var total=sizeA+sizeB;
                var preflightIdentity=JsonDocument.Parse("""{"batch_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","generation":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","snapshot_hash":null,"schema_version":1}""").RootElement.Clone();
                return Task.FromResult(new AdapterResult(true,JsonSerializer.SerializeToElement(new{identity=preflightIdentity,files=new[]{new{step_id="step-00002",node_key="node-2",item_revision_uid="revision-2",file_ref=new{dataset_uid="dataset-2",file_uid="file-2",file_name="file-2.jt",relation_type="IMAN_Rendering"},file_size=sizeA},new{step_id="step-00003",node_key="node-3",item_revision_uid="revision-3",file_ref=new{dataset_uid="dataset-3",file_uid="file-3",file_name="file-3.jt",relation_type="IMAN_Rendering"},file_size=sizeB}},total_byte_length=total,error_code=oversize?"cache_file_batch_size_exceeded":null})));
            }
            if(failFirstFile&&operation.StepId=="step-00002")throw new ConnectorNoEffectException("teamcenter_file_download_failed");
            var payload=operation.Payload;var artifactIdentity=JsonSerializer.SerializeToElement(new{batch_id=payload.GetProperty("batch_id").GetString(),generation=payload.GetProperty("generation").GetString(),snapshot_hash=(string?)null,schema_version=1});
            return Task.FromResult(new AdapterResult(true,new LocalModelArtifact("missing.jt","model/jt",new string('a',64),32,
                artifactIdentity,payload.GetProperty("node_key").GetString()!,payload.GetProperty("item_revision_uid").GetString()!,payload.GetProperty("file_ref").Clone(),Now.ToString("O"))));
        }
    }

    private sealed class FakeUploader:IAppCaptureUploader
    {
        public Task<JsonElement> UploadAsync(string planId,string leaseId,string stepId,LocalCaptureArtifact capture,RuntimeSession session,CancellationToken ct)=>throw new NotSupportedException();
        public Task<JsonElement> UploadModelAsync(string planId,string leaseId,string stepId,LocalModelArtifact model,RuntimeSession session,CancellationToken ct)=>
            Task.FromResult(JsonSerializer.SerializeToElement(new{artifact_id="artifact-1",media_type="model/jt",sha256=model.Sha256,byte_size=model.ByteSize,version=1}));
    }

    public void Dispose(){if(Directory.Exists(root))Directory.Delete(root,true);}
}
