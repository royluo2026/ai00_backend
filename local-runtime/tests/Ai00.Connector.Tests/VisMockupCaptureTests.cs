using Ai00.Connector.Adapters.VisMockup;
using Ai00.Connector.Contracts;
using System.Text.Json;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class VisMockupCaptureTests : IDisposable
{
    private readonly string _directory = Path.Combine(Path.GetTempPath(), "ai00-capture-tests", Guid.NewGuid().ToString("N"));

    [Fact]
    public async Task CaptureUsesVisMockupActiveViewAndReturnsPngMetadata()
    {
        var document = new FakeDocument("BOM-1", "tc://bom/1", FakeNode.FlatTree(1));
        var fake = new FakeVisMockupCom { ExistingApplication = new FakeApplication("14.2.0", document) };
        using var sta = new StaDispatcher();
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([Path.GetTempPath()]), fake, _directory);

        var artifact = await adapter.CaptureAsync(new CaptureRequest("run-1", "step-1", "op-10", 1, new("png", 1, 1, "current")));

        Assert.Equal(1, document.CaptureImageCalls);
        Assert.Equal("image/png", artifact.MediaType);
        Assert.Equal(1, artifact.Width);
        Assert.Equal(1, artifact.Height);
        Assert.True(File.Exists(artifact.Path));
    }

    [Fact]
    public async Task GovernedCaptureUsesPlanStepIdAndCreatesAttemptSpecificFiles()
    {
        var document = new FakeDocument("BOM-1", "tc://bom/1", FakeNode.FlatTree(1));
        var fake = new FakeVisMockupCom { ExistingApplication = new FakeApplication("14.2.0", document) };
        using var sta = new StaDispatcher();
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([Path.GetTempPath()]), fake, _directory);
        var payload = JsonSerializer.SerializeToElement(new
        {
            capture_run_id = "run-1", operation_id = "op-10", attempt = 2,
            format = "png", width = 1, height = 1, background = "current",
        });

        var result = await adapter.ExecuteAsync(
            new AdapterOperation("vismockup.view.capture@1", payload, "capture-step-7"), default);
        var artifact = Assert.IsType<LocalCaptureArtifact>(result.Data);

        Assert.EndsWith("capture-step-7-attempt-2.png", artifact.Path, StringComparison.Ordinal);
    }

    public void Dispose()
    {
        if (Directory.Exists(_directory)) Directory.Delete(_directory, true);
    }
}
