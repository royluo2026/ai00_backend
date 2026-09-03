using Ai00.Connector.Adapters.VisMockup;

namespace Ai00.Connector.Tests;

public sealed class FakeVisMockupCom : IVisMockupCom
{
    public IVisMockupApplication? ExistingApplication { get; set; }
    public int LaunchCalls { get; private set; }
    public HashSet<int> ThreadIds { get; } = [];
    public HashSet<ApartmentState> ApartmentStates { get; } = [];

    public bool TryGetActiveApplication(out IVisMockupApplication? application)
    {
        ThreadIds.Add(Environment.CurrentManagedThreadId);
        ApartmentStates.Add(Thread.CurrentThread.GetApartmentState());
        application = ExistingApplication;
        return application is not null;
    }

    public void Launch() => LaunchCalls++;
    public IVisMockupApplication WaitForActiveApplication(TimeSpan timeout) =>
        ExistingApplication ?? throw new InvalidOperationException("not active");

    public static FakeApplication WithDocument(string documentId, int nodeCount = 1) =>
        new("14.2.0", new FakeDocument(documentId, "tc://bom/1", FakeNode.FlatTree(nodeCount)));
}

public sealed record FakeApplication(string ProductVersion, IVisMockupDocument? ActiveDocument) : IVisMockupApplication;
public sealed class FakeDocument(string documentId, string sourceIdentity, IVisMockupNode rootNode) : IVisMockupDocument
{
    private readonly HashSet<string> _visible = [];
    public string DocumentId { get; } = documentId;
    public string SourceIdentity { get; } = sourceIdentity;
    public IVisMockupNode RootNode { get; } = rootNode;
    public int CaptureImageCalls { get; private set; }
    public CaptureProfile Profile { get; private set; } = new("png", 1, 1, "current");
    public IReadOnlyCollection<string> AllNodeKeys => Traverse().Select(item => item.NodeKey).ToArray();
    public IReadOnlyCollection<string> VisibleNodeKeys => _visible.ToArray();
    public void SetNodeVisible(string nodeKey, bool visible)
    {
        if (!AllNodeKeys.Contains(nodeKey, StringComparer.Ordinal)) throw new InvalidOperationException("node not found");
        if (visible) _visible.Add(nodeKey); else _visible.Remove(nodeKey);
    }
    public void ApplyCaptureProfile(CaptureProfile profile) => Profile = profile;
    public string AttachModel(string path) => "attached-" + Path.GetFileNameWithoutExtension(path);
    public void CaptureImage(string path)
    {
        CaptureImageCalls++;
        var header = new byte[24] { 137, 80, 78, 71, 13, 10, 26, 10, 0, 0, 0, 13, 73, 72, 68, 82, 0, 0, 0, 0, 0, 0, 0, 0 };
        System.Buffers.Binary.BinaryPrimitives.WriteInt32BigEndian(header.AsSpan(16, 4), Profile.Width);
        System.Buffers.Binary.BinaryPrimitives.WriteInt32BigEndian(header.AsSpan(20, 4), Profile.Height);
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllBytes(path, header);
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
    public static IVisMockupNode FlatTree(int count)
    {
        var children = Enumerable.Range(1, Math.Max(0, count - 1))
            .Select(index => (IVisMockupNode)new FakeNode($"node-{index}", $"Node {index}", $"occ-{index}", $"model-{index}", []))
            .ToArray();
        return new FakeNode("node-0", "Node 0", "occ-0", "model-0", children);
    }
}
