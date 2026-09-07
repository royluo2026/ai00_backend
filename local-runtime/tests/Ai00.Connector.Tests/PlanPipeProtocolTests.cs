using Xunit;

namespace Ai00.Connector.Tests;

public sealed class PlanPipeProtocolTests
{
    [Fact]
    public void DuplexPlanPipeUsesExplicitJsonMessageBoundaries()
    {
        var root = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", ".."));
        var client = File.ReadAllText(Path.Combine(root, "src", "Ai00.Connector.Service", "PlanSessionHostClient.cs"));
        var host = File.ReadAllText(Path.Combine(root, "src", "Ai00.Connector.SessionHost", "PlanPipeHost.cs"));

        Assert.Contains("WriteLineAsync", client);
        Assert.Contains("ReadLineAsync", client);
        Assert.Contains("WriteLineAsync", host);
        Assert.Contains("ReadLineAsync", host);
        Assert.DoesNotContain("SerializeAsync(pipe", client);
        Assert.DoesNotContain("DeserializeAsync<ConnectorPlanOutcome>", client);
        Assert.DoesNotContain("DeserializeAsync<ConnectorPlanExecutionRequest>", host);
    }
}
