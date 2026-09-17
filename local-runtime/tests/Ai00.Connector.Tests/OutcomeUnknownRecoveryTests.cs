using Ai00.Connector.AppHost;
using Ai00.Connector.Contracts;
using Ai00.Connector.Contracts.V2;
using System.Text.Json;
using System.Text.Json.Nodes;
using Xunit;
namespace Ai00.Connector.Tests;
public sealed class OutcomeUnknownRecoveryTests : IDisposable
{
    private readonly string root = Path.Combine(Path.GetTempPath(), "ai00-app-test-" + Guid.NewGuid().ToString("N"));
    private static readonly DateTimeOffset Now = DateTimeOffset.Parse("2026-09-07T01:03:00Z");
    [Theory] [InlineData(false)] [InlineData(true)]
    public async Task LostAckRestartResendsExactSignedOutcomeWithoutCom(bool expired)
    {
        using var key=new DeviceSigningKeyStore(root).GetOrCreate();
        var journal=new AppPlanJournal(Path.Combine(root,"journal"));
        var adapter=new FakeAdapter(()=>Task.FromResult(new AdapterResult(true,new{connected=true})));
        var outcome=await Worker(journal,adapter,key).ExecuteAsync(Lease(),Session(),CancellationToken.None);
        var credentials=new AppCredentialStore(root,new Uri("https://gateway.example.com"));
        credentials.SaveSession(Session());
        var first=new AcceptedThenDisconnected();using var http=new HttpClient(first);
        var transport=new RuntimeTransport(http,new Uri("https://gateway.example.com"));
        Assert.False(await new OutcomeDelivery(transport,journal).TryDeliverAsync(outcome,Session(),false,CancellationToken.None));
        Assert.DoesNotContain(journal.Events,e=>e.Kind=="acknowledged");
        var reopened=new AppPlanJournal(journal.Path);
        var saved=Assert.Single(Worker(reopened,adapter,key).Recover());
        var restored=new AppCredentialStore(root,new Uri("https://gateway.example.com")).LoadSession()!;
        Assert.Equal(Session(),restored);
        var recoveryRegistrations=0;
        await new OutcomeDelivery(transport,reopened,()=>expired?Now.AddDays(1):Now).DeliverAsync(saved,restored,_=>
        {
            recoveryRegistrations++;
            return Task.FromResult(restored with{InstanceId="recovery-instance",Token="recovery-secret",ExpiresAt=Now.AddDays(2)});
        },CancellationToken.None);
        Assert.Equal(expired?1:0,recoveryRegistrations);
        Assert.Equal(first.Bodies[0],first.Bodies[1]);
        Assert.Equal(outcome.ToJson(),first.Bodies[1]);
        Assert.EndsWith(expired?"/acknowledge":"/outcome",first.Paths[1]);
        Assert.Empty(Worker(new AppPlanJournal(journal.Path),adapter,key).Recover());
        Assert.Equal(1,adapter.Calls);
    }
    private sealed class AcceptedThenDisconnected:HttpMessageHandler
    {
        public List<string> Bodies{get;}=[];public List<string> Paths{get;}=[];
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken ct)
        {
            Bodies.Add(await request.Content!.ReadAsStringAsync(ct));Paths.Add(request.RequestUri!.AbsolutePath);
            if(Bodies.Count==1)throw new HttpRequestException("server accepted but ACK connection lost");
            return new HttpResponseMessage(System.Net.HttpStatusCode.OK){Content=new StringContent("{\"success\":true,\"data\":{\"accepted\":true,\"already_applied\":true}}")};
        }
    }
    [Fact] public async Task TimeoutBecomesOutcomeUnknownAndStopsLaterSteps()
    {
        using var key = new DeviceSigningKeyStore(root).GetOrCreate();
        var plan=ProtocolV2VectorTests.Vector["plan"]!.DeepClone().AsObject();
        plan["steps"]![0]!["timeout_seconds"]=1;
        plan["steps"]![0]!["side_effect_classification"]="write";
        plan["steps"]![0]!["post_condition_probe_id"]="vismockup.application.probe@1";
        var second=plan["steps"]![0]!.DeepClone();second["step_id"]="step-00002";
        plan["steps"]!.AsArray().Add(second);
        using var cloud=ProtocolV2VectorTests.TestKey("plan");ProtocolV2VectorTests.SignPlan(plan,cloud);
        var adapter=new FakeAdapter(()=>new TaskCompletionSource<AdapterResult>().Task);
        var worker=Worker(new AppPlanJournal(Path.Combine(root,"journal")),adapter,key);
        var outcome=await worker.ExecuteAsync(Lease() with{PlanJson=plan.ToJsonString()},Session(),CancellationToken.None);
        Assert.Equal("outcome_unknown",outcome.OverallStatus);Assert.Equal(1,adapter.Calls);Assert.Equal(1,outcome.Steps.GetArrayLength());
    }
    [Fact] public async Task ReadTimeoutIsFailedWithoutEffectAndRequiresFreshProcess()
    {
        using var key = new DeviceSigningKeyStore(root).GetOrCreate();
        var plan=ProtocolV2VectorTests.Vector["plan"]!.DeepClone().AsObject();
        plan["steps"]![0]!["timeout_seconds"]=1;
        plan["steps"]![0]!["side_effect_classification"]="read";
        plan["steps"]![0]!["post_condition_probe_id"]=null;
        using var cloud=ProtocolV2VectorTests.TestKey("plan");ProtocolV2VectorTests.SignPlan(plan,cloud);
        var adapter=new FakeAdapter(()=>new TaskCompletionSource<AdapterResult>().Task);
        var worker=Worker(new AppPlanJournal(Path.Combine(root,"journal")),adapter,key);

        var outcome=await worker.ExecuteAsync(Lease() with{PlanJson=plan.ToJsonString()},Session(),CancellationToken.None);

        Assert.Equal("failed_without_effect",outcome.OverallStatus);
        Assert.False(worker.ExecutionQuarantined);
        Assert.True(worker.RequiresProcessRestart);
    }
    [Fact] public async Task ChildrenTimeoutCompletesCleanupWithoutRestartAndAllowsNextPlan()
    {
        using var key = new DeviceSigningKeyStore(root).GetOrCreate();
        var plan=ProtocolV2VectorTests.Vector["plan"]!.DeepClone().AsObject();
        plan["steps"]![0]!["timeout_seconds"]=1;
        plan["steps"]![0]!["operation_id"]="teamcenter.product_structure.children.read@1";
        plan["steps"]![0]!["side_effect_classification"]="read";
        plan["steps"]![0]!["post_condition_probe_id"]=null;
        using var cloud=ProtocolV2VectorTests.TestKey("plan");
        ProtocolV2VectorTests.SignPlan(plan,cloud);
        var cleaned=false;
        var adapter=new FakeAdapter(()=>Task.FromResult(new AdapterResult(true)),
            "teamcenter.product_structure.children.read@1", async ct=>{
                if(cleaned)return new AdapterResult(true);
                try { await Task.Delay(Timeout.Infinite,ct); }
                finally { await Task.Delay(50); cleaned=true; }
                return new AdapterResult(true);
            });
        var worker=Worker(new AppPlanJournal(Path.Combine(root,"journal")),adapter,key);
        var outcome=await worker.ExecuteAsync(Lease() with{PlanJson=plan.ToJsonString()},Session(),CancellationToken.None);
        Assert.Equal("failed_without_effect",outcome.OverallStatus);
        Assert.False(worker.ExecutionQuarantined);
        Assert.False(worker.RequiresProcessRestart);
        Assert.True(cleaned);
        plan["plan_id"]="children-next";
        ProtocolV2VectorTests.SignPlan(plan,cloud);
        var next=await worker.ExecuteAsync(Lease() with{PlanJson=plan.ToJsonString()},Session(),CancellationToken.None);
        Assert.Equal("succeeded",next.OverallStatus);
    }
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task ChildrenTimeoutWithoutConfirmedCleanupRequiresRestart(bool cleanupFails)
    {
        using var key=new DeviceSigningKeyStore(root).GetOrCreate();
        var plan=ProtocolV2VectorTests.Vector["plan"]!.DeepClone().AsObject();
        plan["steps"]![0]!["timeout_seconds"]=1;
        plan["steps"]![0]!["operation_id"]="teamcenter.product_structure.children.read@1";
        plan["steps"]![0]!["side_effect_classification"]="read";
        plan["steps"]![0]!["post_condition_probe_id"]=null;
        using var cloud=ProtocolV2VectorTests.TestKey("plan"); ProtocolV2VectorTests.SignPlan(plan,cloud);
        var adapter=new FakeAdapter(()=>new TaskCompletionSource<AdapterResult>().Task,
            "teamcenter.product_structure.children.read@1",
            cleanupFails ? async ct=>{
                try { await Task.Delay(Timeout.Infinite,ct); }
                catch(OperationCanceledException) { throw new ConnectorException("teamcenter_worker_cleanup_failed"); }
                return new AdapterResult(true);
            } : null);
        var worker=Worker(new AppPlanJournal(Path.Combine(root,"journal")),adapter,key);
        var outcome=await worker.ExecuteAsync(Lease() with{PlanJson=plan.ToJsonString()},Session(),CancellationToken.None);
        Assert.Equal("failed_without_effect",outcome.OverallStatus);
        Assert.False(worker.ExecutionQuarantined);
        Assert.True(worker.RequiresProcessRestart);
    }
    [Fact] public async Task AdapterRejectionBeforeComIsFailedWithoutEffectForWritePlan()
    {
        using var key = new DeviceSigningKeyStore(root).GetOrCreate();
        var plan=ProtocolV2VectorTests.Vector["plan"]!.DeepClone().AsObject();
        plan["steps"]![0]!["side_effect_classification"]="write";
        plan["steps"]![0]!["post_condition_probe_id"]="vismockup.document.snapshot@1";
        using var cloud=ProtocolV2VectorTests.TestKey("plan");ProtocolV2VectorTests.SignPlan(plan,cloud);
        var adapter=new FakeAdapter(()=>throw new ConnectorNoEffectException("vismockup_session_node_mapping_stale"));
        var worker=Worker(new AppPlanJournal(Path.Combine(root,"journal")),adapter,key);

        var outcome=await worker.ExecuteAsync(Lease() with{PlanJson=plan.ToJsonString()},Session(),CancellationToken.None);

        Assert.Equal("failed_without_effect",outcome.OverallStatus);
        Assert.Equal("vismockup_session_node_mapping_stale",outcome.Steps[0].GetProperty("error_code").GetString());
        Assert.False(worker.ExecutionQuarantined);
    }
    [Fact] public async Task ArtifactOperationsFailBeforeInvocationWhenV2TransportIsUnavailable()
    {
        using var key=new DeviceSigningKeyStore(root).GetOrCreate();
        var plan=ProtocolV2VectorTests.Vector["plan"]!.DeepClone().AsObject();plan["steps"]![0]!["operation_id"]="vismockup.model.open@1";
        using var cloud=ProtocolV2VectorTests.TestKey("plan");ProtocolV2VectorTests.SignPlan(plan,cloud);
        var adapter=new FakeAdapter(()=>Task.FromResult(new AdapterResult(true)),"vismockup.model.open@1");
        var journal=new AppPlanJournal(Path.Combine(root,"journal"));
        var error=await Assert.ThrowsAnyAsync<Exception>(()=>Worker(journal,adapter,key).ExecuteAsync(Lease() with{PlanJson=plan.ToJsonString()},Session(),CancellationToken.None));
        Assert.Equal("v2_artifact_transport_unavailable",error.Message);Assert.Empty(journal.Events);Assert.Equal(0,adapter.Calls);
    }
    [Fact] public async Task JournalIsDurableBeforeComInvocation()
    {
        using var key = new DeviceSigningKeyStore(root).GetOrCreate();
        var journal = new AppPlanJournal(Path.Combine(root,"journal"));
        var adapter = new FakeAdapter(() => {
            Assert.Equal(new[]{"plan_received","lease_acquired","invocation_started"}, new AppPlanJournal(journal.Path).Events.Select(x=>x.Kind));
            return Task.FromResult(new AdapterResult(true,new { connected = true }));
        });
        var worker = Worker(journal,adapter,key);
        var outcome = await worker.ExecuteAsync(Lease(), Session(), CancellationToken.None);
        Assert.Equal("succeeded",outcome.OverallStatus);
        Assert.Equal(1,adapter.Calls);
        Assert.Equal(outcome.ToJson(), (await worker.ExecuteAsync(Lease(),Session(),CancellationToken.None)).ToJson());
        Assert.Equal(1,adapter.Calls);
    }
    [Fact] public async Task CancellationAfterInvocationIsSignedUnknownAndNoReplay()
    {
        using var key = new DeviceSigningKeyStore(root).GetOrCreate();
        var journal = new AppPlanJournal(Path.Combine(root,"journal"));
        var plan=ProtocolV2VectorTests.Vector["plan"]!.DeepClone().AsObject();
        plan["steps"]![0]!["side_effect_classification"]="write";
        plan["steps"]![0]!["post_condition_probe_id"]="vismockup.application.probe@1";
        using var cloud=ProtocolV2VectorTests.TestKey("plan");ProtocolV2VectorTests.SignPlan(plan,cloud);
        using var cancel = new CancellationTokenSource();
        var adapter = new FakeAdapter(() => { cancel.Cancel(); return new TaskCompletionSource<AdapterResult>().Task; });
        var worker = Worker(journal,adapter,key);
        var outcome = await worker.ExecuteAsync(Lease() with{PlanJson=plan.ToJsonString()},Session(),cancel.Token);
        Assert.Equal("outcome_unknown",outcome.OverallStatus);
        OutcomeV2.ParseAndVerify(outcome.ToJson(),key.PublicJwk.GetRawText());
        Assert.True(worker.ExecutionQuarantined);
        Assert.Equal(1,adapter.Calls);
    }
    [Fact] public void CrashRecoverySignsUnknownWithoutCom()
    {
        using var key = new DeviceSigningKeyStore(root).GetOrCreate();
        var journal = new AppPlanJournal(Path.Combine(root,"journal"));
        journal.Append("plan_received","plan-002",Lease().PlanJson);
        journal.Append("lease_acquired","plan-002",JsonSerializer.Serialize(Lease()));
        journal.Append("invocation_started","plan-002",JsonSerializer.Serialize(new {step_id="step-00001",started_at=Now.ToString("O")}));
        var adapter = new FakeAdapter(() => throw new Exception("COM must not run"));
        var recovered = Worker(new AppPlanJournal(journal.Path),adapter,key).Recover();
        Assert.Single(recovered);
        Assert.Equal("outcome_unknown",recovered[0].OverallStatus);
        Assert.Equal(0,adapter.Calls);
        Assert.Single(Worker(new AppPlanJournal(journal.Path),adapter,key).Recover());
        journal.Append("reconciled","plan-002","{}");
        Assert.Empty(Worker(new AppPlanJournal(journal.Path),adapter,key).Recover());
    }
    [Fact] public void CrashBeforeASecondStepDoesNotReportThePartiallyExecutedPlanAsSucceeded()
    {
        using var key = new DeviceSigningKeyStore(root).GetOrCreate();
        var plan=ProtocolV2VectorTests.Vector["plan"]!.DeepClone().AsObject();
        var second=plan["steps"]![0]!.DeepClone();second["step_id"]="step-00002";
        plan["steps"]!.AsArray().Add(second);
        using var cloud=ProtocolV2VectorTests.TestKey("plan");ProtocolV2VectorTests.SignPlan(plan,cloud);
        var lease=Lease() with{PlanJson=plan.ToJsonString()};
        var journal=new AppPlanJournal(Path.Combine(root,"journal"));
        journal.Append("plan_received","plan-002",lease.PlanJson);
        journal.Append("lease_acquired","plan-002",JsonSerializer.Serialize(lease));
        var result=JsonSerializer.SerializeToElement(new{connected=true});
        journal.Append("step_terminal","plan-002",JsonSerializer.Serialize(new {
            step_id="step-00001",started_at=PlanExecutionWorker.Timestamp(Now),completed_at=PlanExecutionWorker.Timestamp(Now),
            status="succeeded",result,result_hash=CanonicalJsonV2.Hash(result),
            error_code=(string?)null,reconciliation_state="not_required"}));

        var recovered=Assert.Single(Worker(journal,new FakeAdapter(()=>throw new Exception("must not run")),key).Recover());

        Assert.Equal("failed_without_effect",recovered.OverallStatus);
        Assert.Equal(2,recovered.Steps.GetArrayLength());
        Assert.Equal("invocation_not_started",recovered.Steps[1].GetProperty("error_code").GetString());
    }
    [Fact] public void APreviouslyInconclusiveManualReviewCanBeProbedAgainAfterAnotherAppRestart()
    {
        using var key = new DeviceSigningKeyStore(root).GetOrCreate();
        var journal = new AppPlanJournal(Path.Combine(root,"journal"));
        var adapter = new FakeAdapter(() => throw new Exception("recovery must only probe"));
        var outcome = Worker(journal,adapter,key).Recover();
        Assert.Empty(outcome);
        journal.Append("plan_received","plan-002",Lease().PlanJson);
        journal.Append("lease_acquired","plan-002",JsonSerializer.Serialize(Lease()));
        journal.Append("invocation_started","plan-002",JsonSerializer.Serialize(new {step_id="step-00001",started_at=Now.ToString("O")}));
        var original = Assert.Single(Worker(journal,adapter,key).Recover());
        journal.Append("reconciled","plan-002","{}");
        journal.Append("manual_review_required","plan-002","{}");

        var retry = Assert.Single(Worker(new AppPlanJournal(journal.Path),adapter,key).Recover());

        Assert.Equal(original.ToJson(), retry.ToJson());
        journal.Append("reconciliation_retry_v3","plan-002","{}");
        Assert.Single(Worker(new AppPlanJournal(journal.Path),adapter,key).Recover());
    }
    [Theory]
    [InlineData("plan_reconciliation_invalid", true)]
    [InlineData("runtime_session_conflict", false)]
    [InlineData("cloud_temporarily_unavailable", false)]
    public void OnlyACloudRejectedHistoricalRecoveryCanBeSkipped(string code, bool expected)
    {
        Assert.Equal(expected, RuntimeSessionWorker.IsObsoleteRecovery(code));
    }
    [Fact] public async Task AuthenticatedClosedPlanAcknowledgementSkipsOnlyThatExactOutcomeAfterRestart()
    {
        using var key=new DeviceSigningKeyStore(root).GetOrCreate();
        var journal=new AppPlanJournal(Path.Combine(root,"journal"));
        var adapter=new FakeAdapter(()=>throw new Exception("recovery must never replay the operation"));
        AppendInterruptedPlan(journal,"plan-002",Lease());
        var otherPlan=ProtocolV2VectorTests.Vector["plan"]!.DeepClone().AsObject();
        otherPlan["plan_id"]="plan-other";
        using(var cloud=ProtocolV2VectorTests.TestKey("plan"))ProtocolV2VectorTests.SignPlan(otherPlan,cloud);
        AppendInterruptedPlan(journal,"plan-other",Lease() with{PlanJson=otherPlan.ToJsonString()});
        var recovered=Worker(journal,adapter,key).Recover();
        var closed=Assert.Single(recovered,outcome=>outcome.PlanId=="plan-002");
        var other=Assert.Single(recovered,outcome=>outcome.PlanId=="plan-other");
        var signedOutcome=journal.Events.Single(e=>e.Kind=="outcome"&&e.PlanId==closed.PlanId).Data;
        using var http=new HttpClient(new InspectRequest(async request=>
        {
            Assert.Equal("/api/v1/simulation/connectors/v2/runtime/reconciliation/register",request.RequestUri!.AbsolutePath);
            Assert.Equal("device-credential",request.Headers.GetValues("X-AI00-Device-Credential").Single());
            Assert.False(request.Headers.Contains("X-AI00-Runtime-Session"));
            using var body=JsonDocument.Parse(await request.Content!.ReadAsStringAsync());
            Assert.Equal(closed.PlanId,body.RootElement.GetProperty("plan_id").GetString());
            return new HttpResponseMessage(System.Net.HttpStatusCode.Conflict){Content=new StringContent("{\"detail\":{\"code\":\"plan_reconciliation_invalid\"}}")};
        }));
        Assert.True(await RuntimeSessionWorker.RecoverOneAsync(closed,journal,async ct=>{await new RuntimeTransport(http,new Uri("https://gateway.example.com")).SendAsync(
            HttpMethod.Post,"runtime/reconciliation/register",new{plan_id=closed.PlanId},ct,credential:"device-credential");},CancellationToken.None));

        var afterRestart=Worker(new AppPlanJournal(journal.Path),adapter,key).Recover();

        Assert.Equal(signedOutcome,new AppPlanJournal(journal.Path).Events.Single(e=>e.Kind=="outcome"&&e.PlanId==closed.PlanId).Data);
        Assert.Equal(other.ToJson(),Assert.Single(afterRestart).ToJson());
        Assert.Equal(0,adapter.Calls);
        Assert.Contains(journal.Events,e=>e.Kind=="reconciliation_retry_v3"&&e.PlanId==closed.PlanId);
        Assert.Contains(journal.Events,e=>e.Kind=="acknowledged"&&e.PlanId==closed.PlanId);
    }
    [Fact] public async Task AcknowledgedUnknownAllowsANewExplicitPlanButAnotherPendingUnknownStillBlocks()
    {
        using var key=new DeviceSigningKeyStore(root).GetOrCreate();
        var journal=new AppPlanJournal(Path.Combine(root,"journal"));
        AppendInterruptedPlan(journal,"plan-002",Lease());
        var recoveryWorker=Worker(journal,new FakeAdapter(()=>throw new Exception("recovery must not replay")),key);
        var closed=Assert.Single(recoveryWorker.Recover());
        Assert.True(await RuntimeSessionWorker.RecoverOneAsync(closed,journal,_=>throw new RuntimeTransportException("plan_reconciliation_invalid"),CancellationToken.None));
        var nextPlan=ProtocolV2VectorTests.Vector["plan"]!.DeepClone().AsObject();
        nextPlan["plan_id"]="plan-next";
        using(var cloud=ProtocolV2VectorTests.TestKey("plan"))ProtocolV2VectorTests.SignPlan(nextPlan,cloud);
        var adapter=new FakeAdapter(()=>Task.FromResult(new AdapterResult(true,new{connected=true})));
        var restarted=Worker(new AppPlanJournal(journal.Path),adapter,key);

        var next=await restarted.ExecuteAsync(Lease() with{PlanJson=nextPlan.ToJsonString()},Session(),CancellationToken.None);

        Assert.Equal("succeeded",next.OverallStatus);
        Assert.Equal(1,adapter.Calls);
        var pendingPlan=ProtocolV2VectorTests.Vector["plan"]!.DeepClone().AsObject();
        pendingPlan["plan_id"]="plan-pending";
        using(var cloud=ProtocolV2VectorTests.TestKey("plan"))ProtocolV2VectorTests.SignPlan(pendingPlan,cloud);
        AppendInterruptedPlan(journal,"plan-pending",Lease() with{PlanJson=pendingPlan.ToJsonString()});
        Assert.Single(Worker(journal,new FakeAdapter(()=>throw new Exception("recovery must not replay")),key).Recover(),item=>item.PlanId=="plan-pending");
        var blockedPlan=ProtocolV2VectorTests.Vector["plan"]!.DeepClone().AsObject();
        blockedPlan["plan_id"]="plan-blocked";
        using(var cloud=ProtocolV2VectorTests.TestKey("plan"))ProtocolV2VectorTests.SignPlan(blockedPlan,cloud);

        var error=await Assert.ThrowsAsync<InvalidDataException>(()=>Worker(new AppPlanJournal(journal.Path),adapter,key).ExecuteAsync(
            Lease() with{PlanJson=blockedPlan.ToJsonString()},Session(),CancellationToken.None));

        Assert.Equal("runtime_quarantined",error.Message);
        Assert.Equal(1,adapter.Calls);
    }
    private static void AppendInterruptedPlan(AppPlanJournal journal,string planId,LeasedPlan lease)
    {
        journal.Append("plan_received",planId,lease.PlanJson);
        journal.Append("lease_acquired",planId,JsonSerializer.Serialize(lease));
        journal.Append("invocation_started",planId,JsonSerializer.Serialize(new{step_id="step-00001",started_at=Now.ToString("O")}));
    }
    [Theory] [InlineData("device")] [InlineData("generation")] [InlineData("instance")] [InlineData("expiry")] [InlineData("key")] [InlineData("lease")]
    public async Task InvalidBindingsNeverReachAdapter(string field)
    {
        using var key = new DeviceSigningKeyStore(root).GetOrCreate();
        var journal = new AppPlanJournal(Path.Combine(root,"journal"));
        var adapter = new FakeAdapter(() => Task.FromResult(new AdapterResult(true)));
        var session=Session(); var lease=Lease();
        if(field=="device")session=session with{DeviceId="other"};
        if(field=="generation")session=session with{Generation=8};
        if(field=="instance")session=session with{InstanceId="other"};
        if(field=="expiry")session=session with{ExpiresAt=Now.AddSeconds(-1)};
        if(field=="lease")lease=lease with{LeaseUntil=Now.AddSeconds(-1)};
        if(field=="key")lease=lease with{PlanJson=lease.PlanJson.Replace("cloud-plan-key-2026-09","unknown-key")};
        await Assert.ThrowsAnyAsync<Exception>(()=>Worker(journal,adapter,key).ExecuteAsync(lease,session,CancellationToken.None));
        Assert.Empty(journal.Events); Assert.Equal(0,adapter.Calls);
    }
    internal static RuntimeSession Session()=>new("device-001","tenant-001",7,"runtime-instance-001","session-secret",Now.AddMinutes(3));
    internal static LeasedPlan Lease()=>new("lease-002",Now.AddMinutes(2),ProtocolV2VectorTests.Vector["plan"]!.ToJsonString());
    private static PlanExecutionWorker Worker(AppPlanJournal journal,FakeAdapter adapter,DeviceSigningKey key)=>new(journal,adapter,key,"device-key-001",new Dictionary<string,TrustedPlanKey>{{"cloud-plan-key-2026-09",new(ProtocolV2VectorTests.Vector["plan_public_jwk"]!.ToJsonString(),Now.AddDays(-1),Now.AddDays(1),false)}},()=>Now);
    internal sealed class FakeAdapter(Func<Task<AdapterResult>> invoke,string operation="vismockup.application.probe@1",Func<CancellationToken,Task<AdapterResult>>? cancellable=null):IConnectorAdapter
    {
        public int Calls {get;private set;}
        public AdapterManifest Manifest {get;}=new("ai00.vismockup",1,"siemens.vismockup","14.2.0",[new(operation,"sha256:"+new string('4',64))]);
        public Task<AdapterHealth> ProbeAsync(CancellationToken ct)=>Task.FromResult(new AdapterHealth(true,"ready",true,true,"14.2.0"));
        public Task<AdapterResult> ExecuteAsync(AdapterOperation operation,CancellationToken ct){Calls++;return cancellable is null?invoke():cancellable(ct);}
    }
    private sealed class InspectRequest(Func<HttpRequestMessage,Task<HttpResponseMessage>> handle):HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken ct)=>handle(request);
    }
    public void Dispose(){if(Directory.Exists(root))Directory.Delete(root,true);}
}
