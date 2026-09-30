using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using Ai00.Connector.Contracts;
using Microsoft.Data.Sqlite;

namespace Ai00.Connector.Adapters.VisMockup;

public sealed partial class TeamcenterReadOnlyRuntime
{
    private sealed record BulkSnapshot(string Batch,string Principal,string Source,string Generation,string Captured,
        int Count,string? Hash,string? Native,int Cursor,bool Ready);
    private sealed record BulkRow(int Position,TeamcenterChildNode Structure,int ChildCount,string? Properties);
    private static SqliteCommand BulkSql(SqliteConnection db,string sql,params object?[] values)
    {
        var command=db.CreateCommand();command.CommandText=sql;
        for(var i=0;i<values.Length;i++)command.Parameters.AddWithValue("$p"+i,values[i]??DBNull.Value);
        return command;
    }
    private static void BulkSchema(SqliteConnection db)
    {
        using var schema=db.CreateCommand();schema.CommandText="""
            CREATE TABLE IF NOT EXISTS tc_cloud_snapshots(batch_id TEXT PRIMARY KEY,principal_hash TEXT NOT NULL,source_hash TEXT NOT NULL,
              generation TEXT NOT NULL,captured_at TEXT NOT NULL,node_count INTEGER NOT NULL DEFAULT 0,structure_hash TEXT,native_generation TEXT,
              structure_cursor INTEGER NOT NULL DEFAULT 0,structure_ready INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS tc_cloud_snapshot_rows(batch_id TEXT NOT NULL,position INTEGER NOT NULL,node_key TEXT NOT NULL,
              structure_json TEXT NOT NULL,child_count INTEGER NOT NULL,properties_json TEXT,PRIMARY KEY(batch_id,position),UNIQUE(batch_id,node_key));
            CREATE TABLE IF NOT EXISTS tc_cloud_snapshot_pages(batch_id TEXT NOT NULL,cursor INTEGER NOT NULL,page_size INTEGER NOT NULL,
              body_json TEXT NOT NULL,PRIMARY KEY(batch_id,cursor,page_size));
            """;schema.ExecuteNonQuery();
    }
    private static BulkSnapshot? BulkLoad(SqliteConnection db,string batch)
    {
        using var read=BulkSql(db,"SELECT * FROM tc_cloud_snapshots WHERE batch_id=$p0",batch);using var row=read.ExecuteReader();
        if(!row.Read())return null;
        return new(batch,row.GetString(1),row.GetString(2),row.GetString(3),row.GetString(4),row.GetInt32(5),
            row.IsDBNull(6)?null:row.GetString(6),row.IsDBNull(7)?null:row.GetString(7),row.GetInt32(8),row.GetInt32(9)==1);
    }
    private static void BulkSave(SqliteConnection db,BulkSnapshot snapshot)
    {
        using var save=BulkSql(db,"""
            INSERT INTO tc_cloud_snapshots VALUES($p0,$p1,$p2,$p3,$p4,$p5,$p6,$p7,$p8,$p9)
            ON CONFLICT(batch_id) DO UPDATE SET node_count=excluded.node_count,structure_hash=excluded.structure_hash,
              native_generation=excluded.native_generation,structure_cursor=excluded.structure_cursor,structure_ready=excluded.structure_ready
            """,snapshot.Batch,snapshot.Principal,snapshot.Source,snapshot.Generation,snapshot.Captured,snapshot.Count,snapshot.Hash,snapshot.Native,snapshot.Cursor,snapshot.Ready?1:0);
        save.ExecuteNonQuery();
    }
    private static List<BulkRow> BulkRows(SqliteConnection db,string batch,int cursor,int size)
    {
        using var read=BulkSql(db,"SELECT position,structure_json,child_count,properties_json FROM tc_cloud_snapshot_rows WHERE batch_id=$p0 AND position>=$p1 ORDER BY position LIMIT $p2",batch,cursor,size);
        using var reader=read.ExecuteReader();var rows=new List<BulkRow>();
        while(reader.Read())rows.Add(new(reader.GetInt32(0),JsonSerializer.Deserialize<TeamcenterChildNode>(reader.GetString(1))!,reader.GetInt32(2),reader.IsDBNull(3)?null:reader.GetString(3)));
        return rows;
    }
    private static ConnectorException BulkInvalid()=>new("teamcenter_worker_response_invalid");
    private static bool BulkToken(string? value)=>value is not null&&Regex.IsMatch(value,"\\A[a-f0-9]{32}\\z");

