using Ai00.Connector.Adapters.VisMockup;
using Ai00.Connector.Contracts;
using Ai00.Connector.SessionHost;
using System.Security.Principal;
using System.Diagnostics;
using System.Text.Json;

var options = SessionHostOptions.FromEnvironment();
var deviceId = Environment.GetEnvironmentVariable("AI00_CONNECTOR_DEVICE_ID")
    ?? throw new InvalidOperationException("AI00_CONNECTOR_DEVICE_ID is required");
var windowsSid = WindowsIdentity.GetCurrent().User?.Value
    ?? throw new InvalidOperationException("Current Windows SID is unavailable");
using var instance = SingleInstanceGuard.Acquire(deviceId, windowsSid);
using var sta = new StaDispatcher();
var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy(options.AllowedRoots.Append(options.ArtifactCacheRoot)), options.VisMockupExe);
var ledgerPath = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "AI00", "command-ledger.jsonl");
var host = new CommandPipeHost(
    new CommandDispatcher(adapter, new CommandLedger(ledgerPath), options.ArtifactCacheRoot),
    options.OperationSigningKeys,
    ConnectorPipeName.For(deviceId, windowsSid));
var planHost = new PlanPipeHost(
    new ValidatedPlanDispatcher([adapter], options.OperationSigningKeys),
    ConnectorPipeName.PlanFor(deviceId, windowsSid));
using var presenceCancellation = new CancellationTokenSource();
var presence = PublishPresenceAsync(adapter, windowsSid, presenceCancellation.Token);
try
{
    await Task.WhenAll(
        host.RunAsync(CancellationToken.None),
        planHost.RunAsync(CancellationToken.None));
}
finally
{
    presenceCancellation.Cancel();
    try { await presence; } catch (OperationCanceledException) { }
    if (File.Exists(SessionHostPresencePath.Value)) File.Delete(SessionHostPresencePath.Value);
}

static async Task PublishPresenceAsync(
    VisMockupAdapter adapter, string windowsSid, CancellationToken cancellationToken)
{
    Directory.CreateDirectory(Path.GetDirectoryName(SessionHostPresencePath.Value)!);
    using var timer = new PeriodicTimer(TimeSpan.FromSeconds(5));
    do
    {
        var health = await adapter.ProbeAsync(cancellationToken);
        var advertised = string.IsNullOrWhiteSpace(health.ProductVersion)
            ? adapter.Manifest
            : adapter.Manifest with { ProductVersion = health.ProductVersion };
        var value = new SessionHostPresence(
            windowsSid, Process.GetCurrentProcess().SessionId, Environment.ProcessId,
            advertised, DateTimeOffset.UtcNow);
        var temporary = SessionHostPresencePath.Value + ".tmp-" + Guid.NewGuid().ToString("N");
        await File.WriteAllTextAsync(temporary, JsonSerializer.Serialize(value), cancellationToken);
        File.Move(temporary, SessionHostPresencePath.Value, true);
    } while (await timer.WaitForNextTickAsync(cancellationToken));
}
