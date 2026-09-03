using System.Net.Http.Json;
using System.Text.Json.Serialization;
using Ai00.Connector.Contracts;
using Microsoft.Extensions.Options;

namespace Ai00.Connector.Service;

public sealed class ConnectorGatewayClient(
    HttpClient http,
    IOptions<RuntimeOptions> options,
    IDeviceCredentialStore credentialStore) : IConnectorPlanGateway
{
    private readonly RuntimeOptions _options = options.Value;

    public async Task HeartbeatAsync(object health, CancellationToken cancellationToken)
    {
        using var request = Request(HttpMethod.Post, "/api/v1/connector/heartbeat", health);
        using var response = await http.SendAsync(request, cancellationToken);
        response.EnsureSuccessStatusCode();
    }

    public async Task<LeasedConnectorPlan?> LeaseAsync(CancellationToken cancellationToken)
    {
        using var request = Request(HttpMethod.Post, "/api/v1/connector/plans/lease", new { lease_seconds = 120 });
        using var response = await http.SendAsync(request, cancellationToken);
        response.EnsureSuccessStatusCode();
        var envelope = await response.Content.ReadFromJsonAsync<ApiEnvelope<LeaseBody?>>(cancellationToken: cancellationToken);
        return envelope?.Data is { } lease ? new(lease.LeaseId, lease.Plan) : null;
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
        [property: JsonPropertyName("plan")] ConnectorExecutionPlan Plan);
}
