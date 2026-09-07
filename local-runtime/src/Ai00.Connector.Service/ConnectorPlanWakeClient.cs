using System.Net.WebSockets;
using System.Text.Json;
using Microsoft.Extensions.Options;

namespace Ai00.Connector.Service;

public interface IConnectorPlanWakeSignal
{
    Task WaitAsync(TimeSpan fallback, CancellationToken cancellationToken);
}

public sealed class ConnectorPlanWakeClient(
    IDeviceCredentialStore credentialStore,
    IOptions<RuntimeOptions> options,
    ILogger<ConnectorPlanWakeClient> logger) : BackgroundService, IConnectorPlanWakeSignal
{
    private readonly RuntimeOptions _options = options.Value;
    private readonly SemaphoreSlim _signal = new(0, 1);

    public async Task WaitAsync(TimeSpan fallback, CancellationToken cancellationToken)
    {
        await _signal.WaitAsync(fallback, cancellationToken);
    }

    public static Uri BuildEndpoint(Uri gateway)
    {
        var websocketGateway = new UriBuilder(gateway)
        {
            Scheme = gateway.Scheme == Uri.UriSchemeHttps ? "wss" : "ws",
            Port = gateway.IsDefaultPort ? -1 : gateway.Port,
        }.Uri;
        return new Uri(websocketGateway, "api/v1/simulation/connectors/plans/wake");
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                var credential = credentialStore.Load();
                var fallback = new Uri(_options.GatewayUrl.TrimEnd('/') + "/");
                var gateway = ConnectorGatewayEndpoint.Resolve(credential, fallback);
                using var socket = new ClientWebSocket();
                socket.Options.SetRequestHeader("X-AI00-Connector-ID", credential.DeviceId);
                socket.Options.SetRequestHeader("X-AI00-Connector-Token", credential.DeviceToken);
                await socket.ConnectAsync(BuildEndpoint(gateway), stoppingToken);
                await ReceiveAsync(socket, stoppingToken);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                break;
            }
            catch (Exception error)
            {
                logger.LogDebug(error, "Connector wake channel unavailable; lease polling remains active");
                await Task.Delay(TimeSpan.FromSeconds(2), stoppingToken);
            }
        }
    }

    private async Task ReceiveAsync(ClientWebSocket socket, CancellationToken cancellationToken)
    {
        var buffer = new byte[4096];
        while (socket.State == WebSocketState.Open && !cancellationToken.IsCancellationRequested)
        {
            using var message = new MemoryStream();
            WebSocketReceiveResult part;
            do
            {
                part = await socket.ReceiveAsync(buffer, cancellationToken);
                if (part.MessageType == WebSocketMessageType.Close) return;
                if (message.Length + part.Count > buffer.Length) throw new InvalidDataException("connector_wake_message_too_large");
                message.Write(buffer, 0, part.Count);
            } while (!part.EndOfMessage);

            using var document = JsonDocument.Parse(message.ToArray());
            var type = document.RootElement.TryGetProperty("type", out var value) ? value.GetString() : null;
            if (type is "ready" or "plan_available") Signal();
        }
    }

    private void Signal()
    {
        if (_signal.CurrentCount == 0) _signal.Release();
    }
}
