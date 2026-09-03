using Ai00.Connector.Contracts;
using System.Text.Json.Serialization;

namespace Ai00.Connector.Adapters.VisMockup;

public sealed record VisMockupSnapshotNode(
    [property: JsonPropertyName("node_key")] string NodeKey,
    [property: JsonPropertyName("parent_key")] string? ParentKey,
    [property: JsonPropertyName("child_order")] int ChildOrder,
    [property: JsonPropertyName("depth")] int Depth,
    [property: JsonPropertyName("printable_name")] string PrintableName,
    [property: JsonPropertyName("occurrence_id")] string OccurrenceId,
    [property: JsonPropertyName("product_ref")] string ProductRef);

public sealed record VisMockupDocumentSnapshot(
    [property: JsonPropertyName("document_id")] string DocumentId,
    [property: JsonPropertyName("source_identity")] string SourceIdentity,
    [property: JsonPropertyName("root_node_key")] string RootNodeKey,
    [property: JsonPropertyName("nodes")] IReadOnlyList<VisMockupSnapshotNode> Nodes,
    [property: JsonPropertyName("snapshot_hash")] string SnapshotHash);

public sealed class DocumentSnapshotReader
{
    public VisMockupDocumentSnapshot Read(IVisMockupDocument document, int maxNodes, int maxDepth)
    {
        if (maxNodes is < 1 or > 10_000 || maxDepth is < 0 or > 64)
            throw new ConnectorException("bom_snapshot_limit_invalid");
        var nodes = new List<VisMockupSnapshotNode>();
        var seen = new HashSet<string>(StringComparer.Ordinal);
        var queue = new Queue<(IVisMockupNode Node, string? Parent, int ChildOrder, int Depth)>();
        queue.Enqueue((document.RootNode, null, 0, 0));
        while (queue.TryDequeue(out var current))
        {
            if (nodes.Count == maxNodes) throw new ConnectorException("bom_snapshot_limit_exceeded");
            if (current.Depth > maxDepth || string.IsNullOrWhiteSpace(current.Node.NodeKey) || !seen.Add(current.Node.NodeKey))
                throw new ConnectorException("bom_snapshot_invalid");
            nodes.Add(new(
                current.Node.NodeKey, current.Parent, current.ChildOrder, current.Depth,
                current.Node.PrintableName, current.Node.OccurrenceId, current.Node.ModelId));
            for (var index = 0; index < current.Node.Children.Count; index++)
                queue.Enqueue((current.Node.Children[index], current.Node.NodeKey, index, current.Depth + 1));
        }
        var projection = new Dictionary<string, object?>
        {
            ["document_id"] = document.DocumentId,
            ["source_identity"] = document.SourceIdentity,
            ["root_node_key"] = document.RootNode.NodeKey,
            ["nodes"] = nodes.Select(node => new Dictionary<string, object?>
            {
                ["node_key"] = node.NodeKey, ["parent_key"] = node.ParentKey,
                ["child_order"] = node.ChildOrder, ["depth"] = node.Depth,
                ["printable_name"] = node.PrintableName, ["occurrence_id"] = node.OccurrenceId,
                ["product_ref"] = node.ProductRef,
            }).ToArray(),
        };
        return new(document.DocumentId, document.SourceIdentity, document.RootNode.NodeKey, nodes, CanonicalJson.Hash(projection));
    }
}
