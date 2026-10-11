using Ai00.Connector.Adapters.VisMockup;

namespace Ai00.Connector.Tests;

public sealed class FakeVisMockupCom : IVisMockupCom
{
    public bool ProcessRunning { get; set; }
    public int? ProcessId { get; set; }
    public long? ProcessStartUtcTicks { get; set; }
    public VisMockupProcessState InspectProcess() => new(ProcessRunning || ExistingApplication is not null,
        "14.2.0", ProcessId, ProcessStartUtcTicks);
    public IVisMockupApplication? ExistingApplication { get; set; }
    public IVisMockupApplication? LaunchedApplication { get; set; }
    public int LaunchCalls { get; private set; }
    public int HideOwnedWindowsCalls { get; private set; }
    public HashSet<int> ThreadIds { get; } = [];
    public HashSet<ApartmentState> ApartmentStates { get; } = [];

    public bool TryGetActiveApplication(out IVisMockupApplication? application)
    {
        ThreadIds.Add(Environment.CurrentManagedThreadId);
        ApartmentStates.Add(Thread.CurrentThread.GetApartmentState());
        application = ExistingApplication;
        return application is not null;
    }

    public void Launch()
    {
        LaunchCalls++;
        ExistingApplication = LaunchedApplication;
    }
    public void HideOwnedWindows() => HideOwnedWindowsCalls++;
    public IVisMockupApplication WaitForActiveApplication(TimeSpan timeout) =>
        ExistingApplication ?? throw new InvalidOperationException("not active");

    public static FakeApplication WithDocument(string documentId, int nodeCount = 1) =>
        new("14.2.0", new FakeDocument(documentId, "tc://bom/1", FakeNode.FlatTree(nodeCount)));
}

