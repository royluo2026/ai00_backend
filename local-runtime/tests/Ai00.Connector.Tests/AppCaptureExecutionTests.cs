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
    [InlineData(false, "succeeded")]
    [InlineData(true, "outcome_unknown")]
    public async Task CaptureOutcomeContainsUploadedArtifactOrQuarantinesAmbiguousUpload(bool failUpload,string expected)
    {
        var root=Path.Combine(Path.GetTempPath(),"ai00-capture-execution-"+Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            using var key=new DeviceSigningKeyStore(root).GetOrCreate();
            var plan=ProtocolV2VectorTests.Vector["plan"]!.DeepClone().AsObject();
            plan["steps"]![0]!["operation_id"]="vismockup.view.capture@1";
            plan["steps"]![0]!["side_effect_classification"]="read";
            plan["steps"]![0]!["post_condition_probe_id"]=null;
            using var cloud=ProtocolV2VectorTests.TestKey("plan");
            ProtocolV2VectorTests.SignPlan(plan,cloud);
            var capture=new LocalCaptureArtifact(Path.Combine(root,"step.png"),"image/png",new string('a',64),32,1,1,1);
            var adapter=new OutcomeUnknownRecoveryTests.FakeAdapter(
                ()=>Task.FromResult(new AdapterResult(true,capture)),"vismockup.view.capture@1");
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
                Assert.Equal("uploaded-capture",result.GetProperty("artifact").GetProperty("artifact_id").GetString());
                Assert.DoesNotContain(capture.Path,outcome.ToJson());
            }
        }
        finally{Directory.Delete(root,true);}
    }

    private sealed class FakeUploader(bool fail) : IAppCaptureUploader
    {
        public int Calls {get;private set;}
        public string? StepId {get;private set;}
        public Task<JsonElement> UploadAsync(string planId,string leaseId,string stepId,
            LocalCaptureArtifact capture,RuntimeSession session,CancellationToken ct)
        {
            Calls++;StepId=stepId;
            if(fail)throw new HttpRequestException("receipt_lost");
            return Task.FromResult(JsonSerializer.SerializeToElement(new{artifact_id="uploaded-capture"}));
        }
    }
}
