using System.Xml;
using System.Xml.Linq;
using System.Text.RegularExpressions;
using Ai00.Connector.Contracts;

namespace Ai00.Connector.Adapters.VisMockup;

public sealed partial class VisMockupAdapter
{
    private static readonly XNamespace CacheXml = "http://www.plmxml.org/Schemas/PLMXMLSchema";
    // Logical structure belongs to the pinned package, native geometry to the
    // environment. Never key either by a display name or revision UID.
    private sealed class CacheEnvironment(int processId,long started,string handle,string path)
    {
        internal readonly int ProcessId=processId;
        internal readonly long Started=started;
        internal readonly string Handle=handle, Path=path;
        internal readonly Dictionary<string,string[]> Children=new(StringComparer.Ordinal);
        internal readonly Dictionary<string,string> Geometry=new(StringComparer.Ordinal);
        internal readonly Dictionary<string,double[]> Transforms=new(StringComparer.Ordinal);
        internal readonly Dictionary<string,(XElement Instance,XElement View)> Parts=new(StringComparer.Ordinal);
        internal string? AssemblyPath;
        internal Dictionary<string,(string Key,string CadId)>? Native;
        internal bool Uncertain;
    }
    private readonly Dictionary<string,CacheEnvironment> _cacheEnvironments=new(StringComparer.Ordinal);
    private readonly Dictionary<string,(string Key,string CadId)[]> _viewerGeometry=new(StringComparer.Ordinal);

    private CacheEnvironment? FindCacheEnvironment(IVisMockupDocument document)
    {
        var process=RequireProcessIdentity();
        return _cacheEnvironments.Values.SingleOrDefault(item=>item.ProcessId==process.ProcessId
            && item.Started==process.ProcessStartUtcTicks && item.Handle==document.DocumentId
            && string.Equals(item.Path,document.SourceIdentity,StringComparison.OrdinalIgnoreCase));
    }

