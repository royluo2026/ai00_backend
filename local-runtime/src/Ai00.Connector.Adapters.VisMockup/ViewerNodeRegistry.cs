using System.Text.Json;
using Ai00.Connector.Contracts;

namespace Ai00.Connector.Adapters.VisMockup;

// All members below are confined to the Adapter's existing STA. Runtime numeric
// keys stay in _sessionNodeKeys, shared with the existing mapping lifecycle.
public sealed partial class VisMockupAdapter
{
    private readonly Dictionary<string,(string SourceNode, string Locator, string CadId, string Kind)> _viewerNodes = new(StringComparer.Ordinal);
    private sealed record ViewerNodeResolution(string source_node_id,string? node_ref,string status,
        string? error_code=null,bool? visible=null,string visibility_state="unknown");
    private (string Association,string Session,string Source,string Root)? _viewerScope;
    private long _viewerEpoch = 1;
    public Func<bool>? ViewerInteractionAdmissionAllowed { get; set; }
    private Action<string,object>? _viewerDiagnostic;
    public Action<string,object>? ViewerDiagnostic { get=>_viewerDiagnostic;set{_viewerDiagnostic=value;if(_treeCache is not null)_treeCache.Diagnostic=value;} }
    private void TraceViewer(string stage,object detail){try{ViewerDiagnostic?.Invoke(stage,detail);}catch{}}

    private void RequireViewerAdmission()
    {
        if(ViewerInteractionAdmissionAllowed?.Invoke()!=true)
            throw new ConnectorNoEffectException("viewer_authorization_required");
    }

    private void InvalidateViewerStructure()
    {
        foreach(var reference in _viewerNodes.Keys) _sessionNodeKeys.Remove(reference);
        _viewerNodes.Clear(); _viewerGeometry.Clear(); _viewerScope=null; _viewerEpoch++;
    }

    private IVisMockupDocument RequireViewerDocument(string association,string session)
    {
        if(string.IsNullOrWhiteSpace(association) || string.IsNullOrWhiteSpace(session))
            throw new ConnectorNoEffectException("viewer_scope_invalid");
        IVisMockupDocument document;
        try { document=_connection.RequireActiveDocument(); RequireExpectedDocumentSession(document,session); }
        catch(ConnectorException) { InvalidateViewerStructure(); throw new ConnectorNoEffectException("document_session_changed"); }
        var scope=(association,session,document.SourceIdentity,document.RootNode.NodeKey);
        if(_viewerScope != scope) { InvalidateViewerStructure(); _viewerScope=scope; }
        return document;
    }

    private IVisMockupDocument RecheckViewerDocument(string association, string session, long epoch)
    {
        var document = RequireViewerDocument(association, session);
        if (_viewerEpoch != epoch) throw new ConnectorNoEffectException("viewer_mapping_expired");
        return document;
    }

    private static string ViewerDescriptorText(JsonElement value, string field, int maximum, string error)
    {
        if (value.ValueKind != JsonValueKind.Object || !value.TryGetProperty(field, out var property)
            || property.ValueKind != JsonValueKind.String)
            throw new ConnectorNoEffectException(error);
        var text = property.GetString()!;
        if (string.IsNullOrWhiteSpace(text) || text.Length > maximum) throw new ConnectorNoEffectException(error);
        return text;
    }

