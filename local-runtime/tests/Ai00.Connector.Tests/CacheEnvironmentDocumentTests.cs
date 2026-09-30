using System.Text.Json;
using System.Security.Cryptography;
using System.Xml.Linq;
using Ai00.Connector.Adapters.VisMockup;
using Ai00.Connector.Contracts;
using Ai00.Connector.Contracts.V2;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class CacheEnvironmentDocumentTests : IDisposable
{
    readonly string folder=Path.Combine(Path.GetTempPath(),"cache-env-"+Guid.NewGuid().ToString("N"));
    static readonly XNamespace ns="http://www.plmxml.org/Schemas/PLMXMLSchema";
    static JsonElement Json(object value)=>JsonSerializer.SerializeToElement(value);
    static object Ref(string path,string media)=>new{artifact_id="a"+Path.GetFileNameWithoutExtension(path),media_type=media,
        sha256=Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant(),byte_size=new FileInfo(path).Length,version=1};
    JsonElement Package(string environment,string name,bool parent=false)
    {
        var path=Path.Combine(folder,Guid.NewGuid().ToString("N"));Directory.CreateDirectory(Path.Combine(path,"dependencies"));
        var jt=Path.Combine(path,"dependencies","part.jt");File.WriteAllText(jt,"verified-geometry");
        var roots=parent?"P":"A";
        var graph=new XElement(ns+"InstanceGraph",new XAttribute("id","graph"),new XAttribute("rootRefs",roots));
        foreach(var (id,children,geometry) in parent?new[]{("P","A B",false),("A","GA",false),("B","GB",false),("GA","",true),("GB","",true)}:new[]{("A","GA",false),("GA","",true)})
        {
            graph.Add(new XElement(ns+"ProductInstance",new XAttribute("id",id),new XAttribute("name",id),new XAttribute("partRef","#v"+id),
                new XElement(ns+"UserData",new XElement(ns+"UserValue",new XAttribute("title","bl_occurrence_uid"),new XAttribute("value",id))),
                new XElement(ns+"Transform",id=="GA"?"1 0 0 0 0 1 0 0 0 0 1 0 0.0635 0.311 0.33 1":id=="GB"?"0 1 0 0 -1 0 0 0 0 0 1 0 2.9 -0.4 0.23 1":"1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1")));
            var view=new XElement(ns+"ProductRevisionView",new XAttribute("id","v"+id),new XAttribute("name",id));
            if(children!="")view.SetAttributeValue("instanceRefs",children);
            if(geometry)view.Add(new XElement(ns+"Representation",new XAttribute("format","JT"),new XAttribute("location","dependencies/part.jt")));
            graph.Add(view);
        }
        var xml=new XElement(ns+"PLMXML",new XAttribute("name",name),new XElement(ns+"UserData",
            new XElement(ns+"UserValue",new XAttribute("title","ai00_environment_gid"),new XAttribute("value",environment)),
            new XElement(ns+"UserValue",new XAttribute("title","ai00_cache_layout"),new XAttribute("value","frozen_absolute_geometry.v1"))),new XElement(ns+"ProductDef",graph));
        var top=Path.Combine(path,"environment.plmxml");xml.Save(top);
        var packet=new{artifact_ref=Ref(top,"application/vnd.siemens.plmxml+xml"),package_dependencies=new[]{new{package_path="dependencies/part.jt",artifact_ref=Ref(jt,"model/jt")}},cache_binding=new{batch_id=new string('a',32),generation=(string?)null,snapshot_hash=(string?)null,schema_version=1}};
        var values=JsonSerializer.Deserialize<Dictionary<string,object>>(Json(packet))!;
        values["package_hash"]=CanonicalJsonV2.Hash(Json(packet));values["local_artifact_path"]=top;
        return Json(values);
    }

    internal static FakeApplication Application()
    {
        var app=new FakeApplication("14",null);
        app.DocumentFactory=path=>{
            var doc=new FakeDocument(path,path,new FakeNode("root","environment","","",[]){CadId="root"});
            var loaded=new Dictionary<string,List<string>>();var sequence=0;
            void Load(string file){var xml=XDocument.Load(file);foreach(var view in xml.Descendants(ns+"ProductRevisionView").Where(v=>v.Elements(ns+"Representation").Any())){
                var id=(string)view.Element(ns+"UserData")!.Elements(ns+"UserValue").Single(p=>(string?)p.Attribute("title")=="bl_occurrence_uid").Attribute("value")!;
                var key=(++sequence)+":"+id;
                if(!loaded.ContainsKey(file))loaded[file]=[];
                loaded[file].Add(key);
                var graph=xml.Descendants(ns+"InstanceGraph").Single();
                var instance=graph.Elements(ns+"ProductInstance").Single(x=>(string?)x.Attribute("id")==id);
                // Reproduce VisMockup: placement on a geometry root is ignored.
                var matrix=(string?)graph.Attribute("rootRefs")==id
                    ? new double[]{.001,0,0,0,0,.001,0,0,0,0,.001,0,0,0,0,1}
                    :instance.Element(ns+"Transform")!.Value.Split(' ').Select(x=>double.Parse(x,System.Globalization.CultureInfo.InvariantCulture)).ToArray();
                doc.RuntimeNodes[key]=new FakeNode(key,id,id,"same-revision",[]){CadId="cad:"+key,GlobalTransform=matrix};
            }}
            // Legacy exporter does not provide root view metadata, but should
            // still reach the document-count assertion before the fix.
            if(XDocument.Load(path).Root?.Attribute("author")?.Value=="AI00 environment")Load(path);
            doc.AfterInsertDocument=file=>{
                // A positioned inserted hierarchy is registered before its
                // geometry appears in AllNodes. Native loading is explicit.
                doc.AfterAllNodesVisibilityWrite=()=>{Load(file);doc.AfterAllNodesVisibilityWrite=null;};
            };
            doc.AfterDeleteInsertedDocument=file=>{foreach(var key in loaded.GetValueOrDefault(file,[]))doc.RuntimeNodes.Remove(key);loaded.Remove(file);};
            return doc;
        };
        return app;
    }
    static FakeNode Node(FakeDocument doc,string id)=>(FakeNode)doc.RuntimeNodes.Values.Single(node=>node.OccurrenceId==id);
    static string Key(FakeDocument doc,string id)=>Node(doc,id).NodeKey;
    [Fact]
    public async Task Environment_container_has_one_replaceable_assembly_after_each_expansion()
    {
        using var sta=new StaDispatcher();var app=Application();
        var adapter=new VisMockupAdapter(sta,new AllowedPathPolicy([folder]),new FakeVisMockupCom{ExistingApplication=app,ProcessId=123,ProcessStartUtcTicks=456});
        await adapter.OpenManagedCacheAsync(Package("10","W10"),default);
        var doc=app.LastOpenedDocument!;
        Assert.Single(doc.InsertedDocumentPaths);
        var baseGraph=XDocument.Load(doc.SourceIdentity).Descendants(ns+"InstanceGraph").Single();
        Assert.Empty(baseGraph.Elements());
        await adapter.OpenManagedCacheAsync(Package("10","W10",true),default);
        var graph=XDocument.Load(Assert.Single(doc.InsertedDocumentPaths)).Descendants(ns+"InstanceGraph").Single();
        Assert.Single(((string)graph.Attribute("rootRefs")!).Split(' '));
        Assert.Equal(2,graph.Descendants(ns+"Representation").Count());
        Assert.Equal(1,app.OpenCalls);
    }
    [Fact]
    public async Task Expired_previous_JT_does_not_change_the_existing_environment()
    {
        using var sta=new StaDispatcher();var app=Application();
        var adapter=new VisMockupAdapter(sta,new AllowedPathPolicy([folder]),new FakeVisMockupCom{ExistingApplication=app,ProcessId=123,ProcessStartUtcTicks=456});
        await adapter.OpenManagedCacheAsync(Package("10","W10"),default);
        var doc=app.LastOpenedDocument!;var assembly=Assert.Single(doc.InsertedDocumentPaths);
        var jt=(string)XDocument.Load(assembly).Descendants(ns+"Representation").Single().Attribute("location")!;
        File.Delete(jt);
        var error=await Assert.ThrowsAsync<ConnectorNoEffectException>(()=>adapter.OpenManagedCacheAsync(Package("10","W10",true),default));
        Assert.Equal("cache_environment_dependency_unavailable",error.Code);
        Assert.Equal(assembly,Assert.Single(doc.InsertedDocumentPaths));Assert.Equal(1,doc.InsertDocumentCalls);
        Assert.Equal(.0635,Node(doc,"GA").GlobalTransform[12]);
    }
    [Fact]
    public async Task Unmanaged_insert_is_never_removed_by_environment_replacement()
    {
        using var sta=new StaDispatcher();var app=Application();
        var adapter=new VisMockupAdapter(sta,new AllowedPathPolicy([folder]),new FakeVisMockupCom{ExistingApplication=app,ProcessId=123,ProcessStartUtcTicks=456});
        await adapter.OpenManagedCacheAsync(Package("10","W10"),default);
        var doc=app.LastOpenedDocument!;doc.AfterInsertDocument=null;doc.InsertDocument(Path.Combine(folder,"external.jt"));
        var error=await Assert.ThrowsAsync<ConnectorNoEffectException>(()=>adapter.OpenManagedCacheAsync(Package("10","W10",true),default));
        Assert.Equal("cache_environment_structure_changed",error.Code);Assert.Equal(2,doc.InsertedDocumentPaths.Count);Assert.Equal(2,doc.InsertDocumentCalls);
    }
    [Fact]
    public async Task Parent_after_part_reuses_environment_and_does_not_duplicate_geometry()
    {
        using var sta=new StaDispatcher();
        var app=Application();
        var adapter=new VisMockupAdapter(sta,new AllowedPathPolicy([folder]),new FakeVisMockupCom{ExistingApplication=app,ProcessId=123,ProcessStartUtcTicks=456}){ViewerInteractionAdmissionAllowed=()=>true};
        var a=await adapter.OpenManagedCacheAsync(Package("10","W10 test2"),default);
        app.LastOpenedDocument!.SetNodeVisible(Key(app.LastOpenedDocument,"GA"),false);
        var p=await adapter.OpenManagedCacheAsync(Package("10","W10 test2",true),default);
        Assert.Equal(1,app.OpenCalls);
        Assert.Equal(Json(a).GetProperty("document_identity").GetProperty("document_handle").GetString(),Json(p).GetProperty("document_identity").GetProperty("document_handle").GetString());
        Assert.Equal("W10 test2.plmxml",Path.GetFileName(app.LastOpenedDocument!.SourceIdentity));
        Assert.Equal(2,app.LastOpenedDocument.InsertDocumentCalls);
        Assert.Equal(new[]{"GA","GB"},app.LastOpenedDocument.RuntimeNodes.Values.Select(n=>n.OccurrenceId).Where(id=>id!="").Order().ToArray());
        Assert.False(((FakeNode)Node(app.LastOpenedDocument,"GA")).IsVisible);
        Assert.Equal(new double[]{.0635,.311,.33},Node(app.LastOpenedDocument,"GA").GlobalTransform.Skip(12).Take(3));
        Assert.Equal(new double[]{0,1,0,0,-1,0,0,0,0,0,1,0,2.9,-.4,.23,1},Node(app.LastOpenedDocument,"GB").GlobalTransform);
        var session=Json(p).GetProperty("document_identity").GetProperty("document_session").GetString()!;
        var descriptors=Json(new[]{new{source_node_id="assembly",kind="occurrence_path",occurrence_path=new[]{new{occurrence_uid="P",item_revision_uid="r"}}},
            new{source_node_id="part",kind="occurrence_path",occurrence_path=new[]{new{occurrence_uid="P",item_revision_uid="r"},new{occurrence_uid="A",item_revision_uid="r"}}}});
        var mapped=Json(await adapter.ResolveViewerNodesAsync("environment",session,descriptors));
        Assert.All(mapped.GetProperty("nodes").EnumerateArray(),node=>Assert.Equal("mapped",node.GetProperty("status").GetString()));
        var epoch=mapped.GetProperty("structure_epoch").GetInt64();
        var assembly=mapped.GetProperty("nodes")[0].GetProperty("node_ref").GetString()!;
        var part=mapped.GetProperty("nodes")[1].GetProperty("node_ref").GetString()!;
        app.LastOpenedDocument.BatchVisibilityWrites.Clear();
        await adapter.ExecuteViewerNodeAsync("environment",session,epoch,assembly,"vismockup.node.visibility.change@1",Json(new{action="show"}));
        var batch=Assert.Single(app.LastOpenedDocument.BatchVisibilityWrites);
        Assert.True(batch.Visible);Assert.Equal(new[]{Key(app.LastOpenedDocument,"GA"),Key(app.LastOpenedDocument,"GB")}.Order(),batch.Keys.Order());
        Assert.True(Node(app.LastOpenedDocument,"GA").IsVisible);Assert.True(Node(app.LastOpenedDocument,"GB").IsVisible);
        app.LastOpenedDocument.BatchVisibilityWrites.Clear();
        await adapter.ExecuteViewerNodeAsync("environment",session,epoch,assembly,"vismockup.node.visibility.change@1",Json(new{action="hide"}));
        batch=Assert.Single(app.LastOpenedDocument.BatchVisibilityWrites);
        Assert.False(batch.Visible);Assert.Equal(2,batch.Keys.Length);
        Assert.False(Node(app.LastOpenedDocument,"GA").IsVisible);Assert.False(Node(app.LastOpenedDocument,"GB").IsVisible);
        await adapter.ExecuteViewerNodeAsync("environment",session,epoch,assembly,"vismockup.node.visibility.change@1",Json(new{action="show"}));
        app.LastOpenedDocument.BatchVisibilityWrites.Clear();
        await adapter.ExecuteViewerNodeAsync("environment",session,epoch,part,"vismockup.node.visibility.change@1",Json(new{action="hide"}));
        Assert.Equal(new[]{Key(app.LastOpenedDocument,"GA")},Assert.Single(app.LastOpenedDocument.BatchVisibilityWrites).Keys);
        Assert.False(Node(app.LastOpenedDocument,"GA").IsVisible);Assert.True(Node(app.LastOpenedDocument,"GB").IsVisible);
        mapped=Json(await adapter.ResolveViewerNodesAsync("environment",session,descriptors));
        Assert.Equal("mixed",mapped.GetProperty("nodes")[0].GetProperty("visibility_state").GetString());
        Assert.Equal("hidden",mapped.GetProperty("nodes")[1].GetProperty("visibility_state").GetString());
        await adapter.OpenManagedCacheAsync(Package("10","W10 test2",true),default);
        Assert.Equal(1,app.OpenCalls);Assert.Equal(2,app.LastOpenedDocument.InsertDocumentCalls);
        Assert.False(Node(app.LastOpenedDocument,"GA").IsVisible);Assert.True(Node(app.LastOpenedDocument,"GB").IsVisible);
        await adapter.OpenManagedCacheAsync(Package("20","Other environment"),default);
        Assert.Equal(2,app.OpenCalls);
    }
    [Theory]
    [InlineData("W10 / test:2","W10 _ test_2.plmxml")]
    [InlineData("CON","仿真环境-10.plmxml")]
    public async Task Environment_name_is_a_safe_label_not_document_identity(string name,string expected)
    {
        using var sta=new StaDispatcher();var app=Application();
        var adapter=new VisMockupAdapter(sta,new AllowedPathPolicy([folder]),new FakeVisMockupCom{ExistingApplication=app,ProcessId=123,ProcessStartUtcTicks=456});
        await adapter.OpenManagedCacheAsync(Package("10",name),default);
        Assert.Equal(expected,Path.GetFileName(app.LastOpenedDocument!.SourceIdentity));
        var restarted=new VisMockupAdapter(sta,new AllowedPathPolicy([folder]),new FakeVisMockupCom{ExistingApplication=app,ProcessId=123,ProcessStartUtcTicks=456});
        var error=await Assert.ThrowsAsync<ConnectorNoEffectException>(()=>restarted.OpenManagedCacheAsync(Package("10",name),default));
        Assert.Equal("cache_environment_requires_reopen",error.Code);Assert.Equal(1,app.OpenCalls);
    }
    [Fact]
    public async Task Registered_insert_without_geometry_cannot_report_success_or_be_replayed()
    {
        using var sta=new StaDispatcher();var app=Application();
        var adapter=new VisMockupAdapter(sta,new AllowedPathPolicy([folder]),new FakeVisMockupCom{ExistingApplication=app,ProcessId=123,ProcessStartUtcTicks=456});
        await adapter.OpenManagedCacheAsync(Package("10","W10"),default);
        app.LastOpenedDocument!.AfterInsertDocument=_=>{};
        var error=await Assert.ThrowsAsync<ConnectorException>(()=>adapter.OpenManagedCacheAsync(Package("10","W10",true),default));
        Assert.Equal("cache_environment_insert_outcome_unknown",error.Code);
        var again=await Assert.ThrowsAsync<ConnectorNoEffectException>(()=>adapter.OpenManagedCacheAsync(Package("10","W10",true),default));
        Assert.Equal("cache_environment_requires_reopen",again.Code);
        Assert.Equal(1,app.OpenCalls);Assert.Equal(2,app.LastOpenedDocument.InsertDocumentCalls);
    }
    [Fact]
    public async Task Single_part_keeps_world_position_and_bad_native_placement_blocks_success()
    {
        using var sta=new StaDispatcher();var app=Application();
        var adapter=new VisMockupAdapter(sta,new AllowedPathPolicy([folder]),new FakeVisMockupCom{ExistingApplication=app,ProcessId=123,ProcessStartUtcTicks=456});
        await adapter.OpenManagedCacheAsync(Package("10","W10"),default);
        var doc=app.LastOpenedDocument!;
        Assert.Equal(new double[]{.0635,.311,.33},Node(doc,"GA").GlobalTransform.Skip(12).Take(3));
        doc.SetNodeVisible(Key(doc,"GA"),false);
        var load=doc.AfterInsertDocument;
        doc.AfterInsertDocument=file=>{
            load!(file);var activate=doc.AfterAllNodesVisibilityWrite;
            doc.AfterAllNodesVisibilityWrite=()=>{activate!();((FakeNode)Node(doc,"GB")).GlobalTransform=new double[]{1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1};};
        };
        var error=await Assert.ThrowsAsync<ConnectorException>(()=>adapter.OpenManagedCacheAsync(Package("10","W10",true),default));
        Assert.Equal("cache_environment_transform_mismatch",error.Code);
        Assert.False(Node(doc,"GA").IsVisible);
        var again=await Assert.ThrowsAsync<ConnectorNoEffectException>(()=>adapter.OpenManagedCacheAsync(Package("10","W10",true),default));
        Assert.Equal("cache_environment_requires_reopen",again.Code);
    }
    [Fact]
    public async Task Activation_failure_restores_existing_hidden_geometry_and_requires_reopen()
    {
        using var sta=new StaDispatcher();var app=Application();
        var adapter=new VisMockupAdapter(sta,new AllowedPathPolicy([folder]),new FakeVisMockupCom{ExistingApplication=app,ProcessId=123,ProcessStartUtcTicks=456});
        await adapter.OpenManagedCacheAsync(Package("10","W10"),default);
        var doc=app.LastOpenedDocument!;doc.SetNodeVisible(Key(doc,"GA"),false);
        doc.SetAllNodesVisibleError=new InvalidOperationException("load failed after effect");
        var error=await Assert.ThrowsAsync<ConnectorException>(()=>adapter.OpenManagedCacheAsync(Package("10","W10",true),default));
        Assert.Equal("cache_environment_insert_outcome_unknown",error.Code);
        Assert.False(Node(doc,"GA").IsVisible);
        Assert.Equal(1,app.OpenCalls);
    }
    [Fact]
    public async Task First_assembly_open_has_one_root_and_later_part_does_not_insert_again()
    {
        using var sta=new StaDispatcher();var app=Application();
        var adapter=new VisMockupAdapter(sta,new AllowedPathPolicy([folder]),new FakeVisMockupCom{ExistingApplication=app,ProcessId=123,ProcessStartUtcTicks=456});
        await adapter.OpenManagedCacheAsync(Package("10","W10",true),default);
        var graph=XDocument.Load(Assert.Single(app.LastOpenedDocument!.InsertedDocumentPaths)).Descendants(ns+"InstanceGraph").Single();
        var root=(string)graph.Attribute("rootRefs")!;
        Assert.DoesNotContain(' ',root);
        Assert.Contains(graph.Elements(ns+"ProductRevisionView"),view=>(string?)view.Attribute("instanceRefs")=="GA GB");
        await adapter.OpenManagedCacheAsync(Package("10","W10"),default);
        Assert.Equal(1,app.OpenCalls);Assert.Equal(1,app.LastOpenedDocument.InsertDocumentCalls);
        Assert.Equal(new[]{"GA","GB"},app.LastOpenedDocument.RuntimeNodes.Values.Select(n=>n.OccurrenceId).Where(id=>id!="").Order().ToArray());
    }
    public void Dispose(){if(Directory.Exists(folder))Directory.Delete(folder,true);}
}
