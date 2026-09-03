using Ai00.Connector.Contracts;
using Microsoft.Extensions.Options;

namespace Ai00.Connector.Service;

public sealed class RuntimeWorker(DeviceGatewayClient gateway, SessionHostClient sessionHost, IOptions<RuntimeOptions> options, ILogger<RuntimeWorker> logger) : BackgroundService
{
    private readonly RuntimeOptions _options = options.Value;
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        var nextHeartbeat = DateTimeOffset.MinValue;
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                if (DateTimeOffset.UtcNow >= nextHeartbeat)
                {
                    await gateway.HeartbeatAsync(stoppingToken);
                    nextHeartbeat = DateTimeOffset.UtcNow.AddSeconds(30);
                }
                var command = await gateway.LeaseAsync(stoppingToken);
                if (command is not null)
                {
                    OperationCompletion completion;
                    try
                    {
                        var request = await gateway.PrepareAsync(command, stoppingToken);
                        completion = await sessionHost.ExecuteAsync(request, stoppingToken);
                        completion = await gateway.FinalizeAsync(command, completion, stoppingToken);
                    }
                    catch (Exception) { completion = new(command.Operation.OperationId, "outcome_unknown", ErrorCode: "session_host_unavailable"); }
                    await gateway.CompleteAsync(command.Operation.OperationId, command.LeaseId, completion, stoppingToken);
                }
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested) { break; }
            catch (Exception ex) { logger.LogWarning(ex, "Local Runtime loop failed"); }
            await Task.Delay(TimeSpan.FromSeconds(Math.Clamp(_options.PollSeconds, 1, 60)), stoppingToken);
        }
    }
}
