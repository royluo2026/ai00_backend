using System.Text.Json;
using System.Text.RegularExpressions;
using Ai00.Connector.Contracts;
using Ai00.Connector.Contracts.V2;

namespace Ai00.Connector.Adapters.VisMockup;

public sealed partial class VisMockupAdapter
{
    // STA-owned provenance from successful cache opens; never infer this from titles.
    private readonly Dictionary<string,(int ProcessId,long Started,string Handle,string Path)> _openedCachePackages = new(StringComparer.Ordinal);

    public Task<object> OpenManagedCacheAsync(JsonElement payload, CancellationToken ct) => _sta.InvokeAsync<object>(() =>
    {
        ct.ThrowIfCancellationRequested();
        static void Closed(JsonElement value, params string[] allowed)
        {
            if(value.ValueKind!=JsonValueKind.Object || value.EnumerateObject().Select(p=>p.Name).Distinct().Count()!=value.EnumerateObject().Count() || value.EnumerateObject().Any(p=>!allowed.Contains(p.Name)))
                throw new ConnectorNoEffectException("cache_open_input_invalid");
        }
        static bool Match(JsonElement value,string pattern) => value.ValueKind==JsonValueKind.String && Regex.IsMatch(value.GetString()!,pattern,RegexOptions.CultureInvariant);
        Closed(payload,"artifact_ref","cache_binding","package_hash","package_dependencies","local_artifact_path");
        var binding=payload.GetProperty("cache_binding");
        Closed(binding,"batch_id","generation","snapshot_hash","schema_version");
        if(!Match(binding.GetProperty("batch_id"),"^[a-f0-9]{32}$") || binding.GetProperty("schema_version").GetInt32()!=1 ||
            binding.GetProperty("generation").ValueKind!=JsonValueKind.Null && !Match(binding.GetProperty("generation"),"^[a-f0-9]{32}$") ||
            binding.GetProperty("snapshot_hash").ValueKind!=JsonValueKind.Null && !Match(binding.GetProperty("snapshot_hash"),"^sha256:[a-f0-9]{64}$"))
            throw new ConnectorNoEffectException("cache_open_input_invalid");
        var artifact=payload.GetProperty("artifact_ref");
        var dependencies=payload.TryGetProperty("package_dependencies",out var provided)?provided:JsonSerializer.SerializeToElement(Array.Empty<object>());
        if(dependencies.ValueKind!=JsonValueKind.Array || dependencies.GetArrayLength()>10000)
            throw new ConnectorNoEffectException("cache_open_input_invalid");
        var packageHash=CanonicalJsonV2.Hash(JsonSerializer.SerializeToElement(new {artifact_ref=artifact,package_dependencies=dependencies,cache_binding=binding}));
        if(payload.GetProperty("package_hash").GetString()!=packageHash) throw new ConnectorNoEffectException("cache_package_identity_mismatch");
        string Verify(string path,JsonElement reference)
        {
            Closed(reference,"artifact_id","media_type","sha256","byte_size","version");
            if(!Match(reference.GetProperty("artifact_id"),"^[A-Za-z0-9_.-]{1,191}$") || !Match(reference.GetProperty("sha256"),"^[a-f0-9]{64}$") || reference.GetProperty("version").GetInt64()<1)
                throw new ConnectorNoEffectException("artifact_ref_invalid");
            var safe=_paths.RequireVerifiedArtifact(path,reference.GetProperty("sha256").GetString()!);
            if(new FileInfo(safe).Length!=reference.GetProperty("byte_size").GetInt64()) throw new ConnectorNoEffectException("artifact_integrity_failed");
            var media=reference.GetProperty("media_type").GetString();
            if(Path.GetExtension(safe).Equals(".jt",StringComparison.OrdinalIgnoreCase)?media!="model/jt":media is not ("model/plmxml" or "application/vnd.siemens.plmxml+xml"))
                throw new ConnectorNoEffectException("artifact_ref_invalid");
            return safe;
        }
        var safePath=Verify(payload.GetProperty("local_artifact_path").GetString()!,artifact);
        var packageRoot=Path.GetDirectoryName(safePath)!;
        var paths=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach(var dependency in dependencies.EnumerateArray())
        {
            Closed(dependency,"package_path","artifact_ref");
            if(!Match(dependency.GetProperty("package_path"),"^dependencies/[A-Za-z0-9_.-]+[.]jt$")) throw new ConnectorNoEffectException("artifact_path_invalid");
            var relative=dependency.GetProperty("package_path").GetString()!;
            if(!paths.Add(relative)) throw new ConnectorNoEffectException("artifact_path_invalid");
            Verify(Path.Combine(packageRoot,relative),dependency.GetProperty("artifact_ref"));
        }
        // Artifact IDs identify transport records, not the bytes opened natively.
        // Keep the complete snapshot binding, content and dependency locations pinned.
        static object Content(JsonElement reference) => new {sha256=reference.GetProperty("sha256"),byte_size=reference.GetProperty("byte_size"),media_type=reference.GetProperty("media_type")};
        var contentIdentity=CanonicalJsonV2.Hash(JsonSerializer.SerializeToElement(new {
            cache_binding=binding,artifact=Content(artifact),dependencies=dependencies.EnumerateArray()
                .OrderBy(item=>item.GetProperty("package_path").GetString(),StringComparer.Ordinal)
                .Select(item=>new {package_path=item.GetProperty("package_path"),artifact=Content(item.GetProperty("artifact_ref"))}).ToArray()}));
        var application=_connection.RequireActiveApplication(true);
        var before=RequireProcessIdentity();
        foreach(var key in _openedCachePackages.Where(entry=>entry.Value.ProcessId!=before.ProcessId || entry.Value.Started!=before.ProcessStartUtcTicks).Select(entry=>entry.Key).ToArray())
            _openedCachePackages.Remove(key);
        IVisMockupDocument? document=OpenCacheEnvironment(application,safePath,paths,before.ProcessId!.Value,before.ProcessStartUtcTicks!.Value);
        var environmentDocument=document is not null;
        if(document is null && _openedCachePackages.TryGetValue(contentIdentity,out var registered))
        {
            var matches=application.OpenDocuments.Where(candidate=>candidate.DocumentId==registered.Handle &&
                Path.IsPathFullyQualified(candidate.SourceIdentity) && string.Equals(Path.GetFullPath(candidate.SourceIdentity),registered.Path,StringComparison.OrdinalIgnoreCase)).Take(2).ToArray();
            if(matches.Length==1)
            {
                // The retained package may be in an older plan directory. Verify it
                // too: lazy native geometry loads must still read the pinned bytes.
                Verify(registered.Path,artifact);
                foreach(var dependency in dependencies.EnumerateArray())
                    Verify(Path.Combine(Path.GetDirectoryName(registered.Path)!,dependency.GetProperty("package_path").GetString()!),dependency.GetProperty("artifact_ref"));
                document=matches[0];
            }
            else _openedCachePackages.Remove(contentIdentity);
        }
        ct.ThrowIfCancellationRequested();
        InvalidateViewerStructure();
        document??=VisMockupDocumentOpen.Open(application,safePath,before.ProcessId);
        _ownedDocumentId=document.DocumentId;
        var after=RequireProcessIdentity();
        if(before.ProcessId!=after.ProcessId || before.ProcessStartUtcTicks!=after.ProcessStartUtcTicks || string.IsNullOrWhiteSpace(document.DocumentId))
            throw new ConnectorException("vismockup_document_identity_changed");
        var native=new {process_id=before.ProcessId!.Value,process_started_utc_ticks=before.ProcessStartUtcTicks!.Value.ToString(System.Globalization.CultureInfo.InvariantCulture),document_handle=document.DocumentId};
        if(!environmentDocument && !_openedCachePackages.ContainsKey(contentIdentity))
        {
            if(_openedCachePackages.Count>=VisMockupDocumentOpen.MaximumDocuments) _openedCachePackages.Remove(_openedCachePackages.Keys.First());
            _openedCachePackages[contentIdentity]=(before.ProcessId.Value,before.ProcessStartUtcTicks.Value,document.DocumentId,safePath);
        }
        return new {protocol="ai00.viewer.opened-cache.v1",cache_binding=binding,package_hash=packageHash,artifact_ref=artifact,
            document_identity=new {document_session=CanonicalJson.Hash(native),native.process_id,native.process_started_utc_ticks,native.document_handle}};
    });
}
