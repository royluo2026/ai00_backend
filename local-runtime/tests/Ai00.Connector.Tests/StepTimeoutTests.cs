using System.Text.Json;
using Ai00.Connector.Contracts;
using Ai00.Connector.SessionHost;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class StepTimeoutTests
{
    [Fact]
    public async Task DispatcherEnforcesSignedStepTimeoutAsOutcomeUnknown()
    {
        var adapter = new BlockingAdapter();
        var payload = JsonSerializer.SerializeToElement(new { });
        var step = new ConnectorStep("step-1", "test.block@1", "sha256:" + new string('a', 64), [], payload, CanonicalJson.Hash(payload), 1);
        var plan = new ConnectorExecutionPlan("ai00.connector.execution-plan.v1", "plan-1", "tenant-1", "user-1", "device-1", "capability-1", "sha256:" + new string('b', 64), adapter.Manifest.AdapterId, 1, new("test.product", "1.0.0", "2.0.0"), [step], DateTimeOffset.UtcNow, DateTimeOffset.UtcNow.AddMinutes(1), "unused");

        var outcome = await new AdapterDispatcher([adapter]).ExecuteAsync(plan, default);

        Assert.Equal("outcome_unknown", outcome.Status);
        Assert.Equal("step_timeout_outcome_unknown", outcome.Steps[0].ErrorCode);
    }

    private sealed class BlockingAdapter : IConnectorAdapter
    {
        public AdapterManifest Manifest { get; } = new("test.adapter", 1, "test.product", "1.1.0", [new("test.block@1", "sha256:" + new string('a', 64))]);
        public Task<AdapterHealth> ProbeAsync(CancellationToken cancellationToken) => Task.FromResult(new AdapterHealth(true, "ready"));
        public async Task<AdapterResult> ExecuteAsync(AdapterOperation operation, CancellationToken cancellationToken)
        {
            await Task.Delay(Timeout.InfiniteTimeSpan, cancellationToken);
            return new(true);
        }
    }
}
