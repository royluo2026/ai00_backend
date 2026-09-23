using System.Diagnostics;
using System.Globalization;
using System.Text;
using System.Text.Json;
using System.Threading.Channels;
using Ai00.Connector.Contracts;

namespace Ai00.Connector.Adapters.VisMockup;

internal interface ITeamcenterVisualizationLifecycle
{
    bool IsReady(long generation);
    Task StartAsync(long generation, string endpointId, string username, string password, CancellationToken ct);
    void Invalidate(long generation);
    Task StopAsync(long generation, CancellationToken ct);
}

internal sealed class TeamcenterVisualizationSession(Func<Process> startProcess, string materialRoot)
    : ITeamcenterVisualizationLifecycle
{
    private const string Prefix = "AI00_TC_VIS_V2:";
    private readonly object state = new();
    private readonly SemaphoreSlim operation = new(1,1);
    private readonly Queue<string> timings = new();
    private Child? current;
    private long invalidThrough;

    private sealed class Child(Process process, long generation)
    {
        internal readonly Process Process = process;
        internal readonly long Generation = generation;
        internal readonly CancellationTokenSource Abort = new();
        internal readonly CancellationTokenSource Drain = new();
        internal readonly Channel<JsonElement> Frames = Channel.CreateBounded<JsonElement>(16);
        internal Task Output = Task.CompletedTask, Error = Task.CompletedTask;
        internal Task? Stop;
        internal bool Ready;
        internal int Busy;
        internal string? ExpectedId, ExpectedType;
    }

    internal IReadOnlyList<string> Timings { get { lock(state) return timings.ToArray(); } }
    public bool IsReady(long generation)
    {
        lock(state) return current is { Ready:true } child && child.Generation==generation
            && !child.Abort.IsCancellationRequested && !child.Process.HasExited;
    }

    private void Timing(string phase, double ms)
    {
        var line=TeamcenterProcessWorker.SanitizeVisualizationTiming(
            "AI00_TC_TIMING_V1:"+JsonSerializer.Serialize(new {phase,elapsed_ms=ms}));
        if(line is null)return;
        lock(state) { if(timings.Count==32)timings.Dequeue();timings.Enqueue(line); }
        Console.Error.WriteLine(line);
    }

    public void Invalidate(long generation)
    {
        Child? child;
        lock(state) { invalidThrough=Math.Max(invalidThrough,generation);child=current?.Generation==generation?current:null;if(child is not null)child.Ready=false; }
        child?.Abort.Cancel();
    }

    public async Task StartAsync(long generation,string endpointId,string username,string password,CancellationToken ct)
    {
        await operation.WaitAsync(ct);
        Child? child=null;
        try
        {
            Child? old;lock(state)old=current;
            if(old is not null)await StopAsync(old.Generation,CancellationToken.None);
            var started=Stopwatch.GetTimestamp();
            lock(state)
            {
                ct.ThrowIfCancellationRequested();
                if(generation<=invalidThrough)throw new ConnectorException("teamcenter_session_expired");
                child=new Child(startProcess(),generation) { Busy=1 };current=child;
            }
            Timing("process_start",Stopwatch.GetElapsedTime(started).TotalMilliseconds);
            child.Output=PumpAsync(child,false);child.Error=PumpAsync(child,true);
            using var linked=CancellationTokenSource.CreateLinkedTokenSource(ct,child.Abort.Token);
            var id=Guid.NewGuid().ToString("N");
            await SendAsync(child,"login",id,new {endpoint_id=endpointId,username,password},linked.Token);
            await ReceiveAsync(child,"ready",id,linked.Token);
            lock(state)
            {
                linked.Token.ThrowIfCancellationRequested();
                if(current!=child||generation<=invalidThrough)throw new ConnectorException("teamcenter_session_expired");
                child.Ready=true;
            }
        }
        catch { if(child is not null)await StopAsync(generation,CancellationToken.None);throw; }
        finally { if(child is not null)Volatile.Write(ref child.Busy,0);operation.Release(); }
    }

    public async Task<TeamcenterLaunchResult> ConsumeAsync(TeamcenterSourceSelector selector,string expectedVisdocUid,
        string visualizationOperation,Func<string,CancellationToken,Task> consumer,CancellationToken ct)
    {
        await operation.WaitAsync(ct);
        Child? child=null;string? operationRoot=null;bool invoked=false;Exception? consumerError=null;
        try
        {
            lock(state)
            {
                child=current;
                if(child is null||!IsReady(child.Generation))throw new ConnectorNoEffectException("teamcenter_session_expired");
                child.Busy=1;
            }
            using var linked=CancellationTokenSource.CreateLinkedTokenSource(ct,child.Abort.Token);
            var token=linked.Token;
            TeamcenterProcessWorker.SecureVisualizationMaterialRoot(materialRoot);
            operationRoot=Path.Combine(Path.GetFullPath(materialRoot),Guid.NewGuid().ToString("N"));
            TeamcenterProcessWorker.SecureVisualizationMaterialRoot(operationRoot);
            var id=Guid.NewGuid().ToString("N");
            await SendAsync(child,"consume",id,new {source_selector=selector,expected_visdoc_uid=expectedVisdocUid,
                source_identity_hash=selector.IdentityHash,material_root=operationRoot,visualization_operation=visualizationOperation},token);
            var material=await ReceiveAsync(child,"material_ready",id,token);
            var path=TeamcenterProcessWorker.ValidateMaterialPath(operationRoot,
                TeamcenterProcessWorker.ParseVisualizationMaterialReady(material.GetRawText(),expectedVisdocUid,selector.IdentityHash));
            var started=Stopwatch.GetTimestamp();
            var retained=TeamcenterProcessWorker.RetainRendererMaterial(materialRoot,path);
            Timing("material_retain",Stopwatch.GetElapsedTime(started).TotalMilliseconds);
            token.ThrowIfCancellationRequested();
            started=Stopwatch.GetTimestamp();invoked=true;
            try { await consumer(retained,token); }
            catch(Exception error){consumerError=error;}
            finally {Timing("native_consumer",Stopwatch.GetElapsedTime(started).TotalMilliseconds);}
            started=Stopwatch.GetTimestamp();
            await SendAsync(child,consumerError is null?"material_consumed":"material_failed",id,new {},token);
            var final=await ReceiveAsync(child,"result",id,token);
            Timing("ack_final",Stopwatch.GetElapsedTime(started).TotalMilliseconds);
            if(consumerError is not null)System.Runtime.ExceptionServices.ExceptionDispatchInfo.Capture(consumerError).Throw();
            RequireKeys(final,"ok","result");
            if(final.GetProperty("ok").ValueKind!=JsonValueKind.True)throw Invalid();
            var resultElement=final.GetProperty("result");
            RequireKeys(resultElement,"launch_id","runner_started","expected_visdoc_uid","source_identity_hash");
            var result=resultElement.Deserialize<TeamcenterLaunchResult>()??throw Invalid();
            if(!result.RunnerStarted||result.ExpectedVisdocUid!=expectedVisdocUid||result.SourceIdentityHash!=selector.IdentityHash
                ||result.LaunchId is null||!System.Text.RegularExpressions.Regex.IsMatch(result.LaunchId,@"\Atclaunch:[a-f0-9]{64}\z"))throw Invalid();
            if(!IsReady(child.Generation))throw new ConnectorException("teamcenter_session_expired");
            return result;
        }
        catch(Exception error)
        {
            if(child is not null)await StopAsync(child.Generation,CancellationToken.None);
            if(consumerError is not null)System.Runtime.ExceptionServices.ExceptionDispatchInfo.Capture(consumerError).Throw();
            if(!invoked)throw TeamcenterProcessWorker.NoEffectBeforeVisualizationConsumer(error,"");
            // Native effect may already exist; never classify a lost final frame as no-effect.
            throw new ConnectorException("invocation_outcome_unknown");
        }
        finally
        {
            if(operationRoot is not null)try{Directory.Delete(operationRoot,true);}catch(IOException){}catch(UnauthorizedAccessException){}
            if(child is not null)Volatile.Write(ref child.Busy,0);
            operation.Release();
        }
    }

    public Task StopAsync(long generation,CancellationToken ct)
    {
        lock(state)
        {
            invalidThrough=Math.Max(invalidThrough,generation);
            if(current is not { } child||child.Generation!=generation)return Task.CompletedTask;
            child.Ready=false;
            // Do not detach until teardown completes: a second Stop must join the same cleanup.
            return child.Stop??=Task.Run(()=>StopChildAsync(child));
        }
    }
    private async Task StopChildAsync(Child child)
    {
        child.Abort.Cancel();
        using var timeout=new CancellationTokenSource(TimeSpan.FromSeconds(2));
        try
        {
            if(!child.Process.HasExited&&Volatile.Read(ref child.Busy)==0)
            {
                await SendAsync(child,"logout",Guid.NewGuid().ToString("N"),new {},timeout.Token);
                child.Process.StandardInput.Close();
                await child.Process.WaitForExitAsync(timeout.Token);
            }
        }
        catch { /* Shutdown falls back to terminating only this owned child. */ }
        finally
        {
            try
            {
                if(!child.Process.HasExited)child.Process.Kill();
                await child.Process.WaitForExitAsync().WaitAsync(TimeSpan.FromSeconds(2));
            }
            catch(InvalidOperationException){}catch(TimeoutException){}
            child.Drain.Cancel();
            try{await Task.WhenAll(child.Output,child.Error).WaitAsync(TimeSpan.FromSeconds(2));}catch{}
            lock(state) {if(current==child)current=null;}
            child.Process.Dispose();
        }
    }

    private async Task PumpAsync(Child child,bool stderr)
    {
        var reader=stderr?child.Process.StandardError:child.Process.StandardOutput;
        var buffer=new char[2048];var line=new StringBuilder();bool discard=false;
        try
        {
            while(true)
            {
                var count=await reader.ReadAsync(buffer.AsMemory(),child.Drain.Token);
                if(count==0)break;
                for(var i=0;i<count;i++)
                {
                    var ch=buffer[i];
                    if(ch=='\n')
                    {
                        if(!discard)
                        {
                            var text=line.ToString().TrimEnd('\r');
                            if(stderr)
                            {
                                var safe=TeamcenterProcessWorker.SanitizeVisualizationTiming(text);
                                if(safe is not null){lock(state){if(timings.Count==32)timings.Dequeue();timings.Enqueue(safe);}Console.Error.WriteLine(safe);}
                            }
                            else if(text.StartsWith(Prefix,StringComparison.Ordinal))
                            {
                                if(Encoding.UTF8.GetByteCount(text)>65536)throw Invalid();
                                using var doc=JsonDocument.Parse(text[Prefix.Length..],new JsonDocumentOptions{MaxDepth=32});
                                ValidateUnique(doc.RootElement);RequireKeys(doc.RootElement,"type","generation","request_id","payload");
                                lock(child)
                                {
                                    var frame=doc.RootElement;
                                    if(child.ExpectedId is null||frame.GetProperty("request_id").GetString()!=child.ExpectedId
                                        ||frame.GetProperty("generation").GetString()!=child.Generation.ToString(CultureInfo.InvariantCulture)
                                        ||frame.GetProperty("type").GetString()!=child.ExpectedType
                                            && frame.GetProperty("type").GetString()!="result")throw Invalid();
                                    child.ExpectedId=null;child.ExpectedType=null;
                                }
                                if(!child.Frames.Writer.TryWrite(doc.RootElement.Clone()))throw Invalid();
                            }
                        }
                        line.Clear();discard=false;
                    }
                    else if(!discard)
                    {
                        if(line.Length>=(stderr?1024:65536))
                        {
                            if(!stderr&&line.ToString().StartsWith(Prefix,StringComparison.Ordinal))throw Invalid();
                            line.Clear();discard=true;
                        }
                        else line.Append(ch);
                    }
                }
            }
            if(!stderr)throw Invalid();
        }
        catch(Exception)
        {
            child.Frames.Writer.TryComplete(Invalid());
            child.Abort.Cancel();
            _=StopAsync(child.Generation,CancellationToken.None);
        }
    }

    private static async Task SendAsync(Child child,string type,string id,object payload,CancellationToken ct)
    {
        var line=Prefix+JsonSerializer.Serialize(new {type,generation=child.Generation.ToString(CultureInfo.InvariantCulture),request_id=id,payload});
        if(Encoding.UTF8.GetByteCount(line)>65536)throw Invalid();
        lock(child)
        {
            if(child.ExpectedId is not null)throw Invalid();
            child.ExpectedId=id;
            child.ExpectedType=type switch {"login"=>"ready","consume"=>"material_ready","logout"=>"closed",_=>"result"};
        }
        await child.Process.StandardInput.WriteLineAsync(line.AsMemory(),ct);
        await child.Process.StandardInput.FlushAsync(ct);
    }
    private static async Task<JsonElement> ReceiveAsync(Child child,string expected,string id,CancellationToken ct)
    {
        var frame=await child.Frames.Reader.ReadAsync(ct);
        if(frame.GetProperty("generation").GetString()!=child.Generation.ToString(CultureInfo.InvariantCulture)
            ||frame.GetProperty("request_id").GetString()!=id)throw Invalid();
        var payload=frame.GetProperty("payload");
        if(frame.GetProperty("type").GetString()=="result"&&payload.TryGetProperty("ok",out var ok)&&ok.ValueKind==JsonValueKind.False)
        {
            RequireKeys(payload,"ok","code");
            var code=payload.GetProperty("code").GetString();
            throw new ConnectorException(code is "teamcenter_authentication_failed" or "teamcenter_session_expired"
                or "teamcenter_object_not_found" or "teamcenter_visualization_consumer_failed"
                or "teamcenter_source_selector_invalid" or "teamcenter_visualization_operation_invalid"
                or "teamcenter_visualization_launch_info_failed" or "teamcenter_visualization_launch_info_invalid"
                or "teamcenter_direct_model_dataset_unavailable" or "teamcenter_direct_model_dataset_uid_mismatch"
                or "teamcenter_direct_model_dataset_type_invalid" or "teamcenter_direct_model_properties_failed"
                or "teamcenter_direct_model_file_ambiguous" or "teamcenter_direct_model_file_unavailable"
                or "teamcenter_direct_model_download_failed" or "teamcenter_worker_response_invalid"
                ? code : "teamcenter_visualization_launch_failed");
        }
        if(frame.GetProperty("type").GetString()!=expected||payload.ValueKind!=JsonValueKind.Object)throw Invalid();
        if(expected is "ready" or "closed")RequireKeys(payload);
        return payload;
    }
    private static void RequireKeys(JsonElement value,params string[] names)
    {
        if(value.ValueKind!=JsonValueKind.Object||!value.EnumerateObject().Select(x=>x.Name).Order().SequenceEqual(names.Order()))throw Invalid();
    }
    private static void ValidateUnique(JsonElement value)
    {
        if(value.ValueKind==JsonValueKind.Object)
        {
            var seen=new HashSet<string>(StringComparer.Ordinal);
            foreach(var property in value.EnumerateObject()){if(!seen.Add(property.Name))throw Invalid();ValidateUnique(property.Value);}
        }
        else if(value.ValueKind==JsonValueKind.Array)foreach(var item in value.EnumerateArray())ValidateUnique(item);
    }
    private static ConnectorException Invalid()=>new("teamcenter_worker_response_invalid");
}
