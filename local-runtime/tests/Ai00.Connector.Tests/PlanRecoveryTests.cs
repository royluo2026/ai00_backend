using System.Text.Json;
using Ai00.Connector.Contracts;
using Ai00.Connector.Service;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class PlanRecoveryTests : IDisposable
{
    private readonly string _directory = Path.Combine(Path.GetTempPath(), "ai00-plan-journal-tests", Guid.NewGuid().ToString("N"));

    [Fact]
    public async Task RestartReconcilesStartedStepBeforeLeasingAnotherPlan()
    {
        var journal = new PlanJournal(Path.Combine(_directory, "journal.json"));
        journal.Admit(Plan());
        journal.RecordStarted("plan-001", "step-1");
        journal = new PlanJournal(Path.Combine(_directory, "journal.json"));
        var gateway = new RecordingPlanGateway();
        var worker = new PlanWorker(journal, gateway, new NoopPlanExecutor());

        await worker.StartOnceAsync(default);

        Assert.Equal("plan-001", gateway.FirstReconciliation!.PlanId);
        Assert.Equal(0, gateway.LeaseCallsBeforeReconciliation);
    }

    [Fact]
    public async Task CompletedPlanReplayReturnsRetainedSignedOutcome()
    {
        var journal = new PlanJournal(Path.Combine(_directory, "journal.json"));
        var outcome = new SignedConnectorPlanOutcome(
            new ConnectorPlanOutcome(ConnectorExecutionPlan.ProtocolVersion, "plan-001", "completed", [], DateTimeOffset.Parse("2026-09-03T00:01:00Z")),
            "hmac-sha256:" + new string('a', 64), "lease-1");
        journal.Admit(Plan());
        journal.RecordCompleted("plan-001", outcome);
        var worker = new PlanWorker(journal, new RecordingPlanGateway(), new NoopPlanExecutor());

        Assert.Equal(outcome, await worker.AcceptAsync(Plan(), default));
    }

    [Fact]
    public void LeasedPlanCarriesTheServerSignatureNeededForAdmission()
    {
        var lease = new LeasedConnectorPlan(
            "lease-1", Plan(), "connector-plan-key-1", "hmac-sha256:" + new string('a', 64));

        Assert.Equal("connector-plan-key-1", lease.KeyId);
        Assert.StartsWith("hmac-sha256:", lease.Signature);
    }

    private static ConnectorExecutionPlan Plan()
    {
        using var vector = JsonDocument.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "connector_execution_plan_v1.json")));
        return vector.RootElement.GetProperty("plan").Deserialize<ConnectorExecutionPlan>()!;
    }

    public void Dispose()
    {
        if (Directory.Exists(_directory)) Directory.Delete(_directory, true);
    }

    private sealed class RecordingPlanGateway : IConnectorPlanGateway
    {
        public PlanReconciliation? FirstReconciliation { get; private set; }
        public int LeaseCallsBeforeReconciliation { get; private set; }
        public Task ReconcileAsync(PlanReconciliation reconciliation, CancellationToken cancellationToken)
        {
            FirstReconciliation ??= reconciliation;
            return Task.CompletedTask;
        }
        public Task<LeasedConnectorPlan?> LeaseAsync(CancellationToken cancellationToken)
        {
            if (FirstReconciliation is null) LeaseCallsBeforeReconciliation++;
            return Task.FromResult<LeasedConnectorPlan?>(null);
        }
    }

    private sealed class NoopPlanExecutor : IConnectorPlanExecutor
    {
        public Task<SignedConnectorPlanOutcome> ExecuteAsync(LeasedConnectorPlan plan, CancellationToken cancellationToken) =>
            throw new InvalidOperationException("not expected");
    }
}
