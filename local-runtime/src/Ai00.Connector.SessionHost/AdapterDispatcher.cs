using Ai00.Connector.Contracts;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Ai00.Connector.SessionHost;

public sealed class AdapterDispatcher(IEnumerable<IConnectorAdapter> adapters)
{
    private readonly IReadOnlyDictionary<string, IConnectorAdapter> _adapters = adapters
        .ToDictionary(item => item.Manifest.AdapterId, StringComparer.Ordinal);
    private readonly SemaphoreSlim _serial = new(1, 1);

    public async Task<ConnectorPlanOutcome> ExecuteAsync(
        ConnectorExecutionPlan plan, CancellationToken cancellationToken,
        IReadOnlyList<MaterializedArtifact>? materializedArtifacts = null)
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
                    var payload = MaterializePayload(step, materializedArtifacts ?? []);
                    var result = await adapter.ExecuteAsync(
                        new AdapterOperation(step.OperationId, payload, step.StepId, step.ContractHash), cancellationToken);
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

    private static JsonElement MaterializePayload(
        ConnectorStep step, IReadOnlyList<MaterializedArtifact> artifacts)
    {
        if (step.OperationId != "vismockup.model.attach@1") return step.Payload;
        var root = JsonNode.Parse(step.Payload.GetRawText())?.AsObject()
            ?? throw new ConnectorException("artifact_materialization_required");
        var binding = root["binding"]?.AsObject()
            ?? throw new ConnectorException("resource_binding_invalid");
        var artifactId = binding["model_ref"]?["artifact_ref"]?["artifact_id"]?.GetValue<string>() ?? "";
        var materialized = artifacts.SingleOrDefault(item => item.ArtifactId == artifactId)
            ?? throw new ConnectorException("artifact_materialization_required");
        binding["local_artifact_path"] = materialized.CachePath;
        return JsonSerializer.SerializeToElement(root);
    }
}
