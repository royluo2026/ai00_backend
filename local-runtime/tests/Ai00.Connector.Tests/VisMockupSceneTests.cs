using Ai00.Connector.Adapters.VisMockup;
using Ai00.Connector.Contracts;
using System.Text.Json;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class VisMockupSceneTests
{
    [Fact]
    public async Task ApplyUsesCompleteExpectedSetsAndConvergesOnReplay()
    {
        var root = new FakeNode("root", "Root", "root", "root", [
            new FakeNode("P-1", "P1", "P1", "P1", []),
            new FakeNode("P-2", "P2", "P2", "P2", []),
            new FakeNode("T-1", "T1", "T1", "T1", []),
        ]);
        var document = new FakeDocument("BOM-1", "tc://bom/1", root);
        var fake = new FakeVisMockupCom { ExistingApplication = new FakeApplication("14.2.0", document) };
        using var sta = new StaDispatcher();
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([Path.GetTempPath()]), fake);
        var scene = SceneState.Create("op-10", ["P-1", "P-2"], ["T-1"], new("png", 1, 1, "current"));

        await adapter.ApplySceneAsync("BOM-1", scene);
        await adapter.ApplySceneAsync("BOM-1", scene);

        Assert.Equal(["P-1", "P-2", "T-1"], document.VisibleNodeKeys.Order(StringComparer.Ordinal));
        Assert.Equal(scene.SceneHash, (await adapter.VerifySceneAsync("BOM-1", "op-10", scene.SceneHash)).ActualSceneHash);
    }

    [Fact]
    public async Task VerifyRejectsUnexpectedVisibleNodes()
    {
        var root = new FakeNode("root", "Root", "root", "root", [
            new FakeNode("P-1", "P1", "P1", "P1", []),
            new FakeNode("P-2", "P2", "P2", "P2", []),
        ]);
        var document = new FakeDocument("BOM-1", "tc://bom/1", root);
        var fake = new FakeVisMockupCom { ExistingApplication = new FakeApplication("14.2.0", document) };
        using var sta = new StaDispatcher();
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([Path.GetTempPath()]), fake);
        var scene = SceneState.Create("op-10", ["P-1"], [], new("png", 1, 1, "current"));
        await adapter.ApplySceneAsync("BOM-1", scene);

        document.SetNodeVisible("P-2", true);

        Assert.False((await adapter.VerifySceneAsync("BOM-1", "op-10", scene.SceneHash)).Matches);
    }

    [Fact]
    public async Task GovernedApplyRequiresUnchangedBaselineSnapshot()
    {
        var document = new FakeDocument("BOM-1", "tc://bom/1", FakeNode.FlatTree(2));
        var fake = new FakeVisMockupCom { ExistingApplication = new FakeApplication("14.2.0", document) };
        using var sta = new StaDispatcher();
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([Path.GetTempPath()]), fake);
        var scene = SceneState.Create("op-10", ["node-1"], [], new("png", 1, 1, "current"));
        var payload = JsonSerializer.SerializeToElement(new
        {
            document_id = "BOM-1",
            baseline_snapshot_hash = "sha256:" + new string('0', 64),
            scene = new
            {
                operation_id = scene.OperationId,
                visible_products = scene.VisibleProducts,
                visible_resources = scene.VisibleResources,
                capture_profile = new { format = "png", width = 1, height = 1, background = "current" },
                scene_hash = scene.SceneHash,
            },
        });

        var error = await Assert.ThrowsAsync<ConnectorException>(() => adapter.ExecuteAsync(
            new AdapterOperation("vismockup.scene.apply@1", payload, "apply-op-10"), default));

        Assert.Equal("vismockup_document_changed", error.Code);
    }
}
