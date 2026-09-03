using System.Diagnostics;
using System.Runtime.InteropServices;
using Ai00.Connector.Contracts;

namespace Ai00.Connector.Adapters.VisMockup;

public sealed class VisMockupAdapter(StaDispatcher sta, AllowedPathPolicy paths, string executable) : IConnectorAdapter
{
    private const string ProgId = "VFFrame.Application";
    private object? _application;
    public AdapterManifest Manifest { get; } = new(
        "ai00.vismockup", 1, "siemens.vismockup", "14.0.0",
        [
            new("vismockup.application.probe@1", "sha256:197cfad8bc3453030fdc288ea78c3abc21699274dd48d4482444af4f62380a37"),
            new("vismockup.document.snapshot@1", "sha256:aa7c11c2501026c470a9cc7bfcbbecc7339879c18bf2b6b86f68ed7fc2e1861b"),
            new("vismockup.model.attach@1", "sha256:444b6b8a963b5a7e04d6b607cfe53699a5c93196a5bf78c98843d12d073fe844"),
            new("vismockup.scene.apply@1", "sha256:fce8ff3a33d996a26c3121d015839e2d68bc3c631a8c8c1091201e95d0bcabd3"),
            new("vismockup.scene.verify@1", "sha256:e99bf5896c3f655afc7470fc140d261225d6f37a1d8224b7e9438a2e7b7a211a"),
            new("vismockup.view.capture@1", "sha256:9c37c00be78afd4590be9fa128b1cddd2d84536d07f24bb690d0a176468c14e5"),
        ]);

