using System.Diagnostics;
using System.Runtime.InteropServices;
using Ai00.Connector.Contracts;

namespace Ai00.Connector.Adapters.VisMockup;

public sealed class VisMockupAdapter : IConnectorAdapter
{
    private const string ProgId = "VFFrame.Application";
    private readonly StaDispatcher _sta;
    private readonly AllowedPathPolicy _paths;
    private readonly string _executable;
    private readonly VisMockupConnection _connection;
    private readonly IVisMockupCom _com;
    private readonly VisMockupSessionState _state = new();
    private readonly SceneController _scene;
    private readonly ModelAttacher _attacher;
    private readonly InternalCapture _capture;
    private readonly VisMockupTreeCache? _treeCache;
    private object? _application;
    private string? _ownedDocumentId;

    public VisMockupAdapter(StaDispatcher sta, AllowedPathPolicy paths, string executable)
        : this(sta, paths, new WindowsVisMockupCom(executable), executable,
            Path.Combine(Path.GetTempPath(), "AI00", "captures"), null) { }

    public VisMockupAdapter(StaDispatcher sta, AllowedPathPolicy paths, IVisMockupCom com)
        : this(sta, paths, com, "", Path.Combine(Path.GetTempPath(), "AI00", "captures"), null) { }

    public VisMockupAdapter(StaDispatcher sta, AllowedPathPolicy paths, IVisMockupCom com, string captureRoot)
        : this(sta, paths, com, "", captureRoot, null) { }

    public VisMockupAdapter(StaDispatcher sta, AllowedPathPolicy paths, IVisMockupCom com, string captureRoot, string treeCachePath)
        : this(sta, paths, com, "", captureRoot, new VisMockupTreeCache(treeCachePath)) { }

    private VisMockupAdapter(StaDispatcher sta, AllowedPathPolicy paths, IVisMockupCom com, string executable, string captureRoot, VisMockupTreeCache? treeCache)
    {
        _sta = sta;
        _paths = paths;
        _executable = executable;
        _com = com;
        _connection = new VisMockupConnection(com);
        _scene = new SceneController(_state);
        _attacher = new ModelAttacher(paths, _state);
        _capture = new InternalCapture(captureRoot);
        _treeCache = treeCache;
    }
    public AdapterManifest Manifest { get; } = new(
        "ai00.vismockup", 1, "siemens.vismockup", "14.0.0",
        [
            new("vismockup.application.probe@1", "sha256:197cfad8bc3453030fdc288ea78c3abc21699274dd48d4482444af4f62380a37"),
            new("vismockup.document.snapshot@1", "sha256:aa7c11c2501026c470a9cc7bfcbbecc7339879c18bf2b6b86f68ed7fc2e1861b"),
            new("vismockup.model.open@1", "sha256:aabd43bb066794c250f7eeed41def7c147a4da7263e813f192efa59a0cb40e34"),
            new("vismockup.model.close@1", "sha256:a1a27969ab8638c9868b384ccb546aed1ece56219ded7c7ec3bb3d6b19861771"),
            new("vismockup.visibility.change@1", "sha256:6ecb8dd2239a2ca881bfc8d40463778f2b80f15f66f1be50a3ceb91a90bff201"),
            new("vismockup.tree.read@1", "sha256:25ac87b341ef76d657c627b45bc0c4de129f55b92e01401dd6f2cd8649dd2f16"),
            new("vismockup.model.attach@1", "sha256:444b6b8a963b5a7e04d6b607cfe53699a5c93196a5bf78c98843d12d073fe844"),
            new("vismockup.scene.apply@1", "sha256:fce8ff3a33d996a26c3121d015839e2d68bc3c631a8c8c1091201e95d0bcabd3"),
            new("vismockup.scene.verify@1", "sha256:e99bf5896c3f655afc7470fc140d261225d6f37a1d8224b7e9438a2e7b7a211a"),
            new("vismockup.view.capture@1", "sha256:10a4b5540a34fb32a2e6a4d24fd1efbe7afb929e2cc3c9fed44f6b4d9893962d"),
        ]);

    public async Task<AdapterHealth> ProbeAsync(CancellationToken cancellationToken)
        => await ProbeAsync(false, cancellationToken);

    public async Task<AdapterHealth> ProbeAsync(bool allowLaunch, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        return await _sta.InvokeAsync(() =>
        {
            try
            {
                var application = _connection.RequireActiveApplication(allowLaunch);
                var documentReady = application.ActiveDocument is not null;
                return new AdapterHealth(true, documentReady ? "ready" : "document_missing", true, documentReady, application.ProductVersion);
            }
            catch (Exception)
            {
                var process = _com.InspectProcess();
                return new AdapterHealth(
                    false, process.Running ? "automation_unavailable" : "unavailable",
                    process.Running, false, process.ProductVersion);
            }
        });
    }

    public Task<VisMockupDocumentSnapshot> SnapshotAsync(int maxNodes, int maxDepth) =>
        _sta.InvokeAsync(() => new DocumentSnapshotReader().Read(_connection.RequireActiveDocument(), maxNodes, maxDepth));

