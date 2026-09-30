using System.Diagnostics;
using System.Text.Json;
using Ai00.Connector.Adapters.VisMockup;
using Ai00.Connector.Contracts;
using Xunit;

namespace Ai00.Connector.Tests;
public sealed class TeamcenterReadOnlySessionTests
{
    private sealed class Harness : IAsyncDisposable
    {
        internal int Starts;
        internal Process? Child;
        internal readonly TeamcenterReadOnlySession Session;
        internal Harness(string mode="normal")
        {
            Session=new TeamcenterReadOnlySession(()=>{
                Starts++;
                var info=TeamcenterProcessWorker.CreateStartInfo(@"C:\Program Files\nodejs\node.exe","unused",[]);
                info.ArgumentList.Clear();info.ArgumentList.Add(Path.Combine(AppContext.BaseDirectory,"teamcenter_readonly_child.cjs"));
                info.ArgumentList.Add(mode=="expire-once"?(Starts==1?"expire":"normal"):mode=="exit-once"?(Starts==1?"exit":"normal"):mode);
                Child=Process.Start(info)!;return Child;
            });
            Session.Activate(1);
        }
        public ValueTask DisposeAsync()=>new(Session.StopAsync(1));
        internal Task<JsonElement> Read(CancellationToken ct=default)=>Session.RunAsync("children",new{},"user","secret",ct);
    }
    [Fact] public async Task Repeated_reads_share_process_and_credentials_switch_restarts_it()
    {
        await using var h=new Harness();using var timeout=new CancellationTokenSource(TimeSpan.FromSeconds(10));
        Assert.Equal(1,(await h.Read(timeout.Token)).GetProperty("count").GetInt32());
        Assert.Equal(2,(await h.Read(timeout.Token)).GetProperty("count").GetInt32());
        Assert.Equal(1,h.Starts);Assert.False(h.Child!.HasExited);
        Assert.Equal(1,(await h.Session.RunAsync("node_properties",new{},"other-user","secret",timeout.Token)).GetProperty("count").GetInt32());
        Assert.Equal(2,h.Starts);
    }
    [Fact] public async Task Expired_session_reconnects_once_without_changing_operation()
    {
        await using var h=new Harness("expire-once");using var timeout=new CancellationTokenSource(TimeSpan.FromSeconds(10));
        Assert.Equal("children",(await h.Read(timeout.Token)).GetProperty("command").GetString());Assert.Equal(2,h.Starts);
    }
    [Fact] public async Task Production_native_byte_pagination_passes_the_real_correlated_process_frame_reader()
    {
        await using var h=new Harness("bulk-large");using var timeout=new CancellationTokenSource(TimeSpan.FromSeconds(20));
        var paths=Enumerable.Range(0,200).Select(index=>new[]{new{occurrence_uid="O"+index,item_revision_uid="rev"}}).ToArray();
        var result=await h.Session.RunAsync("cache_properties",new{occurrence_paths=paths},"user","secret",timeout.Token);
        var rows=result.GetProperty("rows");Assert.InRange(rows.GetArrayLength(),1,199);
        Assert.True(System.Text.Encoding.UTF8.GetByteCount(result.GetRawText())<8*1024*1024);
        Assert.Equal(1,h.Starts);
    }
    [Fact] public async Task Mismatched_frame_is_rejected_and_worker_is_stopped()
    {
        await using var h=new Harness("wrong-id");using var timeout=new CancellationTokenSource(TimeSpan.FromSeconds(10));
        var error=await Assert.ThrowsAsync<ConnectorException>(()=>h.Read(timeout.Token));
        Assert.Equal("teamcenter_worker_response_invalid",error.Message);Assert.Equal(1,h.Starts);
    }
    [Fact] public async Task Interrupted_file_reader_restarts_once_and_records_transport_failure()
    {
        await using var h=new Harness("exit-once");using var timeout=new CancellationTokenSource(TimeSpan.FromSeconds(10));
        var events=new List<JsonElement>();
        h.Session.Diagnostic=(stage,detail)=>{Assert.Equal("tc_worker_transport_failed",stage);events.Add(JsonSerializer.SerializeToElement(detail));};
        var result=await h.Session.RunAsync("cache_file",new{file_ref=new{file_uid="file"}},"user","secret",timeout.Token);
        Assert.Equal("cache_file",result.GetProperty("command").GetString());Assert.Equal(2,h.Starts);
        Assert.Equal("file",result.GetProperty("file_ref").GetProperty("file_uid").GetString());
        var diagnostic=Assert.Single(events);Assert.True(diagnostic.GetProperty("retry_after_failure").GetBoolean());
        Assert.Equal("teamcenter_worker_disconnected",diagnostic.GetProperty("error_code").GetString());
    }
    [Fact] public async Task Revoked_generation_cannot_restart_after_worker_disconnect()
    {
        await using var h=new Harness("exit-once");using var timeout=new CancellationTokenSource(TimeSpan.FromSeconds(10));
        h.Session.Diagnostic=(_,_)=>h.Session.Invalidate(1);
        var error=await Assert.ThrowsAsync<ConnectorException>(()=>h.Session.RunAsync("cache_file",new{},"user","secret",timeout.Token));
        Assert.Equal("teamcenter_session_expired",error.Message);Assert.Equal(1,h.Starts);
    }
    [Theory]
    [InlineData("exit","teamcenter_worker_disconnected",2)]
    [InlineData("wrong-id","teamcenter_worker_response_invalid",1)]
    public async Task File_recovery_is_bounded_and_does_not_retry_invalid_frames(string mode,string code,int starts)
    {
        await using var h=new Harness(mode);using var timeout=new CancellationTokenSource(TimeSpan.FromSeconds(10));
        var error=await Assert.ThrowsAsync<ConnectorException>(()=>h.Session.RunAsync("cache_file",new{},"user","secret",timeout.Token));
        Assert.Equal(code,error.Message);Assert.Equal(starts,h.Starts);
    }
    [Fact] public async Task Cancellation_stops_owned_child_and_logout_fences_late_reads()
    {
        await using var h=new Harness("hang");using var timeout=new CancellationTokenSource(TimeSpan.FromMilliseconds(350));
        await Assert.ThrowsAnyAsync<OperationCanceledException>(()=>h.Read(timeout.Token));Assert.Equal(1,h.Starts);
        h.Session.Invalidate(1);await h.Session.StopAsync(1);
        var error=await Assert.ThrowsAsync<ConnectorException>(()=>h.Read());Assert.Equal("teamcenter_session_expired",error.Message);
        Assert.Equal(1,h.Starts);
    }
}