    public async Task<AdapterHealth> ProbeAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var status = await StatusAsync();
        var ready = (bool)(status.GetType().GetProperty("connected")?.GetValue(status) ?? false);
        return new AdapterHealth(ready, ready ? "ready" : "unavailable");
    }

    public async Task<AdapterResult> ExecuteAsync(AdapterOperation operation, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        object result = operation.OperationId switch
        {
            "vismockup.application.probe@1" => await StatusAsync(),
            "vismockup.status" => await StatusAsync(),
            "vismockup.launch" => await LaunchAsync(),
            "vismockup.model.open" => await OpenFileAsync(operation.Payload.GetProperty("file_path").GetString() ?? ""),
            "vismockup.visibility" => await VisibilityAsync(operation.Payload.GetProperty("action").GetString() ?? ""),
            "vismockup.tree" => await TreeAsync(operation.Payload.TryGetProperty("max_depth", out var depth) ? depth.GetInt32() : 3),
            "vismockup.highlight" => await HighlightAsync(operation.Payload.GetProperty("catia_names").EnumerateArray().Select(item => item.GetString() ?? "").Where(item => item.Length > 0).ToHashSet(StringComparer.Ordinal)),
            "vismockup.capture" => await CaptureAsync(),
            _ => throw new InvalidOperationException("adapter_operation_not_allowed"),
        };
        return new AdapterResult(true, result);
    }
    private dynamic Connect()
    {
        var type = Type.GetTypeFromProgID(ProgId, throwOnError: true)!;
        _application ??= Activator.CreateInstance(type) ?? throw new COMException("Unable to create VisMockup COM application");
        return _application;
    }
    public Task<object> StatusAsync() => sta.InvokeAsync<object>(() =>
    {
        try { dynamic app = Connect(); _ = app.Documents; return new { connected = true, platform = "windows" }; }
        catch { _application = null; return new { connected = false, platform = "windows" }; }
    });
    public async Task<object> LaunchAsync()
    {
        var status = await StatusAsync();
        if ((bool)(status.GetType().GetProperty("connected")?.GetValue(status) ?? false)) return new { status = "already_running" };
        var fullExe = Path.GetFullPath(executable);
        if (!File.Exists(fullExe)) throw new FileNotFoundException("VisMockup executable not found", fullExe);
        Process.Start(new ProcessStartInfo(fullExe) { UseShellExecute = true });
        return new { status = "starting" };
    }
    public Task<object> OpenFileAsync(string filePath) => sta.InvokeAsync<object>(() =>
    {
        var safePath = paths.ValidateModelPath(filePath); dynamic app = Connect(); app.Documents.Open(safePath); return new { opened = true };
    });
    public Task<object> VisibilityAsync(string action) => sta.InvokeAsync<object>(() =>
    {
        dynamic app = Connect(); dynamic documents = app.Documents;
        if ((int)documents.Count <= 0) throw new InvalidOperationException("No active VisMockup document");
        dynamic view = documents.Item(1).ActiveView;
        switch (action) { case "all_on": view.AllNodesOn(); break; case "all_off": view.AllNodesOff(); break; case "deselect": view.DeSelectAllNodes(); break; default: throw new InvalidOperationException("Unsupported visibility action"); }
        return new { action };
    });
    public Task<object> TreeAsync(int maxDepth) => sta.InvokeAsync<object>(() =>
    {
        dynamic app = Connect(); dynamic documents = app.Documents;
        if ((int)documents.Count <= 0) throw new InvalidOperationException("No active VisMockup document");
        dynamic root = documents.Item(1).ActiveView.RootNode;
        var nodes = new List<object>();
        var queue = new Queue<(object Node, string? Parent, int Depth)>();
        queue.Enqueue((root, null, 0));
        while (queue.Count > 0)
        {
            var item = queue.Dequeue(); dynamic node = item.Node;
            string name;
            string catiaName = "";
            try { name = Convert.ToString(node.PrintableName) ?? ""; } catch { name = Convert.ToString(node.Fullname) ?? ""; }
            try { catiaName = Convert.ToString(node.MetaDataProperties.GetPropertyByName("catiaOccurrenceName")) ?? ""; } catch { }
            var nodeKey = Convert.ToString(node.GetNodeKey()) ?? "";
            var childCount = Convert.ToInt32(node.NumChildren);
            nodes.Add(new { node_key = nodeKey, parent_node_key = item.Parent, name, catia_occurrence_name = catiaName, has_more = item.Depth >= maxDepth && childCount > 0 });
            if (item.Depth < maxDepth)
            {
                dynamic collection = node.Children;
                for (var index = 0; index < childCount; index++) queue.Enqueue((collection.Node(index), nodeKey, item.Depth + 1));
            }
        }
        return new { nodes, max_depth = maxDepth };
    });
    public Task<object> HighlightAsync(IReadOnlySet<string> catiaNames) => sta.InvokeAsync<object>(() =>
    {
        dynamic app = Connect(); dynamic documents = app.Documents;
        if ((int)documents.Count <= 0) throw new InvalidOperationException("No active VisMockup document");
        dynamic view = documents.Item(1).ActiveView;
        var found = new HashSet<string>(StringComparer.Ordinal);
        var stack = new Stack<dynamic>(); stack.Push(view.RootNode);
        while (stack.Count > 0)
        {
            dynamic node = stack.Pop();
            string name = "";
            try { name = Convert.ToString(node.MetaDataProperties.GetPropertyByName("catiaOccurrenceName")) ?? ""; } catch { }
            if (catiaNames.Contains(name))
            {
                try { node.Selected = true; } catch { }
                found.Add(name);
            }
            try
            {
                var count = Convert.ToInt32(node.NumChildren); dynamic children = node.Children;
                for (var index = count - 1; index >= 0; index--) stack.Push(children.Node(index));
            }
            catch { }
        }
        var missing = catiaNames.Where(name => !found.Contains(name)).OrderBy(name => name, StringComparer.Ordinal).ToArray();
        return new { matched = found.Count, not_found = missing };
    });
    public Task<object> CaptureAsync() => sta.InvokeAsync<object>(() =>
    {
        dynamic app = Connect(); dynamic documents = app.Documents;
        if ((int)documents.Count <= 0) throw new InvalidOperationException("No active VisMockup document");
        var directory = Path.Combine(Path.GetTempPath(), "AI00", "captures"); Directory.CreateDirectory(directory);
        var path = Path.Combine(directory, $"vismockup_{DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()}.png");
        documents.Item(1).ActiveView.CaptureImage(path);
        return new { path, exists = File.Exists(path) };
    });
}
