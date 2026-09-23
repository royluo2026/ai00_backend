using System.Text.Json;
using Ai00.Connector.Contracts;

namespace Ai00.Connector.Adapters.VisMockup;

// All members below are confined to the Adapter's existing STA. Runtime numeric
// keys stay in _sessionNodeKeys, shared with the existing mapping lifecycle.
public sealed partial class VisMockupAdapter
{
    private readonly Dictionary<string,(string SourceNode, string Locator, string CadId)> _viewerNodes = new(StringComparer.Ordinal);
    private (string Association,string Session,string Source,string Root)? _viewerScope;
    private long _viewerEpoch = 1;
    public Func<bool>? ViewerInteractionAdmissionAllowed { get; set; }

    private void RequireViewerAdmission()
    {
        if(ViewerInteractionAdmissionAllowed?.Invoke()!=true)
            throw new ConnectorNoEffectException("viewer_authorization_required");
    }

    private void InvalidateViewerStructure()
    {
        foreach(var reference in _viewerNodes.Keys) _sessionNodeKeys.Remove(reference);
        _viewerNodes.Clear(); _viewerScope=null; _viewerEpoch++;
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
        var remaining = 511;
        var childrenByKey = new Dictionary<string, IReadOnlyList<IVisMockupNode>>(StringComparer.Ordinal);
        var primaryOccurrenceByKey = new Dictionary<string, string>(StringComparer.Ordinal);
        var occurrencesByKey = new Dictionary<string, IReadOnlyList<string>>(StringComparer.Ordinal);
        var prefixes = new Dictionary<string, IVisMockupNode>(StringComparer.Ordinal) { [""] = root };
        IReadOnlyList<IVisMockupNode> Children(IVisMockupNode node)
        {
            RequireViewerAdmission();
            var key = node.NodeKey;
            if (childrenByKey.TryGetValue(key, out var known)) return known;
            RequireViewerAdmission();
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
            RequireViewerAdmission();
            var key = node.NodeKey;
            if (occurrencesByKey.TryGetValue(key, out var known)) return known;
            RequireViewerAdmission();
            return occurrencesByKey[key] = node.OccurrenceIds;
        }
        string PrimaryOccurrence(IVisMockupNode node)
        {
            RequireViewerAdmission();
            var key = node.NodeKey;
            if (primaryOccurrenceByKey.TryGetValue(key, out var known)) return known;
            RequireViewerAdmission();
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
                RequireViewerAdmission();
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
        var results=new List<object>();
        foreach(var descriptor in sourceNodes.EnumerateArray())
        {
            RequireViewerAdmission();
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
                else if (kind == "single_part_root" && fields.Length != 2)
                    throw new ConnectorNoEffectException("viewer_node_invalid");
                var locator=CanonicalJson.Hash(descriptor);
                var previous=_viewerNodes.FirstOrDefault(p=>p.Value.SourceNode==source && p.Value.Locator==locator);
                if(previous.Key is not null && _sessionNodeKeys.ContainsKey(previous.Key))
                { results.Add(new {source_node_id=source,node_ref=previous.Key,status="mapped"}); continue; }
                IVisMockupNode node;
                switch(kind)
                {
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
                RequireViewerAdmission();
                var cadId = node.CadId;
                if(string.IsNullOrWhiteSpace(cadId)) throw new ConnectorNoEffectException("viewer_instance_identity_unavailable");
                if(_viewerNodes.Count>=4096 || _sessionNodeKeys.Count>=4096)
                    throw new ConnectorNoEffectException("viewer_mapping_capacity");
                var reference="viewer:"+Guid.NewGuid().ToString("N");
                _sessionNodeKeys[reference]=node.NodeKey;
                _viewerNodes[reference]=(source,locator,cadId);
                results.Add(new {source_node_id=source,node_ref=reference,status="mapped"});
            }
            catch(ConnectorNoEffectException error) when (error.Code != "viewer_authorization_required")
            { results.Add(new {source_node_id=source,node_ref=(string?)null,status="unmapped",error_code=error.Code}); }
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
        }
        catch(Exception) { InvalidateViewerStructure(); throw new ConnectorNoEffectException("viewer_mapping_expired"); }
        document = RecheckViewerDocument(sourceAssociationId, documentSession, structureEpoch);
        RequireViewerAdmission();
        // After crossing the native write boundary no exception can prove no effect.
        try
        {
            if(visibility)
            {
                var visible=action=="show";
                document.SetNodeVisible(key,visible);
                if(document.IsNodeVisible(key)!=visible) throw new ConnectorException("viewer_visibility_unconfirmed");
                RecheckViewerDocument(sourceAssociationId, documentSession, structureEpoch);
                return new {node_ref=nodeRef,visible};
            }
            var selected=action=="highlight";
            document.SetNodeSelected(key,selected);
            RecheckViewerDocument(sourceAssociationId, documentSession, structureEpoch);
            return new {node_ref=nodeRef,selected};
        }
        catch (Exception)
        {
            InvalidateViewerStructure();
            throw new ConnectorException("viewer_outcome_unknown");
        }
    });
}
