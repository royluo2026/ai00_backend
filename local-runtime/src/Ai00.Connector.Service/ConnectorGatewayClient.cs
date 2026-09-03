using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Serialization;
using Ai00.Connector.Contracts;
using Microsoft.Extensions.Options;

namespace Ai00.Connector.Service;

public sealed class ConnectorGatewayClient(
    HttpClient http,
    IOptions<RuntimeOptions> options,
    IDeviceCredentialStore credentialStore,
    ArtifactTransfer artifactTransfer) : IConnectorPlanGateway, IConnectorHeartbeatSink
{
    private readonly RuntimeOptions _options = options.Value;

    public async Task HeartbeatAsync(object health, CancellationToken cancellationToken)
    {
        using var request = Request(HttpMethod.Post, "/api/v1/connector/heartbeat", health);
        using var response = await http.SendAsync(request, cancellationToken);
        response.EnsureSuccessStatusCode();
    }

    public Task SendAsync(ConnectorHealthReport report, CancellationToken cancellationToken) =>
        HeartbeatAsync(report, cancellationToken);

    public async Task<LeasedConnectorPlan?> LeaseAsync(CancellationToken cancellationToken)
    {
        using var request = Request(HttpMethod.Post, "/api/v1/connector/plans/lease", new { lease_seconds = 120 });
        using var response = await http.SendAsync(request, cancellationToken);
        response.EnsureSuccessStatusCode();
        var envelope = await response.Content.ReadFromJsonAsync<ApiEnvelope<LeaseBody?>>(cancellationToken: cancellationToken);
        return envelope?.Data is { } lease
            ? new(lease.LeaseId, lease.Plan, lease.KeyId, lease.Signature)
            : null;
    }

    public async Task ReconcileAsync(PlanReconciliation reconciliation, CancellationToken cancellationToken)
    {
        var signed = reconciliation.Outcome ?? OutcomeUnknown(reconciliation.PlanId);
        using var request = Request(
            HttpMethod.Post,
            $"/api/v1/connector/plans/{Uri.EscapeDataString(reconciliation.PlanId)}/complete",
            new { lease_id = signed.LeaseId, outcome = signed.Outcome, signature = signed.Signature });
        using var response = await http.SendAsync(request, cancellationToken);
        response.EnsureSuccessStatusCode();
    }

    public async Task<IReadOnlyList<MaterializedArtifact>> PrepareArtifactsAsync(
        LeasedConnectorPlan lease, CancellationToken cancellationToken)
    {
        var materialized = new List<MaterializedArtifact>();
        foreach (var step in lease.Plan.Steps.Where(item => item.OperationId == "vismockup.model.attach@1"))
        {
            var artifact = step.Payload.GetProperty("binding").GetProperty("model_ref").GetProperty("artifact_ref");
            var reference = new ConnectorArtifactRef(
                artifact.GetProperty("artifact_id").GetString() ?? throw new ConnectorException("artifact_ref_invalid"),
                artifact.GetProperty("media_type").GetString() ?? "",
                artifact.GetProperty("sha256").GetString() ?? "",
                artifact.GetProperty("byte_size").GetInt64(), artifact.GetProperty("version").GetInt32());
            var path = $"/api/v1/connector/plans/{Uri.EscapeDataString(lease.Plan.PlanId)}/artifacts/" +
                $"{Uri.EscapeDataString(reference.ArtifactId)}?lease_id={Uri.EscapeDataString(lease.LeaseId)}";
            using var request = Request(HttpMethod.Get, path);
            using var response = await http.SendAsync(request, cancellationToken);
            response.EnsureSuccessStatusCode();
            var envelope = await response.Content.ReadFromJsonAsync<ApiEnvelope<ArtifactGrant>>(cancellationToken: cancellationToken)
                ?? throw new ConnectorException("artifact_download_unavailable");
            var download = Uri.TryCreate(envelope.Data.DownloadUrl, UriKind.Absolute, out var absolute)
                ? absolute : new Uri(new Uri(_options.GatewayUrl.TrimEnd('/') + "/"), envelope.Data.DownloadUrl.TrimStart('/'));
            materialized.Add(await artifactTransfer.DownloadAsync(reference, download, cancellationToken));
        }
        return materialized;
    }

    public async Task<ConnectorPlanOutcome> UploadCaptureResultsAsync(
        LeasedConnectorPlan lease, ConnectorPlanOutcome outcome, CancellationToken cancellationToken)
    {
        var stepById = lease.Plan.Steps.ToDictionary(item => item.StepId, StringComparer.Ordinal);
        var results = new List<ConnectorStepResult>(outcome.Steps.Count);
        foreach (var result in outcome.Steps)
        {
            if (result.Status != "completed" || !stepById.TryGetValue(result.StepId, out var step) ||
                step.OperationId != "vismockup.view.capture@1")
            {
                results.Add(result);
                continue;
            }
            if (result.Result is not JsonElement local || !local.TryGetProperty("path", out var pathValue))
                throw new ConnectorException("capture_result_invalid");
            var localPath = Path.GetFullPath(pathValue.GetString() ?? "");
            var captureRoot = Path.GetFullPath(_options.CaptureRoot).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
            if (!localPath.StartsWith(captureRoot, StringComparison.OrdinalIgnoreCase))
                throw new ConnectorException("capture_result_invalid");
            var info = new FileInfo(localPath);
            if (!info.Exists || info.Length > 100 * 1024 * 1024)
                throw new ConnectorException("capture_result_invalid");
            var sha256 = local.GetProperty("sha256").GetString() ?? "";
            if (sha256.Length != 64 || info.Length != local.GetProperty("byte_size").GetInt64())
                throw new ConnectorException("capture_result_invalid");
            await using (var hashStream = info.OpenRead())
            {
                var actual = Convert.ToHexString(
                    await System.Security.Cryptography.SHA256.HashDataAsync(hashStream, cancellationToken)
                ).ToLowerInvariant();
                if (!string.Equals(actual, sha256, StringComparison.Ordinal))
                    throw new ConnectorException("artifact_integrity_failed", localPath);
            }
            await using var content = info.OpenRead();
            using var request = Request(
                HttpMethod.Put,
                $"/api/v1/connector/plans/{Uri.EscapeDataString(lease.Plan.PlanId)}/steps/{Uri.EscapeDataString(step.StepId)}/result-artifact" +
                $"?lease_id={Uri.EscapeDataString(lease.LeaseId)}");
            request.Headers.Add("X-AI00-Content-SHA256", sha256);
            request.Headers.Add("X-AI00-Content-Length", info.Length.ToString(System.Globalization.CultureInfo.InvariantCulture));
            request.Headers.Add("X-AI00-Media-Type", "image/png");
            request.Content = new StreamContent(content);
            request.Content.Headers.ContentType = new("image/png");
            using var response = await http.SendAsync(request, cancellationToken);
            response.EnsureSuccessStatusCode();
            var envelope = await response.Content.ReadFromJsonAsync<ApiEnvelope<ArtifactResult>>(cancellationToken: cancellationToken)
                ?? throw new ConnectorException("artifact_upload_unconfirmed");
            var projected = new Dictionary<string, object?> { ["artifact"] = envelope.Data.ArtifactRef };
            results.Add(result with { Result = projected, ResultHash = CanonicalJson.Hash(projected) });
        }
        return outcome with { Steps = results };
    }

    private SignedConnectorPlanOutcome OutcomeUnknown(string planId)
    {
        var credential = credentialStore.Load();
        var reportedAt = DateTimeOffset.UtcNow;
        reportedAt = reportedAt.AddTicks(-(reportedAt.Ticks % TimeSpan.TicksPerSecond));
        var outcome = new ConnectorPlanOutcome(
            ConnectorExecutionPlan.ProtocolVersion, planId, "outcome_unknown", [], reportedAt);
        return new(outcome, ConnectorOutcomeSecurity.Sign(outcome, credential.DeviceToken), "reconciliation-required");
    }

    private HttpRequestMessage Request(HttpMethod method, string path, object? body = null)
    {
        var credential = credentialStore.Load();
        var request = new HttpRequestMessage(method, new Uri(new Uri(_options.GatewayUrl.TrimEnd('/') + "/"), path.TrimStart('/')));
        request.Headers.Add("X-AI00-Device-ID", credential.DeviceId);
        request.Headers.Add("X-AI00-Device-Token", credential.DeviceToken);
        if (body is not null) request.Content = JsonContent.Create(body);
        return request;
    }

    private sealed record ApiEnvelope<T>(bool Success, T Data);
    private sealed record LeaseBody(
        [property: JsonPropertyName("lease_id")] string LeaseId,
        [property: JsonPropertyName("plan")] ConnectorExecutionPlan Plan,
        [property: JsonPropertyName("key_id")] string KeyId,
        [property: JsonPropertyName("signature")] string Signature);
    private sealed record ArtifactGrant(
        [property: JsonPropertyName("artifact_ref")] JsonElement ArtifactRef,
        [property: JsonPropertyName("download_url")] string DownloadUrl);
    private sealed record ArtifactResult(
        [property: JsonPropertyName("artifact_ref")] JsonElement ArtifactRef);
}
