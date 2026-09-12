using Ai00.Connector.Adapters.VisMockup;
using Ai00.Connector.Contracts;
using Ai00.Connector.SessionHost;
using System.Security.Principal;
using System.Diagnostics;
using System.Text.Json;

var options = SessionHostOptions.FromEnvironment();
var windowsSid = WindowsIdentity.GetCurrent().User?.Value
    ?? throw new InvalidOperationException("Current Windows SID is unavailable");
var connectorId = Environment.GetEnvironmentVariable("AI00_CONNECTOR_DEVICE_ID")
    ?? throw new InvalidOperationException("connector_device_identity_missing");
var userId = Environment.GetEnvironmentVariable("AI00_CONNECTOR_USER_ID")
    ?? throw new InvalidOperationException("connector_user_identity_missing");
using var instance = SingleInstanceGuard.Acquire(connectorId, windowsSid);
var presencePath = SessionHostPresencePath.For(windowsSid);
using var sta = new StaDispatcher();
var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy(options.AllowedRoots.Append(options.ArtifactCacheRoot)),
    options.VisMockupExe, options.CaptureRoot);
var planHost = new PlanPipeHost(
    new ValidatedPlanDispatcher([adapter]),
    ConnectorPipeName.PlanFor(connectorId, windowsSid));
using var presenceCancellation = new CancellationTokenSource();
var presence = PublishPresenceAsync(adapter, windowsSid, presencePath, presenceCancellation.Token);
try
{
    await planHost.RunAsync(CancellationToken.None);
}
finally
{
    presenceCancellation.Cancel();
    try { await presence; } catch (OperationCanceledException) { }
    if (File.Exists(presencePath)) File.Delete(presencePath);
}

static async Task PublishPresenceAsync(
    VisMockupAdapter adapter, string windowsSid, string presencePath,
    CancellationToken cancellationToken)
{
    Directory.CreateDirectory(Path.GetDirectoryName(presencePath)!);
    using var timer = new PeriodicTimer(TimeSpan.FromSeconds(5));
    do
    {
        var value = new SessionHostPresence(
            windowsSid, Process.GetCurrentProcess().SessionId, Environment.ProcessId,
            adapter.Manifest, DateTimeOffset.UtcNow);
        var temporary = presencePath + ".tmp-" + Guid.NewGuid().ToString("N");
        await File.WriteAllTextAsync(temporary, JsonSerializer.Serialize(value), cancellationToken);
        File.Move(temporary, presencePath, true);
    } while (await timer.WaitForNextTickAsync(cancellationToken));
}