    private IVisMockupDocument? OpenCacheEnvironment(IVisMockupApplication application,string packagePath,
        HashSet<string> dependencies,int processId,long started)
    {
        // Legacy packages have no environment protocol and retain their existing
        // open path (including formats accepted directly by VisMockup).
        if(new FileInfo(packagePath).Length>64*1024*1024 || !File.ReadAllText(packagePath).Contains("frozen_absolute_geometry.v1",StringComparison.Ordinal))return null;
        using var reader=XmlReader.Create(packagePath,new XmlReaderSettings{DtdProcessing=DtdProcessing.Prohibit,XmlResolver=null,MaxCharactersInDocument=64*1024*1024});
        var xml=XDocument.Load(reader);
        var root=xml.Root;
        var metadata=root?.Element(CacheXml+"UserData");
        string? Meta(string name)=>metadata?.Elements(CacheXml+"UserValue").SingleOrDefault(x=>(string?)x.Attribute("title")==name)?.Attribute("value")?.Value;
        if(Meta("ai00_cache_layout")!="frozen_absolute_geometry.v1")return null;
        var environment=Meta("ai00_environment_gid");
        var name=(string?)root!.Attribute("name");
        if(environment is null || !Regex.IsMatch(environment,"^[1-9][0-9]*$") || string.IsNullOrWhiteSpace(name))
            throw new ConnectorNoEffectException("cache_environment_identity_invalid");
        var graph=root.Element(CacheXml+"ProductDef")?.Element(CacheXml+"InstanceGraph")
            ?? throw new ConnectorNoEffectException("cache_environment_graph_invalid");
        var instances=graph.Elements(CacheXml+"ProductInstance").ToDictionary(x=>(string)x.Attribute("id")!,StringComparer.Ordinal);
        var views=graph.Elements(CacheXml+"ProductRevisionView").ToDictionary(x=>(string)x.Attribute("id")!,StringComparer.Ordinal);
        var children=new Dictionary<string,string[]>(StringComparer.Ordinal);
        var geometry=new Dictionary<string,(XElement Instance,XElement View,string Signature)>(StringComparer.Ordinal);
        var transforms=new Dictionary<string,double[]>(StringComparer.Ordinal);
        foreach(var (id,instance) in instances)
        {
            var view=views.GetValueOrDefault(((string?)instance.Attribute("partRef")??"").TrimStart('#'))
                ?? throw new ConnectorNoEffectException("cache_environment_graph_invalid");
            var descendants=((string?)view.Attribute("instanceRefs")??"").Split(' ',StringSplitOptions.RemoveEmptyEntries);
            if(descendants.Any(child=>!instances.ContainsKey(child)))throw new ConnectorNoEffectException("cache_environment_graph_invalid");
            children[id]=descendants;
            if(!view.Elements(CacheXml+"Representation").Any())continue;
            if(descendants.Length!=0)throw new ConnectorNoEffectException("cache_environment_geometry_invalid");
            var values=(instance.Element(CacheXml+"Transform")?.Value??"").Split((char[]?)null,StringSplitOptions.RemoveEmptyEntries);
            var matrix=new double[values.Length];
            for(var i=0;i<values.Length;i++)
                if(!double.TryParse(values[i],System.Globalization.NumberStyles.Float,System.Globalization.CultureInfo.InvariantCulture,out matrix[i]))
                    throw new ConnectorNoEffectException("cache_environment_transform_invalid");
            if(!ValidEnvironmentTransform(matrix))throw new ConnectorNoEffectException("cache_environment_transform_invalid");
            transforms[id]=matrix;
            // Compare the verified content and world transform before rewriting
            // local paths: retries live in different temporary plan directories.
            var signature=instance.ToString(SaveOptions.DisableFormatting)+view.ToString(SaveOptions.DisableFormatting);
            var nativeView=new XElement(view);
            foreach(var representation in nativeView.Elements(CacheXml+"Representation"))
            {
                var location=(string?)representation.Attribute("location")??"";
                if(!dependencies.Contains(location))throw new ConnectorNoEffectException("cache_environment_dependency_invalid");
                representation.SetAttributeValue("location",System.IO.Path.GetFullPath(System.IO.Path.Combine(System.IO.Path.GetDirectoryName(packagePath)!,location)));
            }
            var user=nativeView.Element(CacheXml+"UserData");
            if(user is null){user=new XElement(CacheXml+"UserData",new XAttribute("id","native-metadata-"+id));nativeView.AddFirst(user);}
            user.Elements(CacheXml+"UserValue").Where(x=>(string?)x.Attribute("title")=="bl_occurrence_uid").Remove();
            user.Add(new XElement(CacheXml+"UserValue",new XAttribute("title","bl_occurrence_uid"),new XAttribute("value",id)));
            geometry[id]=(new XElement(instance),nativeView,signature);
        }
        // Prove acyclic before any native writes, including disconnected nodes.
        var visited=new HashSet<string>();var visiting=new HashSet<string>();
        void Visit(string id,int depth){if(depth>256||!visiting.Add(id))throw new ConnectorNoEffectException("cache_environment_graph_invalid");
            if(visited.Add(id))foreach(var child in children[id])Visit(child,depth+1);visiting.Remove(id);}
        foreach(var id in children.Keys)Visit(id,0);
        foreach(var key in _cacheEnvironments.Where(x=>x.Value.ProcessId!=processId||x.Value.Started!=started).Select(x=>x.Key).ToArray())_cacheEnvironments.Remove(key);
        _cacheEnvironments.TryGetValue(environment,out var state);
        IVisMockupDocument? document=null;
        if(state is not null)
        {
            document=application.OpenDocuments.SingleOrDefault(d=>d.DocumentId==state.Handle&&string.Equals(d.SourceIdentity,state.Path,StringComparison.OrdinalIgnoreCase));
            if(document is null){_cacheEnvironments.Remove(environment);state=null;}
            else if(state.Uncertain)throw new ConnectorNoEffectException("cache_environment_requires_reopen");
        }
        if(state is null)
        {
            // A Connector restart loses native provenance. Do not create another
            // window or adopt an unproven old one based on its human title.
            foreach(var candidate in application.OpenDocuments)
            {
                var source=candidate.SourceIdentity;
                if(!System.IO.Path.IsPathFullyQualified(source)||!source.EndsWith(".plmxml",StringComparison.OrdinalIgnoreCase)||!File.Exists(source))continue;
                if(new FileInfo(source).Length>64*1024*1024)continue;
                using var existingReader=XmlReader.Create(source,new XmlReaderSettings{DtdProcessing=DtdProcessing.Prohibit,XmlResolver=null,MaxCharactersInDocument=64*1024*1024});
                XElement? existing;
                try{existing=XDocument.Load(existingReader).Root;}catch(XmlException){continue;}
                if((string?)existing?.Attribute("author")=="AI00 environment"&&existing.Element(CacheXml+"UserData")?.Elements(CacheXml+"UserValue")
                    .Any(value=>(string?)value.Attribute("title")=="ai00_environment_gid"&&(string?)value.Attribute("value")==environment)==true)
                    throw new ConnectorNoEffectException("cache_environment_requires_reopen");
            }
        }
        if(state is not null)
            foreach(var (id,item) in geometry)
                if(state.Geometry.TryGetValue(id,out var previous)&&previous!=item.Signature)
                    throw new ConnectorNoEffectException("cache_environment_geometry_conflict");
        var additions=geometry.Where(x=>state is null||!state.Geometry.ContainsKey(x.Key)).ToArray();
        if(document is not null && application.ActiveDocument?.DocumentId!=document.DocumentId)
        {
            document.SelectExistingNativeWindow(processId);
            if(application.ActiveDocument?.DocumentId!=document.DocumentId)throw new ConnectorNoEffectException("vismockup_document_identity_changed");
        }
        if(additions.Length>0)
        {
            var parts=state is null?new Dictionary<string,(XElement Instance,XElement View)>(StringComparer.Ordinal):new(state.Parts,StringComparer.Ordinal);
            foreach(var item in additions)parts[item.Key]=(item.Value.Instance,item.Value.View);
            // Active documents may outlive the temporary JT cache. Fail before
            // changing the scene if a dependency required for replacement expired.
            if(parts.Values.SelectMany(item=>item.View.Elements(CacheXml+"Representation")).Any(item=>!File.Exists((string?)item.Attribute("location"))))
                throw new ConnectorNoEffectException("cache_environment_dependency_unavailable");
            var invalid=System.IO.Path.GetInvalidFileNameChars();
            var fileName=new string(name.Select(c=>invalid.Contains(c)?'_':c).ToArray()).Trim().TrimEnd('.');
            if(fileName.Length>100)fileName=fileName[..100];
            if(string.IsNullOrWhiteSpace(fileName)||Regex.IsMatch(fileName,@"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])($|\.)",RegexOptions.IgnoreCase))fileName="仿真环境-"+environment;
            var folder=System.IO.Path.Combine(System.IO.Path.GetDirectoryName(packagePath)!,"environment");
            Directory.CreateDirectory(folder);
            string WriteNativePackage(string suffix,string[] ids)
            {
                var nativePath=System.IO.Path.Combine(folder,fileName+suffix+".plmxml");
                var nativeGraph=new XElement(CacheXml+"InstanceGraph",new XAttribute("id","environment-graph"),new XAttribute("rootRefs",string.Join(' ',ids)));
                if(ids.Length==0)nativeGraph.Attribute("rootRefs")!.Remove();
                // VisMockup ignores a geometry root's Transform, even when it
                // is the only part. Always place geometry under an identity root.
                if(ids.Length>0)
                {
                    var rootId="environment-root-"+environment;
                    var viewId="environment-view-"+environment;
                    nativeGraph.SetAttributeValue("rootRefs",rootId);
                    nativeGraph.Add(new XElement(CacheXml+"ProductInstance",new XAttribute("id",rootId),new XAttribute("name",name),new XAttribute("partRef","#"+viewId),
                        new XElement(CacheXml+"Transform","1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1")));
                    nativeGraph.Add(new XElement(CacheXml+"ProductRevisionView",new XAttribute("id",viewId),new XAttribute("name",name),new XAttribute("instanceRefs",string.Join(' ',ids))));
                }
                foreach(var id in ids){nativeGraph.Add(new XElement(parts[id].Instance));nativeGraph.Add(new XElement(parts[id].View));}
                new XDocument(new XElement(CacheXml+"PLMXML",new XAttribute("schemaVersion","6"),new XAttribute("units","metre"),
                    new XAttribute("author","AI00 environment"),new XAttribute("name",name),new XElement(metadata!),new XElement(CacheXml+"ProductDef",new XAttribute("id","environment-product"),nativeGraph))).Save(nativePath);
                return nativePath;
            }
            InvalidateViewerStructure();
            if(document is null)
            {
                // The named document is an empty stable container. Its one
                // inserted assembly can be replaced without changing the window
                // or document session; the container adds no model-tree root.
                var containerPath=WriteNativePackage("",[]);
                document=VisMockupDocumentOpen.Open(application,containerPath,processId);
                state=new CacheEnvironment(processId,started,document.DocumentId,containerPath);
                _cacheEnvironments[environment]=state;
            }
            var previousPaths=document.InsertedDocumentPaths.ToArray();
            if(previousPaths.Length!=(state!.AssemblyPath is null?0:1)
                || (state.AssemblyPath is not null&&!string.Equals(previousPaths[0],state.AssemblyPath,StringComparison.OrdinalIgnoreCase)))
                throw new ConnectorNoEffectException("cache_environment_structure_changed");
            var previous=state.Geometry.Count==0?[]:document.GetAllNodes(32768).Select(node=>
                (Key:node.NodeKey,CadId:node.CadId,Occurrence:node.OccurrenceId,Visible:node.IsVisible)).ToArray();
            var previousKeys=previous.Select(node=>node.Key).ToHashSet(StringComparer.Ordinal);
            var hidden=previous.Where(node=>!node.Visible).ToArray();
            var hiddenIds=hidden.Select(node=>node.Occurrence).ToHashSet(StringComparer.Ordinal);
            var nativePath=WriteNativePackage("-assembly",parts.Keys.ToArray());
            var replaced=false;
            try
            {
                var expected=state!.Geometry.Keys.Concat(additions.Select(item=>item.Key)).ToHashSet(StringComparer.Ordinal);
                var expectedTransforms=new Dictionary<string,double[]>(state.Transforms,StringComparer.Ordinal);
                foreach(var item in additions)expectedTransforms[item.Key]=transforms[item.Key];
                document.InsertDocument(nativePath);
                // Validate the staged replacement before retiring the old
                // assembly. Node keys change; visibility follows occurrence IDs.
                document.SetAllNodesVisible(true);
                var native=ReadEnvironmentGeometry(document,expected,false,expectedTransforms,previousKeys);
                if(native.Count!=expected.Count)
                {
                    TraceViewer("cache_environment_insert_incomplete",new{environment_gid=environment,document_handle=document.DocumentId,expected_geometry=expected.Count,actual_geometry=native.Count});
                    throw new ConnectorException("cache_environment_insert_incomplete");
                }
                document.SetNodesVisible(native.Where(item=>hiddenIds.Contains(item.Key)).Select(item=>item.Value.Key).ToArray(),false);
                if(previousPaths.Length==1)document.DeleteInsertedDocument(0);
                replaced=true;
                if(document.InsertedDocumentPaths.Count!=1||!string.Equals(document.InsertedDocumentPaths[0],nativePath,StringComparison.OrdinalIgnoreCase))
                    throw new ConnectorException("cache_environment_structure_changed");
                native=ReadEnvironmentGeometry(document,expected,false,expectedTransforms);
                if(native.Count!=expected.Count||native.Any(item=>hiddenIds.Contains(item.Key)&&document.FindNodeByKey(item.Value.Key).IsVisible))
                    throw new ConnectorException("cache_environment_visibility_restore_failed");
                state.Native=native;
                state.AssemblyPath=nativePath;
                foreach(var item in additions)state.Parts[item.Key]=(item.Value.Instance,item.Value.View);
                TraceViewer("cache_environment_transform_verified",new{environment_gid=environment,document_handle=document.DocumentId,verified_geometry=native.Count});
                TraceViewer("cache_environment_root_replaced",new{environment_gid=environment,document_handle=document.DocumentId,assembly_roots=1,total_geometry=native.Count});
            }
            catch(Exception error)
            {
                state!.Uncertain=true;
                if(!replaced)try
                {
                    var staged=document.InsertedDocumentPaths.ToList().FindIndex(path=>string.Equals(path,nativePath,StringComparison.OrdinalIgnoreCase));
                    if(staged>=0)document.DeleteInsertedDocument(staged);
                    foreach(var old in hidden)
                    {
                        var current=document.FindNodeByKey(old.Key);
                        if(current.CadId!=old.CadId)throw new ConnectorException("cache_environment_visibility_restore_failed");
                    }
                    document.SetNodesVisible(hidden.Select(old=>old.Key).ToArray(),false);
                    if(hidden.Any(old=>document.FindNodeByKey(old.Key).IsVisible))throw new ConnectorException("cache_environment_visibility_restore_failed");
                }
                catch(Exception rollback){TraceViewer("cache_environment_rollback_failed",new{environment_gid=environment,error_code=(rollback as ConnectorException)?.Code??rollback.GetType().Name});}
                TraceViewer("cache_environment_insert_failed",new{environment_gid=environment,document_handle=document.DocumentId,error_code=(error as ConnectorException)?.Code??error.GetType().Name});
                if(error is ConnectorException nativeError&&nativeError.Code.StartsWith("cache_environment_transform_",StringComparison.Ordinal))throw;
                throw new ConnectorException("cache_environment_insert_outcome_unknown");
            }
            foreach(var item in additions){state.Geometry.Add(item.Key,item.Value.Signature);state.Transforms.Add(item.Key,transforms[item.Key]);}
        }
        if(document is null||state is null)throw new ConnectorNoEffectException("cache_environment_geometry_empty");
        // A later parent request expands the graph. The single native assembly
        // contains each occurrence once and retains its previous visibility.
        foreach(var (id,nested) in children)state.Children[id]=state.Children.TryGetValue(id,out var old)?old.Union(nested,StringComparer.Ordinal).ToArray():nested;
        TraceViewer("cache_environment_document",new{environment_gid=environment,document_handle=document.DocumentId,inserted_geometry=additions.Length,total_geometry=state.Geometry.Count});
        return document;
    }

