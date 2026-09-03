using Ai00.Connector.Contracts;

namespace Ai00.Connector.Service;

public sealed record LeasedConnectorPlan(
    string LeaseId,
    ConnectorExecutionPlan Plan,
    string KeyId,
    string Signature);

public interface IConnectorPlanGateway
{
    Task<LeasedConnectorPlan?> LeaseAsync(CancellationToken cancellationToken);
    Task ReconcileAsync(PlanReconciliation reconciliation, CancellationToken cancellationToken);
}

public interface IConnectorPlanExecutor
{
    Task<SignedConnectorPlanOutcome> ExecuteAsync(LeasedConnectorPlan plan, CancellationToken cancellationToken);
}

public sealed class PowerGuardedPlanExecutor(
    IConnectorPlanExecutor inner,
    ISystemPowerGuard power) : IConnectorPlanExecutor
{
    public async Task<SignedConnectorPlanOutcome> ExecuteAsync(
        LeasedConnectorPlan plan,
        CancellationToken cancellationToken)
    {
        using var lease = power.Acquire(plan.Plan.PlanId);
        return await inner.ExecuteAsync(plan, cancellationToken);
    }
}

public sealed class PlanWorker(
    PlanJournal journal,
    IConnectorPlanGateway gateway,
    IConnectorPlanExecutor executor)
{
    public async Task StartOnceAsync(CancellationToken cancellationToken)
    {
        var pending = journal.FirstUnreconciled();
        if (pending is not null)
        {
            await gateway.ReconcileAsync(pending, cancellationToken);
            journal.MarkReconciled(pending.PlanId);
            return;
        }

        var leased = await gateway.LeaseAsync(cancellationToken);
        if (leased is null) return;
        var retained = await AcceptAsync(leased, cancellationToken);
        if (retained is not null)
        {
            await gateway.ReconcileAsync(new(leased.Plan.PlanId, PlanState.Completed, retained), cancellationToken);
            journal.MarkReconciled(leased.Plan.PlanId);
        }
    }

    public Task<SignedConnectorPlanOutcome?> AcceptAsync(
        ConnectorExecutionPlan plan,
        CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        return Task.FromResult(journal.RetainedOutcome(plan.PlanId));
    }

    private async Task<SignedConnectorPlanOutcome?> AcceptAsync(
        LeasedConnectorPlan leased,
        CancellationToken cancellationToken)
    {
        var retained = journal.RetainedOutcome(leased.Plan.PlanId);
        if (retained is not null) return retained;
        journal.Admit(leased.Plan);
        var outcome = await executor.ExecuteAsync(leased, cancellationToken);
        journal.RecordCompleted(leased.Plan.PlanId, outcome);
        return outcome;
    }
}

public sealed class ConnectorPlanBackgroundWorker(
    PlanWorker worker,
    Microsoft.Extensions.Options.IOptions<RuntimeOptions> options,
    ILogger<ConnectorPlanBackgroundWorker> logger) : BackgroundService
{
    private readonly RuntimeOptions _options = options.Value;

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                await worker.StartOnceAsync(stoppingToken);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested) { break; }
            catch (Exception ex) { logger.LogWarning(ex, "Simulation Connector Plan loop failed"); }
            await Task.Delay(TimeSpan.FromSeconds(Math.Clamp(_options.PollSeconds, 1, 60)), stoppingToken);
        }
    }
}
