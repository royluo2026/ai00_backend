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
        await Assert.ThrowsAnyAsync<Exception>(()=>probes.ObserveAsync("vismockup.model.open@1",CancellationToken.None));
        Assert.Empty(com.ThreadIds);Assert.Equal(0,com.LaunchCalls);
    }
}
