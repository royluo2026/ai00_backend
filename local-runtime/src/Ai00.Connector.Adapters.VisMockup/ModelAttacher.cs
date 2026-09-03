using System.Text.Json;
using Ai00.Connector.Contracts;

namespace Ai00.Connector.Adapters.VisMockup;

public sealed record NodeBinding(string NodeKey, string BindingId);

public sealed class ModelAttacher(
    AllowedPathPolicy paths,
    VisMockupSessionState state)
{
    public NodeBinding Attach(IVisMockupDocument document, string documentId, string baselineSnapshotHash, JsonElement binding)
    {
        if (document.DocumentId != documentId) throw new ConnectorException("vismockup_document_changed");
        state.RequireBaseline(document, baselineSnapshotHash);
        var manifestNodeKey = binding.GetProperty("node_key").GetString()
            ?? throw new ConnectorException("resource_binding_invalid");
        var artifact = binding.GetProperty("model_ref").GetProperty("artifact_ref");
        var expectedHash = artifact.GetProperty("sha256").GetString()
            ?? throw new ConnectorException("artifact_ref_invalid");
        if (!binding.TryGetProperty("local_artifact_path", out var localPath))
            throw new ConnectorException("artifact_materialization_required");
        var path = paths.RequireVerifiedArtifact(localPath.GetString() ?? "", expectedHash);
        var actualNodeKey = document.AttachModel(path);
        if (string.IsNullOrWhiteSpace(actualNodeKey)) throw new ConnectorException("model_attach_failed");
        state.Bind(manifestNodeKey, actualNodeKey);
        var type = binding.GetProperty("resource_type").GetString() ?? "resource";
        var code = binding.GetProperty("normalized_code").GetString() ?? "unknown";
        return new(manifestNodeKey, type + ":" + code);
    }
}
