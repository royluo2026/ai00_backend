using System.Text.Json;
using Ai00.Connector.Adapters.VisMockup;
using Ai00.Connector.Contracts;
using Ai00.Connector.SessionHost;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class ServerContractTests : IDisposable
{
    private readonly string _captures = Path.Combine(Path.GetTempPath(), "ai00-server-contract", Guid.NewGuid().ToString("N"));

    [Fact]
    public async Task ServerPlanCompletesReverseCaptureAndAttachesEachResultExactlyOnce()
    {
        var document = new FakeDocument("BOM-1", "tc://bom/1", FakeNode.FlatTree(1));
        var fakeCom = new FakeVisMockupCom { ExistingApplication = new FakeApplication("14.2.0", document) };
        using var sta = new StaDispatcher();
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([Path.GetTempPath()]), fakeCom, _captures);
        var contract = adapter.Manifest.Operations.Single(item => item.OperationId == "vismockup.view.capture@1");
        var operationIds = new[] { "op-30", "op-20", "op-10" };
        var steps = operationIds.Select((operationId, index) =>
        {
            var payload = JsonSerializer.SerializeToElement(new
            {
                capture_run_id = "capture-1", operation_id = operationId, attempt = 1,
                format = "png", width = 1, height = 1, background = "current",
            });
            return new ConnectorStep(
                $"capture-{operationId}", contract.OperationId, contract.ContractHash,
                index == 0 ? [] : [$"capture-{operationIds[index - 1]}"], payload,
                CanonicalJson.Hash(payload), 30);
        }).ToArray();
        var plan = new ConnectorExecutionPlan(
            ConnectorExecutionPlan.ProtocolVersion, "capture-1", "tenant-1", "user-1", "device-1",
            "capability-version-1", "sha256:" + new string('a', 64), adapter.Manifest.AdapterId, 1,
            new("siemens.vismockup", "14.0.0", "15.0.0"), steps,
            DateTimeOffset.UtcNow, DateTimeOffset.UtcNow.AddMinutes(5), "not-used-by-dispatcher");

        var outcome = await new AdapterDispatcher([adapter]).ExecuteAsync(plan, default);
        var craft = new FakeCraftScreenshotArea();
        foreach (var step in outcome.Steps)
        {
            var artifact = Assert.IsType<LocalCaptureArtifact>(step.Result);
            craft.Attach(step.StepId, artifact.Sha256);
            craft.Attach(step.StepId, artifact.Sha256);
        }

        Assert.Equal("completed", outcome.Status);
        Assert.Equal(["capture-op-30", "capture-op-20", "capture-op-10"], outcome.Steps.Select(item => item.StepId));
        Assert.Equal(3, craft.Attachments.Count);
        Assert.Equal(3, document.CaptureImageCalls);
    }

    public void Dispose()
    {
        if (Directory.Exists(_captures)) Directory.Delete(_captures, true);
    }

    private sealed class FakeCraftScreenshotArea
    {
        public Dictionary<string, string> Attachments { get; } = new(StringComparer.Ordinal);
        public void Attach(string stepId, string artifactHash) => Attachments.TryAdd(stepId, artifactHash);
    }
}