    private (string Key,string CadId)[] ResolveEnvironmentGeometry(CacheEnvironment state,IVisMockupDocument document,string[] path)
    {
        if(state.Uncertain)throw new ConnectorNoEffectException("cache_environment_requires_reopen");
        if(path.Length==0||path.Any(id=>!state.Children.ContainsKey(id)))throw new ConnectorNoEffectException("vismockup_online_occurrence_unmapped");
        for(var i=1;i<path.Length;i++)if(!state.Children[path[i-1]].Contains(path[i],StringComparer.Ordinal))throw new ConnectorNoEffectException("vismockup_online_occurrence_unmapped");
        var desired=new HashSet<string>(StringComparer.Ordinal);var seen=new HashSet<string>();var pending=new Stack<string>();pending.Push(path[^1]);
        while(pending.TryPop(out var id))
        {
            if(!seen.Add(id))continue;
            if(state.Geometry.ContainsKey(id))desired.Add(id);
            foreach(var child in state.Children[id])pending.Push(child);
        }
        if(desired.Count==0)throw new ConnectorNoEffectException("vismockup_online_occurrence_unmapped");
        state.Native??=ReadEnvironmentGeometry(document,state.Geometry.Keys.ToHashSet(StringComparer.Ordinal),true);
        return desired.Select(id=>state.Native.TryGetValue(id,out var found)?found:throw new ConnectorNoEffectException("vismockup_online_occurrence_unmapped")).ToArray();
    }

