using Ai00.Connector.Adapters.VisMockup;
using Xunit;
namespace Ai00.Connector.Tests;
public sealed class VisMockupBreakawayTests
{
    [Fact] public void UnsignedOrNonAllowlistedExecutableIsRejectedBeforeLaunch()
    {
        Assert.ThrowsAny<Exception>(()=>new VisMockupBreakawayLauncher(@"C:\untrusted\vis.exe","publisher").Launch());
    }
    [Fact] public void ExistingApplicationIsNeverRelaunched()
    {
        var com=new FakeVisMockupCom{ExistingApplication=FakeVisMockupCom.WithDocument("existing")};
        var connection=new VisMockupConnection(com);
        Assert.Same(com.ExistingApplication,connection.RequireActiveApplication(true));
        Assert.Equal(0,com.LaunchCalls);
    }
    [Fact] public async Task ReconciliationRejectsUndeclaredProbeWithoutCom()
    {
        var com=new FakeVisMockupCom();using var sta=new StaDispatcher();
        var probes=new PostConditionProbes(sta,com);
        await Assert.ThrowsAnyAsync<Exception>(()=>probes.ObserveAsync("vismockup.model.open@1",null,CancellationToken.None));
        Assert.Empty(com.ThreadIds);Assert.Equal(0,com.LaunchCalls);
    }
    [Theory]
    [InlineData(false, true, "failed_without_effect")]
    [InlineData(true, true, "succeeded")]
    public async Task VisibilityRecoveryProbeClassifiesTheObservedNodeState(
        bool actualVisible, bool expectedVisible, string expectedClassification)
    {
        var document = new FakeDocument("document", "user", FakeNode.FlatTree(1));
        if (actualVisible) document.SetNodeVisible("node-0", true);
        var com = new FakeVisMockupCom
        {
            ExistingApplication = new FakeApplication("14.2.0", document),
        };
        using var sta = new StaDispatcher();
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([Path.GetTempPath()]), com);
        var probes = new PostConditionProbes(sta, com, adapter);
        var input = System.Text.Json.JsonSerializer.SerializeToElement(
            new { node_key = "node-0", expected_visible = expectedVisible });

        var result = await probes.ObserveAsync(
            "vismockup.document.snapshot@1", input, CancellationToken.None);

        Assert.Contains($"classification = {expectedClassification}", result.ToString());
    }

    [Fact]
    public async Task VisibilityRecoveryHasNoLingeringEffectAfterTheTargetDocumentWasClosed()
    {
        var directory = Path.Combine(Path.GetTempPath(), "ai00-recovery-closed-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        try
        {
            var document = new FakeDocument("other", "tc://other", FakeNode.FlatTree(1));
            var com = new FakeVisMockupCom { ExistingApplication = new FakeApplication("14.2.0", document) };
            using var sta = new StaDispatcher();
            var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([directory]), com,
                Path.Combine(directory, "captures"), Path.Combine(directory, "tree.db"));
            var probes = new PostConditionProbes(sta, com, adapter);
            var input = System.Text.Json.JsonSerializer.SerializeToElement(
                new { node_key = "pdm:closed-document-node", expected_visible = true });

            var result = await probes.ObserveAsync(
                "vismockup.document.snapshot@1", input, CancellationToken.None);

            Assert.Contains("classification = failed_without_effect", result.ToString());
        }
        finally { Directory.Delete(directory, true); }
    }
}
