using System.Text.Json.Serialization;

namespace Ai00.Connector.Adapters.VisMockup;

public sealed record LiveHierarchyInventoryNode(
    [property: JsonPropertyName("node_key")] string NodeKey,
    [property: JsonPropertyName("parent_key")] string? ParentKey,
    [property: JsonPropertyName("child_order")] int ChildOrder,
    [property: JsonPropertyName("name")] string Name,
    [property: JsonPropertyName("occurrence_id")] string OccurrenceId,
    [property: JsonPropertyName("product_ref")] string ProductRef);

public sealed record LiveHierarchyInventoryItem(
    [property: JsonPropertyName("native_index")] int NativeIndex,
    [property: JsonPropertyName("name")] string Name,
    [property: JsonPropertyName("snapshot_hash")] string SnapshotHash,
    [property: JsonPropertyName("nodes")] IReadOnlyList<LiveHierarchyInventoryNode> Nodes,
    [property: JsonPropertyName("complete")] bool Complete);

public sealed record LiveHierarchyInventoryPage(
    [property: JsonPropertyName("document_session")] string DocumentSession,
    [property: JsonPropertyName("start_index")] int StartIndex,
    [property: JsonPropertyName("next_index")] int? NextIndex,
    [property: JsonPropertyName("total_hierarchies")] int TotalHierarchies,
    [property: JsonPropertyName("hierarchies")] IReadOnlyList<LiveHierarchyInventoryItem> Hierarchies);
