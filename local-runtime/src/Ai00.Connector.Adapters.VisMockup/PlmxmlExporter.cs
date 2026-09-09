using System.Security.Cryptography;
using Ai00.Connector.Contracts;

namespace Ai00.Connector.Adapters.VisMockup;

public sealed record LocalPlmxmlArtifact(string Path, string Sha256, long ByteSize, int HierarchyIndex);

/// <summary>Bounded ExportEx staging. Only ConnectorHost may consume the local path.</summary>
public sealed class PlmxmlExporter(string root, long maxBytes = 64L * 1024 * 1024)
{
    private readonly string _root = Path.GetFullPath(root);

    public LocalPlmxmlArtifact Export(IVisMockupDocument document, string expectedDocumentId, int hierarchyIndex, string stepId)
    {
        if (document.DocumentId != expectedDocumentId) throw new ConnectorException("vismockup_document_changed");
        if (hierarchyIndex < 0) throw new ConnectorException("vismockup_hierarchy_index_invalid");
        if (string.IsNullOrWhiteSpace(stepId) || stepId.Any(ch => !char.IsLetterOrDigit(ch) && ch is not '-' and not '_'))
            throw new ConnectorException("export_step_id_invalid");
        Directory.CreateDirectory(_root);
        var path = Path.Combine(_root, stepId + ".plmxml");
        document.ExportPlmxml(path, hierarchyIndex);
        var info = new FileInfo(path);
        if (!info.Exists || info.Length <= 0) throw new ConnectorException("plmxml_export_empty");
        if (info.Length > maxBytes)
        {
            File.Delete(path);
            throw new ConnectorException("plmxml_export_too_large");
        }
        using var stream = File.OpenRead(path);
        var hash = Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant();
        return new(path, hash, info.Length, hierarchyIndex);
    }
}
