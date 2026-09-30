using System.Security.Cryptography;
using System.Text.Json;
using System.Text.RegularExpressions;
using Ai00.Connector.Contracts;
using Microsoft.Data.Sqlite;

namespace Ai00.Connector.Adapters.VisMockup;

public sealed record LocalModelArtifact(string Path,string MediaType,string Sha256,long ByteSize,
    JsonElement Identity,string NodeKey,string ItemRevisionUid,JsonElement FileReference,string AcquiredAt);

public sealed partial class TeamcenterReadOnlyRuntime
{
    public async Task<JsonElement> PreflightModelFilesAsync(JsonElement input,CancellationToken ct)
    {
        Closed(input,"identity","source_selector","files");
        var identity=input.GetProperty("identity");Closed(identity,"batch_id","generation","snapshot_hash","schema_version");
        var batch=identity.GetProperty("batch_id").GetString();var generation=identity.GetProperty("generation").GetString();
        var snapshot=identity.GetProperty("snapshot_hash");
            if(!BulkToken(batch)||generation is not null&&!BulkToken(generation)||identity.GetProperty("schema_version").GetInt32()!=1||
            snapshot.ValueKind is not (JsonValueKind.Null or JsonValueKind.String)||snapshot.ValueKind==JsonValueKind.String&&
            !Regex.IsMatch(snapshot.GetString()!,"\\Asha256:[a-f0-9]{64}\\z"))throw new ConnectorNoEffectException("cache_file_preflight_input_invalid");
        var selector=ReadSelector(input.GetProperty("source_selector"));var values=input.GetProperty("files");
        if(values.ValueKind!=JsonValueKind.Array||values.GetArrayLength() is <1 or >8)throw new ConnectorNoEffectException("cache_file_preflight_input_invalid");
        var members=new List<(string Step,string Node,string Revision,JsonElement Reference)>();
        var stepIds=new HashSet<string>(StringComparer.Ordinal);var fileMap=new Dictionary<string,string>(StringComparer.Ordinal);
        foreach(var value in values.EnumerateArray())
        {
            var fields=value.EnumerateObject().Select(item=>item.Name).Order().ToArray();
            if(!fields.SequenceEqual(new[]{"file_ref","item_revision_uid","node_key","step_id"})&&
                !fields.SequenceEqual(new[]{"expected_content_hash","file_ref","item_revision_uid","node_key","step_id"}))
                throw new ConnectorNoEffectException("cache_file_preflight_input_invalid");
            var reference=value.GetProperty("file_ref");
            Closed(reference,"dataset_uid","file_uid","file_name","relation_type");
            var step=value.GetProperty("step_id").GetString()??"";var node=value.GetProperty("node_key").GetString()??"";
            var revision=value.GetProperty("item_revision_uid").GetString()??"";var uid=reference.GetProperty("file_uid").GetString()??"";
            var name=reference.GetProperty("file_name").GetString()??"";
            if(step.Length is <1 or >512||!stepIds.Add(step)||node.Length is <1 or >512||revision.Length is <1 or >512||
                uid.Length is <1 or >128||name.Length is <1 or >512||name.IndexOfAny(['/', '\\'])>=0||name.Any(char.IsControl)||
                !name.EndsWith(".jt",StringComparison.OrdinalIgnoreCase)||reference.GetProperty("dataset_uid").GetString() is not {Length:>0 and <=512}||
                reference.GetProperty("relation_type").GetString()!="IMAN_Rendering")throw new ConnectorNoEffectException("cache_file_preflight_input_invalid");
            var hasExpectedHash=value.TryGetProperty("expected_content_hash",out var expectedHash);
            if(hasExpectedHash&&expectedHash.ValueKind is not (JsonValueKind.Null or JsonValueKind.String))throw new ConnectorNoEffectException("cache_file_preflight_input_invalid");
            if(hasExpectedHash&&expectedHash.ValueKind==JsonValueKind.String&&
                !Regex.IsMatch(expectedHash.GetString()!,"\\Asha256:[a-f0-9]{64}\\z"))throw new ConnectorNoEffectException("cache_file_preflight_input_invalid");
            if(fileMap.TryGetValue(uid,out var existingName)&&existingName!=name)throw new ConnectorNoEffectException("cache_file_preflight_input_invalid");
            fileMap[uid]=name;members.Add((step,node,revision,reference.Clone()));
        }
        long version;CancellationToken sessionToken;lock(credentialState){version=sessionGeneration;sessionToken=sessionCancellation.Token;}
        using var linked=CancellationTokenSource.CreateLinkedTokenSource(ct,sessionToken);var token=linked.Token;
        await gate.WaitAsync(token);
        try
        {
            var credentials=RequireCredentials();var principal=CachePrincipalHash();
            void Fence(){token.ThrowIfCancellationRequested();lock(credentialState){if(version!=sessionGeneration||principal!=CachePrincipalHash())throw new ConnectorNoEffectException("cache_principal_changed");}}
            Fence();var response=await worker.ReadCacheBulkAsync("cache_file_preflight",new{source_selector=selector,files=fileMap.Select(item=>new{file_uid=item.Key,file_name=item.Value}).ToArray()},credentials.User,credentials.Password,token);Fence();
            Closed(response,"files");var returned=response.GetProperty("files");
            if(returned.ValueKind!=JsonValueKind.Array||returned.GetArrayLength()!=fileMap.Count)throw new ConnectorException("teamcenter_worker_response_invalid");
            var sizes=new Dictionary<string,long>(StringComparer.Ordinal);long total=0;
            foreach(var item in returned.EnumerateArray())
            {
                Closed(item,"file_uid","file_name","file_size");var uid=item.GetProperty("file_uid").GetString();var name=item.GetProperty("file_name").GetString();var size=item.GetProperty("file_size").GetInt64();
                if(uid is null||name is null||!fileMap.TryGetValue(uid,out var expectedName)||name!=expectedName||size<1||size>9_007_199_254_740_991||!sizes.TryAdd(uid,size))throw new ConnectorException("teamcenter_worker_response_invalid");
                total=checked(total+size);
            }
            if(sizes.Count!=fileMap.Count)throw new ConnectorException("teamcenter_worker_response_invalid");
            var output=members.Select(member=>new{step_id=member.Step,node_key=member.Node,item_revision_uid=member.Revision,file_ref=member.Reference,file_size=sizes[member.Reference.GetProperty("file_uid").GetString()!]}).ToArray();
            var outputIdentity=identity.Clone();
            return JsonSerializer.SerializeToElement(new{identity=outputIdentity,files=output,total_byte_length=total,error_code=total>(members.Count==1?512L:100L)*1024*1024?"cache_file_batch_size_exceeded":null});
        }
        catch(OverflowException){throw new ConnectorNoEffectException("teamcenter_file_size_invalid");}
        finally{gate.Release();}
    }

