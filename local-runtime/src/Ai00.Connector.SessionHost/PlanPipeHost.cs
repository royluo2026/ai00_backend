using System.IO.Pipes;
using System.Text;
using System.Text.Json;
using System.Security.AccessControl;
using System.Security.Principal;
using Ai00.Connector.Contracts;

namespace Ai00.Connector.SessionHost;

public sealed class ValidatedPlanDispatcher(
    IEnumerable<IConnectorAdapter> adapters)
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
        var validation = PlanValidator.ValidateAdapter(request.Plan, adapter.Manifest);
        if (!validation.IsValid)
            return Rejected(request.Plan, validation.ErrorCode);
        return await _dispatcher.ExecuteAsync(
            request.Plan, cancellationToken, request.MaterializedArtifacts ?? []);
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
            var security = new System.IO.Pipes.PipeSecurity();
            security.AddAccessRule(new PipeAccessRule(
                new SecurityIdentifier(WellKnownSidType.LocalServiceSid, null),
                PipeAccessRights.ReadWrite, AccessControlType.Allow));
            await using var pipe = NamedPipeServerStreamAcl.Create(
                pipeName, PipeDirection.InOut, 1, PipeTransmissionMode.Byte,
                PipeOptions.Asynchronous, 64 * 1024, 64 * 1024, security);
            await pipe.WaitForConnectionAsync(cancellationToken);
            using var reader = new StreamReader(pipe, Encoding.UTF8, false, 64 * 1024, leaveOpen: true);
            using var writer = new StreamWriter(pipe, new UTF8Encoding(false), 64 * 1024, leaveOpen: true)
            {
                AutoFlush = true,
            };
            var requestJson = await reader.ReadLineAsync(cancellationToken);
            var request = string.IsNullOrWhiteSpace(requestJson)
                ? null
                : JsonSerializer.Deserialize<ConnectorPlanExecutionRequest>(requestJson);
            var outcome = request is null
                ? throw new ConnectorException("connector_plan_request_invalid")
                : await dispatcher.ExecuteAsync(request, cancellationToken);
            await writer.WriteLineAsync(JsonSerializer.Serialize(outcome).AsMemory(), cancellationToken);
        }
    }

}
