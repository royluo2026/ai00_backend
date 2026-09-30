using System.Text.Json;
using Ai00.Connector.Adapters.VisMockup;
using Ai00.Connector.Contracts;
using Xunit;

public sealed class TeamcenterModelFileTests
{
    [Fact]
    public async Task FixedFileUsesPrivateReaderAndContentHashWithoutViewerOrBom()
    {
        var root=Path.Combine(Path.GetTempPath(),"ai00-cache-file-test-"+Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        using var runtime=new TeamcenterReadOnlyRuntime(new Worker(),Path.Combine(root,"cache.db"));
        await runtime.LoginAsync("tc-production","test-user","test-password",CancellationToken.None);
        var input=JsonSerializer.SerializeToElement(new {batch_id=new string('a',32),generation=new string('b',32),snapshot_hash=(string?)null,schema_version=1,node_key="node",item_revision_uid="revision",source_selector=new{endpoint_id="tc-production",object_uid="item",item_revision_uid="revision",bom_view_uid="",revision_rule="Latest Working",configuration_date="2026-09-28T00:00:00Z"},file_ref=new{dataset_uid="dataset",file_uid="fixed-file",file_name="fixed.jt",relation_type="IMAN_Rendering"},expected_content_hash=(string?)null,artifact_resource_refs=new[]{"simulation://model-cache/"+new string('a',32)}});
        var result=await runtime.FetchModelFileAsync(input,CancellationToken.None);
        Assert.Equal(32,result.ByteSize);
        Assert.Equal(64,result.Sha256.Length);
        Assert.Equal("model/jt",result.MediaType);
        Assert.Equal("fixed-file",result.FileReference.GetProperty("file_uid").GetString());
        var mismatch=JsonSerializer.SerializeToElement(new{batch_id=new string('a',32),generation=new string('b',32),snapshot_hash=(string?)null,schema_version=1,node_key="node",item_revision_uid="revision",source_selector=input.GetProperty("source_selector"),file_ref=input.GetProperty("file_ref"),expected_content_hash="sha256:"+new string('0',64),artifact_resource_refs=new[]{"simulation://model-cache/"+new string('a',32)}});
        await Assert.ThrowsAsync<ConnectorNoEffectException>(()=>runtime.FetchModelFileAsync(mismatch,CancellationToken.None));
    }
    [Theory]
    [InlineData(32L, false)]
    [InlineData(264498976L, false)]
    [InlineData(536870912L, false)]
    [InlineData(536870913L, true)]
    public async Task BatchPreflightReturnsExactFileSizesWithoutCallingFms(long size, bool exceeded)
    {
        var root=Path.Combine(Path.GetTempPath(),"ai00-cache-preflight-test-"+Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        var worker=new Worker{Size=size};
        using var runtime=new TeamcenterReadOnlyRuntime(worker,Path.Combine(root,"cache.db"));
        await runtime.LoginAsync("tc-production","test-user","test-password",CancellationToken.None);
        var identity=new{batch_id=new string('a',32),generation=new string('b',32),snapshot_hash=(string?)null,schema_version=1};
        var files=new[]{new{step_id="step-00002",node_key="node",item_revision_uid="revision",file_ref=new{dataset_uid="dataset",file_uid="fixed-file",file_name="fixed.jt",relation_type="IMAN_Rendering"},expected_content_hash=(string?)null}};
        var input=JsonSerializer.SerializeToElement(new{identity,source_selector=new{endpoint_id="tc-production",object_uid="item",item_revision_uid="revision",bom_view_uid="",revision_rule="Latest Working",configuration_date="2026-09-28T00:00:00Z"},files});
        var result=await runtime.PreflightModelFilesAsync(input,CancellationToken.None);
        Assert.Equal(identity.batch_id,result.GetProperty("identity").GetProperty("batch_id").GetString());
        Assert.Equal(size,result.GetProperty("files")[0].GetProperty("file_size").GetInt64());
        Assert.Equal(size,result.GetProperty("total_byte_length").GetInt64());
        Assert.Equal(exceeded?"cache_file_batch_size_exceeded":null,result.GetProperty("error_code").GetString());
        Assert.Equal(new[]{"cache_file_preflight"},worker.Commands);
    }
    internal sealed class Worker:ITeamcenterWorker
    {
        public long Size{get;init;}=32L;
        public List<string> Commands{get;}=[];
        public Task<JsonElement> ReadCacheBulkAsync(string command,object payload,string username,string password,CancellationToken ct)
        {
            Commands.Add(command);
            if(command=="cache_file_preflight")
            {
                var preflightPayload=JsonSerializer.SerializeToElement(payload);
                Assert.Equal("fixed-file",preflightPayload.GetProperty("files")[0].GetProperty("file_uid").GetString());
                return Task.FromResult(JsonSerializer.SerializeToElement(new{files=new[]{new{file_uid="fixed-file",file_name="fixed.jt",file_size=Size}}}));
            }
            Assert.Equal("cache_file",command);var p=JsonSerializer.SerializeToElement(payload);
            Assert.Contains(p.GetProperty("file_ref").GetProperty("file_uid").GetString(),new[]{"fixed-file","file"});
            var file=Path.Combine(p.GetProperty("output_root").GetString()!,"fixed.jt");File.WriteAllBytes(file,new byte[32]);
            return Task.FromResult(JsonSerializer.SerializeToElement(new{local_path=file,byte_size=32}));
        }
        public Task ValidateCredentialsAsync(string e,string u,string p,CancellationToken ct)=>Task.CompletedTask;
        public Task<IReadOnlyList<string>> GetRevisionRulesAsync(string u,string p,CancellationToken ct)=>throw new NotSupportedException();
        public Task<TeamcenterProductSearchResult> SearchAsync(string i,string r,string rule,string d,string u,string p,CancellationToken ct)=>throw new NotSupportedException();
        public Task<IReadOnlyList<TeamcenterOccurrence>> ObserveAsync(TeamcenterSourceSelector s,int n,int d,string projection,string u,string p,CancellationToken ct)=>throw new NotSupportedException();
        public Task<TeamcenterLaunchResult> LaunchAsync(TeamcenterSourceSelector s,string expected,string u,string p,CancellationToken ct)=>throw new NotSupportedException();
        public Task<TeamcenterLaunchResult> ConsumeVisualizationAsync(TeamcenterSourceSelector s,string expected,string op,Func<string,CancellationToken,Task> consumer,string u,string p,CancellationToken ct)=>throw new NotSupportedException();
    }
}
