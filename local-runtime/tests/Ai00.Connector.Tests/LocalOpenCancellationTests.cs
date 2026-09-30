using Ai00.Connector.AppHost;
using Ai00.Connector.Contracts;
using Ai00.Connector.Contracts.V2;
using System.Text.Json;
using Xunit;
namespace Ai00.Connector.Tests;
public sealed class LocalOpenCancellationTests
{
    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task Plan_executor_records_no_effect_for_cancelled_pre_native_open(bool queued)
    {
        var root=Path.Combine(Path.GetTempPath(),"ai00-cancel-test-"+Guid.NewGuid().ToString("N"));
        try {
            var now=DateTimeOffset.Parse("2026-09-07T01:03:00Z");
            var id="vismockup-command-"+new string('a',64);
            var plan=ProtocolV2VectorTests.Vector["plan"]!.DeepClone().AsObject();
            plan["plan_id"]=id;
            var step=plan["steps"]![0]!.AsObject();step["operation_id"]="vismockup.model.open@3";
            step["contract_hash"]=CancelledAdapter.Hash;step["side_effect_classification"]="write";step["post_condition_probe_id"]="vismockup.document.identity@1";
            using var signing=ProtocolV2VectorTests.TestKey("plan");ProtocolV2VectorTests.SignPlan(plan,signing);
            using var device=(DeviceSigningKey)typeof(DeviceSigningKey).GetConstructors(System.Reflection.BindingFlags.Instance|System.Reflection.BindingFlags.NonPublic).Single().Invoke([ProtocolV2VectorTests.TestKey("device")]);
            var adapter=new CancelledAdapter();var cancels=new LocalOpenCancellation();
            if(queued)cancels.Cancel(id);
            var worker=new PlanExecutionWorker(new AppPlanJournal(Path.Combine(root,"journal")),adapter,device,"device-key-001",
                new Dictionary<string,TrustedPlanKey>{{"cloud-plan-key-2026-09",new(ProtocolV2VectorTests.Vector["plan_public_jwk"]!.ToJsonString(),now.AddDays(-1),now.AddDays(1),false)}},
                ()=>now,localOpenCancellation:cancels);
            var task=worker.ExecuteAsync(new("lease-002",now.AddMinutes(2),plan.ToJsonString()),new("device-001","tenant-001",7,"runtime-instance-001","session-secret",now.AddMinutes(3)),default);
            if(!queued){await Task.WhenAny(adapter.Started.Task,task).WaitAsync(TimeSpan.FromSeconds(5));if(task.IsCompleted)await task;cancels.Cancel(id);}
            var result=await task.WaitAsync(TimeSpan.FromSeconds(5));
            Assert.Equal("failed_without_effect",result.OverallStatus);
            Assert.Equal("cache_open_interrupted",result.Steps[0].GetProperty("error_code").GetString());
            Assert.Equal(queued?0:1,adapter.Calls);Assert.False(worker.ExecutionQuarantined);
        } finally {if(Directory.Exists(root))Directory.Delete(root,true);}
    }
    private sealed class CancelledAdapter:IConnectorAdapter
    {
        public const string Hash="sha256:ae5547ff86c1d537cefe34098c68c0e8bbbec1aa20df850996767022029bf4d3";
        public TaskCompletionSource Started{get;}=new(TaskCreationOptions.RunContinuationsAsynchronously);
        public int Calls;
        public AdapterManifest Manifest{get;}=new("ai00.vismockup",1,"siemens.vismockup","14.2.0",[new("vismockup.model.open@3",Hash)]);
        public Task<AdapterHealth> ProbeAsync(CancellationToken ct)=>Task.FromResult(new AdapterHealth(true,"ready",true,true,"14.2.0"));
        public async Task<AdapterResult> ExecuteAsync(AdapterOperation operation,CancellationToken ct)
        {
            Calls++;Started.SetResult();
            try{await Task.Delay(Timeout.Infinite,ct);}catch(OperationCanceledException){throw new ConnectorNoEffectException("cache_open_interrupted");}
            throw new InvalidOperationException("must not reach native open");
        }
    }
    [Fact]
    public void Control_request_only_accepts_an_exact_operation_id()
    {
        var id="vismockup-command-"+new string('a',64);
        var json=System.Text.Json.JsonSerializer.Serialize(new{type="cache_open_cancel",request_id="tc-"+new string('b',32),operation_id=id});
        Assert.Equal(id,Assert.IsType<CacheOpenCancelCommand>(TeamcenterControlProtocol.ParseRequest(json)).OperationId);
        Assert.ThrowsAny<Exception>(()=>TeamcenterControlProtocol.ParseRequest(json.Replace(id,"*")));
        Assert.ThrowsAny<Exception>(()=>TeamcenterControlProtocol.ParseRequest(json[..^1]+",\"payload\":{}}"));
    }
    [Fact]
    public void Cancellation_is_exact_and_covers_queued_and_running_opens()
    {
        var cancellations=new LocalOpenCancellation();var a="vismockup-command-"+new string('a',64);var b="vismockup-command-"+new string('b',64);
        cancellations.Cancel(a);
        using var first=cancellations.Begin(a,default);using var second=cancellations.Begin(b,default);
        Assert.True(first.Token.IsCancellationRequested);Assert.False(second.Token.IsCancellationRequested);
        cancellations.Cancel(b);Assert.True(second.Token.IsCancellationRequested);
        Assert.Throws<InvalidDataException>(()=>cancellations.Cancel("arbitrary"));
    }
}
