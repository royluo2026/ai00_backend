using Ai00.LocalRuntime.SessionHost;

var options = SessionHostOptions.FromEnvironment();
using var sta = new StaDispatcher();
var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy(options.AllowedRoots.Append(options.ArtifactCacheRoot)), options.VisMockupExe);
var ledgerPath = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "AI00", "command-ledger.jsonl");
var host = new CommandPipeHost(new CommandDispatcher(adapter, new CommandLedger(ledgerPath), options.ArtifactCacheRoot), options.OperationSigningKeys);
await host.RunAsync(CancellationToken.None);
