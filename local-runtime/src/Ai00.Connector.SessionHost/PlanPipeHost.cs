using System.IO.Pipes;
using System.Text.Json;
using Ai00.Connector.Contracts;

namespace Ai00.Connector.SessionHost;

public sealed class ValidatedPlanDispatcher(
    IEnumerable<IConnectorAdapter> adapters,
    IReadOnlyDictionary<string, string> signingKeys)
{
    private readonly IReadOnlyDictionary<string, IConnectorAdapter> _adapters = adapters
        .ToDictionary(item => item.Manifest.AdapterId, StringComparer.Ordinal);
    private readonly AdapterDispatcher _dispatcher = new(adapters);

    public async Task<ConnectorPlanOutcome> ExecuteAsync(
        ConnectorPlanExecutionRequest request,
        CancellationToken cancellationToken)
    {
        if (!_adapters.TryGetValue(request.Plan.AdapterId, out var adapter))
            return Rejected(request.Plan, "adapter_unavailable");
        var validation = PlanValidator.Validate(
            request.Plan,
            adapter.Manifest,
            new(request.DeviceId, request.UserId, DateTimeOffset.UtcNow,
                request.KeyId, request.Signature, signingKeys));
        if (!validation.IsValid)
            return Rejected(request.Plan, validation.ErrorCode);
        return await _dispatcher.ExecuteAsync(request.Plan, cancellationToken);
    }

    private static ConnectorPlanOutcome Rejected(ConnectorExecutionPlan plan, string code)
    {
        var now = DateTimeOffset.UtcNow;
        now = now.AddTicks(-(now.Ticks % TimeSpan.TicksPerSecond));
        return new(plan.Protocol, plan.PlanId, "failed", [], now);
    }
}

public sealed class PlanPipeHost(
    ValidatedPlanDispatcher dispatcher,
    string pipeName)
{
    public async Task RunAsync(CancellationToken cancellationToken)
    {
        while (!cancellationToken.IsCancellationRequested)
        {
            await using var pipe = new NamedPipeServerStream(
                pipeName, PipeDirection.InOut, 1, PipeTransmissionMode.Byte,
                PipeOptions.Asynchronous | PipeOptions.CurrentUserOnly, 64 * 1024, 64 * 1024);
            await pipe.WaitForConnectionAsync(cancellationToken);
            var request = await JsonSerializer.DeserializeAsync<ConnectorPlanExecutionRequest>(
                pipe, cancellationToken: cancellationToken);
            var outcome = request is null
                ? throw new ConnectorException("connector_plan_request_invalid")
                : await dispatcher.ExecuteAsync(request, cancellationToken);
            await JsonSerializer.SerializeAsync(pipe, outcome, cancellationToken: cancellationToken);
            await pipe.FlushAsync(cancellationToken);
        }
    }
}
