using System.Diagnostics;
using System.Text.Json;
using Ai00.Connector.Contracts;
namespace Ai00.Connector.AppHost;

public sealed class ViewerInteractionExecutor(ViewerInteractionSession session,ViewerInteractionRuntimeContext runtime,
    ViewerExecutionGate gate,ViewerInteractionJournal journal,Func<string,string,bool> supports,
    Func<string,string,long,string,string,JsonElement,Task<object>> invoke,
    Func<DateTimeOffset>? clock=null,Func<TimeSpan>? monotonic=null,TimeSpan? invocationTimeout=null,
    Action<string,object>? diagnostic=null)
{
    private DateTimeOffset Now=>(clock??(()=>DateTimeOffset.UtcNow))();
    private TimeSpan Monotonic=>(monotonic??(()=>TimeSpan.FromSeconds((double)Stopwatch.GetTimestamp()/Stopwatch.Frequency)))();
    public ViewerInteractionResponse? QueryRequest(string interaction,string request)
    {
        var entry=journal.Find(interaction,request);
        return entry is null?null:entry.Outcome??new(request,"outcome_unknown",error_code:"request_in_progress");
    }
    public async Task<ViewerInteractionResponse> ExecuteAsync(ViewerInteractionRequest request,CancellationToken ct)
    {
        var total=Stopwatch.StartNew();double comMs=0,journalMs=0;
        var budget=invocationTimeout??TimeSpan.FromSeconds(60);
        void Trace(string stage,object detail){try{diagnostic?.Invoke(stage,new{request_id=request.RequestId,detail});}catch{/* Diagnostics cannot change an operation's outcome. */}}
        Trace("execute_received",new{budget_ms=budget.TotalMilliseconds});
        ViewerInteractionResponse Reject(string code)=>new(request.RequestId,"rejected",error_code:code,timings:new{total_ms=total.Elapsed.TotalMilliseconds,com_ms=comMs,journal_ms=journalMs});
        var authorization=session.Validate(request.InteractionId,runtime.Current,Now,Monotonic);
        if(authorization is not null)return Reject(authorization);
        var previous=journal.Find(request.InteractionId,request.RequestId);
        if(previous is not null)return previous.RequestDigest!=request.Digest?Reject("request_id_conflict"):
            previous.Outcome??new(request.RequestId,"outcome_unknown",error_code:"request_in_progress");
        if(gate.IsQuarantined||journal.HasUnknown)return Reject("runtime_quarantined");
        using var lease=gate.TryEnterInteractive();
        if(lease is null)return new(request.RequestId,"busy",error_code:"viewer_busy");
        var value=request.Document;var grant=session.Current;
        if(grant is null||grant.SessionNonce!=request.InteractionId)return Reject("interaction_closed");
        using var dispatch=session.BeginDispatch(grant);
        authorization=session.Validate(request.InteractionId,runtime.Current,Now,Monotonic);
        if(authorization is not null)return Reject(authorization);
        var operation=value.GetProperty("operation_id").GetString()!;
        if(!grant.Operations.EnumerateArray().Any(op=>op.GetProperty("id").GetString()==operation && supports(operation,op.GetProperty("contract_hash").GetString()!)))return Reject("interaction_operation_forbidden");
        if(ct.IsCancellationRequested)return Reject("invocation_not_started");
        var timer=Stopwatch.StartNew();
        try{journal.Admit(request,grant);}
        catch(Exception error) when(error is IOException or UnauthorizedAccessException or InvalidDataException)
        {return Reject(error is InvalidDataException?error.Message:"journal_unavailable");}
        journalMs+=timer.Elapsed.TotalMilliseconds;
        Trace("execute_admitted",new{operation,action=value.GetProperty("arguments").GetProperty("action").GetString(),sequence=value.GetProperty("sequence").GetInt64(),structure_epoch=value.GetProperty("structure_epoch").GetInt64(),target_count=value.GetProperty("targets").GetArrayLength()});
        var targets=new List<object>();string status="completed";string? errorCode=null;var stopped=false;
        foreach(var target in value.GetProperty("targets").EnumerateArray())
        {
            var node=target.GetString()!;
            if(stopped){targets.Add(new{node_ref=node,status="not_started",error_code=(string?)null});continue;}
            var validation=session.Validate(request.InteractionId,runtime.Current,Now,Monotonic);
            if(validation is not null||ct.IsCancellationRequested||total.Elapsed>=budget)
            {
                status="rejected";errorCode=validation??(total.Elapsed>=budget?"invocation_budget_exhausted":"invocation_not_started");stopped=true;
                targets.Add(new{node_ref=node,status="not_started",error_code=errorCode});continue;
            }
            var itemStatus="completed";string? itemError=null;timer.Restart();
            Trace("native_started",new{node_ref=node});
            try
            {
                // The adapter rechecks document, mapping epoch and node identity on its existing STA.
                var pending=invoke(grant.SourceAssociationId,grant.DocumentSession,value.GetProperty("structure_epoch").GetInt64(),node,operation,value.GetProperty("arguments"));
                _=pending.ContinueWith(t=>{Trace("native_settled",new{node_ref=node,status=t.Status.ToString(),elapsed_ms=total.Elapsed.TotalMilliseconds,exception_type=t.Exception?.GetBaseException().GetType().Name,hresult=t.Exception?.GetBaseException().HResult});},CancellationToken.None,TaskContinuationOptions.ExecuteSynchronously,TaskScheduler.Default);
                await pending.WaitAsync(budget-total.Elapsed>TimeSpan.Zero?budget-total.Elapsed:TimeSpan.Zero,ct);
            }
            catch(ConnectorNoEffectException error){itemStatus="rejected";itemError=SafeCode(error.Code);status="rejected";errorCode=itemError;stopped=true;}
            catch(Exception error) when(error is not (OutOfMemoryException or StackOverflowException))
            {
                Trace("native_failed",new{node_ref=node,exception_type=error.GetType().Name,hresult=error.HResult,code=error is ConnectorException known?SafeCode(known.Code):null,elapsed_ms=timer.Elapsed.TotalMilliseconds});
                itemStatus=status="outcome_unknown";itemError=errorCode="invocation_outcome_unknown";stopped=true;
                gate.Quarantine(errorCode);
            }
            comMs+=timer.Elapsed.TotalMilliseconds;
            Trace("target_completed",new{node_ref=node,status=itemStatus,error_code=itemError,elapsed_ms=timer.Elapsed.TotalMilliseconds});
            targets.Add(new{node_ref=node,status=itemStatus,error_code=itemError});
        }
        // These deterministic audit timings stop before the terminal fsync:
        // journal_ms measures admission only; total_ms is pre-outcome-flush.
        // End-to-end acceptance must measure caller wall latency through response.
        var outcome=new ViewerInteractionResponse(request.RequestId,status,new{targets},errorCode,new{total_ms=total.Elapsed.TotalMilliseconds,com_ms=comMs,journal_ms=journalMs});
        try{journal.Complete(request.InteractionId,request.RequestId,outcome);}
        catch(Exception error) when(error is IOException or UnauthorizedAccessException)
        {Trace("journal_failed",new{exception_type=error.GetType().Name,hresult=error.HResult});gate.Quarantine("journal_unavailable");return new(request.RequestId,"outcome_unknown",error_code:"journal_unavailable");}
        Trace("execute_completed",new{status,error_code=errorCode,elapsed_ms=total.Elapsed.TotalMilliseconds});
        return outcome;
    }
    private static string SafeCode(string value)=>System.Text.RegularExpressions.Regex.IsMatch(value,"\\A[a-z][a-z0-9_]{0,95}\\z")?value:"interaction_rejected";
}
