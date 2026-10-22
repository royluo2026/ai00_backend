using System.Text.Json;
using System.Diagnostics;
using Ai00.Connector.Contracts;
using Ai00.Connector.Contracts.V2;
using Ai00.Connector.Adapters.VisMockup;
namespace Ai00.Connector.AppHost;

public sealed record AppJournalEvent(long Sequence,string Kind,string PlanId,string Data);
public sealed class AppPlanJournal
{
    private readonly object gate=new();
    private List<AppJournalEvent> events;
    private long appendTailSequence;
    private long appendTailOffset;
    private string AppendPath => Path + ".events";
    public string Path {get;}
    public IReadOnlyList<AppJournalEvent> Events{get{lock(gate)return events.ToArray();}}
    public AppPlanJournal(string path)
    {
        Path=System.IO.Path.GetFullPath(path);
        events=File.Exists(Path)?JsonSerializer.Deserialize<List<AppJournalEvent>>(File.ReadAllBytes(Path))??throw new InvalidDataException("journal_invalid"):[];
        if(events.Where((e,i)=>e.Sequence!=i+1).Any())throw new InvalidDataException("journal_sequence_invalid");
        appendTailSequence=events.Count;
        if(File.Exists(AppendPath))
        {
            using var stream=new FileStream(AppendPath,FileMode.Open,FileAccess.Read,FileShare.Read);
            ReadAppendEventsLocked(stream);
        }
    }
    public void Append(string kind,string planId,string data)
    {
        lock(gate)
        {
            // Another recovery worker may have opened the same journal before
            // this instance. Refresh the append-only tail before allocating a
            // sequence so a stale in-memory view cannot write a duplicate.
            Directory.CreateDirectory(System.IO.Path.GetDirectoryName(AppendPath)??throw new InvalidDataException("journal_path_invalid"));
            // Keep one exclusive writer handle from tail refresh through durable append.
            // The validated prefix is immutable; only startup replays the full archive.
            using var stream=new FileStream(AppendPath,FileMode.OpenOrCreate,FileAccess.ReadWrite,FileShare.Read,4096,FileOptions.WriteThrough);
            ReadAppendEventsLocked(stream);
            var item=new AppJournalEvent(events.Count+1,kind,planId,data);
            var bytes=JsonSerializer.SerializeToUtf8Bytes(item);
            stream.Write(bytes);
            stream.WriteByte((byte)'\n');
            stream.Flush(true);
            events.Add(item);
            appendTailSequence=item.Sequence;
            appendTailOffset=stream.Position;
        }
    }
    private void ReadAppendEventsLocked(FileStream stream)
    {
        if(stream.Length<appendTailOffset)throw new InvalidDataException("journal_sequence_invalid");
        stream.Position=appendTailOffset;
        if(stream.Position==stream.Length)return;
        long previousSequence=appendTailOffset==0?0:appendTailSequence;
        using var reader=new StreamReader(stream,System.Text.Encoding.UTF8,true,4096,leaveOpen:true);
        while(reader.ReadLine() is { } line)
        {
            if(string.IsNullOrWhiteSpace(line))continue;
            var item=JsonSerializer.Deserialize<AppJournalEvent>(line)??throw new InvalidDataException("journal_invalid");
            if(item.Sequence<=previousSequence)throw new InvalidDataException("journal_sequence_invalid");
            previousSequence=item.Sequence;
            if(item.Sequence<=appendTailSequence)
            {
                if(item.Sequence>events.Count||!events[(int)item.Sequence-1].Equals(item))throw new InvalidDataException("journal_sequence_invalid");
                continue;
            }
            if(item.Sequence!=events.Count+1)throw new InvalidDataException("journal_sequence_invalid");
            events.Add(item);
            appendTailSequence=item.Sequence;
        }
        appendTailOffset=stream.Position;
    }
}

