using System.Security.Cryptography;
using System.Text.Json;
using Microsoft.Data.Sqlite;

namespace Ai00.Connector.Adapters.VisMockup;

internal sealed record CachedTreeNode(
    string NodeKey, string? ParentNodeKey, int ChildOrder, int Depth,
    string Name, string CatiaOccurrenceName, bool HasMore);

internal sealed record CachedTree(IReadOnlyList<CachedTreeNode> Nodes, int MaxDepth);

internal sealed class VisMockupTreeCache
{
    private readonly string connectionString;

    public VisMockupTreeCache(string path)
    {
        var fullPath = Path.GetFullPath(path);
        Directory.CreateDirectory(Path.GetDirectoryName(fullPath)!);
        connectionString = new SqliteConnectionStringBuilder
        {
            DataSource = fullPath,
            Mode = SqliteOpenMode.ReadWriteCreate,
            Cache = SqliteCacheMode.Private,
            Pooling = false,
        }.ToString();
        Initialize();
    }

    internal static string Identity(IVisMockupDocument document) =>
        VisMockupTreeFingerprint.DocumentIdentityHash(document);

    public CachedTree? TryRead(IVisMockupDocument document, int maxDepth)
    {
        using var connection = Open();
        using var metadata = connection.CreateCommand();
        metadata.CommandText = """
            SELECT d.local_id,d.document_id,d.external_revision_fingerprint,d.current_generation,
                   g.max_depth
            FROM vm_cache_documents d
            JOIN vm_cache_generations g
              ON g.document_local_id=d.local_id AND g.generation=d.current_generation
            WHERE d.document_identity_hash=$identity
            """;
        metadata.Parameters.AddWithValue("$identity", Identity(document));
        using var metadataReader = metadata.ExecuteReader();
        if (!metadataReader.Read() || metadataReader.GetInt32(4) < maxDepth) return null;
        var localId = metadataReader.GetInt64(0);
        var storedDocumentId = metadataReader.GetString(1);
        var storedExternalRevision = metadataReader.GetString(2);
        var generation = metadataReader.GetInt64(3);
        metadataReader.Close();

        var currentExternalRevision = VisMockupTreeFingerprint.ExternalRevisionFingerprint(document.SourceIdentity);
        var externallyVerified = currentExternalRevision is not null &&
            string.Equals(storedExternalRevision, currentExternalRevision, StringComparison.Ordinal);
        var sameUnversionedSession = currentExternalRevision is null &&
            storedExternalRevision.Length == 0 &&
            string.Equals(storedDocumentId, document.DocumentId, StringComparison.Ordinal);
        if (!externallyVerified && !sameUnversionedSession) return null;

        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT external_node_key,parent_external_node_key,child_order,depth,
                   printable_name,occurrence_id,has_more
            FROM vm_cache_nodes
            WHERE document_local_id=$document_local_id AND generation=$generation AND depth<=$max_depth
            ORDER BY depth,child_order,external_node_key
            """;
        command.Parameters.AddWithValue("$document_local_id", localId);
        command.Parameters.AddWithValue("$generation", generation);
        command.Parameters.AddWithValue("$max_depth", maxDepth);
        using var reader = command.ExecuteReader();
        var nodes = new List<CachedTreeNode>();
        while (reader.Read()) nodes.Add(new(
            reader.GetString(0), reader.IsDBNull(1) ? null : reader.GetString(1),
            reader.GetInt32(2), reader.GetInt32(3), reader.GetString(4),
            reader.GetString(5), reader.GetBoolean(6)));
        reader.Close();
        if (nodes.Count == 0) return null;

        using var touch = connection.CreateCommand();
        touch.CommandText = "UPDATE vm_cache_documents SET last_accessed_utc=$now WHERE local_id=$local_id";
        touch.Parameters.AddWithValue("$now", DateTimeOffset.UtcNow.ToString("O"));
        touch.Parameters.AddWithValue("$local_id", localId);
        touch.ExecuteNonQuery();
        return new(nodes, maxDepth);
    }

    public void Replace(IVisMockupDocument document, int maxDepth, IReadOnlyList<CachedTreeNode> nodes)
    {
        var identity = Identity(document);
        var treeHash = "sha256:" + Convert.ToHexString(SHA256.HashData(JsonSerializer.SerializeToUtf8Bytes(
            nodes.OrderBy(node => node.Depth).ThenBy(node => node.ParentNodeKey).ThenBy(node => node.ChildOrder)
                .ThenBy(node => node.NodeKey)))).ToLowerInvariant();
        var externalRevision = VisMockupTreeFingerprint.ExternalRevisionFingerprint(document.SourceIdentity) ?? "";
        var now = DateTimeOffset.UtcNow.ToString("O");

        using var connection = Open();
        using var transaction = connection.BeginTransaction();
        using (var upsertDocument = connection.CreateCommand())
        {
            upsertDocument.Transaction = transaction;
            upsertDocument.CommandText = """
                INSERT INTO vm_cache_documents(
                    document_identity_hash,document_id,source_identity,root_node_key,
                    external_revision_fingerprint,current_generation,last_accessed_utc)
                VALUES($identity,$document_id,$source_identity,$root_key,$external_revision,NULL,$now)
                ON CONFLICT(document_identity_hash) DO UPDATE SET
                    document_id=excluded.document_id,
                    source_identity=excluded.source_identity,
                    root_node_key=excluded.root_node_key,
                    external_revision_fingerprint=excluded.external_revision_fingerprint,
                    last_accessed_utc=excluded.last_accessed_utc
                """;
            upsertDocument.Parameters.AddWithValue("$identity", identity);
            upsertDocument.Parameters.AddWithValue("$document_id", document.DocumentId);
            upsertDocument.Parameters.AddWithValue("$source_identity", document.SourceIdentity);
            upsertDocument.Parameters.AddWithValue("$root_key", document.RootNode.NodeKey);
            upsertDocument.Parameters.AddWithValue("$external_revision", externalRevision);
            upsertDocument.Parameters.AddWithValue("$now", now);
            upsertDocument.ExecuteNonQuery();
        }

        long localId;
        long generation;
        using (var head = connection.CreateCommand())
        {
            head.Transaction = transaction;
            head.CommandText = "SELECT local_id,COALESCE(current_generation,0)+1 FROM vm_cache_documents WHERE document_identity_hash=$identity";
            head.Parameters.AddWithValue("$identity", identity);
            using var reader = head.ExecuteReader();
            if (!reader.Read()) throw new InvalidDataException("vismockup_cache_document_missing");
            localId = reader.GetInt64(0);
            generation = reader.GetInt64(1);
        }

        using (var insertGeneration = connection.CreateCommand())
        {
            insertGeneration.Transaction = transaction;
            insertGeneration.CommandText = """
                INSERT INTO vm_cache_generations(
                    document_local_id,generation,root_subtree_hash,freshness,max_depth,node_count,completed_utc)
                VALUES($document_local_id,$generation,$tree_hash,$freshness,$max_depth,$node_count,$now)
                """;
            insertGeneration.Parameters.AddWithValue("$document_local_id", localId);
            insertGeneration.Parameters.AddWithValue("$generation", generation);
            insertGeneration.Parameters.AddWithValue("$tree_hash", treeHash);
            insertGeneration.Parameters.AddWithValue("$freshness", externalRevision.Length == 0 ? "uncertain" : "fresh");
            insertGeneration.Parameters.AddWithValue("$max_depth", maxDepth);
            insertGeneration.Parameters.AddWithValue("$node_count", nodes.Count);
            insertGeneration.Parameters.AddWithValue("$now", now);
            insertGeneration.ExecuteNonQuery();
        }

        foreach (var node in nodes)
        {
            using var insertNode = connection.CreateCommand();
            insertNode.Transaction = transaction;
            insertNode.CommandText = """
                INSERT INTO vm_cache_nodes(
                    document_local_id,generation,external_node_key,parent_external_node_key,
                    child_order,depth,printable_name,occurrence_id,has_more)
                VALUES($document_local_id,$generation,$node_key,$parent_key,
                    $child_order,$depth,$name,$occurrence_id,$has_more)
                """;
            insertNode.Parameters.AddWithValue("$document_local_id", localId);
            insertNode.Parameters.AddWithValue("$generation", generation);
            insertNode.Parameters.AddWithValue("$node_key", node.NodeKey);
            insertNode.Parameters.AddWithValue("$parent_key", (object?)node.ParentNodeKey ?? DBNull.Value);
            insertNode.Parameters.AddWithValue("$child_order", node.ChildOrder);
            insertNode.Parameters.AddWithValue("$depth", node.Depth);
            insertNode.Parameters.AddWithValue("$name", node.Name);
            insertNode.Parameters.AddWithValue("$occurrence_id", node.CatiaOccurrenceName);
            insertNode.Parameters.AddWithValue("$has_more", node.HasMore);
            insertNode.ExecuteNonQuery();
        }

        using (var publish = connection.CreateCommand())
        {
            publish.Transaction = transaction;
            publish.CommandText = "UPDATE vm_cache_documents SET current_generation=$generation WHERE local_id=$local_id";
            publish.Parameters.AddWithValue("$generation", generation);
            publish.Parameters.AddWithValue("$local_id", localId);
            publish.ExecuteNonQuery();
        }
        transaction.Commit();
    }

    private SqliteConnection Open()
    {
        var connection = new SqliteConnection(connectionString);
        connection.Open();
        using var foreignKeys = connection.CreateCommand();
        foreignKeys.CommandText = "PRAGMA foreign_keys=ON";
        foreignKeys.ExecuteNonQuery();
        return connection;
    }

    private void Initialize()
    {
        using var connection = Open();
        using var transaction = connection.BeginTransaction();
        using (var migrate = connection.CreateCommand())
        {
            migrate.Transaction = transaction;
            migrate.CommandText = """
                DROP TABLE IF EXISTS document_nodes;
                DROP TABLE IF EXISTS document_cache;
                """;
            migrate.ExecuteNonQuery();
        }
        using (var command = connection.CreateCommand())
        {
            command.Transaction = transaction;
            command.CommandText = """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS vm_cache_documents(
                  local_id INTEGER PRIMARY KEY,
                  document_identity_hash TEXT NOT NULL UNIQUE,
                  document_id TEXT NOT NULL,
                  source_identity TEXT NOT NULL,
                  root_node_key TEXT NOT NULL,
                  external_revision_fingerprint TEXT NOT NULL,
                  current_generation INTEGER NULL,
                  last_accessed_utc TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS vm_cache_generations(
                  document_local_id INTEGER NOT NULL,
                  generation INTEGER NOT NULL,
                  root_subtree_hash TEXT NOT NULL,
                  freshness TEXT NOT NULL,
                  max_depth INTEGER NOT NULL,
                  node_count INTEGER NOT NULL,
                  completed_utc TEXT NOT NULL,
                  PRIMARY KEY(document_local_id,generation),
                  FOREIGN KEY(document_local_id) REFERENCES vm_cache_documents(local_id) ON DELETE CASCADE);
                CREATE TABLE IF NOT EXISTS vm_cache_nodes(
                  document_local_id INTEGER NOT NULL,
                  generation INTEGER NOT NULL,
                  external_node_key TEXT NOT NULL,
                  parent_external_node_key TEXT NULL,
                  child_order INTEGER NOT NULL,
                  depth INTEGER NOT NULL,
                  printable_name TEXT NOT NULL,
                  occurrence_id TEXT NOT NULL,
                  has_more INTEGER NOT NULL,
                  PRIMARY KEY(document_local_id,generation,external_node_key),
                  FOREIGN KEY(document_local_id,generation)
                    REFERENCES vm_cache_generations(document_local_id,generation) ON DELETE CASCADE);
                CREATE INDEX IF NOT EXISTS ix_vm_cache_nodes_parent
                  ON vm_cache_nodes(document_local_id,generation,parent_external_node_key,child_order);
                """;
            command.ExecuteNonQuery();
        }
        transaction.Commit();
    }
}