    public async Task<object> ReadModelCacheV2Async(JsonElement input,CancellationToken ct)
    {
        Closed(input,"source_selector","batch_id","cursor","page_size","generation","expected_principal_hash");
        var selector=ReadSelector(input.GetProperty("source_selector"));var batch=input.GetProperty("batch_id").GetString();
        var cursor=input.GetProperty("cursor").GetInt32();var size=input.GetProperty("page_size").GetInt32();var generation=input.GetProperty("generation").GetString();
        var expected=input.GetProperty("expected_principal_hash").GetString();
        if(!BulkToken(batch)||cursor<0||size is <1 or >500||cursor==0&&generation is not null||cursor>0&&!BulkToken(generation))throw new ConnectorException("cache_read_input_invalid");
        long sessionVersion;CancellationToken sessionToken;lock(credentialState){sessionVersion=sessionGeneration;sessionToken=sessionCancellation.Token;}
        using var linked=CancellationTokenSource.CreateLinkedTokenSource(ct,sessionToken);var token=linked.Token;
        await gate.WaitAsync(token);
        try
        {
            CheckCachePrincipal(expected);var credentials=RequireCredentials();var principal=CachePrincipalHash();
            void Fence(){token.ThrowIfCancellationRequested();lock(credentialState){if(sessionVersion!=sessionGeneration||principal!=CachePrincipalHash())throw new ConnectorException("cache_principal_changed");}}
            Fence();using var db=new SqliteConnection(connectionString);db.Open();BulkSchema(db);
            var snapshot=BulkLoad(db,batch!);
            if(snapshot is not null&&(snapshot.Principal!=principal||snapshot.Source!=selector.IdentityHash))throw new ConnectorException(snapshot.Principal!=principal?"cache_principal_changed":"cache_source_mismatch");
            if(generation is not null&&generation!=snapshot?.Generation)throw new ConnectorException("teamcenter_cache_generation_stale");
            using(var read=BulkSql(db,"SELECT body_json FROM tc_cloud_snapshot_pages WHERE batch_id=$p0 AND cursor=$p1 AND page_size=$p2",batch,cursor,size))
                if(read.ExecuteScalar() is string saved){Fence();return new TeamcenterModelCacheResult(principal,saved);}
            snapshot??=new(batch!,principal,selector.IdentityHash,Guid.NewGuid().ToString("N"),DateTimeOffset.UtcNow.ToString("O"),0,null,null,0,false);
            BulkSave(db,snapshot);
            async Task<JsonElement> Call(string command,object payload){var result=await worker.ReadCacheBulkAsync(command,payload,credentials.User,credentials.Password,token);Fence();return result;}
            var rows=snapshot.Ready?BulkRows(db,batch!,cursor,size):[];
            if(!snapshot.Ready||rows.Any(row=>row.Properties is null))
            {
                snapshot=await EnsureBulkStructure(db,snapshot,selector,Call,Fence);
                if(cursor>=snapshot.Count)throw new ConnectorException("cache_read_input_invalid");
                rows=BulkRows(db,batch!,cursor,size);
                var missing=rows.Where(row=>row.Properties is null).ToArray();var offset=0;
                while(offset<missing.Length)
                {
                    var group=new List<BulkRow>();object Payload()=>new{source_selector=selector,native_generation=snapshot.Native,occurrence_paths=group.Select(row=>row.Structure.OccurrencePath).ToArray()};
                    while(offset+group.Count<missing.Length&&group.Count<256)
                    {
                        group.Add(missing[offset+group.Count]);
                        if(Encoding.UTF8.GetByteCount(JsonSerializer.Serialize(Payload()))>60000){group.RemoveAt(group.Count-1);break;}
                    }
                    if(group.Count==0)throw new ConnectorException("teamcenter_worker_response_too_large");
                    JsonElement result;
                    try{result=await Call("cache_properties",Payload());}
                    catch(ConnectorException error) when(error.Code=="teamcenter_cache_generation_stale")
                    {
                        // A reauthenticated Java session has new temporary BOM
                        // objects. Rebuild and verify all durable edges before
                        // retrying this unfinished group once with its new token.
                        snapshot=await EnsureBulkStructure(db,snapshot,selector,Call,Fence);
                        result=await Call("cache_properties",Payload());
                    }
                    Closed(result,"rows");var values=result.GetProperty("rows");
                    if(values.ValueKind!=JsonValueKind.Array||values.GetArrayLength()<1||values.GetArrayLength()>group.Count)throw BulkInvalid();
                    var bodies=new List<string>();var captured=DateTimeOffset.UtcNow;
                    for(var i=0;i<values.GetArrayLength();i++)
                    {
                        var value=values[i];Closed(value,"occurrence_path","result");
                        var path=ReadNodePropertyPath(value.GetProperty("occurrence_path"));
                        if(!path.SequenceEqual(group[i].Structure.OccurrencePath))throw BulkInvalid();
                        var raw=value.GetProperty("result");Closed(raw,"properties","raw_fields");
                        var projection=raw.GetProperty("properties").Deserialize<TeamcenterNodeProperties>();var fields=raw.GetProperty("raw_fields");
                        if(projection is null||!ValidNodeProperties(projection,path)||fields.ValueKind!=JsonValueKind.Array||fields.GetArrayLength()>64)throw BulkInvalid();
                        foreach(var field in fields.EnumerateArray())
                        {
                            Closed(field,"object_uid","object_kind","field","read_state","value_json");
                            if(field.GetProperty("read_state").GetString() is not ("value" or "null" or "unavailable"))throw BulkInvalid();
                            using var decoded=JsonDocument.Parse(field.GetProperty("value_json").GetString()!);
                        }
                        bodies.Add(JsonSerializer.Serialize(new{source_identity_hash=selector.IdentityHash,captured_at=captured,cache_hit=false,properties=projection,raw_fields=fields}));
                    }
                    Fence();using var tx=db.BeginTransaction();
                    for(var i=0;i<bodies.Count;i++){using var save=BulkSql(db,"UPDATE tc_cloud_snapshot_rows SET properties_json=$p0 WHERE batch_id=$p1 AND position=$p2",bodies[i],batch,group[i].Position);save.Transaction=tx;save.ExecuteNonQuery();}
                    Fence();tx.Commit();offset+=bodies.Count;
                }
                rows=BulkRows(db,batch!,cursor,size);
            }
            if(rows.Count==0||rows.Any(row=>row.Properties is null))throw BulkInvalid();
            var outputRows=new List<object>();var bytes=0;
            foreach(var row in rows)
            {
                var value=new{structure=row.Structure,page=new{child_count=row.ChildCount},properties_result=JsonSerializer.Deserialize<JsonElement>(row.Properties!)};
                var rowBytes=Encoding.UTF8.GetByteCount(JsonSerializer.Serialize(value));
                if(rowBytes>7*1024*1024)throw new ConnectorException("cache_page_too_large");
                if(outputRows.Count>0&&bytes+rowBytes>4*1024*1024)break;
                outputRows.Add(value);bytes+=rowBytes;
            }
            var next=cursor+outputRows.Count;
            var body=JsonSerializer.Serialize(new{source_identity_hash=snapshot.Source,captured_at=snapshot.Captured,generation=snapshot.Generation,structure_hash=snapshot.Hash,
                node_count=snapshot.Count,cursor,next_cursor=next<snapshot.Count?next:(int?)null,complete=next==snapshot.Count,rows=outputRows});
            if(Encoding.UTF8.GetByteCount(body)>8*1024*1024)throw new ConnectorException("cache_page_too_large");
            // Bound the escaped envelope too: it is embedded once more into a
            // signed plan outcome. Leave room for its fixed protocol metadata.
            if(Encoding.UTF8.GetByteCount(JsonSerializer.Serialize(new TeamcenterModelCacheResult(principal,body)))>16*1024*1024-65536)throw new ConnectorException("cache_page_too_large");
            Fence();using(var save=BulkSql(db,"INSERT INTO tc_cloud_snapshot_pages VALUES($p0,$p1,$p2,$p3)",batch,cursor,size,body))save.ExecuteNonQuery();
            Fence();return new TeamcenterModelCacheResult(principal,body);
        }
        catch(ConnectorException error) when(InvalidatesSession(error)){ClearCredentials();throw;}
        finally{gate.Release();}
    }

