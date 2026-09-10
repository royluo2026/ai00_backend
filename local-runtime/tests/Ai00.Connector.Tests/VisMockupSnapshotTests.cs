using Ai00.Connector.Adapters.VisMockup;
using Ai00.Connector.Contracts;
using Microsoft.Data.Sqlite;
using System.Text.Json;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class VisMockupSnapshotTests
{
    private sealed class CountingNode(
        string nodeKey, IReadOnlyList<IVisMockupNode> children) : IVisMockupNode
    {
        public string NodeKey => nodeKey;
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

        Assert.Equal("sha256:25ac87b341ef76d657c627b45bc0c4de129f55b92e01401dd6f2cd8649dd2f16", operation.ContractHash);
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
            Assert.Equal(2, JsonSerializer.SerializeToElement(cached.Data).GetProperty("nodes").GetArrayLength());
            Assert.True(File.Exists(Path.Combine(directory, "vismockup-tree-cache.db")));
        }
        finally { Directory.Delete(directory, true); }
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
            cache.Replace(firstSession, 3, [new("root", null, 0, 0, "W10", "", false)]);

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
