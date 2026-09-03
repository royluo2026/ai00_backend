using Ai00.Connector.Contracts;

namespace Ai00.Connector.Adapters.VisMockup;

public sealed record VisMockupSnapshotNode(
    string NodeKey,
    string? ParentNodeKey,
    int ChildOrder,
    int Depth,
    string PrintableName,
    string OccurrenceId,
    string ModelId);

public sealed record VisMockupDocumentSnapshot(
    string DocumentId,
    string SourceIdentity,
    string RootNodeKey,
    IReadOnlyList<VisMockupSnapshotNode> Nodes,
    string SnapshotHash);

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
                ["node_key"] = node.NodeKey, ["parent_node_key"] = node.ParentNodeKey,
                ["child_order"] = node.ChildOrder, ["depth"] = node.Depth,
                ["printable_name"] = node.PrintableName, ["occurrence_id"] = node.OccurrenceId,
                ["model_id"] = node.ModelId,
            }).ToArray(),
        };
        return new(document.DocumentId, document.SourceIdentity, document.RootNode.NodeKey, nodes, CanonicalJson.Hash(projection));
    }
}
