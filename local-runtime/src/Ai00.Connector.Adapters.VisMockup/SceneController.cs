using Ai00.Connector.Contracts;

namespace Ai00.Connector.Adapters.VisMockup;

public sealed record CaptureProfile(string Format, int Width, int Height, string Background);

public sealed record SceneState(
    string OperationId,
    IReadOnlyList<string> VisibleProducts,
    IReadOnlyList<string> VisibleResources,
    CaptureProfile CaptureProfile,
    string SceneHash)
{
    public static SceneState Create(
        string operationId,
        IReadOnlyList<string> visibleProducts,
        IReadOnlyList<string> visibleResources,
        CaptureProfile captureProfile)
    {
        var draft = new SceneState(operationId, visibleProducts, visibleResources, captureProfile, "");
        return draft with { SceneHash = draft.ComputeHash() };
    }

    public string ComputeHash() => CanonicalJson.Hash(new Dictionary<string, object?>
    {
        ["operation_id"] = OperationId,
        ["visible_products"] = VisibleProducts.Order(StringComparer.Ordinal).ToArray(),
        ["visible_resources"] = VisibleResources.Order(StringComparer.Ordinal).ToArray(),
        ["capture_profile"] = new Dictionary<string, object?>
        {
            ["format"] = CaptureProfile.Format, ["width"] = CaptureProfile.Width,
            ["height"] = CaptureProfile.Height, ["background"] = CaptureProfile.Background,
        },
    });
}

public sealed record SceneVerification(string ActualSceneHash, bool Matches);

public sealed class VisMockupSessionState
{
    private readonly Dictionary<string, string> _bindings = new(StringComparer.Ordinal);
    public SceneState? LastScene { get; set; }
    public string? DocumentId { get; private set; }
    public string? BaselineSnapshotHash { get; private set; }
    public void Bind(string manifestNodeKey, string actualNodeKey) => _bindings[manifestNodeKey] = actualNodeKey;
    public string Resolve(string nodeKey) => _bindings.GetValueOrDefault(nodeKey, nodeKey);
    public string ToManifestKey(string actualNodeKey) =>
        _bindings.FirstOrDefault(item => item.Value == actualNodeKey).Key ?? actualNodeKey;
    public void RequireBaseline(IVisMockupDocument document, string expectedHash)
    {
        if (DocumentId is null)
        {
            DocumentId = document.DocumentId;
            BaselineSnapshotHash = new DocumentSnapshotReader().Read(document, 10_000, 64).SnapshotHash;
        }
        if (DocumentId != document.DocumentId || BaselineSnapshotHash != expectedHash)
            throw new ConnectorException("vismockup_document_changed");
    }
}

public sealed class SceneController(VisMockupSessionState state)
{
    public string Apply(IVisMockupDocument document, SceneState expected)
    {
        if (expected.SceneHash != expected.ComputeHash()) throw new ConnectorException("scene_verification_failed");
        var all = document.AllNodeKeys.ToHashSet(StringComparer.Ordinal);
        var expectedManifest = expected.VisibleProducts.Concat(expected.VisibleResources).ToHashSet(StringComparer.Ordinal);
        var expectedActual = expectedManifest.Select(state.Resolve).ToHashSet(StringComparer.Ordinal);
        if (expectedActual.Any(key => !all.Contains(key))) throw new ConnectorException("scene_node_not_found");
        foreach (var nodeKey in all) document.SetNodeVisible(nodeKey, expectedActual.Contains(nodeKey));
        document.ApplyCaptureProfile(expected.CaptureProfile);
        state.LastScene = expected;
        return Verify(document, expected.OperationId, expected.SceneHash).ActualSceneHash;
    }

    public SceneVerification Verify(IVisMockupDocument document, string operationId, string expectedHash)
    {
        var last = state.LastScene;
        if (last is null || last.OperationId != operationId)
            throw new ConnectorException("scene_verification_failed");
        var visibleManifest = document.VisibleNodeKeys.Select(state.ToManifestKey).ToHashSet(StringComparer.Ordinal);
        var expectedVisible = last.VisibleProducts.Concat(last.VisibleResources).ToHashSet(StringComparer.Ordinal);
        var actual = visibleManifest.SetEquals(expectedVisible)
            ? last.ComputeHash()
            : CanonicalJson.Hash(new Dictionary<string, object?>
            {
                ["operation_id"] = operationId,
                ["actual_visible_nodes"] = visibleManifest.Order(StringComparer.Ordinal).ToArray(),
                ["capture_profile"] = last.CaptureProfile,
            });
        return new(actual, actual == expectedHash);
    }
}
