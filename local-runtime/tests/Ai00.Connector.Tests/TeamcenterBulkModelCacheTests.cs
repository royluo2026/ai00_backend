using System.Text.Json;
using Ai00.Connector.Adapters.VisMockup;
using Ai00.Connector.Contracts;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class TeamcenterBulkModelCacheTests
{
    private static readonly TeamcenterSourceSelector Source=new("tc-production","obj","rev","","Latest Working","2026-09-28T00:00:00Z");
    private static JsonElement Input(string batch,int cursor=0,string? generation=null,string? principal=null,int size=2)=>JsonSerializer.SerializeToElement(new{source_selector=Source,batch_id=batch,cursor,page_size=size,generation,expected_principal_hash=principal});
    private static JsonElement Body(object result)=>JsonDocument.Parse(Assert.IsType<TeamcenterModelCacheResult>(result).ResultJson).RootElement.Clone();

    [Fact]
    public async Task Adapter_advertises_both_cache_majors_with_their_exact_contract_hashes()
    {
        using var runtime=new TeamcenterReadOnlyRuntime(new Worker(),Path.GetTempFileName());await runtime.LoginAsync("tc-production","u","s",default);
        using var sta=new StaDispatcher();var adapter=new VisMockupAdapter(sta,new AllowedPathPolicy([Path.GetTempPath()]),new FakeVisMockupCom(),Path.GetTempPath(),Path.GetTempFileName(),runtime);
        foreach(var version in new[]{1,2})
        {
            using var contract=JsonDocument.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory,$"teamcenter.model_cache.read@{version}.json")));
            Assert.True(adapter.Manifest.Supports($"teamcenter.model_cache.read@{version}",CanonicalJson.Hash(contract.RootElement)));
            Assert.False(adapter.Manifest.Supports($"teamcenter.model_cache.read@{version}","sha256:"+new string('0',64)));
        }
        Assert.False(adapter.Manifest.Supports("teamcenter.model_cache.read@3","sha256:"+new string('0',64)));
        var result=await adapter.ExecuteAsync(new AdapterOperation("teamcenter.model_cache.read@2",Input(Guid.NewGuid().ToString("N"))),default);
        Assert.True(result.Ok);Assert.IsType<TeamcenterModelCacheResult>(result.Data);
    }

    [Fact]
    public async Task Bulk_pages_preserve_exact_instances_and_completed_pages_survive_restart_without_TC()
    {
        var path=Path.GetTempFileName();var batch=Guid.NewGuid().ToString("N");var worker=new Worker();
        string firstBody,generation,principal;
        using(var runtime=new TeamcenterReadOnlyRuntime(worker,path))
        {
            await runtime.LoginAsync("tc-production","u","s",default);
            var result=Assert.IsType<TeamcenterModelCacheResult>(await runtime.ReadModelCacheV2Async(Input(batch),default));
            principal=result.PrincipalHash;firstBody=result.ResultJson;var body=Body(result);generation=body.GetProperty("generation").GetString()!;
            Assert.Equal(2,body.GetProperty("rows").GetArrayLength());Assert.Equal(2,body.GetProperty("next_cursor").GetInt32());
            Assert.Equal(1,worker.PropertyCalls);Assert.Equal(1,worker.Captures);
            Assert.Equal(firstBody,Assert.IsType<TeamcenterModelCacheResult>(await runtime.ReadModelCacheV2Async(Input(batch),default)).ResultJson);
        }
        var restartedWorker=new Worker();
        using(var restarted=new TeamcenterReadOnlyRuntime(restartedWorker,path))
        {
            await restarted.LoginAsync("tc-production","u","s",default);
            Assert.Equal(firstBody,Assert.IsType<TeamcenterModelCacheResult>(await restarted.ReadModelCacheV2Async(Input(batch),default)).ResultJson);
            Assert.Equal(0,restartedWorker.Captures);Assert.Equal(0,restartedWorker.PropertyCalls);
            var last=Body(await restarted.ReadModelCacheV2Async(Input(batch,2,generation,principal),default));
            Assert.True(last.GetProperty("complete").GetBoolean());Assert.Equal(JsonValueKind.Null,last.GetProperty("next_cursor").ValueKind);
            var row=last.GetProperty("rows")[0];Assert.Equal("B",row.GetProperty("structure").GetProperty("occurrence_path")[0].GetProperty("occurrence_uid").GetString());
            Assert.Equal(1,restartedWorker.Captures);Assert.Equal(1,restartedWorker.PropertyCalls);
        }
    }

    [Fact]
    public async Task Reopened_source_drift_and_principal_switch_refuse_to_mix_the_existing_snapshot()
    {
        var path=Path.GetTempFileName();var batch=Guid.NewGuid().ToString("N");string generation,principal;
        using(var runtime=new TeamcenterReadOnlyRuntime(new Worker(),path))
        {
            await runtime.LoginAsync("tc-production","u","s",default);
            var first=Assert.IsType<TeamcenterModelCacheResult>(await runtime.ReadModelCacheV2Async(Input(batch),default));principal=first.PrincipalHash;generation=Body(first).GetProperty("generation").GetString()!;
        }
        using var restarted=new TeamcenterReadOnlyRuntime(new Worker{Changed=true},path);await restarted.LoginAsync("tc-production","u","s",default);
        Assert.Equal("teamcenter_cache_generation_stale",(await Assert.ThrowsAsync<ConnectorException>(()=>restarted.ReadModelCacheV2Async(Input(batch,2,generation,principal),default))).Message);
        await restarted.LoginAsync("tc-production","other","s",default);
        Assert.Equal("cache_principal_changed",(await Assert.ThrowsAsync<ConnectorException>(()=>restarted.ReadModelCacheV2Async(Input(batch),default))).Message);
    }

    [Fact]
    public async Task Byte_budget_reduces_page_rows_without_losing_the_next_cursor_or_rereading_saved_properties()
    {
        var worker=new Worker{LargeRaw=true};var batch=Guid.NewGuid().ToString("N");using var runtime=new TeamcenterReadOnlyRuntime(worker,Path.GetTempFileName());
        await runtime.LoginAsync("tc-production","u","s",default);
        var first=Assert.IsType<TeamcenterModelCacheResult>(await runtime.ReadModelCacheV2Async(Input(batch),default));var body=Body(first);
        Assert.Single(body.GetProperty("rows").EnumerateArray());Assert.Equal(1,body.GetProperty("next_cursor").GetInt32());
        var second=Body(await runtime.ReadModelCacheV2Async(Input(batch,1,body.GetProperty("generation").GetString(),first.PrincipalHash,size:1),default));
        Assert.Single(second.GetProperty("rows").EnumerateArray());Assert.Equal(2,second.GetProperty("next_cursor").GetInt32());Assert.Equal(1,worker.PropertyCalls);
    }

    [Fact]
    public async Task Logout_cancels_an_unfinished_property_block_and_resume_uses_durable_structure()
    {
        var worker=new Worker{WaitProperty=true};var path=Path.GetTempFileName();var batch=Guid.NewGuid().ToString("N");
        using var runtime=new TeamcenterReadOnlyRuntime(worker,path);await runtime.LoginAsync("tc-production","u","s",default);
        var pending=runtime.ReadModelCacheV2Async(Input(batch),default);await worker.PropertyEntered.Task.WaitAsync(TimeSpan.FromSeconds(5));
        await runtime.LogoutAsync(default);await Assert.ThrowsAnyAsync<OperationCanceledException>(()=>pending);
        worker.WaitProperty=false;await runtime.LoginAsync("tc-production","u","s",default);
        var result=Body(await runtime.ReadModelCacheV2Async(Input(batch),default));Assert.Equal(2,result.GetProperty("rows").GetArrayLength());Assert.Equal(2,worker.PropertyCalls);
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task Expired_native_token_rebuilds_and_checks_the_complete_topology_before_one_retry(bool structure)
    {
        var worker=new Worker{ExpireStructure=structure,ExpireProperty=!structure};using var runtime=new TeamcenterReadOnlyRuntime(worker,Path.GetTempFileName());
        await runtime.LoginAsync("tc-production","u","s",default);
        var body=Body(await runtime.ReadModelCacheV2Async(Input(Guid.NewGuid().ToString("N")),default));
        Assert.Equal(2,body.GetProperty("rows").GetArrayLength());Assert.Equal(2,worker.Captures);
        Assert.Equal(structure?1:2,worker.PropertyCalls);
    }

    [Fact]
    public async Task A_byte_limited_native_prefix_is_saved_and_the_remaining_properties_are_collected()
    {
        var worker=new Worker{PartialProperty=true};using var runtime=new TeamcenterReadOnlyRuntime(worker,Path.GetTempFileName());
        await runtime.LoginAsync("tc-production","u","s",default);
        var body=Body(await runtime.ReadModelCacheV2Async(Input(Guid.NewGuid().ToString("N")),default));
        Assert.Equal(2,body.GetProperty("rows").GetArrayLength());Assert.Equal(2,worker.PropertyCalls);
        Assert.Equal("A",body.GetProperty("rows")[1].GetProperty("structure").GetProperty("occurrence_path")[0].GetProperty("occurrence_uid").GetString());
    }

    private sealed class Worker:ITeamcenterWorker
    {
        public int Captures,PropertyCalls;public bool Changed,LargeRaw,WaitProperty,ExpireProperty,ExpireStructure,PartialProperty;public readonly TaskCompletionSource PropertyEntered=new(TaskCreationOptions.RunContinuationsAsynchronously);private string native=Guid.NewGuid().ToString("N");
        private static async Task<JsonElement> Wait(CancellationToken ct){await Task.Delay(Timeout.Infinite,ct);throw new InvalidOperationException();}
        public Task<JsonElement> ReadCacheBulkAsync(string command,object payload,string user,string password,CancellationToken ct)
        {
            var input=JsonSerializer.SerializeToElement(payload);object Row(string occurrence,int order)=>new{occurrence_id=occurrence,parent_occurrence_id=(string?)null,occurrence_path=occurrence=="root"?Array.Empty<TeamcenterOccurrenceEdge>():new[]{new TeamcenterOccurrenceEdge(occurrence,"rev")},depth=occurrence=="root"?0:1,child_order=order,name=occurrence,item_revision_uid="rev",revision_id="00",component_type="Part",has_children=occurrence=="root",child_count=occurrence=="root"?2:0};
            object result;
            if(command=="cache_structure"){Assert.Matches("^[a-f0-9]{32}$",input.GetProperty("capture_key").GetString()!);Captures++;result=new{node_count=3,native_generation=native};}
            else if(command=="cache_structure_page")
            {
                if(ExpireStructure){ExpireStructure=false;native=Guid.NewGuid().ToString("N");throw new ConnectorException("teamcenter_cache_generation_stale");}
                Assert.Equal(native,input.GetProperty("native_generation").GetString());
                result=new{cursor=0,next_cursor=(int?)null,node_count=3,nodes=new[]{Row("root",0),Row("A",0),Row(Changed?"C":"B",1)}};
            }
            else if(command=="cache_properties")
            {
                PropertyCalls++;PropertyEntered.TrySetResult();if(WaitProperty)return Wait(ct);
                if(ExpireProperty){ExpireProperty=false;native=Guid.NewGuid().ToString("N");throw new ConnectorException("teamcenter_cache_generation_stale");}
                Assert.Equal(native,input.GetProperty("native_generation").GetString());
                result=new{rows=input.GetProperty("occurrence_paths").EnumerateArray().Take(PartialProperty?1:256).Select(path=>new{occurrence_path=path,result=new{properties=new TeamcenterNodeProperties("Part","ITEM","00","Part","owner","group","0","kg","12","重要",path.GetArrayLength()==0?null:path[0].GetProperty("occurrence_uid").GetString()),raw_fields=new[]{new{object_uid="rev",object_kind="ItemRevision",field="IMAN_Rendering",read_state="value",value_json="[]"},new{object_uid="rev",object_kind="BOMLine",field="catiaFileName",read_state="value",value_json=JsonSerializer.Serialize(LargeRaw?new string('x',3*1024*1024):"part.CATPart")}}}}).ToArray()};
            }
            else throw new NotSupportedException(command);
            return Task.FromResult(JsonSerializer.SerializeToElement(result));
        }
        public Task ValidateCredentialsAsync(string e,string u,string p,CancellationToken ct)=>Task.CompletedTask;
        public Task<IReadOnlyList<string>> GetRevisionRulesAsync(string u,string p,CancellationToken ct)=>throw new NotSupportedException();
        public Task<TeamcenterProductSearchResult> SearchAsync(string i,string r,string rule,string d,string u,string p,CancellationToken ct)=>throw new NotSupportedException();
        public Task<IReadOnlyList<TeamcenterOccurrence>> ObserveAsync(TeamcenterSourceSelector s,int n,int d,string projection,string u,string p,CancellationToken ct)=>throw new NotSupportedException();
        public Task<TeamcenterLaunchResult> LaunchAsync(TeamcenterSourceSelector s,string expected,string u,string p,CancellationToken ct)=>throw new NotSupportedException();
        public Task<TeamcenterLaunchResult> ConsumeVisualizationAsync(TeamcenterSourceSelector s,string expected,string op,Func<string,CancellationToken,Task> consumer,string u,string p,CancellationToken ct)=>throw new NotSupportedException();
    }
}