    public Task<NodeBinding> AttachModelAsync(string documentId, string baselineSnapshotHash, System.Text.Json.JsonElement binding) =>
        _sta.InvokeAsync(() => _attacher.Attach(_connection.RequireActiveDocument(), documentId, baselineSnapshotHash, binding));

    public Task<string> ApplySceneAsync(string documentId, SceneState scene, string? baselineSnapshotHash = null) =>
        _sta.InvokeAsync(() =>
        {
            var document = _connection.RequireActiveDocument();
            if (document.DocumentId != documentId) throw new ConnectorException("vismockup_document_changed");
            if (baselineSnapshotHash is not null) _state.RequireBaseline(document, baselineSnapshotHash);
            return _scene.Apply(document, scene);
        });

    public Task<SceneVerification> VerifySceneAsync(string documentId, string operationId, string expectedHash) =>
        _sta.InvokeAsync(() =>
        {
            var document = _connection.RequireActiveDocument();
            if (document.DocumentId != documentId) throw new ConnectorException("vismockup_document_changed");
            return _scene.Verify(document, operationId, expectedHash);
        });

    public Task<LocalCaptureArtifact> CaptureAsync(CaptureRequest request) =>
        _sta.InvokeAsync(() => _capture.Capture(_connection.RequireActiveDocument(), request));

