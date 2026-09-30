using System.Text.Json;
using Ai00.Connector.Adapters.VisMockup;
using Ai00.Connector.AppHost;
using Ai00.Connector.Contracts;
using Ai00.Connector.Contracts.V2;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class AppCaptureExecutionTests
{
    [Theory]
    [InlineData(false, "succeeded",false)]
    [InlineData(false, "succeeded",true)]
    [InlineData(true, "outcome_unknown",false)]
    [InlineData(true, "outcome_unknown",true)]
    public async Task CaptureOutcomeContainsUploadedArtifactOrQuarantinesAmbiguousUpload(bool failUpload,string expected,bool modelFile)
    {
        var root=Path.Combine(Path.GetTempPath(),"ai00-capture-execution-"+Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            using var key=new DeviceSigningKeyStore(root).GetOrCreate();
            var plan=ProtocolV2VectorTests.Vector["plan"]!.DeepClone().AsObject();
            var operation=modelFile?"teamcenter.model_file.fetch@1":"vismockup.view.capture@1";
            plan["steps"]![0]!["operation_id"]=operation;
            plan["steps"]![0]!["side_effect_classification"]="read";
            plan["steps"]![0]!["post_condition_probe_id"]=null;
            using var cloud=ProtocolV2VectorTests.TestKey("plan");
            ProtocolV2VectorTests.SignPlan(plan,cloud);
            var capture=new LocalCaptureArtifact(Path.Combine(root,"step.png"),"image/png",new string('a',64),32,1,1,1);
            if(modelFile&&!failUpload)
            {
                var copy=Path.Combine(root,"step.jt");File.WriteAllBytes(copy,new byte[32]);
                File.SetAttributes(copy,FileAttributes.ReadOnly);
            }
            var adapter=new OutcomeUnknownRecoveryTests.FakeAdapter(
                ()=>Task.FromResult(new AdapterResult(true,modelFile?new LocalModelArtifact(Path.Combine(root,"step.jt"),"model/jt",new string('a',64),32,JsonSerializer.SerializeToElement(new{batch_id=new string('b',32),generation=(string?)null,snapshot_hash=(string?)null,schema_version=1}),"node-1","revision-1",JsonSerializer.SerializeToElement(new{dataset_uid="dataset",file_uid="file",file_name="file.jt",relation_type="IMAN_Rendering"}),"2026-09-07T01:03:00Z"):capture)),operation);
            var uploader=new FakeUploader(failUpload);
            var worker=new PlanExecutionWorker(new AppPlanJournal(Path.Combine(root,"journal")),adapter,key,
                "device-key-001",new Dictionary<string,TrustedPlanKey>{{"cloud-plan-key-2026-09",
                    new(ProtocolV2VectorTests.Vector["plan_public_jwk"]!.ToJsonString(),
                        DateTimeOffset.Parse("2026-09-06T00:00:00Z"),DateTimeOffset.Parse("2026-09-08T00:00:00Z"),false)}},
                ()=>DateTimeOffset.Parse("2026-09-07T01:03:00Z"),null,uploader);

            var outcome=await worker.ExecuteAsync(OutcomeUnknownRecoveryTests.Lease() with{PlanJson=plan.ToJsonString()},
                OutcomeUnknownRecoveryTests.Session(),CancellationToken.None);

            Assert.Equal(expected,outcome.OverallStatus);
            Assert.Equal(failUpload,worker.ExecutionQuarantined);
            Assert.Equal(1,uploader.Calls);
            Assert.Equal("step-00001",uploader.StepId);
            if(!failUpload)
            {
                var result=outcome.Steps[0].GetProperty("result");
                Assert.Equal("uploaded-capture",result.GetProperty(modelFile?"artifact_ref":"artifact").GetProperty("artifact_id").GetString());
                Assert.DoesNotContain(root,outcome.ToJson());
                if(modelFile){Assert.False(File.Exists(Path.Combine(root,"step.jt")));Assert.Equal("sha256:"+new string('a',64),result.GetProperty("content_hash").GetString());Assert.Equal(32,result.GetProperty("byte_length").GetInt64());Assert.False(result.GetProperty("captured_bytes_verified").GetBoolean());}
            }
        }
        finally{Directory.Delete(root,true);}
    }

    private sealed class FakeUploader(bool fail) : IAppCaptureUploader
    {
        public int Calls {get;private set;}
        public string? StepId {get;private set;}
        public Task<JsonElement> UploadModelAsync(string planId,string leaseId,string stepId,
            LocalModelArtifact model,RuntimeSession session,CancellationToken ct)
        {
            Calls++;StepId=stepId;
            if(fail)throw new HttpRequestException("receipt_lost");
            return Task.FromResult(JsonSerializer.SerializeToElement(new{artifact_id="uploaded-capture",media_type="model/jt",sha256=model.Sha256,byte_size=model.ByteSize,version=1}));
        }
        public Task<JsonElement> UploadAsync(string planId,string leaseId,string stepId,
            LocalCaptureArtifact capture,RuntimeSession session,CancellationToken ct)
        {
            Calls++;StepId=stepId;
            if(fail)throw new HttpRequestException("receipt_lost");
            return Task.FromResult(JsonSerializer.SerializeToElement(new{artifact_id="uploaded-capture"}));
        }
    }
}
