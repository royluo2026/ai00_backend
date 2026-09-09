using Ai00.Connector.Adapters.VisMockup;
using Ai00.Connector.Contracts;
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
        public string OccurrenceId => nodeKey;
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
}
