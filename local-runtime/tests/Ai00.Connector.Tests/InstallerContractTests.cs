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
        Assert.Contains("ComponentGroupRef Id=\"Ai00ConnectorServicePayload\"", wix, StringComparison.Ordinal);
        Assert.Contains("$(var.ServicePublishDir)\\**", wix, StringComparison.Ordinal);
        Assert.Contains("CurrentVersion\\Run", wix, StringComparison.Ordinal);
        Assert.Contains("AI00 Connector SessionHost", wix, StringComparison.Ordinal);
        Assert.DoesNotContain("FirewallException", wix, StringComparison.Ordinal);

        var settings = File.ReadAllText(SourceFile("appsettings.example.json"));
        Assert.Contains("\"Connector\"", settings, StringComparison.Ordinal);
        Assert.DoesNotContain("\"LocalRuntime\"", settings, StringComparison.Ordinal);

        var planPipe = File.ReadAllText(SourceFile("src", "Ai00.Connector.SessionHost", "PlanPipeHost.cs"));
        Assert.DoesNotContain("PipeOptions.CurrentUserOnly", planPipe, StringComparison.Ordinal);
        Assert.Contains("LocalServiceSid", planPipe, StringComparison.Ordinal);
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
