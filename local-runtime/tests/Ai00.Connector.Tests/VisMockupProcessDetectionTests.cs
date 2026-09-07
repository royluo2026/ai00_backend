using Ai00.Connector.Adapters.VisMockup;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class VisMockupProcessDetectionTests
{
    [Theory]
    [InlineData("VisView", "VisView")]
    [InlineData("VisView", "VisView_NG")]
    [InlineData("visview", "VISVIEW_NG")]
    public void MatchesLauncherAndRuntimeProcessNames(string configuredName, string runningName)
    {
        Assert.True(WindowsVisMockupCom.MatchesProcessName(configuredName, runningName));
    }

    [Fact]
    public void DoesNotMatchUnrelatedProcesses()
    {
        Assert.False(WindowsVisMockupCom.MatchesProcessName("VisView", "OtherViewer"));
    }
}
