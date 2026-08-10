using Ai00.LocalRuntime.Contracts;
using Microsoft.Extensions.Options;

namespace Ai00.LocalRuntime.Service;

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
                    CommandCompletion completion;
                    try { completion = await sessionHost.ExecuteAsync(command, stoppingToken); }
                    catch (Exception ex) { completion = new(command.LeaseId, false, Error: ex.Message[..Math.Min(1000, ex.Message.Length)]); }
                    await gateway.CompleteAsync(command.CommandId, completion, stoppingToken);
                }
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested) { break; }
            catch (Exception ex) { logger.LogWarning(ex, "Local Runtime loop failed"); }
            await Task.Delay(TimeSpan.FromSeconds(Math.Clamp(_options.PollSeconds, 1, 60)), stoppingToken);
        }
    }
}