public sealed class FakeApplication(string productVersion, IVisMockupDocument? activeDocument) : IVisMockupApplication
{
    private IVisMockupDocument? _activeDocument = activeDocument;
    public string ProductVersion { get; } = productVersion;
    public int ActiveDocumentReads { get; private set; }
    public IVisMockupDocument? ActiveDocument
    {
        get { ActiveDocumentReads++; return _activeDocument; }
        set => _activeDocument = value;
    }
    public IReadOnlyList<IVisMockupDocument> OpenDocuments { get; set; } = activeDocument is null ? [] : [activeDocument];
    public FakeDocument? LastOpenedDocument { get; private set; }
    public int OpenCalls { get; private set; }
    public Func<string,FakeDocument>? DocumentFactory { get; set; }
    public IVisMockupDocument OpenDocument(string path)
    {
        OpenCalls++;
        LastOpenedDocument = DocumentFactory?.Invoke(path) ?? new FakeDocument(Path.GetFullPath(path), Path.GetFullPath(path), FakeNode.FlatTree(1));
        ActiveDocument = LastOpenedDocument;
        OpenDocuments = [.. OpenDocuments, LastOpenedDocument];
        return LastOpenedDocument;
    }
    public void CloseAllDocuments()
    {
        ActiveDocument?.Close();
        if (LastOpenedDocument is not null && !ReferenceEquals(LastOpenedDocument, ActiveDocument))
            LastOpenedDocument.Close();
        ActiveDocument = null;
        OpenDocuments = [];
    }
}
public sealed class FakeDocument(string documentId, string sourceIdentity, IVisMockupNode rootNode) : IVisMockupDocument
{
    public NativeDocumentWindow NativeWindow { get; set; }=new("12345","67890");
    public int ActivateNativeWindowCalls { get; private set; }
    public Action? AfterNativeActivation { get; set; }
    public NativeDocumentWindow LocateNativeWindow(int processId,NativeDocumentWindow? previous)=>NativeWindow;
    public NativeDocumentWindow SelectExistingNativeWindow(int processId)
    {
        AfterNativeActivation?.Invoke();
        return NativeWindow;
    }
    public NativeDocumentWindow ActivateNativeWindow(int processId,NativeDocumentWindow target)
    {
        ActivateNativeWindowCalls++;
        if(target!=NativeWindow)throw new Ai00.Connector.Contracts.ConnectorException("vismockup_document_window_changed");
        AfterNativeActivation?.Invoke();
        return target;
    }
    private readonly HashSet<string> _visible = [];
    private readonly HashSet<string> _selected = [];
    private readonly List<string> _insertedDocumentPaths = [];
    public string DocumentId { get; } = documentId;
    public string SourceIdentity { get; } = sourceIdentity;
    public int HierarchyCount { get; set; } = 1;
    public IVisMockupNode RootNode { get; } = rootNode;
    public int CaptureImageCalls { get; private set; }
    public Action<string>? CaptureWriter { get; set; }
    public Dictionary<string, (double Red, double Green, double Blue)> NodeColors { get; } = [];
    public bool IgnoreNodeColors { get; set; }
    public int FitCaptureCalls { get; private set; }
    public void SetNodeColors(IReadOnlyList<string> keys, double red, double green, double blue)
    {
        if (!IgnoreNodeColors) foreach (var key in keys) NodeColors[key] = (red, green, blue);
    }
    public void FitCaptureView() => FitCaptureCalls++;
    public int ExportPlmxmlCalls { get; private set; }
    public string? ExportPlmxmlContent { get; set; }
    public Dictionary<int, string> ExportPlmxmlByHierarchy { get; } = [];
    public bool Closed { get; private set; }
    public List<bool> VisibilityChanges { get; } = [];
    public int SetNodeVisibleCalls { get; private set; }
    public List<(string[] Keys,bool Visible)> BatchVisibilityWrites { get; } = [];
    public void SetNodesVisible(IReadOnlyList<string> keys,bool visible)
    {
        BatchVisibilityWrites.Add((keys.ToArray(),visible));
        foreach(var key in keys)SetNodeVisible(key,visible);
    }
    public int SetNodeSelectedCalls { get; private set; }
    public int FindNodeByKeyCalls { get; private set; }
    public Action? AfterNodeLookup { get; set; }
    public Action? AfterNodeWrite { get; set; }
    public Dictionary<string, IVisMockupNode> CadNodes { get; } = new(StringComparer.Ordinal);
    private Dictionary<string, IVisMockupNode>? _runtimeNodes;
    // Native-key users opt into an index. Legacy tests retain their traversal
    // behavior and can construct identity-only documents without a root node.
    public Dictionary<string, IVisMockupNode> RuntimeNodes => _runtimeNodes ??= IndexNodes(RootNode);
    public IVisMockupNode FindNodeByKey(string key)
    {
        FindNodeByKeyCalls++;
        var node = RuntimeNodes[key];
        AfterNodeLookup?.Invoke();
        return node;
    }
    public IVisMockupNode FindNodeByCadId(string cadId) => CadNodes[cadId];
    public IReadOnlyList<IVisMockupNode> GetAllNodes(int maximum)
    {
        if(RuntimeNodes.Count>maximum)throw new Ai00.Connector.Contracts.ConnectorNoEffectException("viewer_mapping_budget_exceeded");
        return RuntimeNodes.Values.ToArray();
    }
    public Exception? SetNodeVisibleError { get; set; }
    public bool ApplyVisibilityBeforeThrow { get; set; }
    public Exception? SetNodeSelectedError { get; set; }
    public IReadOnlyList<string> InsertedDocumentPaths => _insertedDocumentPaths;
    public int InsertDocumentCalls { get; private set; }
    public Action<string>? AfterInsertDocument { get; set; }
    public Action<string>? AfterDeleteInsertedDocument { get; set; }
    public CaptureProfile Profile { get; private set; } = new("png", 1, 1, "current");
    public IReadOnlyCollection<string> AllNodeKeys => Traverse().Select(item => item.NodeKey).ToArray();
    public IReadOnlyCollection<string> VisibleNodeKeys => _visible.ToArray();
    public IReadOnlyCollection<string> SelectedNodeKeys => _selected.ToArray();
    public bool IsNodeVisible(string nodeKey) => _visible.Contains(nodeKey);
    public void SetNodeVisible(string nodeKey, bool visible)
    {
        SetNodeVisibleCalls++;
        if (_runtimeNodes is null ? !AllNodeKeys.Contains(nodeKey, StringComparer.Ordinal) : !_runtimeNodes.ContainsKey(nodeKey))
            throw new InvalidOperationException("node not found");
        if (visible) _visible.Add(nodeKey); else _visible.Remove(nodeKey);
        var fakeNode = _runtimeNodes is null
            ? Traverse().OfType<FakeNode>().FirstOrDefault(node => node.NodeKey == nodeKey)
            : _runtimeNodes[nodeKey] as FakeNode;
        if (fakeNode is not null) fakeNode.IsVisible = visible;
        AfterNodeWrite?.Invoke();
        if (SetNodeVisibleError is not null)
        {
            if (!ApplyVisibilityBeforeThrow)
            {
                if (visible) _visible.Remove(nodeKey); else _visible.Add(nodeKey);
                if (fakeNode is not null) fakeNode.IsVisible = !visible;
            }
            throw SetNodeVisibleError;
        }
    }
    public void SetNodeSelected(string nodeKey, bool selected)
    {
        SetNodeSelectedCalls++;
        if (_runtimeNodes is null ? !AllNodeKeys.Contains(nodeKey, StringComparer.Ordinal) : !_runtimeNodes.ContainsKey(nodeKey))
            throw new InvalidOperationException("node not found");
        if (selected) _selected.Add(nodeKey); else _selected.Remove(nodeKey);
        AfterNodeWrite?.Invoke();
        if (SetNodeSelectedError is not null) throw SetNodeSelectedError;
    }
    public void ApplyCaptureProfile(CaptureProfile profile) => Profile = profile;
    public string AttachModel(string path) => "attached-" + Path.GetFileNameWithoutExtension(path);
    public string InsertDocument(string path)
    {
        InsertDocumentCalls++;
        var fullPath = Path.GetFullPath(path);
        _insertedDocumentPaths.Add(fullPath);
        AfterInsertDocument?.Invoke(fullPath);
        return fullPath;
    }
    public void DeleteInsertedDocument(int index)
    {
        var path=_insertedDocumentPaths[index];
        _insertedDocumentPaths.RemoveAt(index);
        AfterDeleteInsertedDocument?.Invoke(path);
    }
    public void CaptureImage(string path)
    {
        CaptureImageCalls++;
        if (CaptureWriter is not null) { CaptureWriter(path); return; }
        var header = new byte[24] { 137, 80, 78, 71, 13, 10, 26, 10, 0, 0, 0, 13, 73, 72, 68, 82, 0, 0, 0, 0, 0, 0, 0, 0 };
        System.Buffers.Binary.BinaryPrimitives.WriteInt32BigEndian(header.AsSpan(16, 4), Profile.Width);
        System.Buffers.Binary.BinaryPrimitives.WriteInt32BigEndian(header.AsSpan(20, 4), Profile.Height);
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllBytes(path, header);
    }
    public void ExportPlmxml(string path, int hierarchyIndex)
    {
        ExportPlmxmlCalls++;
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllText(path, ExportPlmxmlByHierarchy.GetValueOrDefault(hierarchyIndex)
            ?? ExportPlmxmlContent ?? $"<PLMXML hierarchy=\"{hierarchyIndex}\"/>");
    }
    public Exception? SetAllNodesVisibleError { get; set; }
    public Action? AfterAllNodesVisibilityWrite { get; set; }
    public void SetAllNodesVisible(bool visible)
    {
        VisibilityChanges.Add(visible);
        foreach (var node in RuntimeNodes.Values)
        {
            if (visible) _visible.Add(node.NodeKey); else _visible.Remove(node.NodeKey);
            if (node is FakeNode fakeNode) fakeNode.IsVisible = visible;
        }
        AfterAllNodesVisibilityWrite?.Invoke();
        if (SetAllNodesVisibleError is not null) throw SetAllNodesVisibleError;
    }
    public void Close() => Closed = true;
    private static Dictionary<string, IVisMockupNode> IndexNodes(IVisMockupNode root)
    {
        var result = new Dictionary<string, IVisMockupNode>(StringComparer.Ordinal);
        var pending = new Queue<IVisMockupNode>();
        pending.Enqueue(root);
        while (pending.TryDequeue(out var node))
        {
            result.TryAdd(node.NodeKey, node);
            foreach (var child in node.Children) pending.Enqueue(child);
        }
        return result;
    }
    private IEnumerable<IVisMockupNode> Traverse()
    {
        var queue = new Queue<IVisMockupNode>();
        queue.Enqueue(RootNode);
        while (queue.TryDequeue(out var node))
        {
            yield return node;
            foreach (var child in node.Children) queue.Enqueue(child);
        }
    }
}
public sealed record FakeNode(
    string NodeKey,
    string PrintableName,
    string OccurrenceId,
    string ModelId,
    IReadOnlyList<IVisMockupNode> Children) : IVisMockupNode
{
    public string CadId { get; init; } = "";
    public IReadOnlyList<double> GlobalTransform { get; set; } = new double[]{1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1};
    public bool IsVisible { get; set; }
    public static IVisMockupNode FlatTree(int count)
    {
        var children = Enumerable.Range(1, Math.Max(0, count - 1))
            .Select(index => (IVisMockupNode)new FakeNode($"node-{index}", $"Node {index}", $"occ-{index}", $"model-{index}", []))
            .ToArray();
        return new FakeNode("node-0", "Node 0", "occ-0", "model-0", children);
    }
}
