using System.Text.Json;
using System.Text.Json.Serialization;
using Ai00.Connector.Contracts;
using Microsoft.Data.Sqlite;

namespace Ai00.Connector.Adapters.VisMockup;

public sealed record TeamcenterModelCacheResult(
    [property: JsonPropertyName("principal_hash")] string PrincipalHash,
    [property: JsonPropertyName("result_json")] string ResultJson);

public sealed partial class TeamcenterReadOnlyRuntime
{
    private string CachePrincipalHash() => ChildrenHash("tc-production\0" + RequirePrincipal());
    private void CheckCachePrincipal(string? expected)
    {
        if (expected is not null && expected != CachePrincipalHash())
            throw new ConnectorException("cache_principal_changed");
    }

    public async Task<object> ReadModelCacheAsync(JsonElement payload, CancellationToken ct)
    {
        Closed(payload,"kind","read_payload_json","expected_principal_hash");
        var kind=payload.GetProperty("kind").GetString();
        var text=payload.GetProperty("read_payload_json").GetString();
        var expected=payload.GetProperty("expected_principal_hash").GetString();
        if (text is null || text.Length>32768 || (kind!="children" && kind!="properties"))
            throw new ConnectorException("cache_read_input_invalid");
        using var document=JsonDocument.Parse(text);
        var input=document.RootElement;
        if(kind=="properties") return await ReadRawPropertiesCacheAsync(input,expected,ct);
        string principal; long generation;
        lock(credentialState){CheckCachePrincipal(expected);principal=CachePrincipalHash();generation=sessionGeneration;}
        var result=await ReadChildrenCoreAsync(input,ct,true);
        lock(credentialState)
        {
            if(principal!=CachePrincipalHash() || generation!=sessionGeneration)
                throw new ConnectorException("cache_principal_changed");
        }
        return new TeamcenterModelCacheResult(principal,JsonSerializer.Serialize(result));
    }

    private async Task<object> ReadRawPropertiesCacheAsync(JsonElement input,string? expected,CancellationToken ct)
    {
        Closed(input,"source_selector","occurrence_path");
        var selector=ReadSelector(input.GetProperty("source_selector"));
        var path=ReadNodePropertyPath(input.GetProperty("occurrence_path"));
        await gate.WaitAsync(ct);
        try
        {
            CheckCachePrincipal(expected); var principal=CachePrincipalHash();
            long generation;lock(credentialState){generation=sessionGeneration;}
            var key=ChildrenHash(principal+"|"+selector.IdentityHash+"|"+JsonSerializer.Serialize(path)+"|raw-properties-v1");
            using var db=new SqliteConnection(connectionString);db.Open();
            using var schema=db.CreateCommand();
            schema.CommandText="CREATE TABLE IF NOT EXISTS tc_raw_property_cache(cache_key TEXT PRIMARY KEY,result_json TEXT NOT NULL)";schema.ExecuteNonQuery();
            using var read=db.CreateCommand();read.CommandText="SELECT result_json FROM tc_raw_property_cache WHERE cache_key=$key";read.Parameters.AddWithValue("$key",key);
            if(read.ExecuteScalar() is string saved)
            {
                var savedNode=System.Text.Json.Nodes.JsonNode.Parse(saved)!.AsObject();savedNode["cache_hit"]=true;
                return new TeamcenterModelCacheResult(principal,savedNode.ToJsonString());
            }
            var credentials=RequireCredentials();
            var raw=await worker.ReadRawNodePropertiesAsync(selector,path,credentials.User,credentials.Password,ct);
            if(raw.ValueKind!=JsonValueKind.Object || !raw.TryGetProperty("properties",out var properties) || !raw.TryGetProperty("raw_fields",out var fields) || fields.ValueKind!=JsonValueKind.Array || fields.GetArrayLength()>64)
                throw new ConnectorException("teamcenter_worker_response_invalid");
            var projection=properties.Deserialize<TeamcenterNodeProperties>();
            if(projection is null || !ValidNodeProperties(projection,path))throw new ConnectorException("teamcenter_worker_response_invalid");
            lock(credentialState)
            {
                if(principal!=CachePrincipalHash() || generation!=sessionGeneration)throw new ConnectorException("cache_principal_changed");
            }
            var result=JsonSerializer.Serialize(new{source_identity_hash=selector.IdentityHash,captured_at=DateTimeOffset.UtcNow,cache_hit=false,properties=projection,raw_fields=fields});
            using var write=db.CreateCommand();write.CommandText="INSERT INTO tc_raw_property_cache(cache_key,result_json) VALUES($key,$body)";write.Parameters.AddWithValue("$key",key);write.Parameters.AddWithValue("$body",result);write.ExecuteNonQuery();
            return new TeamcenterModelCacheResult(principal,result);
        }
        catch(ConnectorException error) when(InvalidatesSession(error)){ClearCredentials();throw;}
        finally{gate.Release();}
    }
}
