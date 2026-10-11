using Ai00.Connector.Contracts;

namespace Ai00.Connector.Adapters.VisMockup;

internal sealed class ReverseCaptureRenderer(VisMockupSessionState state, SceneController scenes, InternalCapture capture)
{
    private string? _documentId;
    private string? _operationId;
    private CapturePixels? _baseline;
    private string[] _targets = [];

    public string Render(IVisMockupDocument document, SceneState scene, IReadOnlyList<string> highlights, bool fitAll)
    {
        if (scene.SceneHash != scene.ComputeHash() || highlights.Any(key => !scene.VisibleProducts.Contains(key)))
            throw new ConnectorException("scene_verification_failed");
        var leaves = Expand(document, scene.VisibleProducts.Concat(scene.VisibleResources).Select(key => state.Resolve(document, key)));
        var targets = Expand(document, highlights.Select(key => state.Resolve(document, key)));
        if (targets.Any(key => !leaves.Contains(key))) throw new ConnectorException("scene_node_not_found");
        var grayTargets = document.DocumentId == _documentId && scene.OperationId == _operationId
            ? leaves.Concat(_targets).Distinct(StringComparer.Ordinal).ToArray() : leaves;
        _baseline = null;
        _documentId = document.DocumentId;
        _operationId = scene.OperationId;
        _targets = targets;
        document.ApplyCaptureProfile(scene.CaptureProfile);
        document.SetNodeColors(grayTargets, .42, .42, .42);
        document.SetAllNodesVisible(false);
        document.SetNodesVisible(leaves, true);
        if (fitAll && leaves.Length > 0) document.FitCaptureView();
        document.RefreshCaptureView();
        state.LastScene = scene;
        state.RenderedLeafKeys = leaves;
        if (!scenes.Verify(document, scene.OperationId, scene.SceneHash).Matches)
            throw new ConnectorException("scene_verification_failed");
        if ((fitAll && leaves.Length > 0) || targets.Length > 0)
        {
            var baseline = capture.ReadPixels(document, scene.CaptureProfile);
            baseline.RequireGrayScene();
            if (targets.Length > 0)
            {
                document.SetNodeColors(targets, 0, 0, 1);
                document.SetAllNodesVisible(false);
                document.SetNodesVisible(leaves, true);
                document.RefreshCaptureView();
                _baseline = baseline;
            }
        }
        return scene.SceneHash;
    }

    public LocalCaptureArtifact Capture(IVisMockupDocument document, CaptureRequest request)
    {
        if (state.RenderedLeafKeys is null) return capture.Capture(document, request);
        if (document.DocumentId != _documentId || request.OperationId != _operationId || _baseline is null)
            throw new ConnectorException("capture_render_required");
        if (state.LastScene is not { } scene || !scenes.Verify(document, request.OperationId, scene.SceneHash).Matches)
            throw new ConnectorException("scene_verification_failed");
        try
        {
            return capture.Capture(document, request,
                path => _baseline.RequireBlueResponse(CapturePixels.Read(path, request.Profile)));
        }
        catch
        {
            document.SetNodeColors(_targets, .42, .42, .42);
            document.SetAllNodesVisible(false);
            document.SetNodesVisible(state.RenderedLeafKeys, true);
            document.RefreshCaptureView();
            throw;
        }
    }

    private static string[] Expand(IVisMockupDocument document, IEnumerable<string> roots)
    {
        var pending = new Stack<IVisMockupNode>(roots.Distinct(StringComparer.Ordinal).Select(document.FindNodeByKey));
        var seen = new HashSet<string>(StringComparer.Ordinal);
        var leaves = new HashSet<string>(StringComparer.Ordinal);
        while (pending.TryPop(out var node))
        {
            if (!seen.Add(node.NodeKey)) continue;
            if (seen.Count > 250_000) throw new ConnectorException("viewer_mapping_budget_exceeded");
            var children = node.GetChildren(250_000);
            if (children.Count == 0) leaves.Add(node.NodeKey);
            else foreach (var child in children) pending.Push(child);
        }
        return leaves.Order(StringComparer.Ordinal).ToArray();
    }
}
