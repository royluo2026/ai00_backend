using System.IO.Pipes;
using System.Text.Json;
using Ai00.Connector.Contracts;

namespace Ai00.Connector.Service;

public sealed class PlanSessionHostClient(
    IDeviceCredentialStore credentialStore,
    ConnectorGatewayClient gateway) : IConnectorPlanExecutor
{
    public async Task<SignedConnectorPlanOutcome> ExecuteAsync(
        LeasedConnectorPlan lease,
        CancellationToken cancellationToken)
    {
        var credential = credentialStore.Load();
        var artifacts = await gateway.PrepareArtifactsAsync(lease, cancellationToken);
        await using var pipe = new NamedPipeClientStream(
            ".", ConnectorPipeName.PlanFor(credential.DeviceId, credential.WindowsSid),
            PipeDirection.InOut, PipeOptions.Asynchronous);
        await pipe.ConnectAsync(5_000, cancellationToken);
        var request = new ConnectorPlanExecutionRequest(
            lease.LeaseId, lease.Plan, lease.KeyId, lease.Signature,
            credential.DeviceId, credential.UserId, artifacts);
        await JsonSerializer.SerializeAsync(pipe, request, cancellationToken: cancellationToken);
        await pipe.FlushAsync(cancellationToken);
        var outcome = await JsonSerializer.DeserializeAsync<ConnectorPlanOutcome>(
            pipe, cancellationToken: cancellationToken)
            ?? throw new ConnectorException("session_host_no_result");
        var projected = await gateway.UploadCaptureResultsAsync(lease, outcome, cancellationToken);
        return new(
            projected,
            ConnectorOutcomeSecurity.Sign(projected, credential.DeviceToken),
            lease.LeaseId);
    }
}
