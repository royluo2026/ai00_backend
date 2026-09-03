using Ai00.Connector.Contracts;

namespace Ai00.Connector.SessionHost;

public sealed class AdapterDispatcher(IEnumerable<IConnectorAdapter> adapters)
{
    private readonly IReadOnlyDictionary<string, IConnectorAdapter> _adapters = adapters
        .ToDictionary(item => item.Manifest.AdapterId, StringComparer.Ordinal);
    private readonly SemaphoreSlim _serial = new(1, 1);

    public async Task<ConnectorPlanOutcome> ExecuteAsync(
        ConnectorExecutionPlan plan,
        CancellationToken cancellationToken)
    {
        if (!_adapters.TryGetValue(plan.AdapterId, out var adapter) ||
            adapter.Manifest.AdapterMajor != plan.AdapterMajor)
            throw new ConnectorException("adapter_unavailable");

        await _serial.WaitAsync(cancellationToken);
        try
        {
            var results = new List<ConnectorStepResult>();
            foreach (var step in plan.Steps)
            {
                var startedAt = WholeSecond(DateTimeOffset.UtcNow);
                try
                {
                    var result = await adapter.ExecuteAsync(
                        new AdapterOperation(step.OperationId, step.Payload, step.StepId), cancellationToken);
                    var completedAt = WholeSecond(DateTimeOffset.UtcNow);
                    if (!result.Ok)
                    {
                        results.Add(new(step.StepId, "failed", null, null, result.ErrorCode, startedAt, completedAt));
                        return new(plan.Protocol, plan.PlanId, "failed", results, completedAt);
                    }
                    results.Add(new(
                        step.StepId, "completed", result.Data, CanonicalJson.Hash(result.Data), "",
                        startedAt, completedAt));
                }
                catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
                {
                    var completedAt = WholeSecond(DateTimeOffset.UtcNow);
                    results.Add(new(step.StepId, "outcome_unknown", null, null, "local_execution_outcome_unknown", startedAt, completedAt));
                    return new(plan.Protocol, plan.PlanId, "outcome_unknown", results, completedAt);
                }
                catch
                {
                    var completedAt = WholeSecond(DateTimeOffset.UtcNow);
                    results.Add(new(step.StepId, "outcome_unknown", null, null, "local_execution_outcome_unknown", startedAt, completedAt));
                    return new(plan.Protocol, plan.PlanId, "outcome_unknown", results, completedAt);
                }
            }
            return new(plan.Protocol, plan.PlanId, "completed", results, WholeSecond(DateTimeOffset.UtcNow));
        }
        finally
        {
            _serial.Release();
        }
    }

    private static DateTimeOffset WholeSecond(DateTimeOffset value) =>
        value.AddTicks(-(value.Ticks % TimeSpan.TicksPerSecond));
}