    private static bool ValidEnvironmentTransform(IReadOnlyList<double> matrix)=>matrix.Count==16&&matrix.All(double.IsFinite)
        &&Math.Abs(matrix[3])<1e-8&&Math.Abs(matrix[7])<1e-8&&Math.Abs(matrix[11])<1e-8&&Math.Abs(matrix[15]-1)<1e-8;

    private Dictionary<string,(string Key,string CadId)> ReadEnvironmentGeometry(IVisMockupDocument document,HashSet<string> expected,bool interaction,IReadOnlyDictionary<string,double[]>? transforms=null,HashSet<string>? ignoredKeys=null)
    {
            var index=new Dictionary<string,(string Key,string CadId)>(StringComparer.Ordinal);
            var watch=System.Diagnostics.Stopwatch.StartNew();
            foreach(var node in document.GetAllNodes(32768))
            {
                if(ignoredKeys?.Contains(node.NodeKey)==true)continue;
                if(interaction)RequireViewerAdmission();
                if(watch.ElapsedMilliseconds>20000)throw new ConnectorNoEffectException("viewer_mapping_budget_exceeded");
                var occurrence=node.OccurrenceId;
                if(!expected.Contains(occurrence))continue;
                if(string.IsNullOrWhiteSpace(node.CadId))throw new ConnectorNoEffectException("viewer_instance_identity_unavailable");
                if(!index.TryAdd(occurrence,(node.NodeKey,node.CadId)))throw new ConnectorNoEffectException("vismockup_online_occurrence_ambiguous");
                if(transforms is not null)
                {
                    IReadOnlyList<double> actual;
                    try{actual=node.GlobalTransform;}
                    catch(Exception error)
                    {
                        TraceViewer("cache_environment_transform_unavailable",new{document_handle=document.DocumentId,occurrence_id=occurrence,error_code=(error as ConnectorException)?.Code??error.GetType().Name});
                        throw new ConnectorException("cache_environment_transform_unavailable");
                    }
                    var desired=transforms[occurrence];
                    if(!ValidEnvironmentTransform(actual)||desired.Where((value,i)=>Math.Abs(value-actual[i])>1e-8).Any())
                    {
                        TraceViewer("cache_environment_transform_mismatch",new{document_handle=document.DocumentId,occurrence_id=occurrence,expected=desired,actual});
                        throw new ConnectorException("cache_environment_transform_mismatch");
                    }
                }
            }
            return index;
    }
}