    private async Task<BulkSnapshot> EnsureBulkStructure(SqliteConnection db,BulkSnapshot snapshot,TeamcenterSourceSelector selector,
        Func<string,object,Task<JsonElement>> call,Action fence)
    {
        try{return await CaptureBulkStructure(db,snapshot,selector,call,fence);}
        catch(ConnectorException error) when(error.Code=="teamcenter_cache_generation_stale")
        {return await CaptureBulkStructure(db,BulkLoad(db,snapshot.Batch)!,selector,call,fence);}
    }

    private async Task<BulkSnapshot> CaptureBulkStructure(SqliteConnection db,BulkSnapshot snapshot,TeamcenterSourceSelector selector,
        Func<string,object,Task<JsonElement>> call,Action fence)
    {
        var manifest=await call("cache_structure",new{source_selector=selector,capture_key=snapshot.Generation});Closed(manifest,"node_count","native_generation");
        var count=manifest.GetProperty("node_count").GetInt32();var native=manifest.GetProperty("native_generation").GetString();
        if(count is <1 or >250000||!BulkToken(native))throw BulkInvalid();
        if(snapshot.Count!=0&&snapshot.Count!=count)throw new ConnectorException("teamcenter_cache_generation_stale");
        if(snapshot.Ready&&snapshot.Native==native)return snapshot;
        snapshot=snapshot with{Count=count};BulkSave(db,snapshot);
        using var digest=IncrementalHash.CreateHash(HashAlgorithmName.SHA256);var graph=new Dictionary<string,(string? Parent,int Count,int Order)>();
        var cursor=0;
        while(cursor<count)
        {
            var page=await call("cache_structure_page",new{source_selector=selector,native_generation=native,cursor,page_size=200});
            Closed(page,"cursor","next_cursor","node_count","nodes");var nodes=page.GetProperty("nodes");
            if(page.GetProperty("cursor").GetInt32()!=cursor||page.GetProperty("node_count").GetInt32()!=count||nodes.ValueKind!=JsonValueKind.Array||nodes.GetArrayLength() is <1 or >200)throw BulkInvalid();
            var next=cursor+nodes.GetArrayLength();var expectedNext=next<count?next:(int?)null;
            if(next>count||(page.GetProperty("next_cursor").ValueKind==JsonValueKind.Null?null:page.GetProperty("next_cursor").GetInt32())!=expectedNext)throw BulkInvalid();
            using var tx=db.BeginTransaction();
            foreach(var value in nodes.EnumerateArray())
            {
                Closed(value,"occurrence_id","parent_occurrence_id","occurrence_path","depth","child_order","name","item_revision_uid","revision_id","component_type","has_children","child_count");
                var node=value.Deserialize<TeamcenterChildNode>();if(node is null)throw BulkInvalid();
                var path=ReadNodePropertyPath(value.GetProperty("occurrence_path"));var childCount=value.GetProperty("child_count").GetInt32();
                if(childCount is <0 or >250000||node.HasChildren!=(childCount>0)||node.ChildOrder<0||node.Depth!=path.Length||node.ItemRevisionUid.Length is <1 or >128
                    ||path.Length>0&&node.ItemRevisionUid!=path[^1].ItemRevisionUid||path.Length==0&&selector.ItemRevisionUid.Length>0&&node.ItemRevisionUid!=selector.ItemRevisionUid)throw BulkInvalid();
                string Id(TeamcenterOccurrenceEdge[] edges)=>ChildrenHash(selector.IdentityHash+"|"+JsonSerializer.Serialize(edges));
                node=node with{OccurrenceId=Id(path),ParentOccurrenceId=path.Length==0?null:Id(path[..^1]),OccurrencePath=path};
                if(cursor==0&&path.Length!=0||cursor>0&&path.Length==0||!graph.TryAdd(node.OccurrenceId,(node.ParentOccurrenceId,childCount,node.ChildOrder)))throw BulkInvalid();
                var identity=JsonSerializer.Serialize(new{path,child_count=childCount,order=node.ChildOrder,item_revision_uid=node.ItemRevisionUid});
                digest.AppendData(Encoding.UTF8.GetBytes(identity+"\n"));
                if(!snapshot.Ready)
                {
                    using var previous=BulkSql(db,"SELECT structure_json,child_count FROM tc_cloud_snapshot_rows WHERE batch_id=$p0 AND position=$p1",snapshot.Batch,cursor);previous.Transaction=tx;
                    using(var read=previous.ExecuteReader())
                    {
                        if(read.Read())
                        {
                            var old=JsonSerializer.Deserialize<TeamcenterChildNode>(read.GetString(0))!;
                            if(old.OccurrenceId!=node.OccurrenceId||old.ChildOrder!=node.ChildOrder||read.GetInt32(1)!=childCount)throw new ConnectorException("teamcenter_cache_generation_stale");
                        }
                    }
                    using var save=BulkSql(db,"INSERT INTO tc_cloud_snapshot_rows VALUES($p0,$p1,$p2,$p3,$p4,NULL) ON CONFLICT(batch_id,position) DO NOTHING",snapshot.Batch,cursor,node.OccurrenceId,JsonSerializer.Serialize(node),childCount);save.Transaction=tx;save.ExecuteNonQuery();
                }
                cursor++;
            }
            if(!snapshot.Ready)
            {
                using var checkpoint=BulkSql(db,"UPDATE tc_cloud_snapshots SET structure_cursor=$p0 WHERE batch_id=$p1",cursor,snapshot.Batch);checkpoint.Transaction=tx;checkpoint.ExecuteNonQuery();
            }
            fence();tx.Commit();
        }
        var children=graph.GroupBy(pair=>pair.Value.Parent??"").ToDictionary(group=>group.Key,group=>group.Select(pair=>pair.Value.Order).Order().ToArray());
        foreach(var pair in graph)
        {
            var entry=pair.Value;if(entry.Parent is not null&&!graph.ContainsKey(entry.Parent))throw BulkInvalid();
            var orders=children.GetValueOrDefault(pair.Key,[]);
            if(orders.Length!=entry.Count||!orders.SequenceEqual(Enumerable.Range(0,entry.Count)))throw BulkInvalid();
        }
        var hash="sha256:"+Convert.ToHexString(digest.GetHashAndReset()).ToLowerInvariant();
        if(snapshot.Hash is not null&&snapshot.Hash!=hash)throw new ConnectorException("teamcenter_cache_generation_stale");
        snapshot=snapshot with{Hash=hash,Native=native,Cursor=count,Ready=true};fence();BulkSave(db,snapshot);return snapshot;
    }
}