    public Task<object> ResolveViewerNodesAsync(string sourceAssociationId,string documentSession,JsonElement sourceNodes) => _sta.InvokeAsync<object>(() =>
    {
        RequireViewerAdmission();
        var document=RequireViewerDocument(sourceAssociationId,documentSession);
        if(sourceNodes.ValueKind!=JsonValueKind.Array || sourceNodes.GetArrayLength() is <1 or >256)
            throw new ConnectorNoEffectException("viewer_nodes_invalid");
        var epoch = _viewerEpoch;
        var root = document.RootNode;
        // One shared budget includes the root and every materialized native node.
        // Each node's occurrence metadata is read at most once in this batch.
        var process = RequireProcessIdentity();
        var environment=FindCacheEnvironment(document);
        var managedCache = environment is not null || _openedCachePackages.Values.Any(item => item.ProcessId == process.ProcessId
            && item.Started == process.ProcessStartUtcTicks && item.Handle == document.DocumentId
            && string.Equals(item.Path, document.SourceIdentity, StringComparison.OrdinalIgnoreCase));
        // Only packages opened and registered by the pinned cache path receive the
        // larger bounded map. Existing online limits and conservative visibility stay.
        var remaining = managedCache ? 32768 : 511;
        var mappingClock = System.Diagnostics.Stopwatch.StartNew();
        void MappingAdmission()
        {
            RequireViewerAdmission();
            if(managedCache && mappingClock.ElapsedMilliseconds >= 20000)
                throw new ConnectorNoEffectException("viewer_mapping_budget_exceeded");
        }
        var childrenByKey = new Dictionary<string, IReadOnlyList<IVisMockupNode>>(StringComparer.Ordinal);
        var primaryOccurrenceByKey = new Dictionary<string, string>(StringComparer.Ordinal);
        var occurrencesByKey = new Dictionary<string, IReadOnlyList<string>>(StringComparer.Ordinal);
        var prefixes = new Dictionary<string, IVisMockupNode>(StringComparer.Ordinal) { [""] = root };
        IReadOnlyList<IVisMockupNode> Children(IVisMockupNode node)
        {
            MappingAdmission();
            var key = node.NodeKey;
            if (childrenByKey.TryGetValue(key, out var known)) return known;
            MappingAdmission();
            IReadOnlyList<IVisMockupNode> children;
            try { children = node.GetChildren(remaining); }
            catch (ConnectorNoEffectException error) when (error.Code == "viewer_mapping_budget_exceeded")
            {
                try
                {
                    Console.Error.WriteLine("AI00_VIEWER_MAPPING_BUDGET_V1:" + JsonSerializer.Serialize(new
                    {
                        parent_key = key, at_root = string.Equals(key, root.NodeKey, StringComparison.Ordinal),
                        child_count = node.ChildCount, remaining
                    }));
                }
                catch { /* A failed diagnostic must not change the mapping result. */ }
                throw;
            }
            remaining -= children.Count;
            childrenByKey[key] = children;
            return children;
        }
        IReadOnlyList<string> Occurrences(IVisMockupNode node)
        {
            MappingAdmission();
            var key = node.NodeKey;
            if (occurrencesByKey.TryGetValue(key, out var known)) return known;
            MappingAdmission();
            return occurrencesByKey[key] = node.OccurrenceIds;
        }
        string PrimaryOccurrence(IVisMockupNode node)
        {
            MappingAdmission();
            var key = node.NodeKey;
            if (primaryOccurrenceByKey.TryGetValue(key, out var known)) return known;
            MappingAdmission();
            return primaryOccurrenceByKey[key] = node.OccurrenceId;
        }
        IVisMockupNode ResolvePath(string[] path)
        {
            var current = root;
            var prefix = "";
            var rootPrimary = PrimaryOccurrence(root);
            var start = string.Equals(rootPrimary, path[0], StringComparison.Ordinal)
                || (!string.IsNullOrWhiteSpace(path[0]) && Occurrences(root).Contains(path[0], StringComparer.Ordinal)) ? 1 : 0;
            for (var index = start; index < path.Length; index++)
            {
                MappingAdmission();
                // Length prefixes keep arbitrary UID text from colliding.
                prefix += path[index].Length + ":" + path[index];
                if (prefixes.TryGetValue(prefix, out var known)) { current = known; continue; }
                IVisMockupNode? match = null;
                var pending = new Queue<IVisMockupNode>(Children(current));
                var aliasFallback = new List<IVisMockupNode>();
                while (pending.Count > 0)
                {
                    var levelCount = pending.Count;
                    var wrappers = new List<IVisMockupNode>();
                    for (var sibling = 0; sibling < levelCount; sibling++)
                    {
                        var child = pending.Dequeue();
                        var primary = PrimaryOccurrence(child);
                        if (string.Equals(primary, path[index], StringComparison.Ordinal))
                        {
                            if (match is not null) throw new ConnectorNoEffectException("vismockup_online_occurrence_ambiguous");
                            match = child;
                        }
                        else if (string.IsNullOrWhiteSpace(primary))
                        {
                            var aliases = Occurrences(child);
                            if (aliases.Contains(path[index], StringComparer.Ordinal))
                            {
                                if (match is not null) throw new ConnectorNoEffectException("vismockup_online_occurrence_ambiguous");
                                match = child;
                            }
                            else if (aliases.Count == 0) wrappers.Add(child);
                        }
                        else aliasFallback.Add(child);
                    }
                    if (match is not null) break;
                    foreach (var wrapper in wrappers)
                        foreach (var nested in Children(wrapper)) pending.Enqueue(nested);
                }
                // The Teamcenter occurrence UID is the canonical fast path. Older
                // Siemens metadata aliases are consulted only when no primary UID
                // matched, avoiding five COM metadata calls for every sibling.
                if (match is null)
                {
                    foreach (var child in aliasFallback)
                    {
                        if (!Occurrences(child).Contains(path[index], StringComparer.Ordinal)) continue;
                        if (match is not null) throw new ConnectorNoEffectException("vismockup_online_occurrence_ambiguous");
                        match = child;
                    }
                }
                current = match ?? throw new ConnectorNoEffectException("vismockup_online_occurrence_unmapped");
                prefixes[prefix] = current;
            }
            return current;
        }
        var results=new List<ViewerNodeResolution>();
        foreach(var descriptor in sourceNodes.EnumerateArray())
        {
            MappingAdmission();
            var source = "";
            try
            {
                source = ViewerDescriptorText(descriptor, "source_node_id", 256, "viewer_node_invalid");
                var fields=descriptor.EnumerateObject().Select(p=>p.Name).ToArray();
                if(fields.Distinct().Count()!=fields.Length || fields.Any(p=>p is not ("source_node_id" or "kind" or "occurrence_path")))
                    throw new ConnectorNoEffectException("viewer_node_invalid");
                var kind = ViewerDescriptorText(descriptor, "kind", 32, "viewer_node_invalid");
                string[] path = [];
                if (kind == "occurrence_path")
                {
                    if (!descriptor.TryGetProperty("occurrence_path", out var pathValue)
                        || pathValue.ValueKind != JsonValueKind.Array || pathValue.GetArrayLength() is <1 or >128)
                        throw new ConnectorNoEffectException("viewer_occurrence_path_invalid");
                    path = pathValue.EnumerateArray().Select(edge =>
                    {
                        var uid = ViewerDescriptorText(edge, "occurrence_uid", 128, "viewer_occurrence_path_invalid");
                        _ = ViewerDescriptorText(edge, "item_revision_uid", 128, "viewer_occurrence_path_invalid");
                        if (edge.EnumerateObject().Count() != 2) throw new ConnectorNoEffectException("viewer_occurrence_path_invalid");
                        return uid;
                    }).ToArray();
                }
                else if (kind is "single_part_root" or "document_root" && fields.Length != 2)
                    throw new ConnectorNoEffectException("viewer_node_invalid");
                var locator=CanonicalJson.Hash(descriptor);
                var previous=_viewerNodes.FirstOrDefault(p=>p.Value.SourceNode==source && p.Value.Locator==locator);
                if(previous.Key is not null && _sessionNodeKeys.ContainsKey(previous.Key))
                { results.Add(new(source,previous.Key,"mapped")); continue; }
                IVisMockupNode node;
                (string Key,string CadId)[]? geometry=null;
                if(environment is not null && kind=="occurrence_path")
                {
                    geometry=ResolveEnvironmentGeometry(environment,document,path);
                    node=document.FindNodeByKey(geometry[0].Key);
                }
                else switch(kind)
                {
                    case "document_root":
                        node=root;
                        break;
                    case "single_part_root":
                        node=root;
                        var children=Children(node);
                        if(children.Count==1 && Children(children[0]).Count==0) node=children[0];
                        else if(children.Count!=0) throw new ConnectorNoEffectException("viewer_single_part_required");
                        break;
                    case "occurrence_path":
                        node=ResolvePath(path);
                        break;
                    default: throw new ConnectorNoEffectException("viewer_node_kind_invalid");
                }
                // CADID is native instance identity, not JT metadata. Without it
                // a reused numeric key cannot be distinguished safely.
                MappingAdmission();
                var cadId = node.CadId;
                if(string.IsNullOrWhiteSpace(cadId)) throw new ConnectorNoEffectException("viewer_instance_identity_unavailable");
                if(_viewerNodes.Count>=(managedCache?65536:4096) || _sessionNodeKeys.Count>=(managedCache?65536:4096))
                    throw new ConnectorNoEffectException("viewer_mapping_capacity");
                var reference="viewer:"+Guid.NewGuid().ToString("N");
                _sessionNodeKeys[reference]=node.NodeKey;
                _viewerNodes[reference]=(source,locator,cadId,kind);
                if(geometry is not null)_viewerGeometry[reference]=geometry;
                results.Add(new(source,reference,"mapped"));
                TraceViewer("node_mapped",new{source_node_id=source,node_ref=reference,structure_epoch=_viewerEpoch,budget_remaining=remaining});
            }
            catch(ConnectorNoEffectException error) when (error.Code != "viewer_authorization_required")
            { TraceViewer("node_unmapped",new{source_node_id=source,error_code=error.Code,budget_remaining=remaining});results.Add(new(source,null,"unmapped",error.Code)); }
        }
        // Mapping finishes first: visibility calibration must never consume the
        // traversal budget needed to identify another requested write target.
        var visibilityByKey=new Dictionary<string,(bool? Visible,string State,string? Error)>(StringComparer.Ordinal);
        var visiting=new HashSet<string>(StringComparer.Ordinal);
        var visibilityRemaining=512;
        (bool? Visible,string State,string? Error) ReadVisibility(IVisMockupNode node)
        {
            RequireViewerAdmission();
            var key=node.NodeKey;
            if(visibilityByKey.TryGetValue(key,out var cached))return cached;
            if(!visiting.Add(key))return(null,"unknown","viewer_visibility_cycle");
            (bool? Visible,string State,string? Error) result;
            try
            {
                if(visibilityRemaining--<=0)throw new ConnectorNoEffectException("viewer_mapping_budget_exceeded");
                var visible=node.IsVisible;
                var seenVisible=visible;var seenHidden=!visible;string? unknown=null;
                foreach(var child in Children(node))
                {
                    var observed=ReadVisibility(child);
                    seenVisible|=observed.State is "visible" or "mixed";
                    seenHidden|=observed.State is "hidden" or "mixed";
                    unknown??=observed.Error;
                }
                result=seenVisible&&seenHidden?(null,"mixed",null):unknown is not null?(null,"unknown",unknown)
                    :(visible,visible?"visible":"hidden",null);
            }
            catch(Exception error) when(error is not (OutOfMemoryException or StackOverflowException)
                && error is not ConnectorNoEffectException { Code: "viewer_authorization_required" })
            {
                result=(null,"unknown",error is ConnectorNoEffectException { Code: "viewer_mapping_budget_exceeded" }
                    ?"viewer_visibility_budget_exceeded":"viewer_visibility_read_failed");
            }
            finally{visiting.Remove(key);}
            visibilityByKey[key]=result;return result;
        }
        for(var index=0;index<results.Count;index++)
        {
            var result=results[index];if(result.status!="mapped")continue;
            RequireViewerAdmission();
            (bool? Visible,string State,string? Error) observed;
            try
            {
                var reference=result.node_ref!;var key=_sessionNodeKeys[reference];
                var node=document.FindNodeByKey(key);
                if(node.NodeKey!=key||node.CadId!=_viewerNodes[reference].CadId)
                    observed=(null,"unknown","viewer_mapping_expired");
                else if(_viewerGeometry.TryGetValue(reference,out var geometry))
                {
                    var states=geometry.Select(target=>{
                        var native=document.FindNodeByKey(target.Key);
                        return native.CadId==target.CadId?ReadVisibility(native):(Visible:(bool?)null,State:"unknown",Error:(string?)"viewer_mapping_expired");
                    }).ToArray();
                    var unknown=states.FirstOrDefault(item=>item.Error is not null).Error;
                    var on=states.Any(item=>item.State is "visible" or "mixed");
                    var off=states.Any(item=>item.State is "hidden" or "mixed");
                    observed=unknown is not null?(null,"unknown",unknown):on&&off?(null,"mixed",null):(on,on?"visible":"hidden",null);
                }
                else observed=ReadVisibility(node);
            }
            catch(Exception error) when(error is not (OutOfMemoryException or StackOverflowException)
                && error is not ConnectorNoEffectException { Code: "viewer_authorization_required" })
            {observed=(null,"unknown","viewer_visibility_read_failed");}
            results[index]=result with{visible=observed.Visible,visibility_state=observed.State,error_code=observed.Error};
            TraceViewer("visibility_calibrated",new{source_node_id=result.source_node_id,visible=observed.Visible,
                visibility_state=observed.State,error_code=observed.Error,budget_remaining=remaining});
        }
        RequireViewerAdmission();
        RecheckViewerDocument(sourceAssociationId, documentSession, epoch);
        return new {structure_epoch=_viewerEpoch,nodes=results};
    });

