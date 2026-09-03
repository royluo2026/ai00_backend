using System.Net.Http.Json;
using System.Security.Principal;
using System.Text.Json.Serialization;

namespace Ai00.Connector.Service;

public static class ConnectorPairing
{
    public static async Task RunAsync(string[] arguments, CancellationToken cancellationToken = default)
    {
        var values = arguments
            .Select((value, index) => (value, index))
            .Where(item => item.value.StartsWith("--", StringComparison.Ordinal) && item.index + 1 < arguments.Length)
            .ToDictionary(item => item.value, item => arguments[item.index + 1], StringComparer.Ordinal);
        if (!values.TryGetValue("--gateway", out var gateway) ||
            !values.TryGetValue("--token", out var token) ||
            !Uri.TryCreate(gateway, UriKind.Absolute, out var gatewayUri) || gatewayUri.Scheme != Uri.UriSchemeHttps)
            throw new InvalidOperationException("Usage: AI00.Connector.Service.exe pair --gateway https://server --token <pairing-code>");

        using var http = new HttpClient { BaseAddress = new Uri(gateway.TrimEnd('/') + "/") };
        using var response = await http.PostAsJsonAsync("api/v1/connector/activate", new
        {
            enrollment_token = token, runtime_version = "1.0.0",
            capabilities = new[] { "ai00.connector.execution-plan.v1", "ai00.vismockup@1" },
        }, cancellationToken);
        response.EnsureSuccessStatusCode();
        var envelope = await response.Content.ReadFromJsonAsync<ApiEnvelope<Activation>>(cancellationToken: cancellationToken)
            ?? throw new InvalidOperationException("connector_activation_invalid");
        var sid = WindowsIdentity.GetCurrent().User?.Value
            ?? throw new InvalidOperationException("windows_sid_unavailable");
        var credentialPath = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),
            "AI00", "Connector", "device.credential");
        new DeviceCredentialStore(credentialPath).Save(new(
            envelope.Data.DeviceId, envelope.Data.OwnerUserId, sid, envelope.Data.DeviceToken));

        Environment.SetEnvironmentVariable("AI00_CONNECTOR_DEVICE_ID", envelope.Data.DeviceId, EnvironmentVariableTarget.Machine);
        Environment.SetEnvironmentVariable(
            "AI00_LOCAL_OPERATION_KEYS",
            $"{envelope.Data.PlanSigningKeyId}={envelope.Data.PlanSigningSecret}",
            EnvironmentVariableTarget.Machine);
        Environment.SetEnvironmentVariable("Connector__GatewayUrl", gateway.TrimEnd('/'), EnvironmentVariableTarget.Machine);
        Console.WriteLine("AI00 Connector pairing completed. Sign out and sign in once to start SessionHost.");
    }

    private sealed record ApiEnvelope<T>(bool Success, T Data);
    private sealed record Activation(
        [property: JsonPropertyName("device_gid")] string DeviceId,
        [property: JsonPropertyName("device_token")] string DeviceToken,
        [property: JsonPropertyName("owner_user_gid")] string OwnerUserId,
        [property: JsonPropertyName("plan_signing_key_id")] string PlanSigningKeyId,
        [property: JsonPropertyName("plan_signing_secret")] string PlanSigningSecret);
}
