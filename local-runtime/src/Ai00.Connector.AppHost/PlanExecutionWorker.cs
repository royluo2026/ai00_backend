using System.Text.Json;
using Ai00.Connector.Contracts;
using Ai00.Connector.Contracts.V2;
namespace Ai00.Connector.AppHost;

public sealed record AppJournalEvent(long Sequence,string Kind,string PlanId,string Data);
public sealed class AppPlanJournal
{
    private readonly object gate=new();
    private List<AppJournalEvent> events;
    public string Path {get;}
    public IReadOnlyList<AppJournalEvent> Events{get{lock(gate)return events.ToArray();}}
    public AppPlanJournal(string path)
    {
        Path=System.IO.Path.GetFullPath(path);
        events=File.Exists(Path)?JsonSerializer.Deserialize<List<AppJournalEvent>>(File.ReadAllBytes(Path))??throw new InvalidDataException("journal_invalid"):[];
        if(events.Where((e,i)=>e.Sequence!=i+1).Any())throw new InvalidDataException("journal_sequence_invalid");
    }
    public void Append(string kind,string planId,string data)
    {
        lock(gate)
        {
            var next=events.Append(new AppJournalEvent(events.Count+1,kind,planId,data)).ToList();
            DurableJsonFile.Write(Path,next);
            events=next;
        }
    }
}

