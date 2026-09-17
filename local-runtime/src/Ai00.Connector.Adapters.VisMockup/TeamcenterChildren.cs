using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using Ai00.Connector.Contracts;
using Microsoft.Data.Sqlite;

namespace Ai00.Connector.Adapters.VisMockup;

public sealed record TeamcenterOccurrenceEdge(
    [property: JsonPropertyName("occurrence_uid")] string OccurrenceUid,
    [property: JsonPropertyName("item_revision_uid")] string ItemRevisionUid);
public sealed record TeamcenterChildNode(
    [property: JsonPropertyName("occurrence_id")] string OccurrenceId,
    [property: JsonPropertyName("parent_occurrence_id")] string? ParentOccurrenceId,
    [property: JsonPropertyName("occurrence_path")] TeamcenterOccurrenceEdge[] OccurrencePath,
    [property: JsonPropertyName("depth")] int Depth,
    [property: JsonPropertyName("child_order")] int ChildOrder,
    [property: JsonPropertyName("name")] string Name,
    [property: JsonPropertyName("item_revision_uid")] string ItemRevisionUid,
    [property: JsonPropertyName("revision_id")] string RevisionId,
    [property: JsonPropertyName("component_type")] string ComponentType,
    [property: JsonPropertyName("has_children")] bool? HasChildren);
public sealed record TeamcenterChildrenBatch(
    [property: JsonPropertyName("parent")] TeamcenterChildNode Parent,
    [property: JsonPropertyName("nodes")] TeamcenterChildNode[] Nodes);
public sealed record TeamcenterChildrenPage(
    [property: JsonPropertyName("source_identity_hash")] string SourceIdentityHash,
    [property: JsonPropertyName("captured_at")] DateTimeOffset CapturedAt,
    [property: JsonPropertyName("cache_hit")] bool CacheHit,
    [property: JsonPropertyName("generation")] string Generation,
    [property: JsonPropertyName("parent")] TeamcenterChildNode Parent,
    [property: JsonPropertyName("nodes")] TeamcenterChildNode[] Nodes,
    [property: JsonPropertyName("cursor")] int Cursor,
    [property: JsonPropertyName("next_cursor")] int? NextCursor,
    [property: JsonPropertyName("child_count")] int ChildCount,
    [property: JsonPropertyName("complete")] bool Complete = false);