public sealed record RuntimeSession(string DeviceId,string TenantId,long Generation,string InstanceId,string Token,DateTimeOffset ExpiresAt);
public sealed record LeasedPlan(string LeaseId,DateTimeOffset LeaseUntil,string PlanJson);
public sealed record TrustedPlanKey(string PublicJwk,DateTimeOffset NotBefore,DateTimeOffset NotAfter,bool Revoked);
public sealed class PlanExecutionWorker(AppPlanJournal journal,IConnectorAdapter adapter,DeviceSigningKey signingKey,string deviceKeyId,IReadOnlyDictionary<string,TrustedPlanKey> keys,Func<DateTimeOffset>? clock=null,IAppArtifactMaterializer? artifactMaterializer=null,IAppCaptureUploader? captureUploader=null,ViewerExecutionGate? viewerGate=null,LocalOpenCancellation? localOpenCancellation=null)
{
    private readonly SemaphoreSlim serial=new(1,1);
    private readonly ViewerExecutionGate executionGate=viewerGate??new();
    private DateTimeOffset Now=>(clock??(()=>DateTimeOffset.UtcNow))();
    internal static TimeSpan RemainingExecutionBudget(int stepSeconds,DateTimeOffset leaseUntil,DateTimeOffset sessionUntil,DateTimeOffset now)=>
        new[]{TimeSpan.FromSeconds(stepSeconds),leaseUntil-now-TimeSpan.FromSeconds(30),sessionUntil-now-TimeSpan.FromSeconds(30)}.Min();
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
        IDisposable? viewerLease=null;
        var invocationStarted=false;
        try
        {
            viewerLease=await executionGate.EnterPlanAsync(ct);
            var plan=Verify(lease.PlanJson);
            var batchFilePlan=plan.CapabilityId=="simulation.model_cache.file.fetch.batch.request";
            if(plan.DeviceId!=session.DeviceId||plan.TenantId!=session.TenantId||plan.RuntimeGeneration!=session.Generation||plan.RuntimeInstanceId!=session.InstanceId||session.ExpiresAt<=Now||lease.LeaseUntil<=Now||lease.LeaseUntil>session.ExpiresAt||lease.LeaseUntil>plan.ExpiresAt||string.IsNullOrWhiteSpace(lease.LeaseId)||plan.IssuedAt>Now||plan.ExpiresAt<=Now)throw new InvalidDataException("plan_session_lease_binding_invalid");
            var previous=journal.Events.Where(e=>e.PlanId==plan.PlanId).ToArray();
            if(previous.Length>0)
            {
                if(previous.First(e=>e.Kind=="plan_received").Data!=lease.PlanJson)throw new InvalidDataException("plan_replay_conflict");
                var retained=previous.LastOrDefault(e=>e.Kind=="outcome");
                if(retained!=null){var result=OutcomeV2.ParseAndVerify(retained.Data,signingKey.PublicJwk.GetRawText());if(result.LeaseId!=lease.LeaseId)throw new InvalidDataException("lease_replay_conflict");return result;}
                throw new InvalidDataException("plan_recovery_required");
            }
            // Only unresolved outcomes can quarantine a new command. Do not
            // re-parse and re-verify the entire finalized archive on every click.
            var history=journal.Events;
            var finalized=history.Where(e=>e.Kind is "reconciled" or "acknowledged")
                .Select(e=>e.PlanId).ToHashSet(StringComparer.Ordinal);
            if(ExecutionQuarantined||history.Any(e=>e.Kind=="outcome"&&!finalized.Contains(e.PlanId)&&
                OutcomeV2.ParseAndVerify(e.Data,signingKey.PublicJwk.GetRawText()).OverallStatus=="outcome_unknown"))
                throw new InvalidDataException("runtime_quarantined");
            var manifest=adapter.Manifest;
            if(plan.AdapterId!=manifest.AdapterId||plan.AdapterMajor!=manifest.AdapterMajor||plan.TargetProduct.GetProperty("product_id").GetString()!=manifest.ProductId||Version.Parse(manifest.ProductVersion)<Version.Parse(plan.TargetProduct.GetProperty("minimum_version").GetString()!)||Version.Parse(manifest.ProductVersion)>=Version.Parse(plan.TargetProduct.GetProperty("maximum_version_exclusive").GetString()!)||plan.Steps.Any(s=>!manifest.Supports(s.OperationId,s.ContractHash)))throw new InvalidDataException("adapter_contract_mismatch");
            ct.ThrowIfCancellationRequested();
            if(plan.Steps.Any(s=>s.OperationId is "vismockup.model.open@1" or "vismockup.model.open@2" or "vismockup.model.insert@1" or "vismockup.model.attach@1")&&artifactMaterializer is null)throw new InvalidDataException("v2_artifact_transport_unavailable");
            if(plan.Steps.Any(s=>s.OperationId is "vismockup.view.capture@1" or "teamcenter.model_file.fetch@1")&&captureUploader is null)throw new InvalidDataException("v2_artifact_upload_unavailable");
            journal.Append("plan_received",plan.PlanId,lease.PlanJson);
            journal.Append("lease_acquired",plan.PlanId,JsonSerializer.Serialize(lease));
            var results=new List<JsonElement>();
            foreach(var step in plan.Steps)
            {
                ct.ThrowIfCancellationRequested();
                if(Now>=lease.LeaseUntil||Now>=session.ExpiresAt)throw new InvalidDataException("lease_expired");
                var started=Now;
                var executionBudget=RemainingExecutionBudget(step.TimeoutSeconds,lease.LeaseUntil,session.ExpiresAt,started);
                if(executionBudget<=TimeSpan.Zero)
                {
                    results.Add(StepResult(step.StepId,started,"failed_without_effect",null,"execution_delivery_budget_exhausted"));
                    journal.Append("step_terminal",plan.PlanId,results[^1].GetRawText());
                    break;
                }
                using var timeout=CancellationTokenSource.CreateLinkedTokenSource(ct);
                timeout.CancelAfter(executionBudget);
                JsonElement payload;
                try{payload=artifactMaterializer is null?step.Payload:await artifactMaterializer.MaterializeAsync(plan.PlanId,lease.LeaseId,step,session,timeout.Token);}
                catch(Exception exception)
                {
                    var code=exception is ConnectorNoEffectException rejected?rejected.Code
                        : exception is RuntimeTransportException transportError?transportError.Message
                        : exception is OperationCanceledException?"artifact_materialization_timeout":"artifact_materialization_failed";
                    results.Add(StepResult(step.StepId,started,"failed_without_effect",null,code));
                    journal.Append("step_terminal",plan.PlanId,results[^1].GetRawText());
                    if(!(batchFilePlan&&step.OperationId=="teamcenter.model_file.fetch@1"&&!ct.IsCancellationRequested))break;
                    continue;
                }
                journal.Append("invocation_started",plan.PlanId,JsonSerializer.Serialize(new{step_id=step.StepId,started_at=Timestamp(started)}));
                string status="succeeded";object? data=null;string? error=null;bool artifactTransferStarted=false;
                Task<AdapterResult>? invocation=null;var adapterTimer=Stopwatch.StartNew();
                using var localOpen=step.OperationId=="vismockup.model.open@3"?localOpenCancellation?.Begin(plan.PlanId,timeout.Token):null;
                var adapterToken=localOpen?.Token??timeout.Token;
                try
                {
                    if(localOpen is not null&&adapterToken.IsCancellationRequested)throw new ConnectorNoEffectException("cache_open_interrupted");
                    invocationStarted=true;
                    invocation=adapter.ExecuteAsync(new(step.OperationId,payload,step.StepId,step.ContractHash),adapterToken);
                    var result=await invocation.WaitAsync(timeout.Token);
                    timeout.Token.ThrowIfCancellationRequested();
                    if(!result.Ok)throw new ConnectorException("adapter_effect_unknown");
                    if(batchFilePlan&&step.OperationId=="teamcenter.model_files.size.preflight@1"&&result.Data is JsonElement preflightData&&
                        preflightData.TryGetProperty("error_code",out var preflightError)&&preflightError.ValueKind==JsonValueKind.String)
                    {
                        status="failed_without_effect";error=preflightError.GetString();data=result.Data;
                    }
                    if(step.OperationId=="teamcenter.model_file.fetch@1")
                        ModelFileTiming.Write("tc_read_and_local_hash_completed",plan.PlanId,step.StepId,adapterTimer.Elapsed.TotalMilliseconds,
                            result.Data is LocalModelArtifact acquired?acquired.ByteSize:0);
                    if(step.OperationId=="vismockup.view.capture@1")
                    {
                        if(result.Data is not LocalCaptureArtifact capture)throw new ConnectorException("capture_result_invalid");
                        artifactTransferStarted=true;
                        var artifact=await captureUploader!.UploadAsync(plan.PlanId,lease.LeaseId,step.StepId,capture,session,timeout.Token);
                        data=new{artifact};
                    }
                    else if(step.OperationId=="teamcenter.model_file.fetch@1")
                    {
                        if(result.Data is not LocalModelArtifact model)throw new ConnectorNoEffectException("model_artifact_invalid");
                        artifactTransferStarted=true;
                        var artifact=await captureUploader!.UploadModelAsync(plan.PlanId,lease.LeaseId,step.StepId,model,session,timeout.Token);
                        data=new{identity=model.Identity,node_key=model.NodeKey,item_revision_uid=model.ItemRevisionUid,file_ref=model.FileReference,artifact_ref=artifact,content_hash="sha256:"+model.Sha256,byte_length=model.ByteSize,acquired_at=model.AcquiredAt,captured_bytes_verified=false};
                        // FMS copies can carry DOS ReadOnly. Cleanup is not publication failure.
                        try{File.SetAttributes(model.Path,File.GetAttributes(model.Path)&~FileAttributes.ReadOnly);File.Delete(model.Path);}
                        catch(IOException){}catch(UnauthorizedAccessException){}
                    }
                    else data=result.Data;
                }
                catch(Exception exception)
                {
                    _ = exception;
                    ConnectorNoEffectException? cleanupProof=null;
                    if(exception is OperationCanceledException&&timeout.IsCancellationRequested&&
                        step.OperationId=="vismockup.model.open@3"&&invocation is not null)
                    {
                        // A deadline can win the await before pre-native materialization
                        // finishes cleanup. Only its explicit terminal proof clears unknown.
                        try{await invocation.WaitAsync(TimeSpan.FromSeconds(5));}
                        catch(ConnectorNoEffectException proof)when(proof.Code is "cancelled" or "cache_open_interrupted")
                        {cleanupProof=proof;}
                        catch{}
                    }
                    var failure=(Exception?)cleanupProof??exception;
                    if(step.OperationId=="teamcenter.model_file.fetch@1")
                        ModelFileTiming.Write("tc_read_failed",plan.PlanId,step.StepId,adapterTimer.Elapsed.TotalMilliseconds,0,
                            exception is ConnectorException connectorFailure?connectorFailure.Code:"read_invocation_failed");
#if DEBUG
                    Console.Error.WriteLine($"[ConnectorHost] adapter operation failed: {exception.GetType().Name}: {exception.Message}");
#endif
                    var noEffect=(failure is ConnectorNoEffectException proven&&proven.Code!="teamcenter_worker_cleanup_failed") ||
                        (!artifactTransferStarted&&step.OperationId!="vismockup.view.capture@1"&&step.SideEffectClassification=="read");
                    status=noEffect?"failed_without_effect":"outcome_unknown";
                    error=failure is ConnectorNoEffectException rejected
                        ? rejected.Code
                        : failure is ConnectorException connectorError
                        ? connectorError.Code
                        : noEffect?"read_invocation_failed":"invocation_outcome_unknown";
                    if(cleanupProof is null&&exception is OperationCanceledException&&timeout.IsCancellationRequested&&!ct.IsCancellationRequested)
                    {
                        // Teamcenter structure and property reads share the same
                        // cancellable subprocess worker. Both can prove cleanup;
                        // a timed-out COM call still requires a fresh host.
                        var cleaned=false;
                    if((step.OperationId is "teamcenter.product_structure.children.read@1" or
                        "teamcenter.node_properties.read@1" or "teamcenter.model_cache.read@1" or "teamcenter.model_cache.read@2" or
                        "teamcenter.model_files.size.preflight@1") && invocation is not null)
                        {
                            try { await invocation.WaitAsync(TimeSpan.FromSeconds(5)); cleaned=true; }
                            catch(OperationCanceledException) { cleaned=invocation.IsCompleted; }
                            catch(ConnectorException cleanupError) { cleaned=cleanupError.Code!="teamcenter_worker_cleanup_failed"; }
                            catch { }
                        }
                        RequiresProcessRestart|=!cleaned;
                    }
                    if(exception is ConnectorException {Code:"teamcenter_worker_cleanup_failed"})
                        RequiresProcessRestart=true;
                    if(!noEffect)ExecutionQuarantined=true;
                }
                results.Add(StepResult(step.StepId,started,status,data,error));
                journal.Append("step_terminal",plan.PlanId,results[^1].GetRawText());
                if(status!="succeeded"&&!(batchFilePlan&&step.OperationId=="teamcenter.model_file.fetch@1"&&
                    status=="failed_without_effect"&&!RequiresProcessRestart&&!ct.IsCancellationRequested))break;
            }
            return PersistOutcome(plan,lease,results);
        }
        catch
        {
            if(invocationStarted)executionGate.Quarantine("plan_outcome_unpersisted");
            throw;
        }
        finally
        {
            if(ExecutionQuarantined||RequiresProcessRestart)executionGate.Quarantine("plan_recovery_required");
            viewerLease?.Dispose();serial.Release();
        }
    }
    public IReadOnlyList<OutcomeV2> Recover()
    {
        var outcomes=new List<OutcomeV2>();
        foreach(var group in journal.Events.GroupBy(e=>e.PlanId))
        {
            if(group.Any(e=>e.Kind is "acknowledged" or "abandoned_without_effect"))continue;
            var reconciled=group.Any(e=>e.Kind=="reconciled");
            var manualReview=group.Any(e=>e.Kind=="manual_review_required");
            // A manual-review marker means the prior read-only post-condition
            // probe was inconclusive, not that the write may be replayed. Keep
            // recovering the signed outcome on later App starts so a healthy
            // VisMockup process can be probed again and release the server fence.
            if(reconciled&&!manualReview)continue;
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
        // External adapter codes (including legacy journal entries) must not
        // prevent signing a known terminal outcome or replay journaled work.
        results=results.Select(result=>{
            if(result.GetProperty("error_code").GetString() is not { } code ||
                (code.Length is > 0 and <= 128 && code.All(c=>c is >= 'a' and <= 'z' or >= '0' and <= '9' or '_' or '.' or '-')))return result;
            var normalized=System.Text.Json.Nodes.JsonNode.Parse(result.GetRawText())!;
            normalized["error_code"]="adapter_error_code_invalid";
            return JsonSerializer.SerializeToElement(normalized);
        }).ToList();
        var status=results.Any(r=>r.GetProperty("status").GetString()=="outcome_unknown")?"outcome_unknown":results.Any(r=>r.GetProperty("status").GetString()=="failed_without_effect")?"failed_without_effect":"succeeded";
        var unsigned=JsonSerializer.Serialize(new{protocol=plan.Protocol,plan_id=plan.PlanId,plan_hash=plan.PlanHash,lease_id=lease.LeaseId,tenant_id=plan.TenantId,device_id=plan.DeviceId,runtime_generation=(long)plan.RuntimeGeneration,runtime_instance_id=plan.RuntimeInstanceId,overall_status=status,steps=results,journal_sequence=journal.Events.Count+1,reported_at=Timestamp(Now),signature_algorithm="ecdsa-p256-sha256",device_key_id=deviceKeyId});
        var signed=OutcomeV2Signer.Sign(unsigned,signingKey);journal.Append("outcome",plan.PlanId,signed);
        return OutcomeV2.ParseAndVerify(signed,signingKey.PublicJwk.GetRawText());
    }
    internal static string Timestamp(DateTimeOffset value)=>value.UtcDateTime.ToString("yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'");
}
