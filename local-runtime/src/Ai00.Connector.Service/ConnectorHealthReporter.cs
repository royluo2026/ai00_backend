using System.Diagnostics;
using System.Text.Json;
using System.Text.Json.Serialization;
using Ai00.Connector.Contracts;
using Microsoft.Extensions.Options;

namespace Ai00.Connector.Service;

public sealed record ConnectorHealthReport(
    [property: JsonPropertyName("connector_version")] string ConnectorVersion,
    [property: JsonPropertyName("protocol_versions")] IReadOnlyList<string> ProtocolVersions,
    [property: JsonPropertyName("bound_user_id")] string BoundUserId,
    [property: JsonPropertyName("session_id")] string SessionId,
    [property: JsonPropertyName("user_session_present")] bool UserSessionPresent,
    [property: JsonPropertyName("session_host_ready")] bool SessionHostReady,
    [property: JsonPropertyName("system_awake")] bool SystemAwake,
    [property: JsonPropertyName("adapters")] IReadOnlyList<AdapterManifest> Adapters,
    [property: JsonPropertyName("reported_at")] DateTimeOffset ReportedAt);

public interface IConnectorHealthSource { ConnectorHealthReport Read(); }
public interface IConnectorHeartbeatSink
{
    Task SendAsync(ConnectorHealthReport report, CancellationToken cancellationToken);
}

public sealed class ConnectorHeartbeatReporter(
    IConnectorHealthSource source,
    IConnectorHeartbeatSink sink)
{
    public Task ReportOnceAsync(CancellationToken cancellationToken) =>
        sink.SendAsync(source.Read(), cancellationToken);
}

public sealed class FileConnectorHealthSource(
    IDeviceCredentialStore credentials,
    IOptions<RuntimeOptions> options)
    : IConnectorHealthSource
{
    private readonly RuntimeOptions _options = options.Value;

    public ConnectorHealthReport Read()
    {
        var credential = credentials.Load();
        SessionHostPresence? presence = null;
        try
        {
            presence = JsonSerializer.Deserialize<SessionHostPresence>(
                File.ReadAllText(SessionHostPresencePath.Value));
            if (presence is null || presence.WindowsSid != credential.WindowsSid ||
                presence.ReportedAt < DateTimeOffset.UtcNow.AddSeconds(-20) ||
                Process.GetProcessById(presence.ProcessId).HasExited)
                presence = null;
        }
        catch { presence = null; }
        return new(
            _options.Version, [ConnectorExecutionPlan.ProtocolVersion], credential.UserId,
            presence?.SessionId.ToString() ?? "missing", presence is not null,
            presence is not null, true, presence is null ? [] : [presence.Adapter],
            DateTimeOffset.UtcNow);
    }
}

public sealed class ConnectorHeartbeatWorker(
    ConnectorHeartbeatReporter reporter,
    ILogger<ConnectorHeartbeatWorker> logger) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        using var timer = new PeriodicTimer(TimeSpan.FromSeconds(30));
        do
        {
            try { await reporter.ReportOnceAsync(stoppingToken); }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested) { break; }
            catch (Exception error) { logger.LogWarning(error, "Connector heartbeat failed"); }
        } while (await timer.WaitForNextTickAsync(stoppingToken));
    }
}
