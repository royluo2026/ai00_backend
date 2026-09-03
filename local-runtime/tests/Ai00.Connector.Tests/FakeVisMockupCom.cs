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
public sealed record FakeDocument(string DocumentId, string SourceIdentity, IVisMockupNode RootNode) : IVisMockupDocument;
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
