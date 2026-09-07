using Ai00.Connector.Contracts;

namespace Ai00.Connector.Service;

public sealed class SessionHostPresenceWorker(
    IDeviceCredentialStore credentialStore,
    ILogger<SessionHostPresenceWorker> logger) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        using var timer = new PeriodicTimer(TimeSpan.FromSeconds(10));
        do
        {
            try
            {
                var credential = credentialStore.Load();
                await SessionHostBrokerClient.EnsureStartedAsync(new SessionHostStartRequest(
                    credential.DeviceId, credential.UserId, credential.WindowsSid), stoppingToken);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                break;
            }
            catch (Exception error)
            {
                logger.LogWarning(error, "Interactive SessionHost is not ready");
            }
        } while (await timer.WaitForNextTickAsync(stoppingToken));
    }
}
