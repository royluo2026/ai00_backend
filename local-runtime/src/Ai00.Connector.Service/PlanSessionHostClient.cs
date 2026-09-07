using System.IO.Pipes;
using System.Text;
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
        var signingKeys = ProtectedSecretStore.Load(Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),
            "AI00", "Connector", "operation.keys"));
        var validation = PlanValidator.ValidateSecurity(
            lease.Plan,
            new(credential.DeviceId, credential.UserId, DateTimeOffset.UtcNow,
                lease.KeyId, lease.Signature, signingKeys));
        if (!validation.IsValid)
            throw new ConnectorException(validation.ErrorCode);
        var artifacts = await gateway.PrepareArtifactsAsync(lease, cancellationToken);
        await SessionHostBrokerClient.EnsureStartedAsync(new(
            credential.DeviceId, credential.UserId, credential.WindowsSid), cancellationToken);
        await using var pipe = new NamedPipeClientStream(
            ".", ConnectorPipeName.PlanFor(credential.DeviceId, credential.WindowsSid),
            PipeDirection.InOut, PipeOptions.Asynchronous);
        await pipe.ConnectAsync(5_000, cancellationToken);
        var request = new ConnectorPlanExecutionRequest(
            lease.LeaseId, lease.Plan, lease.KeyId, lease.Signature,
            credential.DeviceId, credential.UserId, artifacts);
        using var reader = new StreamReader(pipe, Encoding.UTF8, false, 64 * 1024, leaveOpen: true);
        using var writer = new StreamWriter(pipe, new UTF8Encoding(false), 64 * 1024, leaveOpen: true)
        {
            AutoFlush = true,
        };
        await writer.WriteLineAsync(JsonSerializer.Serialize(request).AsMemory(), cancellationToken);
        var response = await reader.ReadLineAsync(cancellationToken);
        var outcome = string.IsNullOrWhiteSpace(response)
            ? throw new ConnectorException("session_host_no_result")
            : JsonSerializer.Deserialize<ConnectorPlanOutcome>(response)
              ?? throw new ConnectorException("session_host_no_result");
        var projected = await gateway.UploadCaptureResultsAsync(lease, outcome, cancellationToken);
        return new(
            projected,
            ConnectorOutcomeSecurity.Sign(projected, credential.DeviceToken),
            lease.LeaseId);
    }

}
