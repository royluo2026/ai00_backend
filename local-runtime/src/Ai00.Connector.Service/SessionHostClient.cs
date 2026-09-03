using System.IO.Pipes;
using System.Text.Json;
using Ai00.Connector.Contracts;

namespace Ai00.Connector.Service;

public sealed class SessionHostClient(IDeviceCredentialStore credentialStore)
{
    public async Task<OperationCompletion> ExecuteAsync(LocalExecutionRequest request, CancellationToken cancellationToken)
    {
        var envelope = request.Lease;
        var operation = envelope.Operation;
        if (!RuntimeCapabilities.Allowed.Contains(operation.CapabilityId))
            return new(operation.OperationId, "failed", ErrorCode: "capability_not_allowed");
        if (operation.ExpiresAt <= DateTimeOffset.UtcNow)
            return new(operation.OperationId, "failed", ErrorCode: "operation_expired");

        var credential = credentialStore.Load();
        await using var pipe = new NamedPipeClientStream(".", ConnectorPipeName.For(credential.DeviceId, credential.WindowsSid), PipeDirection.InOut, PipeOptions.Asynchronous);
        await pipe.ConnectAsync(5_000, cancellationToken);
        await JsonSerializer.SerializeAsync(pipe, request, cancellationToken: cancellationToken);
        await pipe.FlushAsync(cancellationToken);
        var result = await JsonSerializer.DeserializeAsync<OperationCompletion>(pipe, cancellationToken: cancellationToken);
        return result ?? new(operation.OperationId, "outcome_unknown", ErrorCode: "session_host_no_result");
    }
}
