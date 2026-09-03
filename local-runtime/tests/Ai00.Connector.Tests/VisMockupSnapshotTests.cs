using Ai00.Connector.Adapters.VisMockup;
using Ai00.Connector.Contracts;
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
}
