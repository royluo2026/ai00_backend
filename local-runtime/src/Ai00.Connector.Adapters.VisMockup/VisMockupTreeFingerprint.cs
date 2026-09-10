using System.Security.Cryptography;
using System.Text;

namespace Ai00.Connector.Adapters.VisMockup;

public enum CacheFreshness
{
    Fresh,
    Uncertain,
}

public sealed record VmTreeNodeFingerprint(
    string ExternalNodeKey,
    string RevisionFingerprint,
    string SubtreeHash);

public sealed record VmTreeManifest(
    string DocumentIdentityHash,
    string RootNodeKey,
    string RootSubtreeHash,
    string ExternalRevisionFingerprint,
    CacheFreshness Freshness,
    IReadOnlyList<VmTreeNodeFingerprint> Nodes)
{
    public VmTreeNodeFingerprint Node(string externalNodeKey) =>
        Nodes.Single(node => string.Equals(node.ExternalNodeKey, externalNodeKey, StringComparison.Ordinal));
}

public static class VisMockupTreeFingerprint
{
    public static VmTreeManifest Create(IVisMockupDocument document)
    {
        var documentIdentity = DocumentIdentityHash(document);
        var externalRevision = ExternalRevisionFingerprint(document.SourceIdentity);
        var nodes = new List<VmTreeNodeFingerprint>();
        var seen = new HashSet<string>(StringComparer.Ordinal);
        var rootHash = Visit(document.RootNode, nodes, seen);
        return new(
            documentIdentity,
            document.RootNode.NodeKey,
            rootHash,
            externalRevision ?? "",
            externalRevision is null ? CacheFreshness.Uncertain : CacheFreshness.Fresh,
            nodes);
    }

    public static string DocumentIdentityHash(IVisMockupDocument document) =>
        Hash(NormalizeSourceIdentity(document.SourceIdentity));

    public static string? ExternalRevisionFingerprint(string sourceIdentity)
    {
        if (!Path.IsPathFullyQualified(sourceIdentity) || !File.Exists(sourceIdentity)) return null;
        var file = new FileInfo(sourceIdentity);
        file.Refresh();
        return Hash(file.Length.ToString(System.Globalization.CultureInfo.InvariantCulture), file.LastWriteTimeUtc.Ticks.ToString(System.Globalization.CultureInfo.InvariantCulture));
    }

    private static string Visit(
        IVisMockupNode node,
        ICollection<VmTreeNodeFingerprint> nodes,
        ISet<string> seen)
    {
        if (string.IsNullOrWhiteSpace(node.NodeKey) || !seen.Add(node.NodeKey))
            throw new InvalidDataException("vismockup_tree_identity_invalid");
        var revision = Hash(node.PrintableName, node.OccurrenceId, node.ModelId);
        var childHashes = node.Children.Select(child => Visit(child, nodes, seen)).ToArray();
        var subtree = Hash([node.NodeKey, revision, .. childHashes]);
        nodes.Add(new(node.NodeKey, revision, subtree));
        return subtree;
    }

    private static string NormalizeSourceIdentity(string value)
    {
        var source = value.Trim();
        if (!Path.IsPathFullyQualified(source)) return source;
        return Path.GetFullPath(source)
            .TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar)
            .Replace(Path.AltDirectorySeparatorChar, Path.DirectorySeparatorChar)
            .ToUpperInvariant();
    }

    private static string Hash(params string[] values)
    {
        var canonical = string.Join('\u001f', values.Select(value => $"{value.Length}:{value}"));
        return "sha256:" + Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(canonical))).ToLowerInvariant();
    }
}
