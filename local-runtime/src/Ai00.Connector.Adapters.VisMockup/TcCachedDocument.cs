using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using System.Xml;
using System.Xml.Linq;
using Ai00.Connector.Contracts;
using Ai00.Connector.Contracts.V2;
namespace Ai00.Connector.Adapters.VisMockup;
public sealed partial class VisMockupAdapter
{
    private const int MaximumAssemblyXmlBytes=64*1024*1024;
    private const int MaximumCacheOpenPacketBytes=96*1024*1024;
    internal const string TcOpenContractHash="sha256:ed3b82d97c619831446e32110d7ca40f8cce6eac32f223a6fd8db1b7202f6399";
    private static void TcClosed(JsonElement value,params string[] names)
    {
        if(value.ValueKind!=JsonValueKind.Object||value.EnumerateObject().Count()!=names.Length||value.EnumerateObject().Any(p=>!names.Contains(p.Name))||value.EnumerateObject().Select(p=>p.Name).Distinct().Count()!=names.Length)
            throw new ConnectorNoEffectException("cache_open_input_invalid");
    }
    internal async Task<object> OpenTcCacheAsync(JsonElement payload,CancellationToken ct)
    {
        if(Encoding.UTF8.GetByteCount(payload.GetRawText())>MaximumCacheOpenPacketBytes)throw new ConnectorNoEffectException("cache_package_result_limit");
        TcClosed(payload,"cache_binding","preparation_hash","package_hash","source_selector","assembly_xml","tc_dependencies");
        var package=JsonNode.Parse(payload.GetRawText())!.AsObject();package.Remove("package_hash");
        var hash=CanonicalJsonV2.Hash(JsonSerializer.SerializeToElement(package));
        if(payload.GetProperty("package_hash").GetString()!=hash)throw new ConnectorNoEffectException("cache_package_identity_mismatch");
        var binding=payload.GetProperty("cache_binding");TcClosed(binding,"batch_id","generation","snapshot_hash","schema_version");
        var selector=payload.GetProperty("source_selector");
        var dependencies=payload.GetProperty("tc_dependencies");
        if(dependencies.ValueKind!=JsonValueKind.Array||dependencies.GetArrayLength() is <1 or >10000)throw new ConnectorNoEffectException("cache_open_input_invalid");
        var text=payload.GetProperty("assembly_xml").GetString()??"";
        if(Encoding.UTF8.GetByteCount(text)>MaximumAssemblyXmlBytes)throw new ConnectorNoEffectException("cache_package_result_limit");
        XDocument xml;
        using(var reader=XmlReader.Create(new StringReader(text),new XmlReaderSettings{DtdProcessing=DtdProcessing.Prohibit,XmlResolver=null,MaxCharactersInDocument=MaximumAssemblyXmlBytes}))xml=XDocument.Load(reader);
        var root=Path.Combine(_plmxmlRoot,"tc-local");TeamcenterProcessWorker.SecureVisualizationMaterialRoot(root);
        var directory=Path.Combine(root,"packages",hash[7..]);TeamcenterProcessWorker.SecureVisualizationMaterialRoot(directory);
        var dependencyRoot=Path.Combine(directory,"dependencies");TeamcenterProcessWorker.SecureVisualizationMaterialRoot(dependencyRoot);
        var paths=new HashSet<string>(StringComparer.Ordinal);var keys=new HashSet<string>();var proofs=new List<object>();
        var cache=new LocalTeamcenterModelCache(Path.Combine(root,"files"));
        var total=dependencies.GetArrayLength();var completed=0;var hits=0;
        var timer=System.Diagnostics.Stopwatch.StartNew();
        void Log(string stage,long bytes=0,string? code=null)=>Console.Error.WriteLine("AI00_MODEL_FILE_TIMING_V1:"+JsonSerializer.Serialize(new{timestamp=DateTimeOffset.UtcNow,stage,package_hash=hash,completed,total,cache_hits=hits,byte_size=bytes,elapsed_ms=timer.Elapsed.TotalMilliseconds,error_code=code}));
        string principal;
        var packagePath=Path.Combine(directory,"environment.plmxml");
        try {
            principal=_teamcenter.LocalFileCachePrincipal;
            foreach(var dependency in dependencies.EnumerateArray())
            {
                ct.ThrowIfCancellationRequested();TcClosed(dependency,"package_path","file_ref","node_key","item_revision_uid");
                var reference=dependency.GetProperty("file_ref");TcClosed(reference,"dependency_key","endpoint_id","dataset_uid","file_uid","file_name","relation_type");
                var key=reference.GetProperty("dependency_key").GetString()??"";var path=dependency.GetProperty("package_path").GetString()??"";
                var refNode=JsonNode.Parse(reference.GetRawText())!.AsObject();refNode.Remove("dependency_key");
                if(!Regex.IsMatch(key,"\\A[a-f0-9]{64}\\z")||CanonicalJsonV2.Hash(JsonSerializer.SerializeToElement(refNode))!="sha256:"+key
                    ||path!="dependencies/"+key+".jt"||!keys.Add(key)||!paths.Add(path)||reference.GetProperty("endpoint_id").GetString()!=selector.GetProperty("endpoint_id").GetString())
                    throw new ConnectorNoEffectException("cache_tc_dependency_invalid");
            }
            var xmlPaths=xml.Descendants(CacheXml+"Representation").Select(r=>(string?)r.Attribute("location")??"").ToHashSet(StringComparer.Ordinal);
            if(!xmlPaths.SetEquals(paths))throw new ConnectorNoEffectException("cache_environment_dependency_invalid");
            Log("local_cache_checked");
            foreach(var dependency in dependencies.EnumerateArray())
            {
                ct.ThrowIfCancellationRequested();var reference=dependency.GetProperty("file_ref");var key=reference.GetProperty("dependency_key").GetString()!;
                var cacheKey=CanonicalJsonV2.Hash(JsonSerializer.SerializeToElement(new{principal,reference,binding}))[7..];
                var local=await cache.ResolveAsync(cacheKey,async token=>{
                    Log("jt_download_started");var file=JsonNode.Parse(reference.GetRawText())!.AsObject();file.Remove("dependency_key");file.Remove("endpoint_id");
                    var input=JsonNode.Parse(binding.GetRawText())!.AsObject();input["source_selector"]=JsonNode.Parse(selector.GetRawText());input["file_ref"]=file;
                    input["node_key"]=dependency.GetProperty("node_key").GetString();input["item_revision_uid"]=dependency.GetProperty("item_revision_uid").GetString();input["expected_content_hash"]=null;input["artifact_resource_refs"]=new JsonArray();
                    var acquired=await _teamcenter.FetchModelFileAsync(JsonSerializer.SerializeToElement(input),token);
                    Log("jt_download_completed",acquired.ByteSize);return acquired.Path;
                },ct);
                if(local.CacheHit)hits++;
                var target=Path.Combine(directory,dependency.GetProperty("package_path").GetString()!);
                // A document may still reference this immutable package. Never replace its bytes.
                if(File.Exists(target)&&await LocalTeamcenterModelCache.Hash(target,ct)!=local.Sha256)
                    throw new ConnectorNoEffectException("cache_file_content_changed");
                if(!File.Exists(target))
                {
                    var temporary=target+".partial-"+Guid.NewGuid().ToString("N");
                    try {File.Copy(local.Path,temporary);ct.ThrowIfCancellationRequested();File.Move(temporary,target,false);}
                    finally {if(File.Exists(temporary))File.Delete(temporary);}
                }
                // These files are created only by this local resolver. The OIS
                // artifact allowlist deliberately does not include this directory.
                new AllowedPathPolicy([root]).RequireVerifiedArtifact(target,local.Sha256);
                foreach(var rep in xml.Descendants(CacheXml+"Representation").Where(r=>(string?)r.Attribute("location")==dependency.GetProperty("package_path").GetString()))
                {
                    var view=rep.Parent!;var user=view.Element(CacheXml+"UserData")!;
                    user.Add(new XElement(CacheXml+"UserValue",new XAttribute("title","ai00_jt_sha256_"+key),new XAttribute("value",local.Sha256)));
                }
                proofs.Add(new{dependency_key=key,sha256=local.Sha256,byte_size=local.ByteSize});completed++;Log("local_file_verified",local.ByteSize);
            }
            ct.ThrowIfCancellationRequested();
            await File.WriteAllTextAsync(packagePath,xml.ToString(SaveOptions.DisableFormatting),new UTF8Encoding(false),ct);
        } catch(Exception ex) {
            var code=ex is ConnectorException ce?ce.Code:ex is OperationCanceledException?"cancelled":ex is UnauthorizedAccessException?"cache_local_path_forbidden":ex is IOException?"cache_local_io_failed":"cache_local_materialization_failed";Log("local_materialization_failed",code:code);
            throw new ConnectorNoEffectException(code);
        }
        try {cache.Trim(TimeSpan.FromDays(7),10L*1024*1024*1024);LocalModelPackages.Trim(Path.Combine(root,"packages"),TimeSpan.FromDays(7));}
        catch(IOException){}catch(UnauthorizedAccessException){}
        Log("native_open_started");
        return await _sta.InvokeAsync<object>(()=>{
            // Until the first COM mutation, cancellation has a definite no-effect outcome.
            if(ct.IsCancellationRequested)throw new ConnectorNoEffectException("cache_open_interrupted");
            try{if(_teamcenter.LocalFileCachePrincipal!=principal)throw new ConnectorNoEffectException("teamcenter_session_changed");}
            catch(ConnectorException rejected){throw new ConnectorNoEffectException(rejected.Code);}
            var application=_connection.RequireActiveApplication(true);var before=RequireProcessIdentity();
            LocalModelPackages.Protect(directory,before.ProcessId!.Value,before.ProcessStartUtcTicks!.Value);
            InvalidateViewerStructure();
            var document=OpenCacheEnvironment(application,packagePath,paths,before.ProcessId!.Value,before.ProcessStartUtcTicks!.Value)
                ??throw new ConnectorNoEffectException("cache_environment_identity_invalid");
            _ownedDocumentId=document.DocumentId;var after=RequireProcessIdentity();
            if(after.ProcessId!=before.ProcessId||after.ProcessStartUtcTicks!=before.ProcessStartUtcTicks)throw new ConnectorException("vismockup_document_identity_changed");
            var native=new{process_id=before.ProcessId.Value,process_started_utc_ticks=before.ProcessStartUtcTicks.Value.ToString(System.Globalization.CultureInfo.InvariantCulture),document_handle=document.DocumentId};
            Log("native_open_completed");
            return new{protocol="ai00.viewer.opened-tc-cache.v1",cache_binding=binding,package_hash=hash,files=proofs,
                document_identity=new{document_session=CanonicalJson.Hash(native),native.process_id,native.process_started_utc_ticks,native.document_handle}};
        });
    }
}
