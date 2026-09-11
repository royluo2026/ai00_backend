using System.Text.Json;
using Ai00.Connector.Adapters.VisMockup;

if (args.Length != 3) throw new ArgumentException("usage: primary-path insert-path vismockup-exe");
var primaryPath = Path.GetFullPath(args[0]);
var insertedPath = Path.GetFullPath(args[1]);
var executable = Path.GetFullPath(args[2]);
var roots = new[] { Path.GetDirectoryName(primaryPath)!, Path.GetDirectoryName(insertedPath)! }
    .Distinct(StringComparer.OrdinalIgnoreCase).ToArray();
using var sta = new StaDispatcher();
var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy(roots), executable);
var opened = await adapter.OpenManagedFileAsync(primaryPath);
var inserted = await adapter.InsertManagedFileAsync(insertedPath);
Console.WriteLine(JsonSerializer.Serialize(new { opened, inserted }));