public sealed partial class TeamcenterReadOnlyRuntime
{
    private static string ChildrenHash(string text) => "sha256:" + Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(text))).ToLowerInvariant();

    public async Task<object> ReadChildrenAsync(JsonElement payload, CancellationToken ct)
    {
        Closed(payload,"source_selector","parent_path","cursor","page_size","refresh","generation");
        var selector=ReadSelector(payload.GetProperty("source_selector"));
        var pathValue=payload.GetProperty("parent_path");
        if(pathValue.ValueKind!=JsonValueKind.Array || pathValue.GetArrayLength()>128) throw new ConnectorException("teamcenter_children_input_invalid");
        foreach(var edge in pathValue.EnumerateArray()) Closed(edge,"occurrence_uid","item_revision_uid");
        var path=pathValue.Deserialize<TeamcenterOccurrenceEdge[]>()!;
        if(path.Any(e=>string.IsNullOrWhiteSpace(e.OccurrenceUid)||e.OccurrenceUid.Length>128||string.IsNullOrWhiteSpace(e.ItemRevisionUid)||e.ItemRevisionUid.Length>128)) throw new ConnectorException("teamcenter_children_input_invalid");
        var cursor=payload.GetProperty("cursor").GetInt32();
        var size=payload.GetProperty("page_size").GetInt32();
        var refresh=payload.GetProperty("refresh").GetBoolean();
        var generation=payload.GetProperty("generation").GetString();
        if(cursor<0||size is <1 or >500||generation?.Length>128||(cursor==0&&generation!=null)||(cursor>0&&string.IsNullOrEmpty(generation))||(refresh&&(cursor!=0||generation!=null))) throw new ConnectorException("teamcenter_children_input_invalid");
        await gate.WaitAsync(ct);
        try
        {
            var credentials=RequireCredentials();
            var key=ChildrenHash(JsonSerializer.Serialize(new {principal=credentials.User,source=selector.IdentityHash,path,projection="children-v1"}));
            using var db=new SqliteConnection(connectionString); db.Open();
            using var schema=db.CreateCommand();
            schema.CommandText="CREATE TABLE IF NOT EXISTS tc_children_cache(cache_key TEXT PRIMARY KEY,generation TEXT NOT NULL,captured_at TEXT NOT NULL,payload_json TEXT NOT NULL)";
            schema.ExecuteNonQuery();
            TeamcenterChildrenBatch? batch=null; string? savedGeneration=null; DateTimeOffset captured=default;
            using(var read=db.CreateCommand())
            {
                read.CommandText="SELECT generation,captured_at,payload_json FROM tc_children_cache WHERE cache_key=$key";
                read.Parameters.AddWithValue("$key",key);
                using var reader=read.ExecuteReader();
                if(reader.Read()) {savedGeneration=reader.GetString(0);captured=DateTimeOffset.Parse(reader.GetString(1));batch=JsonSerializer.Deserialize<TeamcenterChildrenBatch>(reader.GetString(2));}
            }
            if(generation!=null&&generation!=savedGeneration) throw new ConnectorException("teamcenter_children_generation_stale");
            var hit=batch!=null&&!refresh;
            if(!hit)
            {
                batch=await worker.ReadChildrenAsync(selector,path,credentials.User,credentials.Password,ct);
                if(batch is null || batch.Parent is null || batch.Nodes is null || batch.Nodes.Length>250000) throw new ConnectorException("teamcenter_worker_response_invalid");
                string Id(TeamcenterOccurrenceEdge[] edges)=>ChildrenHash(selector.IdentityHash+"|"+JsonSerializer.Serialize(edges));
                var expectedRevision=path.Length>0?path[^1].ItemRevisionUid:selector.ItemRevisionUid;
                if(batch.Parent.OccurrencePath is null || !batch.Parent.OccurrencePath.SequenceEqual(path)
                    || (expectedRevision.Length>0&&batch.Parent.ItemRevisionUid!=expectedRevision)) throw new ConnectorException("teamcenter_worker_response_invalid");
                var parent=batch.Parent with {OccurrenceId=Id(path),ParentOccurrenceId=path.Length==0?null:Id(path[..^1]),Depth=path.Length};
                var seen=new HashSet<string>(StringComparer.Ordinal);
                var nodes=batch.Nodes.Select((node,index)=>
                {
                    if(node.OccurrencePath is null || node.OccurrencePath.Length!=path.Length+1 || !node.OccurrencePath[..^1].SequenceEqual(path)) throw new ConnectorException("teamcenter_worker_response_invalid");
                    var edge=node.OccurrencePath[^1];
                    if(string.IsNullOrWhiteSpace(edge.OccurrenceUid)||string.IsNullOrWhiteSpace(edge.ItemRevisionUid)||edge.ItemRevisionUid!=node.ItemRevisionUid) throw new ConnectorException("teamcenter_occurrence_identity_invalid");
                    var id=Id(node.OccurrencePath);
                    if(!seen.Add(id)) throw new ConnectorException("teamcenter_occurrence_identity_invalid");
                    return node with {OccurrenceId=id,ParentOccurrenceId=parent.OccurrenceId,Depth=path.Length+1,ChildOrder=index};
                }).ToArray();
                batch=new(parent,nodes); captured=DateTimeOffset.UtcNow;savedGeneration=Guid.NewGuid().ToString("N");
                using var write=db.CreateCommand();
                write.CommandText="INSERT INTO tc_children_cache VALUES($key,$generation,$time,$body) ON CONFLICT(cache_key) DO UPDATE SET generation=excluded.generation,captured_at=excluded.captured_at,payload_json=excluded.payload_json";
                write.Parameters.AddWithValue("$key",key);write.Parameters.AddWithValue("$generation",savedGeneration);write.Parameters.AddWithValue("$time",captured.ToString("O"));write.Parameters.AddWithValue("$body",JsonSerializer.Serialize(batch));write.ExecuteNonQuery();
            }
            if(cursor>batch!.Nodes.Length) throw new ConnectorException("teamcenter_children_input_invalid");
            var page=batch.Nodes.Skip(cursor).Take(size).ToArray();var next=cursor+page.Length;
            return new TeamcenterChildrenPage(selector.IdentityHash,captured,hit,savedGeneration!,batch.Parent,page,cursor,next<batch.Nodes.Length?next:null,batch.Nodes.Length);
        }
        catch(ConnectorException error) when(InvalidatesSession(error)){ClearCredentials();throw;}
        finally {gate.Release();}
    }
}
