using Ai00.Connector.Contracts;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class ProductBoundaryTests
{
    [Fact]
    public void ProductAssembliesUseConnectorName()
    {
        var names = typeof(ConnectorExecutionPlan).Assembly
            .GetReferencedAssemblies()
            .Select(item => item.Name);

        Assert.DoesNotContain(
            names,
            name => name!.StartsWith("Ai00.LocalRuntime", StringComparison.Ordinal));
    }
}
