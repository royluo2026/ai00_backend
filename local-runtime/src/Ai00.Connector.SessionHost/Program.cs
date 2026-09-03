using Ai00.Connector.Adapters.VisMockup;
using Ai00.Connector.Contracts;
using Ai00.Connector.SessionHost;
using System.Security.Principal;

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
await host.RunAsync(CancellationToken.None);
