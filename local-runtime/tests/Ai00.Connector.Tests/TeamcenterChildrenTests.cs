using System.Text.Json;
using Ai00.Connector.Adapters.VisMockup;
using Ai00.Connector.Contracts;
using Xunit;

namespace Ai00.Connector.Tests;

public class TeamcenterChildrenTests
{
    static JsonElement Input(int cursor=0, string? generation=null, bool refresh=false, string rule="Latest Working") =>
        JsonSerializer.SerializeToElement(new { source_selector=new TeamcenterSourceSelector("tc-production","obj","rev","",rule,"2026-09-16T00:00:00Z"), parent_path=Array.Empty<object>(),cursor,page_size=1,refresh,generation });

    [Fact]
    public async Task Adapter_dispatch_returns_lightweight_partial_page_and_exact_contract_hash()
    {
        using var runtime=new TeamcenterReadOnlyRuntime(new Worker(),Path.GetTempFileName());
        await runtime.LoginAsync("tc-production","u","s",default);
        using var sta=new StaDispatcher();
        var adapter=new VisMockupAdapter(sta,new AllowedPathPolicy([Path.GetTempPath()]),
            new FakeVisMockupCom(),Path.GetTempPath(),Path.GetTempFileName(),runtime);
        var contract=JsonDocument.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory,"teamcenter.product_structure.children.read@1.json"))).RootElement;
        Assert.True(adapter.Manifest.Supports("teamcenter.product_structure.children.read@1",CanonicalJson.Hash(contract)));
        var result=await adapter.ExecuteAsync(new AdapterOperation("teamcenter.product_structure.children.read@1",Input()),default);
        Assert.True(result.Ok);
        var page=Assert.IsType<TeamcenterChildrenPage>(result.Data);
        Assert.False(page.Complete);
        Assert.Single(page.Nodes);
        Assert.Null(page.Nodes[0].HasChildren);
        var keys=JsonSerializer.SerializeToElement(page).EnumerateObject().Select(p=>p.Name).Order();
        Assert.Equal(new[]{"source_identity_hash","captured_at","cache_hit","generation","parent","nodes","cursor","next_cursor","child_count","complete"}.Order(),keys);
    }

    [Fact]
    public async Task Cache_pins_pages_and_partitions_credentials_and_selector()
    {
        var worker=new Worker();
        using var runtime=new TeamcenterReadOnlyRuntime(worker,Path.GetTempFileName());
        await runtime.LoginAsync("tc-production","u","s",default);
        var first=Assert.IsType<TeamcenterChildrenPage>(await runtime.ReadChildrenAsync(Input(),default));
        Assert.False(first.CacheHit); Assert.False(first.Complete); Assert.Single(first.Nodes);
        var page=Assert.IsType<TeamcenterChildrenPage>(await runtime.ReadChildrenAsync(Input(1,first.Generation),default));
        Assert.True(page.CacheHit); Assert.Equal(1,worker.Calls); Assert.Equal(2,page.ChildCount);
        Assert.NotEqual(first.Nodes[0].OccurrenceId,page.Nodes[0].OccurrenceId);
        await runtime.ReadChildrenAsync(Input(refresh:true),default);
        Assert.Equal("teamcenter_children_generation_stale",(await Assert.ThrowsAsync<ConnectorException>(()=>runtime.ReadChildrenAsync(Input(1,first.Generation),default))).Message);
        await runtime.ReadChildrenAsync(Input(rule:"Released"),default);
        await runtime.LoginAsync("tc-production","other","s",default);
        await runtime.ReadChildrenAsync(Input(),default);
        await runtime.LoginAsync("tc-production","other","changed",default);
        await runtime.ReadChildrenAsync(Input(),default);
        Assert.Equal(4,worker.Calls);
    }

    sealed class Worker : ITeamcenterWorker
    {
        public int Calls;
        public bool WaitForCancellation;
        public bool CleanupCompleted;
        public string ParentRevision="rev";
        public async Task<TeamcenterChildrenBatch> ReadChildrenAsync(TeamcenterSourceSelector s,TeamcenterOccurrenceEdge[] path,string u,string p,CancellationToken ct)
        {
            Calls++;
            if(WaitForCancellation)
            {
                try { await Task.Delay(Timeout.Infinite,ct); }
                finally { CleanupCompleted=true; }
            }
            TeamcenterChildNode Node(string edge) => new("",null,[new(edge,"rev")],1,edge=="a"?0:1,"Same","rev","01","Part",null);
            return new TeamcenterChildrenBatch(new("",null,[],0,0,"Root",ParentRevision,"01","Assembly",true),[Node("a"),Node("b")]);
        }
        public Task ValidateCredentialsAsync(string e,string u,string p,CancellationToken ct)=>Task.CompletedTask;
        public Task<IReadOnlyList<string>> GetRevisionRulesAsync(string u,string p,CancellationToken ct)=>throw new NotSupportedException();
        public Task<TeamcenterProductSearchResult> SearchAsync(string i,string r,string rule,string d,string u,string p,CancellationToken ct)=>throw new NotSupportedException();
        public Task<IReadOnlyList<TeamcenterOccurrence>> ObserveAsync(TeamcenterSourceSelector s,int n,int d,string projection,string u,string p,CancellationToken ct)=>throw new NotSupportedException();
        public Task<TeamcenterLaunchResult> LaunchAsync(TeamcenterSourceSelector s,string expected,string u,string p,CancellationToken ct)=>throw new NotSupportedException();
        public Task<TeamcenterLaunchResult> ConsumeVisualizationAsync(TeamcenterSourceSelector s,string expected,string visualizationOperation,Func<string,CancellationToken,Task> consumer,string u,string p,CancellationToken ct)=>throw new NotSupportedException();
    }

    [Fact]
    public async Task Canceled_child_read_releases_runtime_gate_for_retry()
    {
        var worker=new Worker {WaitForCancellation=true};
        using var runtime=new TeamcenterReadOnlyRuntime(worker,Path.GetTempFileName());
        await runtime.LoginAsync("tc-production","u","s",default);
        using var cancel=new CancellationTokenSource();
        var pending=runtime.ReadChildrenAsync(Input(),cancel.Token);
        cancel.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(()=>pending);
        Assert.True(worker.CleanupCompleted);
        worker.WaitForCancellation=false;
        var retry=await runtime.ReadChildrenAsync(Input(),default).WaitAsync(TimeSpan.FromSeconds(2));
        Assert.IsType<TeamcenterChildrenPage>(retry);
        Assert.Equal(2,worker.Calls);
    }

    [Fact]
    public async Task Wrong_parent_revision_is_not_cached_as_a_successful_empty_or_valid_result()
    {
        using var runtime=new TeamcenterReadOnlyRuntime(new Worker {ParentRevision="other-revision"},Path.GetTempFileName());
        await runtime.LoginAsync("tc-production","u","s",default);
        Assert.Equal("teamcenter_worker_response_invalid",(await Assert.ThrowsAsync<ConnectorException>(()=>runtime.ReadChildrenAsync(Input(),default))).Message);
    }

    [Fact]
    public async Task First_page_rejects_non_null_matching_generation()
    {
        using var runtime=new TeamcenterReadOnlyRuntime(new Worker(),Path.GetTempFileName());
        await runtime.LoginAsync("tc-production","u","s",default);
        var first=Assert.IsType<TeamcenterChildrenPage>(await runtime.ReadChildrenAsync(Input(),default));
        Assert.Equal("teamcenter_children_input_invalid",(await Assert.ThrowsAsync<ConnectorException>(
            ()=>runtime.ReadChildrenAsync(Input(generation:first.Generation),default))).Message);
    }

    [Fact]
    public async Task Restart_requires_login_then_reuses_only_same_principal_cache()
    {
        var cache=Path.GetTempFileName();var worker=new Worker();
        using(var first=new TeamcenterReadOnlyRuntime(worker,cache))
        {await first.LoginAsync("tc-production","u","s",default);await first.ReadChildrenAsync(Input(),default);}
        using var reopened=new TeamcenterReadOnlyRuntime(worker,cache);
        Assert.Equal("teamcenter_login_required",(await Assert.ThrowsAsync<ConnectorException>(()=>reopened.ReadChildrenAsync(Input(),default))).Message);
        await reopened.LoginAsync("tc-production","u","s",default);
        Assert.True(Assert.IsType<TeamcenterChildrenPage>(await reopened.ReadChildrenAsync(Input(),default)).CacheHit);
        Assert.Equal(1,worker.Calls);
    }
}
