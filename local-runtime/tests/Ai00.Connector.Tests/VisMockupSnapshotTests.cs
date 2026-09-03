using Ai00.Connector.Adapters.VisMockup;
using Ai00.Connector.Contracts;
using System.Text.Json;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class VisMockupSnapshotTests
{
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
}
