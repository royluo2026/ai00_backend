using Ai00.Connector.Adapters.VisMockup;
using Ai00.Connector.Contracts;
using Microsoft.Data.Sqlite;
using System.Text.Json;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class VisMockupSnapshotTests
{
    [Fact]
    public void LeafNodesNeverOpenTheComChildrenCollection()
    {
        var calls = 0;

        var children = WindowsVisMockupCom.MaterializeChildren(0, _ =>
        {
            calls++;
            return FakeNode.FlatTree(1);
        });

        Assert.Empty(children);
        Assert.Equal(0, calls);
    }

    [Fact]
    public void UnreadableComChildSlotCannotProduceAnApparentlyCompleteTree()
    {
        var error = Assert.Throws<ConnectorException>(() => WindowsVisMockupCom.MaterializeChildren(3, index =>
            index == 1
                ? throw new ConnectorException("vismockup_dispatch_d3_h80020009")
                : new FakeNode($"node-{index}", $"Node {index}", "", "", [])));

        Assert.Equal("vismockup_dispatch_d3_h80020009", error.Code);
    }

    private sealed class CountingNode(
        string nodeKey, IReadOnlyList<IVisMockupNode> children) : IVisMockupNode
    {
        public string NodeKey => nodeKey;
        public bool IsVisible => true;
        public string PrintableName => nodeKey;
        public int OccurrenceReads { get; private set; }
        public string OccurrenceId { get { OccurrenceReads++; return nodeKey; } }
        public string ModelId => nodeKey;
        public int ChildrenReads { get; private set; }
        public IReadOnlyList<IVisMockupNode> Children
        {
            get { ChildrenReads++; return children; }
        }
    }

    [Fact]
    public async Task ProbeAttachesExistingInstanceWithoutLaunchingAnother()
    {
        var fake = new FakeVisMockupCom { ExistingApplication = FakeVisMockupCom.WithDocument("BOM-1") };
        using var sta = new StaDispatcher();
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([Path.GetTempPath()]), fake);

        var health = await adapter.ProbeAsync(default);

        Assert.True(health.DocumentReady);
        Assert.Equal(0, fake.LaunchCalls);
        Assert.Single(fake.ThreadIds);
        Assert.Equal([ApartmentState.STA], fake.ApartmentStates);
    }

    [Fact]
    public async Task ProbeReportsRunningProcessWhenItsAutomationObjectCannotBeAttached()
    {
        var fake = new FakeVisMockupCom { ProcessRunning = true };
        using var sta = new StaDispatcher();
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([Path.GetTempPath()]), fake);

        var health = await adapter.ProbeAsync(default);
        var json = JsonSerializer.SerializeToElement(health);

        Assert.False(health.Ready);
        Assert.True(health.ProcessReady);
        Assert.Equal("automation_unavailable", health.Status);
        Assert.True(json.GetProperty("process_ready").GetBoolean());
        Assert.False(json.TryGetProperty("ProcessReady", out _));
    }

    [Fact]
    public async Task SnapshotRejectsTreeBeyondNodeLimit()
    {
        var fake = new FakeVisMockupCom { ExistingApplication = FakeVisMockupCom.WithDocument("BOM-1", 10_001) };
        using var sta = new StaDispatcher();
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([Path.GetTempPath()]), fake);

        var error = await Assert.ThrowsAsync<ConnectorException>(() => adapter.SnapshotAsync(10_000, 64));

        Assert.Equal("bom_snapshot_limit_exceeded", error.Code);
    }

    [Fact]
    public async Task SnapshotRejectsDuplicateNodeIdentity()
    {
        var duplicate = new FakeNode("duplicate", "Duplicate", "occ", "model", []);
        var root = new FakeNode("root", "Root", "root", "root-model", [duplicate, duplicate]);
        var fake = new FakeVisMockupCom
        {
            ExistingApplication = new FakeApplication("14.2.0", new FakeDocument("BOM-1", "tc://bom/1", root)),
        };
        using var sta = new StaDispatcher();
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([Path.GetTempPath()]), fake);

        var error = await Assert.ThrowsAsync<ConnectorException>(() => adapter.SnapshotAsync(10_000, 64));

        Assert.Equal("bom_snapshot_invalid", error.Code);
    }

    [Fact]
    public async Task SnapshotWireResultUsesSimulationSnakeCaseAndProductReferences()
    {
        var fake = new FakeVisMockupCom { ExistingApplication = FakeVisMockupCom.WithDocument("BOM-1") };
        using var sta = new StaDispatcher();
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([Path.GetTempPath()]), fake);

        var snapshot = await adapter.SnapshotAsync(10_000, 64);
        var json = JsonSerializer.SerializeToElement(snapshot);

        Assert.True(json.TryGetProperty("document_id", out _));
        var node = json.GetProperty("nodes")[0];
        Assert.True(node.TryGetProperty("parent_key", out _));
        Assert.True(node.TryGetProperty("product_ref", out var product));
        Assert.False(string.IsNullOrWhiteSpace(product.GetString()));
        Assert.False(node.TryGetProperty("ModelId", out _));
    }

    [Fact]
    public void SnapshotReadsEachComChildrenCollectionOnlyOnce()
    {
        var leaf = new CountingNode("leaf", []);
        var root = new CountingNode("root", [leaf]);
        var document = new FakeDocument("BOM-1", "tc://bom/1", root);

        new DocumentSnapshotReader().Read(document, 10_000, 64);

        Assert.Equal(1, root.ChildrenReads);
        Assert.Equal(1, leaf.ChildrenReads);
    }

    [Fact]
    public void LightweightTreeReadIsAdvertisedAsAnExactSignedOperation()
    {
        var fake = new FakeVisMockupCom { ExistingApplication = FakeVisMockupCom.WithDocument("BOM-1") };
        using var sta = new StaDispatcher();
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([Path.GetTempPath()]), fake);

        var operation = adapter.Manifest.Operations.Single(item => item.OperationId == "vismockup.tree.read@1");

        Assert.Equal("sha256:b3c6a014ac8853a3b6689286ce514b7997bb450f6394253d813308afa8863af0", operation.ContractHash);
        var liveOperation = adapter.Manifest.Operations.Single(item => item.OperationId == "vismockup.tree.read@2");
        Assert.Equal("sha256:5d69cc98e38bd721fb55623b62df5162e68cbfb9bcb51c1b6c25d351c486de7c", liveOperation.ContractHash);
    }

    [Fact]
    public async Task LightweightTreeReadUsesTheSupportedComNodeAbstraction()
    {
        var fake = new FakeVisMockupCom { ExistingApplication = FakeVisMockupCom.WithDocument("BOM-1", 3) };
        using var sta = new StaDispatcher();
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([Path.GetTempPath()]), fake);

        var result = await adapter.ExecuteAsync(new AdapterOperation(
            "vismockup.tree.read@1", JsonSerializer.SerializeToElement(new { max_depth = 3 })), default);
        var json = JsonSerializer.SerializeToElement(result.Data);

        Assert.True(result.Ok);
        Assert.Equal(3, json.GetProperty("nodes").GetArrayLength());
        Assert.Equal("node-0", json.GetProperty("nodes")[0].GetProperty("node_key").GetString());
        Assert.Equal("Node 0", json.GetProperty("nodes")[0].GetProperty("name").GetString());
        Assert.False(json.GetProperty("nodes")[0].TryGetProperty("visible", out _));
    }

    [Fact]
    public async Task LightweightTreeReadReusesTheCurrentDocumentSqliteSnapshot()
    {
        var leaf = new CountingNode("leaf", []);
        var root = new CountingNode("root", [leaf]);
        var fake = new FakeVisMockupCom
        {
            ExistingApplication = new FakeApplication("14.2.0", new FakeDocument("BOM-1", "tc://bom/1", root)),
        };
        var directory = Path.Combine(Path.GetTempPath(), "ai00-vm-tree-cache-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        try
        {
            using var sta = new StaDispatcher();
            var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([Path.GetTempPath()]), fake,
                Path.Combine(directory, "captures"));
            var operation = new AdapterOperation(
                "vismockup.tree.read@1", JsonSerializer.SerializeToElement(new { max_depth = 3 }));

            await adapter.ExecuteAsync(operation, default);
            var firstReads = root.ChildrenReads + leaf.ChildrenReads;
            Assert.Equal(0, root.OccurrenceReads + leaf.OccurrenceReads);
            var cached = await adapter.ExecuteAsync(operation, default);

            Assert.Equal(firstReads, root.ChildrenReads + leaf.ChildrenReads);
            Assert.Equal(0, root.OccurrenceReads + leaf.OccurrenceReads);
            Assert.Equal(2, JsonSerializer.SerializeToElement(cached.Data).GetProperty("nodes").GetArrayLength());
            Assert.True(File.Exists(Path.Combine(directory, "vismockup-tree-cache.db")));
        }
        finally { Directory.Delete(directory, true); }
    }

    private sealed class UnreadableVisibilityNode : IVisMockupNode
    {
        public string NodeKey => "node-0";
        public bool IsVisible => throw new InvalidOperationException("visibility read failed");
        public string PrintableName => "Node 0";
        public string OccurrenceId => "";
        public string ModelId => "";
        public IReadOnlyList<IVisMockupNode> Children => [];
    }

    [Fact]
    public async Task InteractiveTreeReportsLiveVisibilityOnFreshAndCachedReads()
    {
        var directory = NewCacheDirectory("live-visibility");
        try
        {
            var document = new FakeDocument("SESSION-1", "tc://bom/live", FakeNode.FlatTree(2));
            var fake = new FakeVisMockupCom { ExistingApplication = new FakeApplication("14.2.0", document) };
            using var sta = new StaDispatcher();
            var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([Path.GetTempPath()]), fake,
                Path.Combine(directory, "captures"));
            var operation = new AdapterOperation("vismockup.tree.read@2",
                JsonSerializer.SerializeToElement(new { max_depth = 3 }));

            var fresh = JsonSerializer.SerializeToElement((await adapter.ExecuteAsync(operation, default)).Data);
            Assert.False(fresh.GetProperty("nodes")[1].GetProperty("visible").GetBoolean());

            document.SetNodeVisible("node-1", true);
            var cached = JsonSerializer.SerializeToElement((await adapter.ExecuteAsync(operation, default)).Data);
            Assert.True(cached.GetProperty("nodes")[1].GetProperty("visible").GetBoolean());
            Assert.Equal(1, document.SetNodeVisibleCalls);
            Assert.Equal(0, document.ExportPlmxmlCalls);
        }
        finally { Directory.Delete(directory, true); }
    }

    [Fact]
    public async Task CachedTreeWithDifferentTopologyReportsUnknownVisibility()
    {
        var directory = NewCacheDirectory("visibility-topology-mismatch");
        try
        {
            var document = new FakeDocument("SESSION-1", "tc://bom/mismatch", FakeNode.FlatTree(2));
            var cachePath = Path.Combine(directory, "tree.db");
            var cache = new VisMockupTreeCache(cachePath);
            cache.Replace(document, 64, [new("node-0", null, 0, 0, "Root", "", true)]);
            using var sta = new StaDispatcher();
            var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([Path.GetTempPath()]),
                new FakeVisMockupCom { ExistingApplication = new FakeApplication("14.2.0", document) },
                Path.Combine(directory, "captures"), cachePath);

            var result = JsonSerializer.SerializeToElement(await adapter.TreeAsync(3, includeVisibility: true));

            Assert.Equal(JsonValueKind.Null, result.GetProperty("nodes")[0].GetProperty("visible").ValueKind);
            Assert.Equal(0, document.SetNodeVisibleCalls);
        }
        finally { Directory.Delete(directory, true); }
    }

    [Fact]
    public async Task UnreadableLiveVisibilityIsUnknownAndDoesNotAbortTreeRead()
    {
        var document = new FakeDocument("SESSION-1", "tc://bom/unreadable", new UnreadableVisibilityNode());
        using var sta = new StaDispatcher();
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([Path.GetTempPath()]),
            new FakeVisMockupCom { ExistingApplication = new FakeApplication("14.2.0", document) });

        var result = JsonSerializer.SerializeToElement(await adapter.TreeAsync(3, includeVisibility: true));

        Assert.Equal(JsonValueKind.Null, result.GetProperty("nodes")[0].GetProperty("visible").ValueKind);
        Assert.Equal(0, document.SetNodeVisibleCalls);
    }

    [Fact]
    public async Task InteractiveTreeRefreshUsesTheLightweightComTreeAndNeverBlocksOnPlmxmlExport()
    {
        var directory = NewCacheDirectory("explicit-refresh");
        try
        {
            var leaf = new CountingNode("leaf", []);
            var root = new CountingNode("root", [leaf]);
            var document = new FakeDocument("BOM-1", "tc://bom/1", root);
            var fake = new FakeVisMockupCom
            {
                ExistingApplication = new FakeApplication("14.2.0", document),
            };
            using var sta = new StaDispatcher();
            var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([Path.GetTempPath()]), fake,
                Path.Combine(directory, "captures"));

            await adapter.TreeAsync(3);
            await adapter.TreeAsync(3);
            Assert.Equal(0, document.ExportPlmxmlCalls);
            var readsBeforeRefresh = root.ChildrenReads;

            await adapter.TreeAsync(3, forceRefresh: true);

            Assert.Equal(0, document.ExportPlmxmlCalls);
            Assert.True(root.ChildrenReads > readsBeforeRefresh);
        }
        finally { Directory.Delete(directory, true); }
    }

    [Fact]
    public async Task SnapshotRejectsExportShellThatOmitsLiveTopLevelChildren()
    {
        var directory = NewCacheDirectory("export-shell");
        try
        {
            var document = new FakeDocument("SESSION-1", "tc://bom/W10", FakeNode.FlatTree(4))
            {
                ExportPlmxmlContent = """
                    <PLMXML><InstanceGraph rootRefs="root">
                      <ProductInstance id="root" name="Root"/>
                      <ProductInstance id="child" name="Child"/>
                      <Occurrence instanceRefs="#root"><UserData>
                        <UserValue title="__PLM_OCC_PDM_UID" value="root-pdm"/>
                      </UserData></Occurrence>
                      <Occurrence instanceRefs="#root #child"><UserData>
                        <UserValue title="__PLM_OCC_PDM_UID" value="child-pdm"/>
                      </UserData></Occurrence>
                    </InstanceGraph></PLMXML>
                    """,
            };
            var cachePath = Path.Combine(directory, "tree.db");
            var cache = new VisMockupTreeCache(cachePath);
            cache.Replace(document, 64, [new("prior-root", null, 0, 0, "Prior Root", "", false)]);
            using var sta = new StaDispatcher();
            var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([Path.GetTempPath()]),
                new FakeVisMockupCom { ExistingApplication = new FakeApplication("14.2.0", document) },
                Path.Combine(directory, "captures"), cachePath);

            var error = await Assert.ThrowsAsync<ConnectorException>(() => adapter.SnapshotAsync(10_000, 64));

            Assert.Equal("plmxml_current_state_incomplete", error.Code);
            Assert.Equal("prior-root", cache.TryRead(document, 1)!.Nodes[0].NodeKey);
        }
        finally { Directory.Delete(directory, true); }
    }

    [Fact]
    public async Task PlmxmlSnapshotHonorsTheGovernedDepthLimitBeforePublishingCache()
    {
        var directory = NewCacheDirectory("plmxml-depth-limit");
        try
        {
            var document = new FakeDocument("SESSION-1", "tc://bom/W10", FakeNode.FlatTree(2))
            {
                ExportPlmxmlContent = """
                    <PLMXML><InstanceGraph rootRefs="root">
                      <ProductInstance id="root" name="Root"/>
                      <ProductInstance id="child" name="Child"/>
                      <ProductInstance id="leaf" name="Leaf"/>
                      <Occurrence instanceRefs="#root"><UserData>
                        <UserValue title="__PLM_OCC_PDM_UID" value="root-pdm"/>
                      </UserData></Occurrence>
                      <Occurrence instanceRefs="#root #child"><UserData>
                        <UserValue title="__PLM_OCC_PDM_UID" value="child-pdm"/>
                      </UserData></Occurrence>
                      <Occurrence instanceRefs="#root #child #leaf"><UserData>
                        <UserValue title="__PLM_OCC_PDM_UID" value="leaf-pdm"/>
                      </UserData></Occurrence>
                    </InstanceGraph></PLMXML>
                    """,
            };
            var cachePath = Path.Combine(directory, "tree.db");
            using var sta = new StaDispatcher();
            var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([Path.GetTempPath()]),
                new FakeVisMockupCom { ExistingApplication = new FakeApplication("14.2.0", document) },
                Path.Combine(directory, "captures"), cachePath);

            var error = await Assert.ThrowsAsync<ConnectorException>(() => adapter.SnapshotAsync(10_000, 1));

            Assert.Equal("bom_snapshot_limit_exceeded", error.Code);
            Assert.Null(new VisMockupTreeCache(cachePath).TryRead(document, 1));
        }
        finally { Directory.Delete(directory, true); }
    }

    [Fact]
    public async Task DisplayDepthDoesNotTruncateTheCompleteCachedGeneration()
    {
        IVisMockupNode node = new FakeNode("leaf", "Leaf", "", "", []);
        for (var depth = 8; depth >= 0; depth--)
            node = new FakeNode($"node-{depth}", $"Node {depth}", "", "", [node]);
        var fake = new FakeVisMockupCom
        {
            ExistingApplication = new FakeApplication(
                "14.2.0", new FakeDocument("BOM-1", "tc://bom/1", node)),
        };
        using var sta = new StaDispatcher();
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([Path.GetTempPath()]), fake);

        var result = await adapter.ExecuteAsync(
            new AdapterOperation("vismockup.tree.read@1", JsonSerializer.SerializeToElement(new { max_depth = 8 })),
            default);

        Assert.Equal(9, JsonSerializer.SerializeToElement(result.Data).GetProperty("nodes").GetArrayLength());
    }

    [Fact]
    public void TreeCacheIncrementallyUpsertsChangedNodesAndRemovesMissingNodes()
    {
        var directory = Path.Combine(Path.GetTempPath(), "ai00-vm-tree-cache-diff-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        try
        {
            var document = new FakeDocument("BOM-1", "tc://bom/1", FakeNode.FlatTree(1));
            var cache = new VisMockupTreeCache(Path.Combine(directory, "tree.db"));
            cache.Replace(document, 3, [
                new("root", null, 0, 0, "Root", "", false),
                new("old", "root", 0, 1, "Old", "", false),
            ]);

            cache.Replace(document, 3, [
                new("root", null, 0, 0, "Root renamed", "", false),
                new("new", "root", 0, 1, "New", "", false),
            ]);

            var value = cache.TryRead(document, 3)!;
            Assert.Equal(["root", "new"], value.Nodes.Select(item => item.NodeKey));
            Assert.Equal("Root renamed", value.Nodes[0].Name);
        }
        finally { Directory.Delete(directory, true); }
    }

    [Fact]
    public void CompletePlmxmlProjectionIsCachedOnceAndDisplayDepthOnlyFiltersTheRead()
    {
        var directory = NewCacheDirectory("plmxml-projection");
        try
        {
            var root = new FakeNode("session-root", "Root", "", "", [
                new FakeNode("session-child", "Child", "", "", [
                    new FakeNode("session-leaf", "Leaf", "", "", []),
                ]),
            ]);
            var document = new FakeDocument("SESSION-1", "tc://bom/W10", root);
            var cache = new VisMockupTreeCache(Path.Combine(directory, "tree.db"));
            var projection = new VisMockupPlmxmlProjection("pdm:root", [
                new("pdm:root", null, 0, 0, "Root", "W10", "A", "root", "", [], ["Root"], ""),
                new("pdm:child", "pdm:root", 0, 1, "Child", "W10-1", "A", "child", "", [], ["Root", "Child"], ""),
                new("pdm:leaf", "pdm:child", 0, 2, "Leaf", "W10-2", "A", "leaf", "", [], ["Root", "Child", "Leaf"], ""),
            ], "sha256:" + new string('a', 64));

            cache.ReplaceProjection(document, projection);

            var shallow = cache.TryRead(document, 1)!;
            Assert.Equal(["pdm:root", "pdm:child"], shallow.Nodes.Select(node => node.NodeKey));
            Assert.True(shallow.Nodes.Single(node => node.NodeKey == "pdm:child").HasMore);
            Assert.Equal("session-leaf", cache.ResolveSessionNodeKey(document, "pdm:leaf"));
        }
        finally { Directory.Delete(directory, true); }
    }

    [Fact]
    public void ReadOnlyRecoveryCanFollowFreshProjectionOrderAcrossDisplayNameEncodingDifferences()
    {
        var directory = NewCacheDirectory("read-only-recovery-name-encoding");
        try
        {
            var document = new FakeDocument("SESSION-1", "tc://bom/W10",
                new FakeNode("session-root", "Root 正常编码", "", "", [
                    new FakeNode("session-leaf", "Leaf 正常编码", "", "", []),
                ]));
            var cache = new VisMockupTreeCache(Path.Combine(directory, "tree.db"));
            cache.ReplaceProjection(document, new("pdm:root", [
                new("pdm:root", null, 0, 0, "Root 乱码", "W10", "A", "root", "", [], ["Root"], ""),
                new("pdm:leaf", "pdm:root", 0, 1, "Leaf 乱码", "W10-1", "A", "leaf", "", [], ["Root", "Leaf"], ""),
            ], "sha256:" + new string('c', 64)));

            Assert.Throws<InvalidDataException>(() => cache.ResolveSessionNodeKey(document, "pdm:leaf"));
            Assert.Equal("session-leaf", cache.ResolveSessionNodeKey(document, "pdm:leaf", verifyPrintableName: false));
        }
        finally { Directory.Delete(directory, true); }
    }

    [Fact]
    public async Task StableCachedOccurrenceResolvesToTheCurrentSessionNodeForControl()
    {
        var directory = NewCacheDirectory("session-node-control");
        try
        {
            var leaf = new FakeNode("session-leaf", "Leaf", "", "", []);
            var root = new FakeNode("session-root", "Root", "", "", [leaf]);
            var document = new FakeDocument("SESSION-1", "tc://bom/W10", root);
            var databasePath = Path.Combine(directory, "tree.db");
            var cache = new VisMockupTreeCache(databasePath);
            cache.ReplaceProjection(document, new("pdm:root", [
                new("pdm:root", null, 0, 0, "Root", "W10", "A", "root", "", [], ["Root"], ""),
                new("pdm:leaf", "pdm:root", 0, 1, "Leaf", "W10-1", "A", "leaf", "", [], ["Root", "Leaf"], ""),
            ], "sha256:" + new string('b', 64)));
            var fake = new FakeVisMockupCom { ExistingApplication = new FakeApplication("14.2.0", document) };
            using var sta = new StaDispatcher();
            var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([Path.GetTempPath()]), fake,
                Path.Combine(directory, "captures"), databasePath);

            await adapter.ChangeNodeSelectionAsync("pdm:leaf", "highlight");

            Assert.Contains("session-leaf", document.SelectedNodeKeys);
        }
        finally { Directory.Delete(directory, true); }
    }

    [Fact]
    public async Task ActivePlmxmlSourceHydratesStableNodeMappingBeforeControl()
    {
        var directory = NewCacheDirectory("source-plmxml-control");
        var source = Path.Combine(directory, "W10.plmxml");
        File.WriteAllText(source, """
            <PLMXML><InstanceGraph rootRefs="root-instance">
              <ProductInstance id="root-instance" name="Root"/>
              <ProductInstance id="leaf-instance" name="Leaf"/>
              <Occurrence instanceRefs="#root-instance"><UserData>
                <UserValue title="__PLM_OCC_PDM_UID" value="root"/>
              </UserData></Occurrence>
              <Occurrence instanceRefs="#root-instance #leaf-instance"><UserData>
                <UserValue title="__PLM_OCC_PDM_UID" value="leaf"/>
              </UserData></Occurrence>
            </InstanceGraph></PLMXML>
            """);
        try
        {
            var leaf = new FakeNode("session-leaf", "Leaf", "", "", []);
            var root = new FakeNode("session-root", "Root", "", "", [leaf]);
            var document = new FakeDocument("SESSION-1", source, root);
            var fake = new FakeVisMockupCom { ExistingApplication = new FakeApplication("14.2.0", document) };
            var artifactRoot = Path.Combine(directory, "artifacts");
            Directory.CreateDirectory(artifactRoot);
            using var sta = new StaDispatcher();
            var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([artifactRoot]), fake,
                Path.Combine(directory, "captures"), Path.Combine(directory, "tree.db"));

            await adapter.ChangeNodeSelectionAsync("pdm:leaf", "highlight");

            Assert.Contains("session-leaf", document.SelectedNodeKeys);
        }
        finally { Directory.Delete(directory, true); }
    }

    [Fact]
    public async Task ActivePlmxmlSourceCannotHydrateAnIncompleteControlMap()
    {
        var directory = NewCacheDirectory("incomplete-active-plmxml");
        var source = Path.Combine(directory, "W10.plmxml");
        File.WriteAllText(source, """
            <PLMXML><InstanceGraph rootRefs="root">
              <ProductInstance id="root" name="Root"/>
              <ProductInstance id="leaf" name="Leaf"/>
              <Occurrence instanceRefs="#root"><UserData>
                <UserValue title="__PLM_OCC_PDM_UID" value="root"/>
              </UserData></Occurrence>
              <Occurrence instanceRefs="#root #leaf"><UserData>
                <UserValue title="__PLM_OCC_PDM_UID" value="leaf"/>
              </UserData></Occurrence>
            </InstanceGraph></PLMXML>
            """);
        try
        {
            var document = new FakeDocument("SESSION-1", source,
                new FakeNode("session-root", "Root", "", "", [
                    new FakeNode("session-leaf", "Leaf", "", "", []),
                    new FakeNode("session-other", "Other", "", "", []),
                ]));
            var cachePath = Path.Combine(directory, "tree.db");
            using var sta = new StaDispatcher();
            var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([directory]),
                new FakeVisMockupCom { ExistingApplication = new FakeApplication("14.2.0", document) },
                Path.Combine(directory, "captures"), cachePath);

            await Assert.ThrowsAsync<ConnectorNoEffectException>(() =>
                adapter.ChangeNodeSelectionAsync("pdm:leaf", "highlight"));

            Assert.Empty(document.SelectedNodeKeys);
            Assert.Null(new VisMockupTreeCache(cachePath).TryRead(document, 1));
        }
        finally { Directory.Delete(directory, true); }
    }

    [Fact]
    public async Task NodeControlReusesMappingOnlyWithinTheSameVmProcessSession()
    {
        var directory = NewCacheDirectory("session-node-map");
        try
        {
            var leaf = new CountingNode("session-leaf", []);
            var root = new CountingNode("session-root", [leaf]);
            var document = new FakeDocument("SESSION-1", "tc://bom/W10", root);
            var cachePath = Path.Combine(directory, "tree.db");
            new VisMockupTreeCache(cachePath).ReplaceProjection(document, new("pdm:root", [
                new("pdm:root", null, 0, 0, "session-root", "W10", "A", "root", "", [], ["Root"], ""),
                new("pdm:leaf", "pdm:root", 0, 1, "session-leaf", "W10-1", "A", "leaf", "", [], ["Root", "Leaf"], ""),
            ], "sha256:" + new string('a', 64)));
            var fake = new FakeVisMockupCom
            {
                ExistingApplication = new FakeApplication("14.2.0", document),
                ProcessId = 41,
                ProcessStartUtcTicks = 1000,
            };
            using var sta = new StaDispatcher();
            var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([Path.GetTempPath()]), fake,
                Path.Combine(directory, "captures"), cachePath);

            await adapter.ChangeNodeSelectionAsync("pdm:leaf", "highlight");
            var afterFirst = root.ChildrenReads;
            await adapter.ChangeNodeSelectionAsync("pdm:leaf", "highlight");
            Assert.Equal(afterFirst + 1, root.ChildrenReads);

            fake.ProcessStartUtcTicks = 2000;
            await adapter.ChangeNodeSelectionAsync("pdm:leaf", "highlight");
            Assert.Equal(afterFirst + 3, root.ChildrenReads);
        }
        finally { Directory.Delete(directory, true); }
    }

    [Fact]
    public async Task NodeControlInvalidatesMappingWhenTheLocalSourceRevisionChanges()
    {
        var directory = NewCacheDirectory("source-revision-node-map");
        var source = Path.Combine(directory, "model.jt");
        File.WriteAllText(source, "original");
        try
        {
            var leaf = new FakeNode("session-leaf", "Leaf", "", "", []);
            var document = new FakeDocument("SESSION-1", source,
                new FakeNode("session-root", "Root", "", "", [leaf]));
            var cachePath = Path.Combine(directory, "tree.db");
            new VisMockupTreeCache(cachePath).ReplaceProjection(document, new("pdm:root", [
                new("pdm:root", null, 0, 0, "Root", "W10", "A", "root", "", [], ["Root"], ""),
                new("pdm:leaf", "pdm:root", 0, 1, "Leaf", "W10-1", "A", "leaf", "", [], ["Root", "Leaf"], ""),
            ], "sha256:" + new string('a', 64)));
            var fake = new FakeVisMockupCom
            {
                ExistingApplication = new FakeApplication("14.2.0", document),
                ProcessId = 41,
                ProcessStartUtcTicks = 1000,
            };
            using var sta = new StaDispatcher();
            var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([directory]), fake,
                Path.Combine(directory, "captures"), cachePath);

            await adapter.ChangeNodeSelectionAsync("pdm:leaf", "highlight");
            File.WriteAllText(source, "changed source revision");

            await Assert.ThrowsAsync<ConnectorNoEffectException>(() =>
                adapter.ChangeNodeSelectionAsync("pdm:leaf", "highlight"));
            Assert.Single(document.SelectedNodeKeys);
        }
        finally { Directory.Delete(directory, true); }
    }

    [Fact]
    public void TreeCacheSurvivesAVisMockupRestartForTheSameSourceModel()
    {
        var directory = Path.Combine(Path.GetTempPath(), "ai00-vm-tree-cache-reopen-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        var modelPath = Path.Combine(directory, "W10.vfz");
        File.WriteAllText(modelPath, "model");
        try
        {
            var cache = new VisMockupTreeCache(Path.Combine(directory, "tree.db"));
            var firstSession = new FakeDocument("SESSION-1", modelPath, FakeNode.FlatTree(1));
            cache.Replace(firstSession, 3, [new("pdm:root", null, 0, 0, "W10", "", false)]);

            var reopened = new FakeDocument("SESSION-2", modelPath, FakeNode.FlatTree(1));
            var value = cache.TryRead(reopened, 3);

            Assert.NotNull(value);
            Assert.Equal("W10", value!.Nodes[0].Name);
        }
        finally { Directory.Delete(directory, true); }
    }

    [Fact]
    public void TreeCacheRejectsAnUnversionedCrossSessionHit()
    {
        var directory = NewCacheDirectory("uncertain-reopen");
        try
        {
            var cache = new VisMockupTreeCache(Path.Combine(directory, "tree.db"));
            cache.Replace(
                new FakeDocument("SESSION-1", "tc://bom/W10", FakeNode.FlatTree(1)),
                3,
                [new("root", null, 0, 0, "W10", "", false)]);

            var reopened = new FakeDocument("SESSION-2", "tc://bom/W10", FakeNode.FlatTree(1));

            Assert.Null(cache.TryRead(reopened, 3));
        }
        finally { Directory.Delete(directory, true); }
    }

    [Fact]
    public void UnversionedSessionCacheDoesNotClaimCurrentRevisionIsVerified()
    {
        var directory = NewCacheDirectory("unversioned-session");
        try
        {
            var document = new FakeDocument("SESSION-1", "tc://bom/W10", FakeNode.FlatTree(1));
            var cache = new VisMockupTreeCache(Path.Combine(directory, "tree.db"));
            cache.Replace(document, 64, [new("node-0", null, 0, 0, "Root", "", false)]);

            Assert.Equal("verifying", cache.TryRead(document, 1)!.CacheState);
        }
        finally { Directory.Delete(directory, true); }
    }

    [Fact]
    public void StableProjectionCanBeShownAsVerifyingAcrossVisMockupSessions()
    {
        var directory = NewCacheDirectory("stable-reopen");
        try
        {
            var cache = new VisMockupTreeCache(Path.Combine(directory, "tree.db"));
            cache.Replace(
                new FakeDocument("SESSION-1", "tc://bom/W10", FakeNode.FlatTree(1)),
                64,
                [new("pdm:root", null, 0, 0, "W10", "", false)]);

            var reopened = new FakeDocument("SESSION-2", "tc://bom/W10", FakeNode.FlatTree(1));
            var value = cache.TryRead(reopened, 3);

            Assert.NotNull(value);
            Assert.Equal("verifying", value!.CacheState);
        }
        finally { Directory.Delete(directory, true); }
    }

    [Fact]
    public void TreeCacheRejectsAChangedLocalSourceRevision()
    {
        var directory = NewCacheDirectory("source-revision");
        var modelPath = Path.Combine(directory, "W10.vfz");
        File.WriteAllText(modelPath, "before");
        try
        {
            var cache = new VisMockupTreeCache(Path.Combine(directory, "tree.db"));
            var document = new FakeDocument("SESSION-1", modelPath, FakeNode.FlatTree(1));
            cache.Replace(document, 3, [new("root", null, 0, 0, "W10", "", false)]);
            Assert.NotNull(cache.TryRead(document, 3));

            File.AppendAllText(modelPath, "-after");
            File.SetLastWriteTimeUtc(modelPath, DateTime.UtcNow.AddMinutes(1));

            Assert.Null(cache.TryRead(document, 3));
        }
        finally { Directory.Delete(directory, true); }
    }

    [Fact]
    public void TreeCacheKeepsPriorCompleteGenerations()
    {
        var directory = NewCacheDirectory("generations");
        var modelPath = Path.Combine(directory, "W10.vfz");
        File.WriteAllText(modelPath, "model");
        var databasePath = Path.Combine(directory, "tree.db");
        try
        {
            var cache = new VisMockupTreeCache(databasePath);
            var document = new FakeDocument("SESSION-1", modelPath, FakeNode.FlatTree(1));
            cache.Replace(document, 3, [new("root", null, 0, 0, "Before", "", false)]);
            cache.Replace(document, 3, [new("root", null, 0, 0, "After", "", false)]);

            using (var connection = new SqliteConnection($"Data Source={databasePath};Pooling=False"))
            {
                connection.Open();
                using var command = connection.CreateCommand();
                command.CommandText = "SELECT COUNT(*) FROM vm_cache_generations";
                Assert.Equal(2L, (long)command.ExecuteScalar()!);
            }
            Assert.Equal("After", cache.TryRead(document, 3)!.Nodes[0].Name);
        }
        finally { Directory.Delete(directory, true); }
    }

    [Fact]
    public void FailedGenerationPublishLeavesThePreviousHeadReadable()
    {
        var directory = NewCacheDirectory("failed-generation");
        var modelPath = Path.Combine(directory, "W10.vfz");
        File.WriteAllText(modelPath, "model");
        try
        {
            var cache = new VisMockupTreeCache(Path.Combine(directory, "tree.db"));
            var document = new FakeDocument("SESSION-1", modelPath, FakeNode.FlatTree(1));
            cache.Replace(document, 3, [new("root", null, 0, 0, "Good", "", false)]);

            Assert.Throws<SqliteException>(() => cache.Replace(document, 3, [
                new("root", null, 0, 0, "Broken 1", "", false),
                new("root", null, 1, 0, "Broken 2", "", false),
            ]));

            Assert.Equal("Good", cache.TryRead(document, 3)!.Nodes[0].Name);
        }
        finally { Directory.Delete(directory, true); }
    }

    [Fact]
    public void LegacyCacheSchemaIsDiscardedInsteadOfTrustedAsFresh()
    {
        var directory = NewCacheDirectory("legacy-schema");
        var databasePath = Path.Combine(directory, "tree.db");
        try
        {
            using (var connection = new SqliteConnection($"Data Source={databasePath};Pooling=False"))
            {
                connection.Open();
                using var command = connection.CreateCommand();
                command.CommandText = "CREATE TABLE document_cache(document_identity TEXT PRIMARY KEY, max_depth INTEGER NOT NULL);";
                command.ExecuteNonQuery();
            }

            var cache = new VisMockupTreeCache(databasePath);
            var document = new FakeDocument("SESSION-1", "tc://bom/W10", FakeNode.FlatTree(1));

            Assert.Null(cache.TryRead(document, 3));
            using var migrated = new SqliteConnection($"Data Source={databasePath};Pooling=False");
            migrated.Open();
            using var table = migrated.CreateCommand();
            table.CommandText = "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='vm_cache_documents'";
            Assert.Equal(1L, (long)table.ExecuteScalar()!);
        }
        finally { Directory.Delete(directory, true); }
    }

    private static string NewCacheDirectory(string name)
    {
        var directory = Path.Combine(Path.GetTempPath(), $"ai00-vm-tree-cache-{name}-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        return directory;
    }
}
