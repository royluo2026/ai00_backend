using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Xml;
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
    private readonly string _plmxmlRoot;
    private readonly ILiveHierarchyInventoryReader _liveHierarchyReader;
    private readonly TeamcenterReadOnlyRuntime _teamcenter;
    private readonly ITeamcenterVisualizationLauncher _teamcenterVisualizationLauncher = new TeamcenterVisualizationRunner();
    private object? _application;
    private string? _ownedDocumentId;
    private (int ProcessId, long Started, string DocumentId, string Source, string RootKey, string? SourceRevision)? _mappedSession;
    private readonly Dictionary<string, string> _sessionNodeKeys = new(StringComparer.Ordinal);

    public VisMockupAdapter(StaDispatcher sta, AllowedPathPolicy paths, string executable)
        : this(sta, paths, new WindowsVisMockupCom(executable), executable,
            Path.Combine(Path.GetTempPath(), "AI00", "captures"),
            new VisMockupTreeCache(Path.Combine(Path.GetTempPath(), "AI00", "vismockup-tree-cache.db")), null, null) { }

    public VisMockupAdapter(StaDispatcher sta, AllowedPathPolicy paths, string executable, string captureRoot)
        : this(sta, paths, new WindowsVisMockupCom(executable), executable, captureRoot,
            new VisMockupTreeCache(Path.Combine(Path.GetDirectoryName(captureRoot) ?? captureRoot,
                "vismockup-tree-cache.db")), null, null) { }

    public VisMockupAdapter(StaDispatcher sta, AllowedPathPolicy paths, IVisMockupCom com)
        : this(sta, paths, com, "", Path.Combine(Path.GetTempPath(), "AI00", "captures"), null, null, null) { }

    public VisMockupAdapter(StaDispatcher sta, AllowedPathPolicy paths, IVisMockupCom com, string captureRoot)
        : this(sta, paths, com, "", captureRoot,
            new VisMockupTreeCache(Path.Combine(Path.GetDirectoryName(captureRoot) ?? captureRoot, "vismockup-tree-cache.db")), null, null) { }

    public VisMockupAdapter(StaDispatcher sta, AllowedPathPolicy paths, IVisMockupCom com, string captureRoot, string treeCachePath)
        : this(sta, paths, com, "", captureRoot, new VisMockupTreeCache(treeCachePath), null, null) { }

    public VisMockupAdapter(StaDispatcher sta, AllowedPathPolicy paths, IVisMockupCom com, string captureRoot,
        string treeCachePath, TeamcenterReadOnlyRuntime teamcenter)
        : this(sta, paths, com, "", captureRoot, new VisMockupTreeCache(treeCachePath), null, teamcenter) { }

    internal VisMockupAdapter(StaDispatcher sta, AllowedPathPolicy paths, IVisMockupCom com, string captureRoot,
        string treeCachePath, TeamcenterReadOnlyRuntime teamcenter, ITeamcenterVisualizationLauncher launcher)
        : this(sta, paths, com, captureRoot, treeCachePath, teamcenter)
    { _teamcenterVisualizationLauncher = launcher; }

    internal VisMockupAdapter(StaDispatcher sta, AllowedPathPolicy paths, IVisMockupCom com,
        string captureRoot, ILiveHierarchyInventoryReader liveHierarchyReader)
        : this(sta, paths, com, "", captureRoot, null, liveHierarchyReader, null) { }

    private VisMockupAdapter(StaDispatcher sta, AllowedPathPolicy paths, IVisMockupCom com, string executable,
        string captureRoot, VisMockupTreeCache? treeCache, ILiveHierarchyInventoryReader? liveHierarchyReader,
        TeamcenterReadOnlyRuntime? teamcenter)
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
        _plmxmlRoot = Path.Combine(Path.GetDirectoryName(captureRoot) ?? captureRoot, "plmxml");
        _liveHierarchyReader = liveHierarchyReader ?? new VisMockupInProcessHierarchyReader(
            Path.Combine(Path.GetDirectoryName(captureRoot) ?? captureRoot, "native-hierarchy"));
        _teamcenter = teamcenter ?? TeamcenterReadOnlyRuntime.CreateInstalled(
            Path.GetDirectoryName(captureRoot) ?? captureRoot);
    }
    public AdapterManifest Manifest { get; } = new(
        "ai00.vismockup", 1, "siemens.vismockup", "14.0.0",
        [
            new("vismockup.application.probe@1", "sha256:197cfad8bc3453030fdc288ea78c3abc21699274dd48d4482444af4f62380a37"),
            new("vismockup.document.identity.read@1", "sha256:2a8b6e89d3a13cf35b0584a989ed79977700d3cd3fe9fcc918c3b871d1c8c4d7"),
            new("vismockup.document.hierarchy_inventory.read@1", "sha256:a89bdc3fbb04ee643f1434dee83c653df8a04fc406ac7fff1e61ce39ee99685a"),
            new("vismockup.document.snapshot@1", "sha256:aa7c11c2501026c470a9cc7bfcbbecc7339879c18bf2b6b86f68ed7fc2e1861b"),
            new("vismockup.model.open@1", "sha256:aabd43bb066794c250f7eeed41def7c147a4da7263e813f192efa59a0cb40e34"),
            new("vismockup.model.insert@1", "sha256:70e68f565989a75406fabb5ffcc5b6f87233f2e55be9a011b202671a26f7c370"),
            new("vismockup.model.close@1", "sha256:a1a27969ab8638c9868b384ccb546aed1ece56219ded7c7ec3bb3d6b19861771"),
            new("vismockup.visibility.change@1", "sha256:6ecb8dd2239a2ca881bfc8d40463778f2b80f15f66f1be50a3ceb91a90bff201"),
            new("vismockup.node.visibility.change@1", "sha256:b93246b1bb189e3f7e488c4ec0528378cbbf97cd2c3fdd547daf0f2007f05f6c"),
            new("vismockup.node.selection.change@1", "sha256:4ca8699ef27b5de3691dc8e2b6252350e001263e23e805489d16b435b575a539"),
            new("vismockup.tree.read@1", "sha256:b3c6a014ac8853a3b6689286ce514b7997bb450f6394253d813308afa8863af0"),
            new("vismockup.tree.read@2", "sha256:5d69cc98e38bd721fb55623b62df5162e68cbfb9bcb51c1b6c25d351c486de7c"),
            new("vismockup.model.attach@1", "sha256:444b6b8a963b5a7e04d6b607cfe53699a5c93196a5bf78c98843d12d073fe844"),
            new("vismockup.scene.apply@1", "sha256:fce8ff3a33d996a26c3121d015839e2d68bc3c631a8c8c1091201e95d0bcabd3"),
            new("vismockup.scene.verify@1", "sha256:e99bf5896c3f655afc7470fc140d261225d6f37a1d8224b7e9438a2e7b7a211a"),
            new("vismockup.view.capture@1", "sha256:10a4b5540a34fb32a2e6a4d24fd1efbe7afb929e2cc3c9fed44f6b4d9893962d"),
            new("teamcenter.product.search@1", "sha256:212e3c2396bf642456efa5e12674878fdbc201fc60250bcb3f150e19353d0acc"),
            new("teamcenter.product.search@2", "sha256:6ef619b8abeb6705574ffa7e0902708b3c998773c80da4649a0f3f38b01c3310"),
            new("teamcenter.revision_rule.search@1", "sha256:1b6c1a36b0fa4a4654efa3ce4a67111403f2c862aeb20283206786c5ba86d9c0"),
            new("teamcenter.product_structure.observe@1", "sha256:704e6c398c551cc7a667d1ccf4d00c1b7f6330649676dbdd8b4fa9d92857a32b"),
            new("teamcenter.product_structure.page.read@1", "sha256:0ef57b5769664cebca42562cbb711228994e6257901786f84f5dfb82a8a6c6ad"),
            new("teamcenter.product_structure.children.read@1", "sha256:a76cbb3fba1abefdef619baad7a718a641dc6a4ab51ceb1e2e6575851837196f"),
            new("teamcenter.node_properties.read@1", "sha256:aab317614eb33e600e66660b0879fe59fdda138b7c37fe373af1c12d75eff6b5"),
            new("teamcenter.visualization.launch@1", "sha256:d74338b54d5abd84dad3435768aa56756ef4fbb560f1d605b2b1bb9cc18519a8"),
            new("teamcenter.visualization.insert@1", "sha256:d3bd3656f14f8bfb9e3e2090c2462317aac1f4f1ca983fb92a7f8553fae84d1d"),
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

    private async Task<object> ReadDocumentIdentityAsync(System.Text.Json.JsonElement payload, CancellationToken cancellationToken)
    {
        if (payload.ValueKind != System.Text.Json.JsonValueKind.Object || payload.EnumerateObject().Any())
            throw new ConnectorException("vismockup_document_identity_input_invalid");
        cancellationToken.ThrowIfCancellationRequested();
        var result = await _sta.InvokeAsync<object>(() =>
        {
            cancellationToken.ThrowIfCancellationRequested();
            var before = RequireProcessIdentity();
            var handle = _connection.RequireActiveDocument(allowLaunch: false).DocumentId;
            if (string.IsNullOrWhiteSpace(handle))
                throw new ConnectorException("vismockup_document_handle_unavailable");
            var handleAfter = _connection.RequireActiveDocument(allowLaunch: false).DocumentId;
            var after = RequireProcessIdentity();
            if (before.ProcessId != after.ProcessId || before.ProcessStartUtcTicks != after.ProcessStartUtcTicks ||
                !string.Equals(handle, handleAfter, StringComparison.Ordinal))
                throw new ConnectorException("vismockup_document_identity_changed");
            var ticks = before.ProcessStartUtcTicks!.Value.ToString(System.Globalization.CultureInfo.InvariantCulture);
            // Polling cannot detect a handle closed and reused entirely between reads.
            var session = CanonicalJson.Hash(new { process_id = before.ProcessId!.Value,
                process_started_utc_ticks = ticks, document_handle = handle });
            return new { document_session = session, process_id = before.ProcessId.Value,
                process_started_utc_ticks = ticks, document_handle = handle };
        });
        cancellationToken.ThrowIfCancellationRequested();
        return result;
    }

    private async Task<object> ReadHierarchyInventoryAsync(System.Text.Json.JsonElement payload, CancellationToken cancellationToken)
    {
        if (payload.ValueKind != System.Text.Json.JsonValueKind.Object
            || payload.EnumerateObject().Any(item => item.Name is not ("document_session" or "start_index" or "page_size" or "max_nodes")))
            throw new ConnectorException("vismockup_hierarchy_inventory_input_invalid");
        var expectedSession = payload.GetProperty("document_session").GetString() ?? "";
        var startIndex = payload.GetProperty("start_index").GetInt32();
        var pageSize = payload.GetProperty("page_size").GetInt32();
        var maxNodes = payload.GetProperty("max_nodes").GetInt32();
        if (!expectedSession.StartsWith("sha256:", StringComparison.Ordinal) || expectedSession.Length != 71
            || startIndex < 0 || pageSize is < 1 or > 16 || maxNodes is < 1 or > 100_000)
            throw new ConnectorException("vismockup_hierarchy_inventory_input_invalid");
        cancellationToken.ThrowIfCancellationRequested();
        var result = await _sta.InvokeAsync<object>(() =>
        {
            cancellationToken.ThrowIfCancellationRequested();
            var before = RequireProcessIdentity();
            var document = _connection.RequireActiveDocument(allowLaunch: false);
            var session = DocumentSession(before, document.DocumentId);
            if (!string.Equals(session, expectedSession, StringComparison.Ordinal))
                throw new ConnectorException("vismockup_document_changed");
            var page = _liveHierarchyReader.Read(before, document.DocumentId, document.SourceIdentity,
                session, startIndex, pageSize, maxNodes);
            var after = RequireProcessIdentity();
            var documentAfter = _connection.RequireActiveDocument(allowLaunch: false);
            if (!string.Equals(session, DocumentSession(after, documentAfter.DocumentId), StringComparison.Ordinal))
                throw new ConnectorException("vismockup_document_changed");
            return page;
        });
        cancellationToken.ThrowIfCancellationRequested();
        return result;
    }

    private static string DocumentSession(VisMockupProcessState process, string documentHandle)
    {
        var ticks = process.ProcessStartUtcTicks!.Value.ToString(System.Globalization.CultureInfo.InvariantCulture);
        return CanonicalJson.Hash(new { process_id = process.ProcessId!.Value,
            process_started_utc_ticks = ticks, document_handle = documentHandle });
    }

    private VisMockupProcessState RequireProcessIdentity()
    {
        var process = _com.InspectProcess();
        if (!process.Running || process.ProcessId is not > 0 || process.ProcessStartUtcTicks is not > 0)
            throw new ConnectorException("vismockup_process_identity_unavailable");
        return process;
    }

    public Task<VisMockupDocumentSnapshot> SnapshotAsync(int maxNodes, int maxDepth) =>
        _sta.InvokeAsync(() =>
        {
            var document = _connection.RequireActiveDocument();
            _sessionNodeKeys.Clear();
            _mappedSession = null;
            try { return ReadPlmxmlSnapshot(document, maxNodes, maxDepth); }
            catch (ConnectorException error) when (error.Code is
                "plmxml_current_state_structure_missing" or
                "plmxml_current_state_root_identity_missing")
            {
                return new DocumentSnapshotReader().Read(document, maxNodes, maxDepth);
            }
        });

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
            "vismockup.document.identity.read@1" => await ReadDocumentIdentityAsync(operation.Payload, cancellationToken),
            "vismockup.document.hierarchy_inventory.read@1" => await ReadHierarchyInventoryAsync(operation.Payload, cancellationToken),
            "vismockup.application.probe@1" => await ProbeAsync(
                operation.Payload.TryGetProperty("allow_launch", out var allowLaunch) && allowLaunch.GetBoolean(), cancellationToken),
            "vismockup.document.snapshot@1" => await SnapshotAsync(
                operation.Payload.GetProperty("max_nodes").GetInt32(),
                operation.Payload.GetProperty("max_depth").GetInt32()),
            "vismockup.model.open@1" => await OpenManagedFileAsync(
                operation.Payload.GetProperty("local_artifact_path").GetString() ?? ""),
            "vismockup.model.insert@1" => await InsertManagedFileAsync(
                operation.Payload.GetProperty("local_artifact_path").GetString() ?? ""),
            "vismockup.model.close@1" => await CloseManagedFileAsync(),
            "vismockup.visibility.change@1" => await ChangeAllVisibilityAsync(
                operation.Payload.GetProperty("action").GetString() ?? ""),
            "vismockup.node.visibility.change@1" => await ChangeNodeVisibilityAsync(
                operation.Payload.GetProperty("node_key").GetString() ?? "",
                operation.Payload.GetProperty("action").GetString() ?? ""),
            "vismockup.node.selection.change@1" => await ChangeNodeSelectionAsync(
                operation.Payload.GetProperty("node_key").GetString() ?? "",
                operation.Payload.GetProperty("action").GetString() ?? ""),
            "vismockup.tree.read@1" => await TreeAsync(
                operation.Payload.GetProperty("max_depth").GetInt32(),
                operation.Payload.TryGetProperty("force_refresh", out var forceRefresh) && forceRefresh.GetBoolean()),
            "vismockup.tree.read@2" => await TreeAsync(
                operation.Payload.GetProperty("max_depth").GetInt32(),
                operation.Payload.TryGetProperty("force_refresh", out var liveForceRefresh) && liveForceRefresh.GetBoolean(),
                includeVisibility: true),
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
            "teamcenter.product_structure.observe@1" => await _teamcenter.ObserveAsync(operation.Payload, cancellationToken),
            "teamcenter.product_structure.children.read@1" => await _teamcenter.ReadChildrenAsync(operation.Payload, cancellationToken),
            "teamcenter.node_properties.read@1" => await _teamcenter.ReadNodePropertiesAsync(operation.Payload, cancellationToken),
            "teamcenter.product.search@1" => await _teamcenter.SearchAsync(operation.Payload, cancellationToken),
            "teamcenter.product.search@2" => await _teamcenter.SearchV2Async(operation.Payload, cancellationToken),
            "teamcenter.revision_rule.search@1" => await _teamcenter.GetRevisionRulesAsync(operation.Payload, cancellationToken),
            "teamcenter.product_structure.page.read@1" => await _teamcenter.ReadPageAsync(
                operation.Payload.GetProperty("observation_id").GetString() ?? "",
                operation.Payload.GetProperty("cursor").GetInt32(),
                operation.Payload.GetProperty("page_size").GetInt32(), cancellationToken),
            "teamcenter.visualization.launch@1" => await OpenTeamcenterVisualizationAsync(operation.Payload, cancellationToken),
            "teamcenter.visualization.insert@1" => await InsertTeamcenterVisualizationAsync(operation.Payload, cancellationToken),
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

    public Task<object> InsertManagedFileAsync(string filePath) => _sta.InvokeAsync<object>(() =>
    {
        var safePath = _paths.ValidateModelPath(filePath);
        var document = _connection.RequireActiveDocument();
        var expected = Path.GetFullPath(safePath);
        var existing = document.InsertedDocumentPaths.FirstOrDefault(item =>
            Path.IsPathFullyQualified(item) &&
            string.Equals(Path.GetFullPath(item), expected, StringComparison.OrdinalIgnoreCase));
        var insertedPath = existing ?? document.InsertDocument(expected);
        return new
        {
            document_id = document.DocumentId,
            inserted_path = insertedPath,
            inserted_count = document.InsertedDocumentPaths.Count,
            already_present = existing is not null,
        };
    });

    public Task<object> OpenTeamcenterVisualizationAsync(JsonElement payload, CancellationToken ct) =>
        _teamcenter.ConsumeVisualizationAsync(payload, "Open",
            (path, token) => _teamcenterVisualizationLauncher.LaunchAsync(path, token), ct);

    public Task<object> InsertTeamcenterVisualizationAsync(JsonElement payload, CancellationToken ct) =>
        _teamcenter.ConsumeVisualizationAsync(payload, "Insert", async (path, token) =>
        {
            token.ThrowIfCancellationRequested();
            await _sta.InvokeAsync<object>(() =>
            {
                IVisMockupDocument document;
                try { document = _connection.RequireActiveDocument(); }
                catch (ConnectorException error) when (error.Message == "active_document_unavailable")
                { throw new ConnectorException("vismockup_active_document_required"); }
                _ = document.InsertDocument(path);
                return new { inserted = true, document_id = document.DocumentId };
            });
        }, ct);

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

    public Task<object> ChangeNodeVisibilityAsync(string nodeKey, string action) => _sta.InvokeAsync<object>(() =>
    {
        var document = _connection.RequireActiveDocument();
        var sessionNodeKey = ResolveSessionNodeKey(document, nodeKey);
        if (action == "isolate")
        {
            document.SetAllNodesVisible(false);
            document.SetNodeVisible(sessionNodeKey, true);
            return new { node_key = nodeKey, visible = true };
        }

        bool before;
        try { before = document.IsNodeVisible(sessionNodeKey); }
        catch (Exception) { throw new ConnectorNoEffectException("vismockup_node_visibility_lookup_failed"); }
        var visible = action switch
        {
            "show" => true,
            "hide" => false,
            "toggle_visible" => !before,
            _ => throw new ConnectorException("node_visibility_action_unsupported"),
        };
        // A true node flag does not imply loaded geometry or visible descendants.
        // Always issue the explicit view operation, including repeated show/hide.

        try { document.SetNodeVisible(sessionNodeKey, visible); }
        catch (Exception writeError)
        {
            bool after;
            try { after = document.IsNodeVisible(sessionNodeKey); }
            catch (Exception) { throw writeError; }
            if (after == visible) return new { node_key = nodeKey, visible };
            throw new ConnectorNoEffectException("vismockup_node_visibility_write_rejected");
        }

        if (document.IsNodeVisible(sessionNodeKey) != visible)
            throw new ConnectorNoEffectException("vismockup_node_visibility_write_rejected");
        return new { node_key = nodeKey, visible };
    });

    public Task<object> ChangeNodeSelectionAsync(string nodeKey, string action) => _sta.InvokeAsync<object>(() =>
    {
        var selected = action switch
        {
            "highlight" or "select" => true,
            "unhighlight" or "deselect" => false,
            _ => throw new ConnectorException("node_selection_action_unsupported"),
        };
        var document = _connection.RequireActiveDocument();
        document.SetNodeSelected(ResolveSessionNodeKey(document, nodeKey), selected);
        return new { node_key = nodeKey, selected };
    });

    public Task<bool> ObserveNodeVisibilityAsync(string nodeKey) => _sta.InvokeAsync(() =>
    {
        if (nodeKey.StartsWith("cad:", StringComparison.Ordinal))
        {
            var active = _connection.RequireActiveDocument();
            return active.IsNodeVisible(ResolveSessionNodeKey(active,nodeKey));
        }
        if (!nodeKey.StartsWith("pdm:", StringComparison.Ordinal))
            return _connection.RequireActiveDocument().IsNodeVisible(nodeKey);
        var application = _connection.RequireActiveApplication(false);
        foreach (var document in application.OpenDocuments)
        {
            try
            {
                var sessionNodeKey = _treeCache!.ResolveSessionNodeKey(document, nodeKey, verifyPrintableName: false);
                return document.IsNodeVisible(sessionNodeKey);
            }
            catch (InvalidDataException) when (_treeCache!.IsNodeKnownForDifferentDocument(document, nodeKey))
            {
                // Stable PDM occurrence keys are document-scoped in the cache.
                // If the signed key is known only for another document, avoid a
                // costly PLMXML rebuild of this unrelated open document.
            }
            catch (InvalidDataException) when (TryHydrateTreeCacheFromActivePlmxml(document))
            {
                try
                {
                    var sessionNodeKey = _treeCache!.ResolveSessionNodeKey(document, nodeKey, verifyPrintableName: false);
                    return document.IsNodeVisible(sessionNodeKey);
                }
                catch (InvalidDataException) { }
            }
            catch (InvalidDataException) { }
        }
        throw new ConnectorException("vismockup_recovery_node_unavailable");
    });

    private string ResolveSessionNodeKey(IVisMockupDocument document, string key)
    {
        if (key.StartsWith("cad:", StringComparison.Ordinal))
            return _treeCache?.ResolveCadNodeKey(document,key)
                ?? throw new ConnectorNoEffectException("vismockup_cad_locator_missing");
        var process = _com.InspectProcess();
        (int, long, string, string, string, string?)? session =
            process.ProcessId is int id && process.ProcessStartUtcTicks is long started
                ? (id, started, document.DocumentId, document.SourceIdentity, document.RootNode.NodeKey,
                    VisMockupTreeFingerprint.ExternalRevisionFingerprint(document.SourceIdentity))
                : null;
        if (session != _mappedSession)
        {
            _sessionNodeKeys.Clear();
            _mappedSession = session;
        }
        if (key.StartsWith("tc:", StringComparison.Ordinal))
        {
            var occurrence = key[3..];
            if (string.IsNullOrWhiteSpace(occurrence))
                throw new ConnectorNoEffectException("vismockup_session_node_mapping_stale");
            if (_sessionNodeKeys.TryGetValue(key, out var onlineKnown)) return onlineKnown;
            var matches = new List<string>();
            var pending = new Queue<IVisMockupNode>(); pending.Enqueue(document.RootNode);
            while (pending.Count > 0 && matches.Count < 2)
            {
                var node = pending.Dequeue();
                if (string.Equals(node.OccurrenceId, occurrence, StringComparison.Ordinal)) matches.Add(node.NodeKey);
                foreach (var child in node.Children) pending.Enqueue(child);
            }
            if (matches.Count != 1)
                throw new ConnectorNoEffectException(matches.Count == 0
                    ? "vismockup_online_occurrence_unmapped" : "vismockup_online_occurrence_ambiguous");
            if (_sessionNodeKeys.Count >= 4096) _sessionNodeKeys.Clear();
            _sessionNodeKeys[key] = matches[0];
            return matches[0];
        }
        if (!key.StartsWith("pdm:", StringComparison.Ordinal)) return key;
        if (session is not null && _sessionNodeKeys.TryGetValue(key, out var known)) return known;
        string resolved;
        try { resolved = _treeCache?.ResolveSessionNodeKey(document, key) ?? throw new InvalidDataException(); }
        catch (InvalidDataException) when (TryHydrateTreeCacheFromActivePlmxml(document))
        {
            try { resolved = _treeCache!.ResolveSessionNodeKey(document, key); }
            catch (InvalidDataException) { throw new ConnectorNoEffectException("vismockup_session_node_mapping_stale"); }
        }
        catch (InvalidDataException) { throw new ConnectorNoEffectException("vismockup_session_node_mapping_stale"); }
        if (session is not null)
        {
            if (_sessionNodeKeys.Count >= 4096) _sessionNodeKeys.Clear();
            _sessionNodeKeys[key] = resolved;
        }
        return resolved;
    }

    private bool TryHydrateTreeCacheFromActivePlmxml(IVisMockupDocument document)
    {
        if (_treeCache is null || !string.Equals(
                Path.GetExtension(document.SourceIdentity), ".plmxml", StringComparison.OrdinalIgnoreCase))
            return false;
        try
        {
            // The path is not supplied by the web caller: it is the source of the
            // already-open active VisMockup document. Keep the read bounded and
            // inside Connector's configured model roots.
            var source = _paths.ValidateActivePlmxmlSource(document.SourceIdentity);
            if (new FileInfo(source).Length > 64L * 1024 * 1024) return false;
            using var stream = File.OpenRead(source);
            var projection = new VisMockupPlmxmlProjectionReader().Read(stream, 250_000);
            EnsureTopLevelMatches(document, projection);
            _treeCache.ReplaceProjection(document, projection);
            _sessionNodeKeys.Clear();
            return true;
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or
            InvalidOperationException or ConnectorException or XmlException)
        {
            return false;
        }
    }

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
    public Task<object> TreeAsync(int maxDepth, bool forceRefresh = false, bool includeVisibility = false) => _sta.InvokeAsync<object>(() =>
    {
        if (maxDepth is < 1 or > 8) throw new ConnectorException("vismockup_tree_depth_invalid");
        var document = _connection.RequireActiveDocument();
        if (forceRefresh) { _sessionNodeKeys.Clear(); _mappedSession = null; }
        var cached = forceRefresh ? null : _treeCache?.TryRead(document, maxDepth);
        if (cached is not null) return TreeResult(document, cached.Nodes, maxDepth, cached.CacheState,
            includeVisibility ? ReadLiveVisibility(document, cached.Nodes, maxDepth, cached.CacheState) : null);
        // The interactive tree must not wait on VisMockup's non-cancellable
        // ExportEx call. The governed document-snapshot workflow owns PLMXML
        // acquisition; this read path mirrors the proven direct COM traversal.
        var visibility = includeVisibility ? new Dictionary<string, bool?>(StringComparer.Ordinal) : null;
        var complete = ReadCompleteComTree(document, maxDepth, visibility);
        _treeCache?.Replace(document, maxDepth, complete);
        return TreeResult(document, complete, maxDepth, "verified", visibility);
    });

    private VisMockupDocumentSnapshot ReadPlmxmlSnapshot(IVisMockupDocument document, int maxNodes, int maxDepth)
    {
        if (maxNodes is < 1 or > 250_000 || maxDepth is < 0 or > 64)
            throw new ConnectorException("bom_snapshot_limit_invalid");
        LocalPlmxmlArtifact? artifact = null;
        try
        {
            artifact = new PlmxmlExporter(_plmxmlRoot).Export(
                document, document.DocumentId, 0, "snapshot-" + Guid.NewGuid().ToString("N"));
            using var stream = File.OpenRead(artifact.Path);
            var projection = new VisMockupPlmxmlProjectionReader().Read(stream, maxNodes);
            if (projection.Nodes.Any(node => node.Depth > maxDepth))
                throw new ConnectorException("bom_snapshot_limit_exceeded");
            EnsureTopLevelMatches(document, projection);
            _treeCache?.ReplaceProjection(document, projection);
            var nodes = projection.Nodes.Select(node => new VisMockupSnapshotNode(
                node.StableOccurrenceKey,
                node.ParentStableOccurrenceKey,
                node.ChildOrder,
                node.Depth,
                node.PrintableName,
                node.PdmOccurrenceUid,
                node.ProductRef)).ToArray();
            return new(document.DocumentId, document.SourceIdentity,
                projection.RootStableOccurrenceKey, nodes, projection.SnapshotHash);
        }
        finally
        {
            if (artifact is not null && File.Exists(artifact.Path)) File.Delete(artifact.Path);
        }
    }

    private static void EnsureTopLevelMatches(IVisMockupDocument document, VisMockupPlmxmlProjection projection)
    {
        var exportedCount = projection.Nodes.Count(node =>
            string.Equals(node.ParentStableOccurrenceKey, projection.RootStableOccurrenceKey,
                StringComparison.Ordinal));
        if (exportedCount != document.RootNode.Children.Count)
            throw new ConnectorException("plmxml_current_state_incomplete");
    }

    private static IReadOnlyList<CachedTreeNode> ReadCompleteComTree(IVisMockupDocument document, int maxDepth,
        Dictionary<string, bool?>? visibility = null)
    {
        const int maxNodes = 250_000;
        var root = document.RootNode;
        var nodes = new List<CachedTreeNode>();
        var queue = new Queue<(IVisMockupNode Node, string? Parent, int ChildOrder, int Depth)>();
        queue.Enqueue((root, null, 0, 0));
        while (queue.Count > 0)
        {
            var item = queue.Dequeue();
            if (nodes.Count >= maxNodes) throw new ConnectorException("bom_snapshot_limit_exceeded");
            if (item.Depth > maxDepth) throw new ConnectorException("vismockup_tree_depth_limit_exceeded");
            var nodeKey = item.Node.NodeKey;
            var children = item.Node.Children;
            if (visibility is not null)
            {
                try { visibility[nodeKey] = item.Node.IsVisible; }
                catch { visibility[nodeKey] = null; }
            }
            // Keep the interactive tree on VisMockup's lightweight product-
            // structure path. Occurrence metadata can open JT payloads and turn
            // a shallow tree read into a multi-minute geometry scan.
            string cadId;
            try { cadId = item.Node.CadId; } catch { cadId = ""; }
            nodes.Add(new(nodeKey, item.Parent, item.ChildOrder, item.Depth,
                item.Node.PrintableName, "",
                children.Count > 0, cadId));
            if (item.Depth == maxDepth) continue;
            for (var index = 0; index < children.Count; index++)
                queue.Enqueue((children[index], nodeKey, index, item.Depth + 1));
        }
        return nodes;
    }

    private static IReadOnlyDictionary<string, bool?> ReadLiveVisibility(
        IVisMockupDocument document, IReadOnlyList<CachedTreeNode> nodes, int maxDepth, string cacheState)
    {
        try { return ReadLiveVisibilityCore(document, nodes, maxDepth, cacheState); }
        catch { return new Dictionary<string, bool?>(StringComparer.Ordinal); }
    }

    private static IReadOnlyDictionary<string, bool?> ReadLiveVisibilityCore(
        IVisMockupDocument document, IReadOnlyList<CachedTreeNode> nodes, int maxDepth, string cacheState)
    {
        var visible = new Dictionary<string, bool?>(StringComparer.Ordinal);
        var childrenByParent = nodes.Where(node => node.ParentNodeKey is not null)
            .GroupBy(node => node.ParentNodeKey!, StringComparer.Ordinal)
            .ToDictionary(group => group.Key, group => group.OrderBy(node => node.ChildOrder).ToArray(), StringComparer.Ordinal);
        var roots = nodes.Where(node => node.ParentNodeKey is null).ToArray();
        if (roots.Length != 1) return visible;
        var queue = new Queue<(IVisMockupNode Runtime, CachedTreeNode Cached)>();
        queue.Enqueue((document.RootNode, roots[0]));
        while (queue.TryDequeue(out var item))
        {
            var stable = item.Cached.NodeKey.StartsWith("pdm:", StringComparison.Ordinal);
            if ((!stable && item.Runtime.NodeKey != item.Cached.NodeKey) ||
                (stable && cacheState == "verifying" && item.Runtime.PrintableName != item.Cached.Name))
                return new Dictionary<string, bool?>(StringComparer.Ordinal);
            try { visible[item.Cached.NodeKey] = item.Runtime.IsVisible; }
            catch { visible[item.Cached.NodeKey] = null; }
            if (item.Cached.Depth >= maxDepth) continue;
            childrenByParent.TryGetValue(item.Cached.NodeKey, out var expected);
            expected ??= [];
            var current = item.Runtime.Children;
            if (current.Count != expected.Length) return new Dictionary<string, bool?>(StringComparer.Ordinal);
            for (var index = 0; index < expected.Length; index++)
            {
                if (expected[index].ChildOrder != index)
                    return new Dictionary<string, bool?>(StringComparer.Ordinal);
                queue.Enqueue((current[index], expected[index]));
            }
        }
        return visible;
    }

    private static object TreeResult(IVisMockupDocument document, IReadOnlyList<CachedTreeNode> nodes, int maxDepth, string cacheState,
        IReadOnlyDictionary<string, bool?>? visibility)
    {
        var sourceHash = VisMockupTreeCache.Identity(document);
        if (visibility is null) return new
        {
            nodes = nodes.Select(node => new {
                node_key = node.NodeKey, parent_node_key = node.ParentNodeKey,
                name = node.Name, catia_occurrence_name = node.CatiaOccurrenceName,
                control_key = VisMockupTreeCache.ControlKey(sourceHash,node.CadId),
                has_more = node.HasMore,
            }).ToArray(),
            max_depth = maxDepth, cache_state = cacheState,
        };
        return new {
            nodes = nodes.Select(node => new {
                node_key = node.NodeKey, parent_node_key = node.ParentNodeKey,
                name = node.Name, catia_occurrence_name = node.CatiaOccurrenceName,
                control_key = VisMockupTreeCache.ControlKey(sourceHash,node.CadId),
                has_more = node.HasMore,
                visible = visibility.TryGetValue(node.NodeKey, out var live) ? live : null,
            }).ToArray(),
            max_depth = maxDepth, cache_state = cacheState,
        };
    }
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
