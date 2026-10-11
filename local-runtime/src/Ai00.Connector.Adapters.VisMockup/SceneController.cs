using Ai00.Connector.Contracts;
using System.Text.Json;
using System.Text.Json.Serialization;

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

public sealed record SceneVerification(
    [property: JsonPropertyName("actual_scene_hash")] string ActualSceneHash,
    [property: JsonPropertyName("matches")] bool Matches);

public sealed class VisMockupSessionState(
    Func<IVisMockupDocument, VisMockupDocumentSnapshot>? readSnapshot = null,
    Func<IVisMockupDocument, string, string>? resolveNode = null,
    Func<IVisMockupDocument, string>? sessionIdentity = null)
{
    private readonly Dictionary<string, string> _bindings = new(StringComparer.Ordinal);
    private string? _sessionIdentity;
    public SceneState? LastScene { get; set; }
    public string[]? RenderedLeafKeys { get; set; }
    public string? DocumentId { get; private set; }
    public string? BaselineSnapshotHash { get; private set; }
    public void Bind(string manifestNodeKey, string actualNodeKey) => _bindings[manifestNodeKey] = actualNodeKey;
    public string Resolve(string nodeKey) => _bindings.GetValueOrDefault(nodeKey, nodeKey);
    public string Resolve(IVisMockupDocument document, string nodeKey) =>
        _bindings.TryGetValue(nodeKey, out var bound) ? bound : resolveNode?.Invoke(document, nodeKey) ?? nodeKey;
    public void Reset()
    {
        _bindings.Clear();
        LastScene = null;
        RenderedLeafKeys = null;
        DocumentId = null;
        BaselineSnapshotHash = null;
        _sessionIdentity = null;
    }
    public string ToManifestKey(string actualNodeKey) =>
        _bindings.FirstOrDefault(item => item.Value == actualNodeKey).Key ?? actualNodeKey;
    public void RequireBaseline(IVisMockupDocument document, string expectedHash)
    {
        var identity = sessionIdentity?.Invoke(document) ??
            JsonSerializer.Serialize(new[] { document.DocumentId, document.SourceIdentity, document.RootNode.NodeKey });
        if (DocumentId is null)
        {
            var snapshot = readSnapshot?.Invoke(document) ?? new DocumentSnapshotReader().Read(document, 250_000, 64);
            if (snapshot.DocumentId != document.DocumentId || snapshot.SnapshotHash != expectedHash)
                throw new ConnectorException("vismockup_document_changed");
            DocumentId = document.DocumentId;
            BaselineSnapshotHash = snapshot.SnapshotHash;
            _sessionIdentity = identity;
        }
        if (DocumentId != document.DocumentId || BaselineSnapshotHash != expectedHash || _sessionIdentity != identity)
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
        var expectedActual = expectedManifest.Select(key => state.Resolve(document, key)).ToHashSet(StringComparer.Ordinal);
        if (expectedActual.Any(key => !all.Contains(key))) throw new ConnectorException("scene_node_not_found");
        state.RenderedLeafKeys = null;
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
        if (state.RenderedLeafKeys is { } leaves)
        {
            var visible = document.GetAllNodes(250_000).Where(node => node.ChildCount == 0 && node.IsVisible)
                .Select(node => node.NodeKey).ToHashSet(StringComparer.Ordinal);
            var matches = visible.SetEquals(leaves) && last.ComputeHash() == expectedHash;
            return new(matches ? expectedHash : CanonicalJson.Hash(visible.Order(StringComparer.Ordinal).ToArray()), matches);
        }
        var visibleManifest = document.VisibleNodeKeys.ToHashSet(StringComparer.Ordinal);
        var expectedVisible = last.VisibleProducts.Concat(last.VisibleResources)
            .Select(key => state.Resolve(document, key)).ToHashSet(StringComparer.Ordinal);
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
