using System.Net.Http.Json;
using Ai00.LocalRuntime.Contracts;
using Microsoft.Extensions.Options;

namespace Ai00.LocalRuntime.Service;

public sealed class DeviceGatewayClient(HttpClient http, IOptions<RuntimeOptions> options)
{
    private readonly RuntimeOptions _options = options.Value;

    private HttpRequestMessage Request(HttpMethod method, string path, object? body = null)
    {
        if (string.IsNullOrWhiteSpace(_options.DeviceId) || string.IsNullOrWhiteSpace(_options.DeviceToken))
            throw new InvalidOperationException("Device enrollment is required");
        var request = new HttpRequestMessage(method, new Uri(new Uri(_options.GatewayUrl.TrimEnd('/') + "/"), path.TrimStart('/')));
        request.Headers.Add("X-AI00-Device-ID", _options.DeviceId);
        request.Headers.Add("X-AI00-Device-Token", _options.DeviceToken);
        if (body is not null) request.Content = JsonContent.Create(body);
        return request;
    }

    public async Task HeartbeatAsync(CancellationToken cancellationToken)
    {
        using var request = Request(HttpMethod.Post, "/api/v1/device-runtime/heartbeat", new { runtime_version = _options.Version, capabilities = RuntimeCapabilities.Allowed });
        using var response = await http.SendAsync(request, cancellationToken);
        response.EnsureSuccessStatusCode();
    }

    public async Task<CommandEnvelope?> LeaseAsync(CancellationToken cancellationToken)
    {
        using var request = Request(HttpMethod.Post, "/api/v1/device-runtime/commands/lease", new { lease_seconds = 120 });
        using var response = await http.SendAsync(request, cancellationToken);
        response.EnsureSuccessStatusCode();
        var envelope = await response.Content.ReadFromJsonAsync<ApiEnvelope<CommandEnvelope?>>(cancellationToken: cancellationToken);
        return envelope?.Data;
    }

    public async Task CompleteAsync(string commandId, CommandCompletion completion, CancellationToken cancellationToken)
    {
        using var request = Request(HttpMethod.Post, $"/api/v1/device-runtime/commands/{Uri.EscapeDataString(commandId)}/complete", new
        {
            lease_id = completion.LeaseId, success = completion.Success, result = completion.Result, error = completion.Error
        });
        using var response = await http.SendAsync(request, cancellationToken);
        response.EnsureSuccessStatusCode();
    }

    private sealed record ApiEnvelope<T>(bool Success, T Data);
}
