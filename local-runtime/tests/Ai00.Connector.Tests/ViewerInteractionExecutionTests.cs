using System.Text.Json;
using Ai00.Connector.AppHost;
using Xunit;
namespace Ai00.Connector.Tests;

public class ViewerInteractionExecutionTests
{
    [Fact] public async Task OutcomeDiskFailureReturnsUnknownAndRetainsAdmissionForQuery()
    {
        FileStream? locked=null;Rig? active=null;
        using var rig=new Rig(()=>{locked=new FileStream(active!.Journal.Path,FileMode.Open,FileAccess.ReadWrite,FileShare.None);return Task.FromResult<object>(new{});});
        active=rig;
        try
        {
            Assert.Equal("outcome_unknown",(await rig.Executor.ExecuteAsync(Rig.Request(),default)).status);
            Assert.Equal("outcome_unknown",rig.Executor.QueryRequest(new string('a',64),"r1")!.status);
            Assert.True(rig.Gate.IsQuarantined);Assert.Equal(1,rig.Writes);
        }
        finally{locked?.Dispose();}
    }
    [Fact] public async Task ProductionPlanWorkerHoldsTheSameGateAcrossBothSteps()
    {
        using var rig=new Rig();
        using var key=new Ai00.Connector.Contracts.V2.DeviceSigningKeyStore(rig.DirectoryPath).GetOrCreate();
        var plan=ProtocolV2VectorTests.Vector["plan"]!.DeepClone().AsObject();
        var second=plan["steps"]![0]!.DeepClone();second["step_id"]="step-00002";
        second["depends_on"]=System.Text.Json.Nodes.JsonNode.Parse("[\"step-00001\"]");
        plan["steps"]!.AsArray().Add(second);
        using(var cloud=ProtocolV2VectorTests.TestKey("plan"))ProtocolV2VectorTests.SignPlan(plan,cloud);
        var entered=new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var release=new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var calls=0;
        var adapter=new OutcomeUnknownRecoveryTests.FakeAdapter(async()=>{
            Assert.Null(rig.Gate.TryEnterInteractive());
            calls++;if(calls==1){entered.SetResult();await release.Task;}
            return new Ai00.Connector.Contracts.AdapterResult(true,new{connected=true});});
        var worker=new PlanExecutionWorker(new AppPlanJournal(Path.Combine(rig.DirectoryPath,"plans")),adapter,key,"device-key-001",
            new Dictionary<string,TrustedPlanKey>{{"cloud-plan-key-2026-09",new(ProtocolV2VectorTests.Vector["plan_public_jwk"]!.ToJsonString(),DateTimeOffset.Parse("2026-09-06T00:00:00Z"),DateTimeOffset.Parse("2026-09-08T00:00:00Z"),false)}},
            ()=>DateTimeOffset.Parse("2026-09-07T01:03:00Z"),viewerGate:rig.Gate);
        var running=worker.ExecuteAsync(OutcomeUnknownRecoveryTests.Lease() with{PlanJson=plan.ToJsonString()},OutcomeUnknownRecoveryTests.Session(),default);
        await entered.Task.WaitAsync(TimeSpan.FromSeconds(3));
        Assert.Equal("busy",(await rig.Executor.ExecuteAsync(Rig.Request(),default)).status);
        release.SetResult();Assert.Equal("succeeded",(await running).OverallStatus);Assert.Equal(2,calls);
        Assert.Equal("completed",(await rig.Executor.ExecuteAsync(Rig.Request(),default)).status);
    }
    internal sealed class Rig : IDisposable
    {
        internal readonly string DirectoryPath=Path.Combine(Path.GetTempPath(),"viewer-tests-"+Guid.NewGuid().ToString("N"));
        internal readonly ViewerExecutionGate Gate=new();
        internal readonly ViewerInteractionSession Session=new();
        internal readonly ViewerInteractionRuntimeContext Runtime=new();
        internal readonly ViewerInteractionJournal Journal;
        internal readonly ViewerInteractionExecutor Executor;
        internal int Writes;
        internal bool Visible=true;
        internal Rig(Func<Task<object>>? invoke=null,TimeSpan? timeout=null)
        {
            Directory.CreateDirectory(DirectoryPath);
            Journal=new(Path.Combine(DirectoryPath,"events.jsonl"));
            Runtime.Update(ViewerInteractionSessionTests.Runtime(),"key");
            Session.Install(ViewerInteractionSessionTests.Grant(),Runtime.Current,ViewerInteractionSessionTests.Now,TimeSpan.Zero);
            Executor=new(Session,Runtime,Gate,Journal,(_,_)=>true,
                (_,_,_,_,_,_)=>{Writes++;if(invoke is not null)return invoke();Visible=false;return Task.FromResult<object>(new{});},
                ()=>ViewerInteractionSessionTests.Now,()=>TimeSpan.Zero,timeout??TimeSpan.FromSeconds(1));
        }
        internal static ViewerInteractionRequest Request(string id="r1",int sequence=1,string targets="[\"ref1\"]")=>ViewerInteractionProtocol.ParseRequest(JsonSerializer.Serialize(new{
            type="execute",request_id=id,interaction_id=new string('a',64),sequence,structure_epoch=1,
            operation_id="vismockup.node.visibility.change@1",targets=JsonSerializer.Deserialize<JsonElement>(targets),arguments=new{action="hide"}}));
        public void Dispose()=>Directory.Delete(DirectoryPath,true);
    }
    [Fact] public async Task WholePlanGateRejectsInteractionWithoutWriting()
    {
        using var rig=new Rig();using var held=await rig.Gate.EnterPlanAsync(default);
        Assert.Equal("busy",(await rig.Executor.ExecuteAsync(Rig.Request(),default)).status);
        Assert.True(rig.Visible);Assert.Equal(0,rig.Writes);
    }
    [Fact] public async Task AcceptedDuplicateReturnsRetainedOutcomeAndConflictCannotWrite()
    {
        using var rig=new Rig();var request=Rig.Request();
        var first=await rig.Executor.ExecuteAsync(request,default);
        Assert.Equal("completed",first.status);Assert.False(rig.Visible);
        Assert.Equal(first,await rig.Executor.ExecuteAsync(request,default));Assert.Equal(1,rig.Writes);
        Assert.Equal("request_id_conflict",(await rig.Executor.ExecuteAsync(Rig.Request(sequence:2),default)).error_code);
        Assert.Equal("sequence_stale",(await rig.Executor.ExecuteAsync(Rig.Request("r2"),default)).error_code);
    }
    [Fact] public async Task UnknownStopsBatchAndQuarantinesPlansEvenAfterLateCompletion()
    {
        var pending=new TaskCompletionSource<object>(TaskCreationOptions.RunContinuationsAsynchronously);
        using var rig=new Rig(()=>pending.Task,TimeSpan.FromMilliseconds(30));
        var result=await rig.Executor.ExecuteAsync(Rig.Request(targets:"[\"ref1\",\"ref2\"]"),default);
        Assert.Equal("outcome_unknown",result.status);Assert.Equal(1,rig.Writes);
        Assert.Contains("not_started",JsonSerializer.Serialize(result.result));
        pending.SetResult(new{});
        Assert.Equal("runtime_quarantined",(await rig.Executor.ExecuteAsync(Rig.Request("r2",2),default)).error_code);
        await Assert.ThrowsAsync<InvalidDataException>(async()=>{using var lease=await rig.Gate.EnterPlanAsync(default);});
        Assert.Equal(result,rig.Executor.QueryRequest(new string('a',64),"r1"));
    }
    [Fact] public async Task AdmissionFailurePreventsAdapterDispatch()
    {
        using var rig=new Rig();using var locked=new FileStream(rig.Journal.Path,FileMode.OpenOrCreate,FileAccess.ReadWrite,FileShare.None);
        Assert.Equal("journal_unavailable",(await rig.Executor.ExecuteAsync(Rig.Request(),default)).error_code);
        Assert.Equal(0,rig.Writes);
    }
    [Fact] public async Task KnownNoEffectIsRejectedAndDoesNotQuarantine()
    {
        using var rig=new Rig(()=>throw new Ai00.Connector.Contracts.ConnectorNoEffectException("node_unmapped"));
        Assert.Equal("rejected",(await rig.Executor.ExecuteAsync(Rig.Request(),default)).status);
        Assert.False(rig.Gate.IsQuarantined);
    }
}
