using System.Text.Json;
using Ai00.Connector.Adapters.VisMockup;
using Ai00.Connector.Contracts;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class ViewerNodeRegistryTests : IDisposable
{
    readonly string root = Path.Combine(Path.GetTempPath(), "ai00-viewer-map-" + Guid.NewGuid().ToString("N"));
    readonly StaDispatcher sta = new();
    static JsonElement Json(object value) => JsonSerializer.SerializeToElement(value);
    static string Session(string handle) => CanonicalJson.Hash(new { process_id=123,
        process_started_utc_ticks="456", document_handle=handle });

    [Theory]
    [InlineData(true, true, "visible", true)]
    [InlineData(false, false, "hidden", false)]
    [InlineData(true, false, "mixed", null)]
    public async Task Resolution_reports_subtree_visibility_without_writing(bool parentVisible, bool childVisible, string state, bool? visible)
    {
        var child = new CountingNode("child", "child") { Visible = childVisible };
        var tree = new CountingNode("root", "", child) { Visible = parentVisible };
        var (adapter, _, document) = CreateAdapter(tree);
        var result = Json(await adapter.ResolveViewerNodesAsync("source-1", Session("doc"),
            Json(new[] { new { source_node_id = "root", kind = "document_root" } })));
        var node = result.GetProperty("nodes")[0];
        Assert.Equal("mapped", node.GetProperty("status").GetString());
        Assert.Equal(state, node.GetProperty("visibility_state").GetString());
        Assert.Equal(visible, node.GetProperty("visible").Deserialize<bool?>());
        Assert.Empty(document.VisibilityChanges);
        Assert.Equal(0, document.SetNodeVisibleCalls + document.SetNodeSelectedCalls);
    }

    [Fact]
    public async Task Cached_resolution_reads_visibility_again_and_unknown_never_becomes_checked()
    {
        var leaf = new CountingNode("root", "") { Visible = true };
        var (adapter, _, document) = CreateAdapter(leaf);
        var descriptors = Json(new[] { new { source_node_id = "root", kind = "document_root" } });
        var first = Json(await adapter.ResolveViewerNodesAsync("source-1", Session("doc"), descriptors)).GetProperty("nodes")[0];
        Assert.Equal("visible", first.GetProperty("visibility_state").GetString());
        leaf.Visible = false;
        var second = Json(await adapter.ResolveViewerNodesAsync("source-1", Session("doc"), descriptors)).GetProperty("nodes")[0];
        Assert.Equal(first.GetProperty("node_ref").GetString(), second.GetProperty("node_ref").GetString());
        Assert.Equal("hidden", second.GetProperty("visibility_state").GetString());
        leaf.VisibilityError = new InvalidOperationException("native read failed");
        var failed = Json(await adapter.ResolveViewerNodesAsync("source-1", Session("doc"), descriptors)).GetProperty("nodes")[0];
        Assert.Equal("unknown", failed.GetProperty("visibility_state").GetString());
        Assert.Equal(JsonValueKind.Null, failed.GetProperty("visible").ValueKind);
        Assert.Equal(0, document.SetNodeVisibleCalls + document.SetNodeSelectedCalls);
    }

    [Fact]
    public async Task Visibility_budget_does_not_prevent_later_target_mapping_or_assert_full_visibility()
    {
        var target = new CountingNode("target", "target") { Visible = true };
        var others = Enumerable.Range(1, 513).Select(i => new CountingNode("other" + i, "other" + i)).ToArray();
        var wide = new CountingNode("wide", "wide", others) { Visible = true };
        var tree = new CountingNode("root", "", wide, target) { Visible = true };
        var (adapter, _, _) = CreateAdapter(tree);
        wide.Reset();
        var result = Json(await adapter.ResolveViewerNodesAsync("source-1", Session("doc"), Json(new object[]
        {
            new { source_node_id = "root", kind = "document_root" }, Occurrence("target", "target")
        })));
        Assert.All(result.GetProperty("nodes").EnumerateArray(), node => Assert.Equal("mapped", node.GetProperty("status").GetString()));
        Assert.Equal("unknown", result.GetProperty("nodes")[0].GetProperty("visibility_state").GetString());
        Assert.Equal(JsonValueKind.Null, result.GetProperty("nodes")[0].GetProperty("visible").ValueKind);
        Assert.Equal("visible", result.GetProperty("nodes")[1].GetProperty("visibility_state").GetString());
        Assert.Equal(0, wide.ChildrenReads);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Visibility_calibration_stops_on_revoked_admission_or_document_change(bool changeDocument)
    {
        var tree = new CountingNode("root", "", new CountingNode("child", ""));
        var (adapter, app, document) = CreateAdapter(tree);
        tree.AfterChildrenRead = () =>
        {
            if (changeDocument) app.ActiveDocument = new FakeDocument("other", "other", tree);
            else adapter.ViewerInteractionAdmissionAllowed = () => false;
        };
        var error = await Assert.ThrowsAsync<ConnectorNoEffectException>(() => adapter.ResolveViewerNodesAsync("source-1", Session("doc"),
            Json(new[] { new { source_node_id = "root", kind = "document_root" } })));
        Assert.Equal(changeDocument ? "document_session_changed" : "viewer_authorization_required", error.Code);
        Assert.Empty(document.VisibilityChanges);
        Assert.Equal(0, document.SetNodeVisibleCalls + document.SetNodeSelectedCalls);
    }

    [Fact]
    public async Task Document_root_hide_clears_siblings_once_and_later_child_show_preserves_other_branches()
    {
        var left = new CountingNode("left", "left");
        var right = new CountingNode("right", "right");
        var tree = new CountingNode("root", "", left, right);
        var (adapter, _, document) = CreateAdapter(tree);
        document.SetNodeVisible("left", true);
        document.SetNodeVisible("right", true);
        var mapped = Json(await adapter.ResolveViewerNodesAsync("source-1", Session("doc"), Json(new object[]
        {
            new { source_node_id = "document", kind = "document_root" },
            Occurrence("L", "left"), Occurrence("R", "right")
        })));
        tree.Reset(); left.Reset(); right.Reset();
        var events = new List<(string Stage, JsonElement Detail)>();
        adapter.ViewerDiagnostic = (stage, detail) => events.Add((stage, Json(detail)));
        var initialWrites = document.SetNodeVisibleCalls;

        await Act(adapter, mapped, "hide");
        Assert.Equal(new[] { false }, document.VisibilityChanges);
        Assert.Empty(document.VisibleNodeKeys);
        Assert.Equal(initialWrites, document.SetNodeVisibleCalls);
        Assert.Contains(events, entry => entry.Stage == "visibility_readback"
            && entry.Detail.GetProperty("scope").GetString() == "document"
            && entry.Detail.GetProperty("verification_scope").GetString() == "root_flag");

        async Task ActChild(int index, string action) => await adapter.ExecuteViewerNodeAsync("source-1", Session("doc"),
            mapped.GetProperty("structure_epoch").GetInt64(), mapped.GetProperty("nodes")[index].GetProperty("node_ref").GetString()!,
            "vismockup.node.visibility.change@1", Json(new { action }));
        await ActChild(1, "show");
        Assert.True(document.IsNodeVisible("left"));
        Assert.False(document.IsNodeVisible("right"));
        await ActChild(2, "show");
        await ActChild(1, "hide");
        Assert.False(document.IsNodeVisible("left"));
        Assert.True(document.IsNodeVisible("right"));
        Assert.Single(document.VisibilityChanges);
        Assert.Equal(0, tree.ChildrenReads + tree.OccurrenceReads + left.ChildrenReads + left.OccurrenceReads + right.ChildrenReads + right.OccurrenceReads);
    }

    [Theory]
    [InlineData("exception")]
    [InlineData("session")]
    [InlineData("readback")]
    public async Task Document_root_hide_failure_after_write_is_unknown(string failure)
    {
        var (adapter, app, document) = CreateAdapter(new CountingNode("root", "", new CountingNode("child", "")));
        var mapped = Json(await adapter.ResolveViewerNodesAsync("source-1", Session("doc"),
            Json(new[] { new { source_node_id = "root", kind = "document_root" } })));
        if (failure == "exception") document.SetAllNodesVisibleError = new ConnectorNoEffectException("native_all_off_failed");
        if (failure == "session") document.AfterAllNodesVisibilityWrite = () => app.ActiveDocument = new FakeDocument("other", "other", new CountingNode("root", ""));
        if (failure == "readback") document.AfterAllNodesVisibilityWrite = () => document.SetNodeVisible("root", true);
        Assert.Equal("viewer_outcome_unknown", (await Assert.ThrowsAsync<ConnectorException>(() => Act(adapter, mapped, "hide"))).Code);
        Assert.Equal(new[] { false }, document.VisibilityChanges);
    }

    [Theory]
    [InlineData(1)]
    [InlineData(2)]
    [InlineData(513)]
    public async Task Document_root_controls_actual_assembly_root_without_writing_siblings(int childCount)
    {
        var children = Enumerable.Range(1, childCount).Select(i => new CountingNode(i.ToString(), "child" + i)).ToArray();
        var tree = new CountingNode("root", "", children);
        var (adapter, _, document) = CreateAdapter(tree);
        tree.Reset();
        foreach (var child in children) child.Reset();
        var mapped = Json(await adapter.ResolveViewerNodesAsync("source-1", Session("doc"),
            Json(new[] { new { source_node_id = "assembly", kind = "document_root" } })));

        Assert.Equal("mapped", mapped.GetProperty("nodes")[0].GetProperty("status").GetString());
        tree.Reset();
        foreach (var child in children) child.Reset();
        await Act(adapter, mapped, "show");
        await Act(adapter, mapped, "highlight");
        Assert.True(document.IsNodeVisible("root"));
        Assert.Equal("root", Assert.Single(document.SelectedNodeKeys));
        Assert.Equal(1, document.SetNodeVisibleCalls);
        Assert.Equal(1, document.SetNodeSelectedCalls);
        Assert.Equal(0, tree.ChildrenReads + tree.OccurrenceReads);
        Assert.All(children, child => Assert.Equal(0, child.ChildrenReads + child.OccurrenceReads));
    }

    [Fact]
    public async Task Document_root_remains_bound_to_authorized_session_and_single_part_stays_leaf_only()
    {
        var tree = new CountingNode("root", "", new CountingNode("left", ""), new CountingNode("right", ""));
        var (adapter, app, document) = CreateAdapter(tree);
        var descriptors = Json(new[] { new { source_node_id = "assembly", kind = "document_root" } });
        var mapped = Json(await adapter.ResolveViewerNodesAsync("source-1", Session("doc"), descriptors));
        Assert.Equal("mapped", mapped.GetProperty("nodes")[0].GetProperty("status").GetString());
        var leaf = Json(await adapter.ResolveViewerNodesAsync("source-1", Session("doc"),
            Json(new[] { new { source_node_id = "leaf", kind = "single_part_root" } })));
        Assert.Equal("viewer_single_part_required", leaf.GetProperty("nodes")[0].GetProperty("error_code").GetString());
        adapter.ViewerInteractionAdmissionAllowed = () => false;
        Assert.Equal("viewer_authorization_required", (await Assert.ThrowsAsync<ConnectorNoEffectException>(
            () => adapter.ResolveViewerNodesAsync("source-1", Session("doc"), descriptors))).Code);
        await Assert.ThrowsAsync<ConnectorNoEffectException>(() => Act(adapter, mapped, "show"));
        adapter.ViewerInteractionAdmissionAllowed = () => true;
        app.ActiveDocument = new FakeDocument("other", "tc://other", tree);
        Assert.Equal("document_session_changed", (await Assert.ThrowsAsync<ConnectorNoEffectException>(
            () => adapter.ResolveViewerNodesAsync("source-1", Session("doc"), descriptors))).Code);
        await Assert.ThrowsAsync<ConnectorNoEffectException>(() => Act(adapter, mapped, "show"));
        Assert.Equal(0, document.SetNodeVisibleCalls + document.SetNodeSelectedCalls);
    }

    [Fact]
    public async Task Document_root_rejects_occurrence_path_in_direct_adapter_calls()
    {
        var (adapter, _, _) = CreateAdapter(new CountingNode("root", ""));
        var result = Json(await adapter.ResolveViewerNodesAsync("source-1", Session("doc"),
            Json(new[] { new { source_node_id = "root", kind = "document_root", occurrence_path = Array.Empty<object>() } })));
        Assert.Equal("viewer_node_invalid", result.GetProperty("nodes")[0].GetProperty("error_code").GetString());
    }

    [Fact]
    public async Task Opaque_root_mapping_controls_only_bound_document_and_rejects_reused_key()
    {
        Directory.CreateDirectory(root);
        var node = new FakeNode("11", "Bolt", "", "", []) { CadId="Root:Bolt:" };
        var document = new FakeDocument("doc", "tc://one", node);
        var app = new FakeApplication("14.2", document);
        var com = new FakeVisMockupCom { ExistingApplication=app, ProcessId=123, ProcessStartUtcTicks=456 };
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([root]), com);
        adapter.ViewerInteractionAdmissionAllowed=()=>true;
        var resolve = typeof(VisMockupAdapter).GetMethod("ResolveViewerNodesAsync");
        var execute = typeof(VisMockupAdapter).GetMethod("ExecuteViewerNodeAsync");
        Assert.NotNull(resolve); Assert.NotNull(execute);
        var mapped = Json(await (Task<object>)resolve!.Invoke(adapter, ["source-1", Session("doc"),
            Json(new[] { new { source_node_id="root",kind="single_part_root" } })])!);
        var reference = mapped.GetProperty("nodes")[0].GetProperty("node_ref").GetString()!;
        Assert.NotEqual("11", reference);
        var epoch = mapped.GetProperty("structure_epoch").GetInt64();
        async Task<object> Act(string action) => await (Task<object>)execute!.Invoke(adapter,
            ["source-1",Session("doc"),epoch,reference,"vismockup.node.visibility.change@1",Json(new {action})])!;
        for(var i=0;i<100;i++) await Act(i%2==0 ? "show" : "hide");
        Assert.Equal(100,document.SetNodeVisibleCalls);
        Assert.False(document.IsNodeVisible("11"));
        Assert.Equal(0,document.ExportPlmxmlCalls);
        adapter.ViewerInteractionAdmissionAllowed=()=>false;
        await Assert.ThrowsAsync<ConnectorNoEffectException>(()=>Act("show"));
        Assert.Equal(100,document.SetNodeVisibleCalls);
        adapter.ViewerInteractionAdmissionAllowed=()=>true;
        document.RuntimeNodes["11"] = node with { CadId="Root:replacement:" };
        await Assert.ThrowsAsync<ConnectorNoEffectException>(()=>Act("show"));
        Assert.Equal(100,document.SetNodeVisibleCalls);
        app.ActiveDocument = new FakeDocument("different", "tc://other", node);
        await Assert.ThrowsAsync<ConnectorNoEffectException>(()=>Act("show"));
        Assert.Equal(100,document.SetNodeVisibleCalls);
    }

    [Fact]
    public async Task Full_occurrence_paths_separate_duplicate_names_and_raw_keys_are_rejected()
    {
        Directory.CreateDirectory(root);
        var left=new FakeNode("11","Bolt","left","",[]) {CadId="Root:Left:Bolt:"};
        var right=new FakeNode("12","Bolt","right","",[]) {CadId="Root:Right:Bolt:"};
        var document=new FakeDocument("doc","tc://assembly",new FakeNode("10","Root","root","",[left,right]) {CadId="Root:"});
        var app=new FakeApplication("14.2",document);
        var adapter=new VisMockupAdapter(sta,new AllowedPathPolicy([root]),new FakeVisMockupCom {
            ExistingApplication=app,ProcessId=123,ProcessStartUtcTicks=456});
        adapter.ViewerInteractionAdmissionAllowed=()=>true;
        var mapped=Json(await adapter.ResolveViewerNodesAsync("source-1",Session("doc"),Json(new[] {
            new {source_node_id="L",kind="occurrence_path",occurrence_path=new[]{new{occurrence_uid="left",item_revision_uid="rev"}}},
            new {source_node_id="R",kind="occurrence_path",occurrence_path=new[]{new{occurrence_uid="right",item_revision_uid="rev"}}}
        })));
        var refs=mapped.GetProperty("nodes");
        var a=refs[0].GetProperty("node_ref").GetString()!;
        var b=refs[1].GetProperty("node_ref").GetString()!;
        Assert.NotEqual(a,b);
        var epoch=mapped.GetProperty("structure_epoch").GetInt64();
        await adapter.ExecuteViewerNodeAsync("source-1",Session("doc"),epoch,a,"vismockup.node.visibility.change@1",Json(new{action="show"}));
        Assert.True(document.IsNodeVisible("11")); Assert.False(document.IsNodeVisible("12"));
        await Assert.ThrowsAsync<ConnectorNoEffectException>(()=>adapter.ExecuteViewerNodeAsync("source-1",Session("doc"),epoch,"12",
            "vismockup.node.visibility.change@1",Json(new{action="show"})));
        await adapter.InsertManagedFileAsync(WriteModel());
        await Assert.ThrowsAsync<ConnectorNoEffectException>(()=>adapter.ExecuteViewerNodeAsync("source-1",Session("doc"),epoch,b,
            "vismockup.node.visibility.change@1",Json(new{action="show"})));
        Assert.False(document.IsNodeVisible("12"));
    }

    private string WriteModel() { var path=Path.Combine(root,"part.jt"); File.WriteAllText(path,"test"); return path; }

    [Fact]
    public async Task Authorization_revoked_while_waiting_on_sta_prevents_native_write()
    {
        Directory.CreateDirectory(root);
        var node=new FakeNode("11","Bolt","","",[]) {CadId="Root:Bolt:"};
        var document=new FakeDocument("doc","tc://one",node);
        var adapter=new VisMockupAdapter(sta,new AllowedPathPolicy([root]),new FakeVisMockupCom {
            ExistingApplication=new FakeApplication("14.2",document),ProcessId=123,ProcessStartUtcTicks=456});
        var allowed=1;
        adapter.ViewerInteractionAdmissionAllowed=()=>Volatile.Read(ref allowed)==1;
        var mapped=Json(await adapter.ResolveViewerNodesAsync("source-1",Session("doc"),
            Json(new[]{new{source_node_id="root",kind="single_part_root"}})));
        using var entered=new ManualResetEventSlim();
        using var release=new ManualResetEventSlim();
        var blocking=sta.InvokeAsync(()=>{entered.Set();release.Wait(TimeSpan.FromSeconds(10));return true;});
        Task<object>? pending=null;
        try
        {
            Assert.True(entered.Wait(TimeSpan.FromSeconds(5)));
            pending=adapter.ExecuteViewerNodeAsync("source-1",Session("doc"),mapped.GetProperty("structure_epoch").GetInt64(),
                mapped.GetProperty("nodes")[0].GetProperty("node_ref").GetString()!,
                "vismockup.node.visibility.change@1",Json(new{action="show"}));
            Volatile.Write(ref allowed,0);
        }
        finally { release.Set(); await blocking; }
        await Assert.ThrowsAsync<ConnectorNoEffectException>(()=>pending!);
        Assert.Equal(0,document.SetNodeVisibleCalls);
    }

    [Fact]
    public async Task Registered_cached_package_can_map_beyond_online_sibling_budget()
    {
        var (adapter, app, _) = CreateAdapter(new CountingNode("old", ""));
        var path = Path.Combine(root, "snapshot.jt");
        File.WriteAllText(path, "frozen test geometry");
        var artifact = new { artifact_id="test", media_type="model/jt",
            sha256=Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant(),
            byte_size=new FileInfo(path).Length, version=1 };
        var packet = new { artifact_ref=artifact, package_dependencies=Array.Empty<object>(),
            cache_binding=new {batch_id=new string('a',32),generation=(string?)null,snapshot_hash=(string?)null,schema_version=1} };
        var payload=System.Text.Json.Nodes.JsonNode.Parse(Json(packet).GetRawText())!.AsObject();
        payload["package_hash"]=Ai00.Connector.Contracts.V2.CanonicalJsonV2.Hash(Json(packet));
        payload["local_artifact_path"]=path;
        await adapter.OpenManagedCacheAsync(Json(payload),default);
        var tree = new CountingNode("root", "", Enumerable.Range(0,600).Select(i=>new CountingNode("key"+i,"part"+i)).ToArray());
        var document = new FakeDocument(path,path,tree);_ = document.RuntimeNodes;
        app.ActiveDocument=document;app.OpenDocuments=[document];
        var result=Json(await adapter.ResolveViewerNodesAsync("source",Session(path),Json(new[]{Occurrence("last","part599")})));
        Assert.Equal("mapped",result.GetProperty("nodes")[0].GetProperty("status").GetString());
        Assert.Equal(0,document.SetNodeVisibleCalls);
    }

    private (VisMockupAdapter Adapter, FakeApplication App, FakeDocument Document) CreateAdapter(IVisMockupNode node)
    {
        Directory.CreateDirectory(root);
        var document = new FakeDocument("doc", "tc://one", node);
        _ = document.RuntimeNodes; // Build the fake native index during fixture setup.
        var app = new FakeApplication("14.2", document);
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([root]), new FakeVisMockupCom
            { ExistingApplication = app, ProcessId = 123, ProcessStartUtcTicks = 456 });
        adapter.ViewerInteractionAdmissionAllowed = () => true;
        return (adapter, app, document);
    }

    private static object Occurrence(string source, params string[] path) => new
    {
        source_node_id = source, kind = "occurrence_path",
        occurrence_path = path.Select(uid => new { occurrence_uid = uid, item_revision_uid = "rev" }).ToArray()
    };

    private static Task<object> Act(VisMockupAdapter adapter, JsonElement mapped, string action) =>
        adapter.ExecuteViewerNodeAsync("source-1", Session("doc"), mapped.GetProperty("structure_epoch").GetInt64(),
            mapped.GetProperty("nodes")[0].GetProperty("node_ref").GetString()!,
            action is "show" or "hide" ? "vismockup.node.visibility.change@1" : "vismockup.node.selection.change@1",
            Json(new { action }));

    [Theory]
    [InlineData("show", false)]
    [InlineData("hide", false)]
    [InlineData("highlight", false)]
    [InlineData("unhighlight", false)]
    [InlineData("show", true)]
    [InlineData("hide", true)]
    [InlineData("highlight", true)]
    [InlineData("unhighlight", true)]
    public async Task Active_document_change_is_rejected_before_write_and_unknown_after_write(string action, bool afterWrite)
    {
        var node = new CountingNode("11", "part");
        var (adapter, app, document) = CreateAdapter(node);
        var mapped = Json(await adapter.ResolveViewerNodesAsync("source-1", Session("doc"),
            Json(new[] { new { source_node_id = "root", kind = "single_part_root" } })));
        var other = new FakeDocument("other", "tc://other", new CountingNode("11", "other"));
        Action change = () => app.ActiveDocument = other;
        if (afterWrite) document.AfterNodeWrite = change;
        else document.AfterNodeLookup = change;

        if (afterWrite)
            Assert.Equal("viewer_outcome_unknown", (await Assert.ThrowsAsync<ConnectorException>(() => Act(adapter, mapped, action))).Code);
        else
            await Assert.ThrowsAsync<ConnectorNoEffectException>(() => Act(adapter, mapped, action));
        Assert.Equal(afterWrite ? 1 : 0, document.SetNodeVisibleCalls + document.SetNodeSelectedCalls);
        Assert.Equal(0, other.SetNodeVisibleCalls + other.SetNodeSelectedCalls);
        app.ActiveDocument = document;
        await Assert.ThrowsAsync<ConnectorNoEffectException>(() => Act(adapter, mapped, action));
    }

    [Fact]
    public async Task All_four_hot_actions_use_only_native_lookup_without_tree_or_metadata_reads()
    {
        var part = new CountingNode("11", "part");
        var tree = new CountingNode("10", "root", part);
        var (adapter, _, document) = CreateAdapter(tree);
        var mapped = Json(await adapter.ResolveViewerNodesAsync("source-1", Session("doc"), Json(new[] { Occurrence("part", "part") })));
        tree.Reset(); part.Reset();
        var initialLookups = document.FindNodeByKeyCalls;
        for (var i = 0; i < 100; i++)
        {
            await Act(adapter, mapped, "show");
            Assert.True(document.IsNodeVisible("11"));
            await Act(adapter, mapped, "highlight");
            Assert.Contains("11", document.SelectedNodeKeys);
            await Act(adapter, mapped, "hide");
            Assert.False(document.IsNodeVisible("11"));
            await Act(adapter, mapped, "unhighlight");
            Assert.Empty(document.SelectedNodeKeys);
        }
        Assert.Equal(400, document.FindNodeByKeyCalls - initialLookups);
        Assert.Equal(200, document.SetNodeVisibleCalls);
        Assert.Equal(200, document.SetNodeSelectedCalls);
        Assert.Equal(0, tree.ChildrenReads + part.ChildrenReads);
        Assert.Equal(0, tree.OccurrenceReads + part.OccurrenceReads);
        Assert.Equal(0, document.ExportPlmxmlCalls);
    }

    [Theory]
    [InlineData("show")]
    [InlineData("highlight")]
    public async Task A_native_write_then_exception_is_never_reported_as_no_effect(string action)
    {
        var (adapter, _, document) = CreateAdapter(new CountingNode("11", "part"));
        var mapped = Json(await adapter.ResolveViewerNodesAsync("source-1", Session("doc"),
            Json(new[] { new { source_node_id = "root", kind = "single_part_root" } })));
        // Even a misleading lower-level no-effect error cannot undo a dispatched write.
        document.SetNodeVisibleError = new ConnectorNoEffectException("late_native_failure");
        document.ApplyVisibilityBeforeThrow = true;
        document.SetNodeSelectedError = new ConnectorNoEffectException("late_native_failure");
        Assert.Equal("viewer_outcome_unknown", (await Assert.ThrowsAsync<ConnectorException>(() => Act(adapter, mapped, action))).Code);
        Assert.Equal(1, document.SetNodeVisibleCalls + document.SetNodeSelectedCalls);
        Assert.True(action == "show" ? document.IsNodeVisible("11") : document.SelectedNodeKeys.Contains("11"));
    }

    [Fact]
    public async Task Cold_resolution_shares_prefixes_and_reads_each_sibling_identity_once_per_batch()
    {
        var left = new CountingNode("11", "left");
        var right = new CountingNode("12", "right");
        var branch = new CountingNode("20", "branch", left, right);
        var tree = new CountingNode("10", "root", branch);
        var (adapter, _, _) = CreateAdapter(tree);
        foreach (var node in new[] { tree, branch, left, right }) node.Reset();
        var result = Json(await adapter.ResolveViewerNodesAsync("source-1", Session("doc"), Json(new[]
            { Occurrence("L", "root", "branch", "left"), Occurrence("R", "root", "branch", "right") })));
        Assert.All(result.GetProperty("nodes").EnumerateArray(), item => Assert.Equal("mapped", item.GetProperty("status").GetString()));
        Assert.Equal(1, tree.ChildrenReads);
        Assert.Equal(1, branch.ChildrenReads);
        Assert.All(new[] { tree, branch, left, right }, node => Assert.Equal(1, node.OccurrenceReads));
    }

    [Fact]
    public async Task Cold_resolution_matches_any_native_occurrence_alias()
    {
        var part = new AliasNode("11", "viewer-instance", "teamcenter-occurrence");
        var tree = new CountingNode("10", "root", part);
        var (adapter, _, _) = CreateAdapter(tree);
        var result = Json(await adapter.ResolveViewerNodesAsync("source-1", Session("doc"),
            Json(new[] { Occurrence("part", "teamcenter-occurrence") })));
        Assert.Equal("mapped", result.GetProperty("nodes")[0].GetProperty("status").GetString());
    }

    [Fact]
    public async Task Cold_resolution_stops_after_a_primary_occurrence_match()
    {
        var part = new PrimaryNode("11", "teamcenter-occurrence");
        var tree = new CountingNode("10", "root", part);
        var (adapter, _, _) = CreateAdapter(tree);

        var result = Json(await adapter.ResolveViewerNodesAsync("source-1", Session("doc"),
            Json(new[] { Occurrence("part", "teamcenter-occurrence") })));

        Assert.Equal("mapped", result.GetProperty("nodes")[0].GetProperty("status").GetString());
        Assert.Equal(0, part.AliasReads);
    }

    [Fact]
    public async Task Cold_resolution_crosses_only_identityless_native_wrappers()
    {
        var part = new CountingNode("11", "teamcenter-occurrence");
        var wrapper = new CountingNode("12", "", part);
        var tree = new CountingNode("10", "root", wrapper);
        var (adapter, _, _) = CreateAdapter(tree);
        var result = Json(await adapter.ResolveViewerNodesAsync("source-1", Session("doc"),
            Json(new[] { Occurrence("part", "teamcenter-occurrence") })));
        Assert.Equal("mapped", result.GetProperty("nodes")[0].GetProperty("status").GetString());
    }

    [Fact]
    public async Task Direct_occurrence_match_does_not_expand_unrelated_wide_wrappers()
    {
        var part = new CountingNode("target", "teamcenter-occurrence");
        var wrappers = Enumerable.Range(1, 186).Select(i => new CountingNode("wrapper" + i, "",
            new CountingNode("leaf" + i + "a", "other" + i + "a"),
            new CountingNode("leaf" + i + "b", "other" + i + "b"),
            new CountingNode("leaf" + i + "c", "other" + i + "c"))).ToArray();
        var tree = new CountingNode("root", "root", [part, .. wrappers]);
        var (adapter, _, _) = CreateAdapter(tree);
        foreach (var wrapper in wrappers) wrapper.Reset();

        var result = Json(await adapter.ResolveViewerNodesAsync("source-1", Session("doc"),
            Json(new[] { Occurrence("part", "teamcenter-occurrence") })));

        Assert.Equal("mapped", result.GetProperty("nodes")[0].GetProperty("status").GetString());
        Assert.All(wrappers, wrapper => Assert.Equal(0, wrapper.ChildrenReads));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Wide_roots_are_rejected_before_child_materialization(bool singlePart)
    {
        var children = Enumerable.Range(1, 513).Select(i => new CountingNode(i.ToString(), "part" + i)).ToArray();
        var tree = new CountingNode("0", "root", children);
        var (adapter, _, _) = CreateAdapter(tree);
        tree.Reset();
        foreach (var node in children) node.Reset();
        var descriptor = singlePart ? (object)new { source_node_id = "root", kind = "single_part_root" } : Occurrence("part", "part1");
        var result = Json(await adapter.ResolveViewerNodesAsync("source-1", Session("doc"), Json(new[] { descriptor })));
        Assert.Equal("viewer_mapping_budget_exceeded", result.GetProperty("nodes")[0].GetProperty("error_code").GetString());
        Assert.Equal(0, tree.ChildrenReads);
        Assert.All(children, node => Assert.Equal(0, node.OccurrenceReads));
    }

    [Fact]
    public async Task Wide_root_budget_reports_parent_and_actual_child_count()
    {
        var children = Enumerable.Range(1, 513).Select(i => new CountingNode(i.ToString(), "part" + i)).ToArray();
        var tree = new CountingNode("0", "root", children);
        var (adapter, _, _) = CreateAdapter(tree);
        tree.Reset();
        using var output = new StringWriter();
        var original = Console.Error;
        JsonElement result;
        try
        {
            Console.SetError(output);
            result = Json(await adapter.ResolveViewerNodesAsync("source-1", Session("doc"),
                Json(new[] { Occurrence("part", "part1") })));
        }
        finally { Console.SetError(original); }

        Assert.Equal("viewer_mapping_budget_exceeded", result.GetProperty("nodes")[0].GetProperty("error_code").GetString());
        var line = Assert.Single(output.ToString().Split('\n', StringSplitOptions.RemoveEmptyEntries));
        Assert.StartsWith("AI00_VIEWER_MAPPING_BUDGET_V1:", line);
        using var diagnostic = JsonDocument.Parse(line["AI00_VIEWER_MAPPING_BUDGET_V1:".Length..]);
        Assert.Equal("0", diagnostic.RootElement.GetProperty("parent_key").GetString());
        Assert.True(diagnostic.RootElement.GetProperty("at_root").GetBoolean());
        Assert.Equal(513, diagnostic.RootElement.GetProperty("child_count").GetInt32());
        Assert.Equal(511, diagnostic.RootElement.GetProperty("remaining").GetInt32());
        Assert.Equal(0, tree.ChildrenReads);
    }

    [Fact]
    public async Task Cold_resolution_budget_is_shared_across_targets_and_resets_next_batch()
    {
        var leftChildren = Enumerable.Range(1, 300).Select(i => new CountingNode("L" + i, "part" + i)).ToArray();
        var rightChildren = Enumerable.Range(1, 300).Select(i => new CountingNode("R" + i, "part" + i)).ToArray();
        var left = new CountingNode("L", "left", leftChildren);
        var right = new CountingNode("R", "right", rightChildren);
        var tree = new CountingNode("0", "root", left, right);
        var (adapter, _, _) = CreateAdapter(tree);
        foreach (var node in leftChildren.Concat(rightChildren).Concat(new[] { tree, left, right })) node.Reset();
        var result = Json(await adapter.ResolveViewerNodesAsync("source-1", Session("doc"), Json(new[]
            { Occurrence("L", "left", "part1"), Occurrence("R", "right", "part1") })));
        Assert.Equal("mapped", result.GetProperty("nodes")[0].GetProperty("status").GetString());
        Assert.Equal("viewer_mapping_budget_exceeded", result.GetProperty("nodes")[1].GetProperty("error_code").GetString());
        Assert.Equal(0, right.ChildrenReads);
        Assert.InRange(leftChildren.Concat(rightChildren).Concat(new[] { tree, left, right }).Sum(n => n.OccurrenceReads), 1, 512);
        var next = Json(await adapter.ResolveViewerNodesAsync("source-1", Session("doc"), Json(new[] { Occurrence("R", "right", "part1") })));
        Assert.Equal("mapped", next.GetProperty("nodes")[0].GetProperty("status").GetString());
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Cold_resolution_stops_native_reads_after_admission_is_revoked(bool duringOccurrence)
    {
        var left = new CountingNode("11", "left");
        var right = new CountingNode("12", "right");
        var tree = new CountingNode("10", "root", left, right);
        var (adapter, _, document) = CreateAdapter(tree);
        var allowed = true;
        adapter.ViewerInteractionAdmissionAllowed = () => allowed;
        if (duringOccurrence) left.AfterOccurrenceRead = () => allowed = false;
        else tree.AfterChildrenRead = () => allowed = false;
        foreach (var node in new[] { tree, left, right }) node.Reset();
        var error = await Assert.ThrowsAsync<ConnectorNoEffectException>(() => adapter.ResolveViewerNodesAsync(
            "source-1", Session("doc"), Json(new[] { Occurrence("L", "left"), Occurrence("R", "right") })));
        Assert.Equal("viewer_authorization_required", error.Code);
        Assert.Equal(1, tree.ChildrenReads);
        Assert.Equal(duringOccurrence ? 1 : 0, left.OccurrenceReads);
        Assert.Equal(0, right.OccurrenceReads);
        Assert.Equal(0, document.SetNodeVisibleCalls + document.SetNodeSelectedCalls);
    }

    [Theory]
    [InlineData("null")]
    [InlineData("{}")]
    [InlineData("{\"source_node_id\":7,\"kind\":\"single_part_root\"}")]
    [InlineData("{\"source_node_id\":\"bad\",\"kind\":7}")]
    [InlineData("{\"source_node_id\":\"bad\",\"kind\":\"occurrence_path\"}")]
    [InlineData("{\"source_node_id\":\"bad\",\"kind\":\"occurrence_path\",\"occurrence_path\":[null]}")]
    [InlineData("{\"source_node_id\":\"bad\",\"kind\":\"occurrence_path\",\"occurrence_path\":[{\"occurrence_uid\":7,\"item_revision_uid\":\"rev\"}]}")]
    [InlineData("{\"source_node_id\":\"bad\",\"kind\":\"occurrence_path\",\"occurrence_path\":[{\"occurrence_uid\":\"part\"}]}")]
    [InlineData("{\"source_node_id\":\"bad\",\"kind\":\"single_part_root\",\"kind\":\"single_part_root\"}")]
    [InlineData("{\"source_node_id\":\"bad\",\"kind\":\"occurrence_path\",\"occurrence_path\":[{\"occurrence_uid\":\"part\",\"item_revision_uid\":\"rev\",\"node_key\":\"11\"}]}")]
    public async Task Malformed_descriptor_is_an_item_error_without_losing_valid_mappings(string bad)
    {
        var (adapter, _, _) = CreateAdapter(new CountingNode("11", "part"));
        using var batch = JsonDocument.Parse("[{\"source_node_id\":\"root\",\"kind\":\"single_part_root\"}," + bad + "]");
        var result = Json(await adapter.ResolveViewerNodesAsync("source-1", Session("doc"), batch.RootElement));
        Assert.Equal("mapped", result.GetProperty("nodes")[0].GetProperty("status").GetString());
        Assert.Equal("unmapped", result.GetProperty("nodes")[1].GetProperty("status").GetString());
        Assert.True(result.GetProperty("nodes")[1].TryGetProperty("error_code", out _));
        await Act(adapter, result, "show");
    }

    private sealed class CountingNode(string key, string occurrence, params IVisMockupNode[] children) : IVisMockupNode
    {
        public string NodeKey => key;
        public string PrintableName => "part";
        public string CadId => "cad:" + key;
        public string ModelId => "rev";
        public bool Visible { get; set; }
        public Exception? VisibilityError { get; set; }
        public bool IsVisible => VisibilityError is null ? Visible : throw VisibilityError;
        public int ChildrenReads { get; private set; }
        public int OccurrenceReads { get; private set; }
        public Action? AfterChildrenRead { get; set; }
        public Action? AfterOccurrenceRead { get; set; }
        public string OccurrenceId { get { OccurrenceReads++; AfterOccurrenceRead?.Invoke(); return occurrence; } }
        public IReadOnlyList<IVisMockupNode> Children { get { ChildrenReads++; AfterChildrenRead?.Invoke(); return children; } }
        public int ChildCount => children.Length;
        public IReadOnlyList<IVisMockupNode> GetChildren(int maximum)
        {
            if (children.Length > maximum) throw new ConnectorNoEffectException("viewer_mapping_budget_exceeded");
            return Children;
        }
        public void Reset() { ChildrenReads = 0; OccurrenceReads = 0; }
    }

    private sealed class AliasNode(string key, params string[] aliases) : IVisMockupNode
    {
        public string NodeKey => key;
        public string PrintableName => "part";
        public string CadId => "cad:" + key;
        public string ModelId => "rev";
        public bool IsVisible => false;
        public string OccurrenceId => aliases[0];
        public IReadOnlyList<string> OccurrenceIds => aliases;
        public IReadOnlyList<IVisMockupNode> Children => [];
    }

    private sealed class PrimaryNode(string key, string occurrence) : IVisMockupNode
    {
        public int AliasReads { get; private set; }
        public string NodeKey => key;
        public string PrintableName => "part";
        public string CadId => "cad:" + key;
        public string ModelId => "rev";
        public bool IsVisible => false;
        public string OccurrenceId => occurrence;
        public IReadOnlyList<string> OccurrenceIds { get { AliasReads++; return [occurrence]; } }
        public IReadOnlyList<IVisMockupNode> Children => [];
    }

    public void Dispose() { sta.Dispose(); if(Directory.Exists(root)) Directory.Delete(root,true); }
}