    public async Task<AdapterResult> ExecuteAsync(AdapterOperation operation, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        object result = operation.OperationId switch
        {
            "vismockup.application.probe@1" => await ProbeAsync(
                operation.Payload.TryGetProperty("allow_launch", out var allowLaunch) && allowLaunch.GetBoolean(), cancellationToken),
            "vismockup.document.snapshot@1" => await SnapshotAsync(
                operation.Payload.GetProperty("max_nodes").GetInt32(),
                operation.Payload.GetProperty("max_depth").GetInt32()),
            "vismockup.model.open@1" => await OpenManagedFileAsync(
                operation.Payload.GetProperty("local_artifact_path").GetString() ?? ""),
            "vismockup.model.close@1" => await CloseManagedFileAsync(),
            "vismockup.visibility.change@1" => await ChangeAllVisibilityAsync(
                operation.Payload.GetProperty("action").GetString() ?? ""),
            "vismockup.tree.read@1" => await TreeAsync(
                operation.Payload.GetProperty("max_depth").GetInt32()),
            "vismockup.model.attach@1" => await AttachModelAsync(
                operation.Payload.GetProperty("document_id").GetString() ?? "",
                operation.Payload.GetProperty("baseline_snapshot_hash").GetString() ?? "",
                operation.Payload.GetProperty("binding")),
            "vismockup.scene.apply@1" => await ApplySceneAsync(
                operation.Payload.GetProperty("document_id").GetString() ?? "",
                ReadScene(operation.Payload.GetProperty("scene")),
                operation.Payload.GetProperty("baseline_snapshot_hash").GetString() ?? ""),
            "vismockup.scene.verify@1" => await VerifySceneAsync(
                operation.Payload.GetProperty("document_id").GetString() ?? "",
                operation.Payload.GetProperty("operation_id").GetString() ?? "",
                operation.Payload.GetProperty("expected_scene_hash").GetString() ?? ""),
            "vismockup.view.capture@1" => await CaptureAsync(ReadCaptureRequest(operation.Payload, operation.StepId)),
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

    public Task<object> OpenManagedFileAsync(string filePath) => _sta.InvokeAsync<object>(() =>
    {
        var safePath = _paths.ValidateModelPath(filePath);
        var application = _connection.RequireActiveApplication(true);
        var document = application.OpenDocument(safePath);
        _ownedDocumentId = document.DocumentId;
        return new { opened = true, document_id = document.DocumentId };
    });

    public Task<object> CloseManagedFileAsync() => _sta.InvokeAsync<object>(() =>
    {
        var application = _connection.RequireActiveApplication(false);
        application.CloseAllDocuments();
        var closed = _ownedDocumentId;
        _ownedDocumentId = null;
        return new { closed = true, document_id = closed };
    });

    public Task<object> ChangeAllVisibilityAsync(string action) => _sta.InvokeAsync<object>(() =>
    {
        var document = _connection.RequireActiveDocument();
        document.SetAllNodesVisible(action switch
        {
            "all_on" => true,
            "all_off" => false,
            _ => throw new ConnectorException("visibility_action_unsupported"),
        });
        return new { action };
    });

    private static SceneState ReadScene(System.Text.Json.JsonElement value)
    {
        var profile = value.GetProperty("capture_profile");
        return new(
            value.GetProperty("operation_id").GetString() ?? "",
            value.GetProperty("visible_products").EnumerateArray().Select(item => item.GetString() ?? "").ToArray(),
            value.GetProperty("visible_resources").EnumerateArray().Select(item => item.GetString() ?? "").ToArray(),
            new(profile.GetProperty("format").GetString() ?? "", profile.GetProperty("width").GetInt32(), profile.GetProperty("height").GetInt32(), profile.GetProperty("background").GetString() ?? ""),
            value.GetProperty("scene_hash").GetString() ?? "");
    }

    private static CaptureRequest ReadCaptureRequest(System.Text.Json.JsonElement value, string stepId) => new(
        value.GetProperty("capture_run_id").GetString() ?? "",
        string.IsNullOrWhiteSpace(stepId) ? "capture-" + (value.GetProperty("operation_id").GetString() ?? "operation") : stepId,
        value.GetProperty("operation_id").GetString() ?? "",
        value.GetProperty("attempt").GetInt32(),
        new(value.GetProperty("format").GetString() ?? "", value.GetProperty("width").GetInt32(), value.GetProperty("height").GetInt32(), value.GetProperty("background").GetString() ?? ""));
    private dynamic Connect()
    {
        var type = Type.GetTypeFromProgID(ProgId, throwOnError: true)!;
        _application ??= Activator.CreateInstance(type) ?? throw new COMException("Unable to create VisMockup COM application");
        return _application;
    }
    public Task<object> StatusAsync() => _sta.InvokeAsync<object>(() =>
    {
        try { dynamic app = Connect(); _ = app.Documents; return new { connected = true, platform = "windows" }; }
        catch { _application = null; return new { connected = false, platform = "windows" }; }
    });
    public async Task<object> LaunchAsync()
    {
        var status = await StatusAsync();
        if ((bool)(status.GetType().GetProperty("connected")?.GetValue(status) ?? false)) return new { status = "already_running" };
        var fullExe = Path.GetFullPath(_executable);
        if (!File.Exists(fullExe)) throw new FileNotFoundException("VisMockup executable not found", fullExe);
        Process.Start(new ProcessStartInfo(fullExe) { UseShellExecute = true });
        return new { status = "starting" };
    }
    public Task<object> OpenFileAsync(string filePath) => _sta.InvokeAsync<object>(() =>
    {
        var safePath = _paths.ValidateModelPath(filePath); dynamic app = Connect(); app.Documents.Open(safePath); return new { opened = true };
    });
    public Task<object> VisibilityAsync(string action) => _sta.InvokeAsync<object>(() =>
    {
        dynamic app = Connect(); dynamic documents = app.Documents;
        if ((int)documents.Count <= 0) throw new InvalidOperationException("No active VisMockup document");
        dynamic view = documents.Item(1).ActiveView;
        switch (action) { case "all_on": view.AllNodesOn(); break; case "all_off": view.AllNodesOff(); break; case "deselect": view.DeSelectAllNodes(); break; default: throw new InvalidOperationException("Unsupported visibility action"); }
        return new { action };
    });
    public Task<object> TreeAsync(int maxDepth) => _sta.InvokeAsync<object>(() =>
    {
        if (maxDepth is < 1 or > 8) throw new ConnectorException("vismockup_tree_depth_invalid");
        var document = _connection.RequireActiveDocument();
        var cached = _treeCache?.TryRead(document, maxDepth);
        if (cached is not null) return TreeResult(cached.Nodes, maxDepth);
        var root = document.RootNode;
        var nodes = new List<CachedTreeNode>();
        var queue = new Queue<(IVisMockupNode Node, string? Parent, int ChildOrder, int Depth)>();
        queue.Enqueue((root, null, 0, 0));
        while (queue.Count > 0)
        {
            var item = queue.Dequeue();
            var nodeKey = item.Node.NodeKey;
            var children = item.Node.Children;
            nodes.Add(new(nodeKey, item.Parent, item.ChildOrder, item.Depth,
                item.Node.PrintableName, "", item.Depth >= maxDepth && children.Count > 0));
            if (item.Depth < maxDepth)
            {
                for (var index = 0; index < children.Count; index++)
                    queue.Enqueue((children[index], nodeKey, index, item.Depth + 1));
            }
        }
        _treeCache?.Replace(document, maxDepth, nodes);
        return TreeResult(nodes, maxDepth);
    });

    private static object TreeResult(IReadOnlyList<CachedTreeNode> nodes, int maxDepth) => new
    {
        nodes = nodes.Select(node => new
        {
            node_key = node.NodeKey, parent_node_key = node.ParentNodeKey,
            name = node.Name, catia_occurrence_name = node.CatiaOccurrenceName,
            has_more = node.HasMore,
        }).ToArray(),
        max_depth = maxDepth,
    };
    public Task<object> HighlightAsync(IReadOnlySet<string> catiaNames) => _sta.InvokeAsync<object>(() =>
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
    public Task<object> CaptureAsync() => _sta.InvokeAsync<object>(() =>
    {
        dynamic app = Connect(); dynamic documents = app.Documents;
        if ((int)documents.Count <= 0) throw new InvalidOperationException("No active VisMockup document");
        var directory = Path.Combine(Path.GetTempPath(), "AI00", "captures"); Directory.CreateDirectory(directory);
        var path = Path.Combine(directory, $"vismockup_{DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()}.png");
        documents.Item(1).ActiveView.CaptureImage(path);
        return new { path, exists = File.Exists(path) };
    });
}