    internal string LocalFileCachePrincipal { get { lock(credentialState){_ = RequireCredentials();return CachePrincipalHash();} } }

    public async Task<LocalModelArtifact> FetchModelFileAsync(JsonElement input,CancellationToken ct)
    {
        Closed(input,"batch_id","generation","snapshot_hash","schema_version","node_key","item_revision_uid","source_selector","file_ref","expected_content_hash","artifact_resource_refs");
        var selector=ReadSelector(input.GetProperty("source_selector"));
        var batch=input.GetProperty("batch_id").GetString();var generation=input.GetProperty("generation").GetString();
        if(!BulkToken(batch)||generation is not null&&!BulkToken(generation)||input.GetProperty("schema_version").GetInt32()!=1)throw new ConnectorNoEffectException("cache_file_input_invalid");
        var reference=input.GetProperty("file_ref");Closed(reference,"dataset_uid","file_uid","file_name","relation_type");
        var name=reference.GetProperty("file_name").GetString();
        if(string.IsNullOrWhiteSpace(name)||name.Length>512||name.IndexOfAny(['/', '\\'])>=0||name.Any(char.IsControl)||!name.EndsWith(".jt",StringComparison.OrdinalIgnoreCase)||reference.GetProperty("relation_type").GetString()!="IMAN_Rendering")throw new ConnectorNoEffectException("cache_file_input_invalid");
        var root=System.IO.Path.Combine(System.IO.Path.GetDirectoryName(new SqliteConnectionStringBuilder(connectionString).DataSource)!,"teamcenter-model-files");
        TeamcenterProcessWorker.SecureVisualizationMaterialRoot(root);
        long version;CancellationToken sessionToken;lock(credentialState){version=sessionGeneration;sessionToken=sessionCancellation.Token;}
        using var linked=CancellationTokenSource.CreateLinkedTokenSource(ct,sessionToken);var token=linked.Token;
        await gate.WaitAsync(token);string? safePath=null;
        try
        {
            var credentials=RequireCredentials();var principal=CachePrincipalHash();
            void Fence(){token.ThrowIfCancellationRequested();lock(credentialState){if(version!=sessionGeneration||principal!=CachePrincipalHash())throw new ConnectorNoEffectException("cache_principal_changed");}}
            Fence();var result=await worker.ReadCacheBulkAsync("cache_file",new{source_selector=selector,file_ref=reference,output_root=root},credentials.User,credentials.Password,token);Fence();
            safePath=TeamcenterProcessWorker.ValidateMaterialPath(root,result.GetProperty("local_path").GetString()!);
            var info=new FileInfo(safePath);var size=result.GetProperty("byte_size").GetInt64();
            if(!info.Exists||size is <24 or >512*1024*1024||info.Length!=size||(info.Attributes&FileAttributes.ReparsePoint)!=0)throw new ConnectorNoEffectException("cache_file_integrity_failed");
            await using var content=info.OpenRead();var hash=Convert.ToHexString(await SHA256.HashDataAsync(content,token)).ToLowerInvariant();Fence();
            var expected=input.GetProperty("expected_content_hash").GetString();
            if(expected is not null&&expected!="sha256:"+hash)throw new ConnectorNoEffectException("cache_file_content_mismatch");
            var identity=JsonSerializer.SerializeToElement(new{batch_id=batch,generation,snapshot_hash=input.GetProperty("snapshot_hash"),schema_version=1});
            return new(safePath,"model/jt",hash,size,identity,input.GetProperty("node_key").GetString()!,input.GetProperty("item_revision_uid").GetString()!,reference.Clone(),DateTimeOffset.UtcNow.ToString("O"));
        }
        catch{if(safePath is not null)try{File.SetAttributes(safePath,File.GetAttributes(safePath)&~FileAttributes.ReadOnly);File.Delete(safePath);}catch(IOException){}catch(UnauthorizedAccessException){}throw;}
        finally{gate.Release();}
    }
}
