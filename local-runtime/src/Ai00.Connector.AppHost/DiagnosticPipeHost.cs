using System.IO.Pipes;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Extensions.Hosting;
namespace Ai00.Connector.AppHost;

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record DiagnosticIdentity(int ParentPid,int ChildPid,string ExecutablePath,string Signer,string ManifestDigest,string Nonce);
public static class DiagnosticProtocol
{
    public const int MaximumBytes=4096;
    public static string Validate(string json)
    {
        if(Encoding.UTF8.GetByteCount(json)>MaximumBytes)throw new InvalidDataException("diagnostic_size_invalid");
        using var document=JsonDocument.Parse(json,new JsonDocumentOptions{MaxDepth=3});
        var value=document.RootElement;
        var type=value.GetProperty("type").GetString();
        var fields=type switch
        {
            "ready" or "health" or "shutdown"=>new[]{"type"},
            "pairing_state"=>new[]{"type","pairing_id","state"},
            "diagnostic"=>new[]{"type","code"},
            _=>throw new InvalidDataException("diagnostic_message_forbidden")
        };
        var actual=value.EnumerateObject().Select(p=>p.Name).ToArray();
        if(actual.Length!=fields.Length||actual.Distinct().Count()!=actual.Length||actual.Except(fields).Any())throw new InvalidDataException("diagnostic_message_forbidden");
        if(type=="diagnostic"&&value.GetProperty("code").GetString() is not ("runtime_waiting" or "runtime_unavailable" or "recovery_required"))throw new InvalidDataException("diagnostic_code_invalid");
        if(type=="pairing_state"&&(!System.Text.RegularExpressions.Regex.IsMatch(value.GetProperty("pairing_id").GetString()!,"\\Apairing-[a-f0-9]{32}\\z")||value.GetProperty("state").GetString() is not ("created" or "activated" or "expired")))throw new InvalidDataException("pairing_state_invalid");
        return type!;
    }
    public static void ValidateHandshake(string json,DiagnosticIdentity expected)
    {
        if(Encoding.UTF8.GetByteCount(json)>MaximumBytes)throw new InvalidDataException("handshake_size_invalid");
        using var doc=JsonDocument.Parse(json);
        if(doc.RootElement.EnumerateObject().Count()!=6||doc.RootElement.EnumerateObject().Select(p=>p.Name).Distinct().Count()!=6||JsonSerializer.Deserialize<DiagnosticIdentity>(json)!=expected)throw new InvalidDataException("handshake_identity_mismatch");
    }
}

// One native server instance, current-user SID only, PIPE_REJECT_REMOTE_CLIENTS.
public sealed class DiagnosticPipeHost(AppHostOptions options,DiagnosticIdentity identity,IHostApplicationLifetime lifetime):BackgroundService
{
    private readonly TaskCompletionSource ready=new(TaskCreationOptions.RunContinuationsAsynchronously);
    private readonly SemaphoreSlim writes=new(1,1);
    private NamedPipeServerStream? pipe;
    public Task Ready=>ready.Task;
    [DllImport("kernel32.dll",SetLastError=true)]private static extern bool GetNamedPipeClientProcessId(Microsoft.Win32.SafeHandles.SafePipeHandle pipe,out uint pid);
    [StructLayout(LayoutKind.Sequential)]private struct SecurityAttributes{public int Size;public IntPtr Descriptor;public int Inherit;}
    [DllImport("advapi32.dll",CharSet=CharSet.Unicode,SetLastError=true)]private static extern bool ConvertStringSecurityDescriptorToSecurityDescriptorW(string text,uint revision,out IntPtr descriptor,out uint length);
    [DllImport("kernel32.dll")]private static extern IntPtr LocalFree(IntPtr pointer);
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]private static extern Microsoft.Win32.SafeHandles.SafePipeHandle CreateNamedPipeW(string name,uint openMode,uint pipeMode,uint maxInstances,uint outputSize,uint inputSize,uint timeout,ref SecurityAttributes security);
    private NamedPipeServerStream CreatePipe()
    {
        var sid=System.Security.Principal.WindowsIdentity.GetCurrent().User!.Value;
        if(!ConvertStringSecurityDescriptorToSecurityDescriptorW("D:P(A;;GA;;;"+sid+")",1,out var descriptor,out _))throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
        try
        {
            var security=new SecurityAttributes{Size=Marshal.SizeOf<SecurityAttributes>(),Descriptor=descriptor};
            var handle=CreateNamedPipeW("\\\\.\\pipe\\"+options.PipeName,0x40080003,0x8,1,4096,4096,0,ref security);
            if(handle.IsInvalid){handle.Dispose();throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());}
            return new NamedPipeServerStream(PipeDirection.InOut,true,false,handle);
        }
        finally{LocalFree(descriptor);}
    }
    protected override async Task ExecuteAsync(CancellationToken ct)
    {
        try
        {
            pipe=CreatePipe();
            using var handshake=CancellationTokenSource.CreateLinkedTokenSource(ct);handshake.CancelAfter(TimeSpan.FromSeconds(10));
            await pipe.WaitForConnectionAsync(handshake.Token);
            if(!GetNamedPipeClientProcessId(pipe.SafePipeHandle,out var pid)||pid!=options.ParentPid)throw new InvalidDataException("pipe_parent_mismatch");
            await WriteAsync(JsonSerializer.Serialize(identity),handshake.Token);
            DiagnosticProtocol.ValidateHandshake(await ReadAsync(handshake.Token),identity);
            ready.TrySetResult();await SendAsync(new{type="ready"},ct);
            var window=DateTimeOffset.UtcNow;var count=0;
            while(!ct.IsCancellationRequested)
            {
                var json=await ReadAsync(ct);
                if(DateTimeOffset.UtcNow-window>TimeSpan.FromSeconds(1)){window=DateTimeOffset.UtcNow;count=0;}
                if(++count>10)throw new InvalidDataException("diagnostic_rate_exceeded");
                switch(DiagnosticProtocol.Validate(json))
                {
                    case "shutdown":lifetime.StopApplication();return;
                    case "health":await SendAsync(new{type="health"},ct);break;
                    default:throw new InvalidDataException("parent_message_forbidden");
                }
            }
        }
        catch(OperationCanceledException)when(ct.IsCancellationRequested){}
        finally{ready.TrySetCanceled();pipe?.Dispose();lifetime.StopApplication();}
    }
    private async Task<string> ReadAsync(CancellationToken ct)
    {
        var buffer=new byte[DiagnosticProtocol.MaximumBytes];var one=new byte[1];var length=0;
        while(true){if(await pipe!.ReadAsync(one,ct)==0)throw new EndOfStreamException();if(one[0]==10)break;if(length==buffer.Length)throw new InvalidDataException("diagnostic_size_invalid");buffer[length++]=one[0];}
        return new UTF8Encoding(false,true).GetString(buffer,0,length);
    }
    public Task SendAsync(object value,CancellationToken ct){var json=JsonSerializer.Serialize(value);DiagnosticProtocol.Validate(json);return WriteAsync(json,ct);}
    private async Task WriteAsync(string json,CancellationToken ct)
    {
        await writes.WaitAsync(ct);try{await pipe!.WriteAsync(Encoding.UTF8.GetBytes(json+"\n"),ct);await pipe.FlushAsync(ct);}finally{writes.Release();}
    }
}
