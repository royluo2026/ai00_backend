using Xunit;

namespace Ai00.Connector.Tests;

public sealed class InstallerContractTests
{
    [Fact]
    public void InstallerRegistersServiceAndPerUserSessionHostWithoutInboundPort()
    {
        var wix = File.ReadAllText(SourceFile("installer", "Product.wxs"));

        Assert.Contains("Ai00ConnectorService", wix, StringComparison.Ordinal);
        Assert.Contains("Ai00ConnectorSessionHost", wix, StringComparison.Ordinal);
        Assert.Contains("LocalService", wix, StringComparison.Ordinal);
        Assert.Contains("AI00\\Connector", wix, StringComparison.Ordinal);
        Assert.DoesNotContain("FirewallException", wix, StringComparison.Ordinal);
    }

    private static string SourceFile(params string[] parts)
    {
        var directory = new DirectoryInfo(AppContext.BaseDirectory);
        while (directory is not null && !Directory.Exists(Path.Combine(directory.FullName, "installer")))
            directory = directory.Parent;
        Assert.NotNull(directory);
        return Path.Combine([directory!.FullName, .. parts]);
    }
}