    public Task<object> ExecuteViewerNodeAsync(string sourceAssociationId,string documentSession,long structureEpoch,
        string nodeRef,string operationId,JsonElement arguments) => _sta.InvokeAsync<object>(() =>
    {
        RequireViewerAdmission();
        var document=RequireViewerDocument(sourceAssociationId,documentSession);
        if(structureEpoch!=_viewerEpoch || !_viewerNodes.TryGetValue(nodeRef,out var mapping)
            || !_sessionNodeKeys.TryGetValue(nodeRef,out var key))
            throw new ConnectorNoEffectException("viewer_mapping_expired");
        if(arguments.ValueKind!=JsonValueKind.Object || arguments.EnumerateObject().Count()!=1
            || !arguments.TryGetProperty("action",out var actionValue) || actionValue.ValueKind!=JsonValueKind.String)
            throw new ConnectorNoEffectException("viewer_arguments_invalid");
        var action=actionValue.GetString();
        var visibility=operationId=="vismockup.node.visibility.change@1" && action is "show" or "hide";
        var selection=operationId=="vismockup.node.selection.change@1" && action is "highlight" or "unhighlight";
        if(!visibility && !selection) throw new ConnectorNoEffectException("viewer_operation_forbidden");
        try
        {
            var node=document.FindNodeByKey(key);
            if(node.NodeKey!=key || node.CadId!=mapping.CadId) throw new InvalidOperationException();
            if(_viewerGeometry.TryGetValue(nodeRef,out var targets))foreach(var target in targets)
            {
                var native=document.FindNodeByKey(target.Key);
                if(native.NodeKey!=target.Key||native.CadId!=target.CadId)throw new InvalidOperationException();
            }
        }
        catch(Exception) { InvalidateViewerStructure(); throw new ConnectorNoEffectException("viewer_mapping_expired"); }
        document = RecheckViewerDocument(sourceAssociationId, documentSession, structureEpoch);
        RequireViewerAdmission();
        // After crossing the native write boundary no exception can prove no effect.
        var watch=System.Diagnostics.Stopwatch.StartNew();
        var stage="native_write";
        var wholeDocumentHide=visibility && action=="hide" && mapping.Kind=="document_root";
        var targetKeys=_viewerGeometry.TryGetValue(nodeRef,out var geometryTargets)?geometryTargets.Select(item=>item.Key).ToArray():new[]{key};
        TraceViewer(stage,new{node_ref=nodeRef,action,structure_epoch=structureEpoch,scope=wholeDocumentHide?"document":"node",target_count=targetKeys.Length,visibility_dispatch=visibility?"batch":null});
        try
        {
            if(visibility)
            {
                var visible=action=="show";
                if(wholeDocumentHide) document.SetAllNodesVisible(false);
                else document.SetNodesVisible(targetKeys,visible);
                stage="visibility_readback";
                var observed=targetKeys.All(target=>document.IsNodeVisible(target)==visible)?visible:!visible;
                // AllNodesOff supplies document-wide semantics. This bounded read
                // checks the root flag, not every descendant or rendered geometry.
                TraceViewer(stage,new{node_ref=nodeRef,expected=visible,observed,scope=wholeDocumentHide?"document":"node",verification_scope=wholeDocumentHide?"root_flag":"node_flag",elapsed_ms=watch.Elapsed.TotalMilliseconds});
                if(observed!=visible) throw new ConnectorException("viewer_visibility_unconfirmed");
                stage="document_recheck";
                RecheckViewerDocument(sourceAssociationId, documentSession, structureEpoch);
                return new {node_ref=nodeRef,visible};
            }
            var selected=action=="highlight";
            foreach(var target in targetKeys)
            {
                RequireViewerAdmission();
                RecheckViewerDocument(sourceAssociationId,documentSession,structureEpoch);
                document.SetNodeSelected(target,selected);
            }
            stage="document_recheck";
            RecheckViewerDocument(sourceAssociationId, documentSession, structureEpoch);
            return new {node_ref=nodeRef,selected};
        }
        catch (Exception error)
        {
            TraceViewer("adapter_failed",new{node_ref=nodeRef,action,failed_stage=stage,exception_type=error.GetType().Name,hresult=error.HResult,code=error is ConnectorException known?known.Code:null,elapsed_ms=watch.Elapsed.TotalMilliseconds});
            InvalidateViewerStructure();
            throw new ConnectorException("viewer_outcome_unknown");
        }
    });
}
