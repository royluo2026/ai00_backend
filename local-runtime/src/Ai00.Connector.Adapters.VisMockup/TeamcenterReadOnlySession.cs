using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading.Channels;
using Ai00.Connector.Contracts;

namespace Ai00.Connector.Adapters.VisMockup;

// One bounded read worker, separate from rendering effects. Cloud receipts own durable recovery.
internal sealed class TeamcenterReadOnlySession(Func<Process> startProcess)
{
    internal Action<string,object>? Diagnostic {get;set;}
    private const string Prefix="AI00_TC_READ_V1:";
    private readonly object state=new();
    private readonly SemaphoreSlim operation=new(1,1);
    private long generation,invalidThrough=-1;
    private Child? current;
    private sealed class Child(Process process,long generation,string identity)
    {
        internal readonly Process Process=process;
        internal readonly long Generation=generation;
        internal readonly string Identity=identity;
        internal readonly CancellationTokenSource Abort=new(),Drain=new();
        internal readonly Channel<JsonElement> Frames=Channel.CreateBounded<JsonElement>(1);
        internal Task Output=Task.CompletedTask,Error=Task.CompletedTask;
    }
    internal void Activate(long value) {lock(state){generation=value;}}
    internal void Invalidate(long value)
    {
        lock(state){invalidThrough=Math.Max(invalidThrough,value);if(current?.Generation==value)current.Abort.Cancel();}
    }
    internal async Task StopAsync(long value)
    {
        Invalidate(value);
        await operation.WaitAsync();
        try {Child? child;lock(state)child=current?.Generation==value?current:null;if(child is not null)await DropAsync(child,true);}
        finally{operation.Release();}
    }
    internal async Task<JsonElement> RunAsync(string command,object payload,string username,string password,CancellationToken ct)
    {
        if(command is not ("children" or "node_properties" or "node_properties_raw" or "cache_structure" or "cache_structure_page" or "cache_properties" or "cache_file" or "cache_file_preflight"))throw new ConnectorException("teamcenter_worker_command_forbidden");
        var identity=Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(JsonSerializer.Serialize(new[]{username,password}))));
        await operation.WaitAsync(ct);
        try
        {
            for(var attempt=0;attempt<2;attempt++)
            {
                Child? child;long active;
                lock(state){active=generation;if(active<=invalidThrough)throw new ConnectorException("teamcenter_session_expired");child=current;}
                if(child is not null&&(child.Generation!=active||child.Identity!=identity||child.Abort.IsCancellationRequested||child.Process.HasExited))
                {await DropAsync(child,true);child=null;}
                var requestId=Guid.NewGuid().ToString("N");var timer=Stopwatch.StartNew();
                try
                {
                    if(child is null)
                    {
                        lock(state)
                        {
                            ct.ThrowIfCancellationRequested();
                            if(active!=generation||active<=invalidThrough)throw new ConnectorException("teamcenter_session_expired");
                            child=new Child(startProcess(),active,identity);current=child;
                        }
                        child.Output=PumpAsync(child,false);child.Error=PumpAsync(child,true);
                        using var loginToken=CancellationTokenSource.CreateLinkedTokenSource(ct,child.Abort.Token);
                        await child.Process.StandardInput.WriteLineAsync(username.AsMemory(),loginToken.Token);
                        await child.Process.StandardInput.WriteLineAsync(password.AsMemory(),loginToken.Token);
                    }
                    using var linked=CancellationTokenSource.CreateLinkedTokenSource(ct,child.Abort.Token);
                    var id=requestId;
                    var request=JsonSerializer.Serialize(new{command,payload,keep_session=true,request_id=id});
                    if(Encoding.UTF8.GetByteCount(request)>65536)throw new ConnectorException("teamcenter_worker_response_too_large");
                    await child.Process.StandardInput.WriteLineAsync(request.AsMemory(),linked.Token);
                    await child.Process.StandardInput.FlushAsync(linked.Token);
                    var response=await child.Frames.Reader.ReadAsync(linked.Token);
                    var names=response.EnumerateObject().Select(p=>p.Name).Order().ToArray();
                    if(response.GetProperty("request_id").GetString()!=id)throw Invalid();
                    if(response.GetProperty("ok").ValueKind==JsonValueKind.False)
                    {
                        if(!names.SequenceEqual(new[]{"code","ok","request_id"}.Order()))throw Invalid();
                        var code=response.GetProperty("code").GetString();
                        if(code is null||code.Length>128||!code.All(c=>char.IsAsciiLetterOrDigit(c)||c=='_'))throw Invalid();
                        throw new ConnectorException(code);
                    }
                    if(response.GetProperty("ok").ValueKind!=JsonValueKind.True||!names.SequenceEqual(new[]{"ok","request_id","result"}.Order()))throw Invalid();
                    lock(state){if(active!=generation||active<=invalidThrough)throw new ConnectorException("teamcenter_session_expired");}
                    linked.Token.ThrowIfCancellationRequested();
                    return response.GetProperty("result").Clone();
                }
                catch(ConnectorException error) when(error.Message=="teamcenter_session_expired"&&attempt==0&&!ct.IsCancellationRequested)
                {
                    if(child is not null)await DropAsync(child,false);
                    // Only replay a read after TC expiry. A revoked credential generation cannot reconnect.
                    lock(state){if(active!=generation||active<=invalidThrough)throw;}
                }
                catch(ChannelClosedException error)
                {
                    var failure=error.InnerException as ConnectorException??Invalid();
                    var retry=command=="cache_file"&&failure.Code=="teamcenter_worker_disconnected"&&attempt==0&&!ct.IsCancellationRequested;
                    int? exitCode=null;
                    if(child is not null&&child.Process.HasExited)exitCode=child.Process.ExitCode;
                    try{Diagnostic?.Invoke("tc_worker_transport_failed",new{request_id=requestId,method=command,error_code=failure.Code,
                        sequence=attempt+1,elapsed_ms=timer.Elapsed.TotalMilliseconds,observed=exitCode,retry_after_failure=retry});}catch{}
                    if(child is not null)await DropAsync(child,false);
                    ct.ThrowIfCancellationRequested();
                    if(retry)
                    {
                        // FMS reads have not returned bytes to the uploader. Retry the
                        // same reference once, only after the owned child is stopped.
                        lock(state){if(active!=generation||active<=invalidThrough)throw new ConnectorException("teamcenter_session_expired");}
                        continue;
                    }
                    throw failure;
                }
                catch
                {
                    if(child is not null)await DropAsync(child,false);
                    ct.ThrowIfCancellationRequested();throw;
                }
            }
            throw new ConnectorException("teamcenter_session_expired");
        }
        finally{operation.Release();}
    }
    private static async Task PumpAsync(Child child,bool stderr)
    {
        var reader=stderr?child.Process.StandardError:child.Process.StandardOutput;
        var buffer=new char[4096];var line=new StringBuilder();bool discard=false;
        try
        {
            while(true)
            {
                var count=await reader.ReadAsync(buffer.AsMemory(),child.Drain.Token);
                if(count==0){if(!stderr)throw new ConnectorException("teamcenter_worker_disconnected");return;}
                for(var index=0;index<count;index++)
                {
                    var ch=buffer[index];
                    if(ch=='\n')
                    {
                        if(!discard)
                        {
                            var text=line.ToString().TrimEnd('\r');
                            if(stderr)
                            {
                                var safe=TeamcenterProcessWorker.SanitizeVisualizationTiming(text);
                                if(safe is not null)Console.Error.WriteLine(safe);
                            }
                            else if(text.StartsWith(Prefix,StringComparison.Ordinal))
                            {
                                using var doc=JsonDocument.Parse(text[Prefix.Length..],new JsonDocumentOptions{MaxDepth=32});
                                if(doc.RootElement.ValueKind!=JsonValueKind.Object||doc.RootElement.EnumerateObject().GroupBy(p=>p.Name).Any(g=>g.Count()!=1)
                                    ||!doc.RootElement.TryGetProperty("request_id",out _)||!doc.RootElement.TryGetProperty("ok",out _))throw Invalid();
                                if(!child.Frames.Writer.TryWrite(doc.RootElement.Clone()))throw Invalid();
                            }
                        }
                        line.Clear();discard=false;
                    }
                    else if(!discard)
                    {
                        var maximum=stderr?1024:64*1024*1024;
                        if(line.Length>=maximum)
                        {
                            if(!stderr&&line.ToString().StartsWith(Prefix,StringComparison.Ordinal))throw new ConnectorException("teamcenter_worker_response_too_large");
                            line.Clear();discard=true;
                        }
                        else line.Append(ch);
                    }
                }
            }
        }
        catch(Exception error){child.Frames.Writer.TryComplete(error is ConnectorException?error:Invalid());}
    }
    internal static async Task ConfirmWorkerExitAsync(Task exited,TimeSpan timeout)
    {
        try{await exited.WaitAsync(timeout);}
        catch(TimeoutException){throw new ConnectorException("teamcenter_worker_cleanup_failed");}
    }
    private async Task DropAsync(Child child,bool graceful)
    {
        lock(state){if(current==child)current=null;}
        child.Abort.Cancel();
        try
        {
            if(graceful&&!child.Process.HasExited)
            {
                child.Process.StandardInput.Close();
                try{await child.Process.WaitForExitAsync().WaitAsync(TimeSpan.FromSeconds(2));}catch(TimeoutException){}
            }
            if(!child.Process.HasExited)child.Process.Kill();
            await ConfirmWorkerExitAsync(child.Process.WaitForExitAsync(),TimeSpan.FromSeconds(2));
        }
        catch{throw new ConnectorException("teamcenter_worker_cleanup_failed");}
        finally
        {
            child.Drain.Cancel();
            try{await Task.WhenAll(child.Output,child.Error).WaitAsync(TimeSpan.FromSeconds(2));}catch{}
            child.Process.Dispose();
        }
    }
    private static ConnectorException Invalid()=>new("teamcenter_worker_response_invalid");
}
