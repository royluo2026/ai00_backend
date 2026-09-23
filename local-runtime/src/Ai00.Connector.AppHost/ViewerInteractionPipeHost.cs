using System.Diagnostics;
using System.IO.Pipes;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using Ai00.Connector.Adapters.VisMockup;
using Ai00.Connector.Contracts;
using Ai00.Connector.Contracts.V2;
using Microsoft.Extensions.Hosting;
namespace Ai00.Connector.AppHost;

// Dedicated channel: same-user DACL, first-instance reservation, remote rejection,
// and an OS-supplied peer PID. The Electron client checks our PID in the other direction.
public sealed class ViewerInteractionPipeHost(AppHostOptions options,HostManifest manifest,ViewerInteractionSession session,
    ViewerInteractionRuntimeContext runtime,ViewerInteractionExecutor executor,ViewerInteractionJournal journal,
    ViewerExecutionGate gate,VisMockupAdapter adapter):BackgroundService
{
    internal static TimeSpan MonotonicNow()=>TimeSpan.FromSeconds((double)Stopwatch.GetTimestamp()/Stopwatch.Frequency);
    internal static TimeSpan InteractionTimeout(string type)=>TimeSpan.FromSeconds(
        type=="resolve_nodes"?25:type is "prepare_document" or "activate_document"?15:5);
    internal static Task ReleaseAfterRead(Task read,IDisposable dispatch,IDisposable lease)
        =>read.ContinueWith(completed=>
        {
            _=completed.Exception; // Observe a late read failure without reporting an unknown write.
            try{dispatch.Dispose();}finally{lease.Dispose();}
        },CancellationToken.None,TaskContinuationOptions.ExecuteSynchronously,TaskScheduler.Default);
    [DllImport("kernel32.dll",SetLastError=true)]
    private static extern bool GetNamedPipeClientProcessId(Microsoft.Win32.SafeHandles.SafePipeHandle pipe,out uint pid);
    [StructLayout(LayoutKind.Sequential)]
    private struct SecurityAttributes {public int Size;public IntPtr Descriptor;public int Inherit;}
    [DllImport("advapi32.dll",CharSet=CharSet.Unicode,SetLastError=true)]
    private static extern bool ConvertStringSecurityDescriptorToSecurityDescriptorW(string text,uint revision,out IntPtr descriptor,out uint length);
    [DllImport("kernel32.dll")]private static extern IntPtr LocalFree(IntPtr pointer);
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]
    private static extern Microsoft.Win32.SafeHandles.SafePipeHandle CreateNamedPipeW(string name,uint openMode,uint pipeMode,uint maxInstances,uint outputSize,uint inputSize,uint timeout,ref SecurityAttributes security);

    internal static NamedPipeServerStream CreatePipe(string name)
    {
        var sid=System.Security.Principal.WindowsIdentity.GetCurrent().User!.Value;
        if(!ConvertStringSecurityDescriptorToSecurityDescriptorW("D:P(A;;GA;;;"+sid+")",1,out var descriptor,out _))throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
        try
        {
            var security=new SecurityAttributes{Size=Marshal.SizeOf<SecurityAttributes>(),Descriptor=descriptor};
            var handle=CreateNamedPipeW("\\\\.\\pipe\\"+name+".ViewerInteraction",0x40080003,0x8,1,65536,65536,0,ref security);
            if(handle.IsInvalid){handle.Dispose();throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());}
            return new NamedPipeServerStream(PipeDirection.InOut,true,false,handle);
        }
        finally{LocalFree(descriptor);}
    }
    internal static bool IsExpectedPeer(NamedPipeServerStream pipe,int expected)=>GetNamedPipeClientProcessId(pipe.SafePipeHandle,out var pid)&&pid==expected;
    protected override async Task ExecuteAsync(CancellationToken ct)
    {
        while(!ct.IsCancellationRequested)
        {
            using var connection=CancellationTokenSource.CreateLinkedTokenSource(ct);
            using var writes=new SemaphoreSlim(1,1);
            var pending=new List<Task>();
            try
            {
                using var pipe=CreatePipe(options.PipeName);
                await pipe.WaitForConnectionAsync(ct);
                if(!IsExpectedPeer(pipe,options.ParentPid))throw new InvalidDataException("viewer_parent_mismatch");
                var seen=new Dictionary<string,string>(StringComparer.Ordinal);
                async Task ReplyAsync(ViewerInteractionResponse response)
                {
                    var bytes=JsonSerializer.SerializeToUtf8Bytes(response);
                    if(bytes.Length>ViewerInteractionProtocol.MaximumBytes)throw new InvalidDataException("interaction_result_too_large");
                    await writes.WaitAsync(connection.Token);
                    try{await pipe.WriteAsync(bytes,connection.Token);await pipe.WriteAsync(new byte[]{10},connection.Token);await pipe.FlushAsync(connection.Token);}
                    finally{writes.Release();}
                }
                async Task RunAsync(ViewerInteractionRequest request)
                {
                    try{await ReplyAsync(await HandleAsync(request,connection.Token));}
                    catch(Exception error) when(error is IOException or OperationCanceledException or InvalidDataException or ObjectDisposedException)
                    {connection.Cancel();session.Invalidate("pipe_disconnected");}
                }
                while(!connection.IsCancellationRequested)
                {
                    var request=ViewerInteractionProtocol.ParseRequest(await ViewerInteractionProtocol.ReadFrameAsync(pipe,connection.Token));
                    if(seen.TryGetValue(request.RequestId,out var digest))
                    {
                        if(digest!=request.Digest||request.Type!="execute")
                        {await ReplyAsync(new(request.RequestId,"rejected",error_code:"request_id_conflict"));continue;}
                    }
                    else
                    {
                        seen.Add(request.RequestId,request.Digest);
                    }
                    pending.RemoveAll(t=>t.IsCompleted);
                    if(pending.Count>=32){await ReplyAsync(new(request.RequestId,"busy",error_code:"interaction_backpressure"));continue;}
                    pending.Add(RunAsync(request));
                }
            }
            catch(OperationCanceledException) when(connection.IsCancellationRequested){ }
            catch(Exception error) when(error is IOException or InvalidDataException or ProtocolV2Exception or JsonException or DecoderFallbackException){ }
            finally
            {
                session.Invalidate("pipe_disconnected");connection.Cancel();
                await Task.WhenAll(pending);
            }
            if(!ct.IsCancellationRequested)await Task.Delay(100,ct);
        }
    }
    internal async Task<ViewerInteractionResponse> HandleAsync(ViewerInteractionRequest request,CancellationToken ct)
    {
        ViewerInteractionResponse Reject(string code)=>new(request.RequestId,"rejected",error_code:code);
        try
        {
            if(request.Type=="execute")return await executor.ExecuteAsync(request,ct);
            if(request.Type=="query_request")
            {
                var known=executor.QueryRequest(request.InteractionId,request.Document.GetProperty("queried_request_id").GetString()!);
                return known is null?Reject("request_not_found"):known with{request_id=request.RequestId};
            }
            if(request.Type=="close")
            {
                if(session.Current?.SessionNonce!=request.InteractionId)return Reject("interaction_closed");
                session.Invalidate("closed");journal.CloseSession(request.InteractionId);return new(request.RequestId,"completed");
            }
            if(gate.IsQuarantined)return Reject("runtime_quarantined");
            if(request.Type=="install_grant")
            {
                var raw=request.Document.GetProperty("grant");
                if(!manifest.PlanKeys.TryGetValue(raw.GetProperty("key_id").GetString()!,out var key)||key.Revoked)return Reject("grant_key_untrusted");
                var grant=ViewerInteractionGrant.ParseAndVerify(raw.GetRawText(),key.PublicJwk);
                if(grant.IssuedAt<key.NotBefore||grant.IssuedAt>=key.NotAfter)return Reject("grant_key_time_invalid");
                if(grant.Operations.EnumerateArray().Any(op=>!adapter.Manifest.Supports(op.GetProperty("id").GetString()!,op.GetProperty("contract_hash").GetString()!)))return Reject("adapter_contract_mismatch");
                session.Install(grant,runtime.Current,DateTimeOffset.UtcNow,MonotonicNow());
                return new(request.RequestId,"completed",new{interaction_id=grant.SessionNonce});
            }
            var error=session.Validate(request.InteractionId,runtime.Current,DateTimeOffset.UtcNow,MonotonicNow());
            if(error is not null)return Reject(error);
            var lease=gate.TryEnterInteractive();if(lease is null)return new(request.RequestId,"busy",error_code:"viewer_busy");
            var current=session.Current;
            if(current is null||current.SessionNonce!=request.InteractionId){lease.Dispose();return Reject("interaction_closed");}
            var dispatch=session.BeginDispatch(current);
            Task<object>? mapping=null;
            var handedOff=false;
            try
            {
                if(request.Type is "prepare_document" or "activate_document")
                {
                    var target=await (request.Type=="prepare_document"
                        ?adapter.PrepareViewerDocumentAsync(current.DocumentSession,ct)
                        :adapter.ActivateViewerDocumentAsync(current.DocumentSession,ct)).WaitAsync(InteractionTimeout(request.Type),ct);
                    var changed=session.Validate(request.InteractionId,runtime.Current,DateTimeOffset.UtcNow,MonotonicNow());
                    if(changed is not null)return Reject(changed);
                    return new(request.RequestId,"completed",new{process_id=target.ProcessId,document_session=target.DocumentSession,document_id=target.DocumentId,document_window=target.DocumentWindow,window_token=target.WindowToken});
                }
                mapping=adapter.ResolveViewerNodesAsync(current.SourceAssociationId,current.DocumentSession,request.Document.GetProperty("source_nodes"));
                var result=await mapping.WaitAsync(InteractionTimeout(request.Type),ct);
                var response=new ViewerInteractionResponse(request.RequestId,"completed",result);
                return JsonSerializer.SerializeToUtf8Bytes(response).Length<=ViewerInteractionProtocol.MaximumBytes?response:Reject("mapping_result_too_large");
            }
            catch(TimeoutException) when(request.Type=="resolve_nodes" && mapping is not null)
            {
                // Keep both the serial gate and authorization dispatch until the
                // read-only STA work settles. A timed-out mapping is not an unknown write.
                handedOff=true;_ = ReleaseAfterRead(mapping,dispatch,lease);
                return Reject("viewer_mapping_pending");
            }
            catch(Exception timeoutError) when(timeoutError is TimeoutException or OperationCanceledException)
            {
                // Quarantine before releasing the shared lease: a timed-out read
                // can still occupy the STA and must not admit a waiting plan.
                gate.Quarantine("viewer_sta_unavailable");return Reject("viewer_sta_unavailable");
            }
            finally{if(!handedOff){dispatch.Dispose();lease.Dispose();}}
        }
        catch(ConnectorNoEffectException error){return Reject(error.Code);}
        catch(Exception error) when(error is InvalidDataException or ProtocolV2Exception or JsonException or KeyNotFoundException or InvalidOperationException or System.Security.Cryptography.CryptographicException)
        {return Reject("interaction_request_invalid");}
        catch(ConnectorException){return Reject("viewer_mapping_unavailable");}
    }
}