public sealed record RuntimeSession(string DeviceId,string TenantId,long Generation,string InstanceId,string Token,DateTimeOffset ExpiresAt);
public sealed record LeasedPlan(string LeaseId,DateTimeOffset LeaseUntil,string PlanJson);
public sealed record TrustedPlanKey(string PublicJwk,DateTimeOffset NotBefore,DateTimeOffset NotAfter,bool Revoked);
public sealed class PlanExecutionWorker(AppPlanJournal journal,IConnectorAdapter adapter,DeviceSigningKey signingKey,string deviceKeyId,IReadOnlyDictionary<string,TrustedPlanKey> keys,Func<DateTimeOffset>? clock=null,IAppArtifactMaterializer? artifactMaterializer=null)
{
    private readonly SemaphoreSlim serial=new(1,1);
    private DateTimeOffset Now=>(clock??(()=>DateTimeOffset.UtcNow))();
    public bool ExecutionQuarantined {get;private set;}
    public bool RequiresProcessRestart {get;private set;}
    private ExecutionPlanV2 Verify(string json)
    {
        var raw=CanonicalJsonV2.Parse(json);
        if(!keys.TryGetValue(raw.GetProperty("key_id").GetString()!,out var key)||key.Revoked)throw new InvalidDataException("plan_key_untrusted");
        var plan=ExecutionPlanV2.ParseAndVerify(json,key.PublicJwk);
        if(plan.IssuedAt<key.NotBefore||plan.IssuedAt>=key.NotAfter)throw new InvalidDataException("plan_key_time_invalid");
        return plan;
    }
    public async Task<OutcomeV2> ExecuteAsync(LeasedPlan lease,RuntimeSession session,CancellationToken ct)
    {
        await serial.WaitAsync(ct);
        try
        {
            var plan=Verify(lease.PlanJson);
            if(plan.DeviceId!=session.DeviceId||plan.TenantId!=session.TenantId||plan.RuntimeGeneration!=session.Generation||plan.RuntimeInstanceId!=session.InstanceId||session.ExpiresAt<=Now||lease.LeaseUntil<=Now||lease.LeaseUntil>session.ExpiresAt||lease.LeaseUntil>plan.ExpiresAt||string.IsNullOrWhiteSpace(lease.LeaseId)||plan.IssuedAt>Now||plan.ExpiresAt<=Now)throw new InvalidDataException("plan_session_lease_binding_invalid");
            var previous=journal.Events.Where(e=>e.PlanId==plan.PlanId).ToArray();
            if(previous.Length>0)
            {
                if(previous.First(e=>e.Kind=="plan_received").Data!=lease.PlanJson)throw new InvalidDataException("plan_replay_conflict");
                var retained=previous.LastOrDefault(e=>e.Kind=="outcome");
                if(retained!=null){var result=OutcomeV2.ParseAndVerify(retained.Data,signingKey.PublicJwk.GetRawText());if(result.LeaseId!=lease.LeaseId)throw new InvalidDataException("lease_replay_conflict");return result;}
                throw new InvalidDataException("plan_recovery_required");
            }
            if(ExecutionQuarantined||journal.Events.Any(e=>e.Kind=="outcome"&&OutcomeV2.ParseAndVerify(e.Data,signingKey.PublicJwk.GetRawText()).OverallStatus=="outcome_unknown"&&!journal.Events.Any(a=>a.PlanId==e.PlanId&&a.Kind=="reconciled")))throw new InvalidDataException("runtime_quarantined");
            var manifest=adapter.Manifest;
            if(plan.AdapterId!=manifest.AdapterId||plan.AdapterMajor!=manifest.AdapterMajor||plan.TargetProduct.GetProperty("product_id").GetString()!=manifest.ProductId||Version.Parse(manifest.ProductVersion)<Version.Parse(plan.TargetProduct.GetProperty("minimum_version").GetString()!)||Version.Parse(manifest.ProductVersion)>=Version.Parse(plan.TargetProduct.GetProperty("maximum_version_exclusive").GetString()!)||plan.Steps.Any(s=>!manifest.Supports(s.OperationId,s.ContractHash)))throw new InvalidDataException("adapter_contract_mismatch");
            ct.ThrowIfCancellationRequested();
            if(plan.Steps.Any(s=>s.OperationId is "vismockup.model.open@1" or "vismockup.model.insert@1" or "vismockup.model.attach@1")&&artifactMaterializer is null)throw new InvalidDataException("v2_artifact_transport_unavailable");
            if(plan.Steps.Any(s=>s.OperationId=="vismockup.view.capture@1"))throw new InvalidDataException("v2_artifact_upload_unavailable");
            journal.Append("plan_received",plan.PlanId,lease.PlanJson);
            journal.Append("lease_acquired",plan.PlanId,JsonSerializer.Serialize(lease));
            var results=new List<JsonElement>();
            foreach(var step in plan.Steps)
            {
                ct.ThrowIfCancellationRequested();
                if(Now>=lease.LeaseUntil||Now>=session.ExpiresAt)throw new InvalidDataException("lease_expired");
                var started=Now;
                using var timeout=CancellationTokenSource.CreateLinkedTokenSource(ct);
                timeout.CancelAfter(new[]{TimeSpan.FromSeconds(step.TimeoutSeconds),lease.LeaseUntil-Now,session.ExpiresAt-Now}.Min());
                JsonElement payload;
                try{payload=artifactMaterializer is null?step.Payload:await artifactMaterializer.MaterializeAsync(plan.PlanId,lease.LeaseId,step,session,timeout.Token);}
                catch(Exception exception)
                {
                    var code=exception is ConnectorNoEffectException rejected?rejected.Code
                        : exception is RuntimeTransportException transportError?transportError.Message
                        : exception is OperationCanceledException?"artifact_materialization_timeout":"artifact_materialization_failed";
                    results.Add(StepResult(step.StepId,started,"failed_without_effect",null,code));
                    journal.Append("step_terminal",plan.PlanId,results[^1].GetRawText());
                    break;
                }
                journal.Append("invocation_started",plan.PlanId,JsonSerializer.Serialize(new{step_id=step.StepId,started_at=Timestamp(started)}));
                string status="succeeded";object? data=null;string? error=null;
                try
                {
                    var result=await adapter.ExecuteAsync(new(step.OperationId,payload,step.StepId,step.ContractHash),timeout.Token).WaitAsync(timeout.Token);
                    timeout.Token.ThrowIfCancellationRequested();
                    if(!result.Ok)throw new ConnectorException("adapter_effect_unknown");
                    data=result.Data;
                }
                catch(Exception exception)
                {
                    _ = exception;
#if DEBUG
                    Console.Error.WriteLine($"[ConnectorHost] adapter operation failed: {exception.GetType().Name}: {exception.Message}");
#endif
                    var noEffect=step.SideEffectClassification=="read"||exception is ConnectorNoEffectException;
                    status=noEffect?"failed_without_effect":"outcome_unknown";
                    error=exception is ConnectorNoEffectException rejected
                        ? rejected.Code
                        : noEffect?"read_invocation_failed":"invocation_outcome_unknown";
                    if(exception is OperationCanceledException&&timeout.IsCancellationRequested&&!ct.IsCancellationRequested)
                        RequiresProcessRestart=true;
                    if(!noEffect)ExecutionQuarantined=true;
                }
                results.Add(StepResult(step.StepId,started,status,data,error));
                journal.Append("step_terminal",plan.PlanId,results[^1].GetRawText());
                if(status!="succeeded")break;
            }
            return PersistOutcome(plan,lease,results);
        }
        finally{serial.Release();}
    }
    public IReadOnlyList<OutcomeV2> Recover()
    {
        var outcomes=new List<OutcomeV2>();
        foreach(var group in journal.Events.GroupBy(e=>e.PlanId))
        {
            if(group.Any(e=>e.Kind is "acknowledged" or "abandoned_without_effect"))continue;
            var reconciled=group.Any(e=>e.Kind=="reconciled");
            var manualReview=group.Any(e=>e.Kind=="manual_review_required");
            var upgradedProbeAttempted=group.Any(e=>e.Kind=="reconciliation_retry_v3");
            if(reconciled&&(!manualReview||upgradedProbeAttempted))continue;
            var saved=group.LastOrDefault(e=>e.Kind=="outcome");
            if(saved!=null){outcomes.Add(OutcomeV2.ParseAndVerify(saved.Data,signingKey.PublicJwk.GetRawText()));continue;}
            var leaseEvent=group.FirstOrDefault(e=>e.Kind=="lease_acquired");
            if(leaseEvent==null)continue;
            var lease=JsonSerializer.Deserialize<LeasedPlan>(leaseEvent.Data)!;
            var plan=Verify(lease.PlanJson);
            var results=group.Where(e=>e.Kind=="step_terminal").Select(e=>CanonicalJsonV2.Parse(e.Data)).ToList();
            foreach(var started in group.Where(e=>e.Kind=="invocation_started"))
            {
                var item=CanonicalJsonV2.Parse(started.Data);var id=item.GetProperty("step_id").GetString()!;
                if(results.Any(r=>r.GetProperty("step_id").GetString()==id))continue;
                results.Add(StepResult(id,item.GetProperty("started_at").GetDateTimeOffset(),"outcome_unknown",null,"process_recovery_outcome_unknown"));
            }
            if(!results.Any(item=>item.GetProperty("status").GetString()=="outcome_unknown"))
            {
                var pending=plan.Steps.FirstOrDefault(step=>!results.Any(item=>item.GetProperty("step_id").GetString()==step.StepId));
                if(pending!=null)results.Add(StepResult(pending.StepId,Now,"failed_without_effect",null,"invocation_not_started"));
            }
            outcomes.Add(PersistOutcome(plan,lease,results));
        }
        ExecutionQuarantined=outcomes.Any(o=>o.OverallStatus=="outcome_unknown");
        return outcomes;
    }
    private JsonElement StepResult(string id,DateTimeOffset started,string status,object? data,string? error)=>JsonSerializer.SerializeToElement(new{step_id=id,started_at=Timestamp(started),completed_at=Timestamp(Now<started?started:Now),status,result=data,result_hash=status=="succeeded"?CanonicalJsonV2.Hash(JsonSerializer.SerializeToElement(data)):null,error_code=error,reconciliation_state=status=="outcome_unknown"?"pending":"not_required"});
    private OutcomeV2 PersistOutcome(ExecutionPlanV2 plan,LeasedPlan lease,List<JsonElement> results)
    {
        var status=results.Any(r=>r.GetProperty("status").GetString()=="outcome_unknown")?"outcome_unknown":results.Any(r=>r.GetProperty("status").GetString()=="failed_without_effect")?"failed_without_effect":"succeeded";
        var unsigned=JsonSerializer.Serialize(new{protocol=plan.Protocol,plan_id=plan.PlanId,plan_hash=plan.PlanHash,lease_id=lease.LeaseId,tenant_id=plan.TenantId,device_id=plan.DeviceId,runtime_generation=(long)plan.RuntimeGeneration,runtime_instance_id=plan.RuntimeInstanceId,overall_status=status,steps=results,journal_sequence=journal.Events.Count+1,reported_at=Timestamp(Now),signature_algorithm="ecdsa-p256-sha256",device_key_id=deviceKeyId});
        var signed=OutcomeV2Signer.Sign(unsigned,signingKey);journal.Append("outcome",plan.PlanId,signed);
        return OutcomeV2.ParseAndVerify(signed,signingKey.PublicJwk.GetRawText());
    }
    internal static string Timestamp(DateTimeOffset value)=>value.UtcDateTime.ToString("yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'");
}
