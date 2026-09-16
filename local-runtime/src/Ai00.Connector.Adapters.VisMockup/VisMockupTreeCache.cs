using System.Security.Cryptography;
using System.Text.Json;
using Microsoft.Data.Sqlite;
using Ai00.Connector.Contracts;

namespace Ai00.Connector.Adapters.VisMockup;

internal sealed record CachedTreeNode(
    string NodeKey, string? ParentNodeKey, int ChildOrder, int Depth,
    string Name, string CatiaOccurrenceName, bool HasMore, string CadId = "");

internal sealed record CachedTree(IReadOnlyList<CachedTreeNode> Nodes, int MaxDepth, string CacheState);

internal sealed record VisMockupTreeCachePolicy(
    long HardLimitBytes = 2L * 1024 * 1024 * 1024,
    double CleanupTriggerRatio = 0.8,
    double CleanupTargetRatio = 0.6)
{
    public void Validate()
    {
        if (HardLimitBytes < 1 || CleanupTriggerRatio is <= 0 or >= 1 ||
            CleanupTargetRatio is <= 0 or >= 1 || CleanupTargetRatio >= CleanupTriggerRatio)
            throw new ArgumentOutOfRangeException(nameof(HardLimitBytes), "vismockup_cache_policy_invalid");
    }
}

internal sealed class VisMockupTreeCache
{
    private readonly string connectionString;
    private readonly VisMockupTreeCachePolicy policy;

    public VisMockupTreeCache(string path, VisMockupTreeCachePolicy? policy = null)
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
        this.policy = policy ?? new();
        this.policy.Validate();
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
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT external_node_key,parent_external_node_key,child_order,depth,
                   printable_name,occurrence_id,has_more,cad_id
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
            reader.GetString(5), reader.GetBoolean(6), reader.GetString(7)));
        reader.Close();
        if (nodes.Count == 0) return null;
        var crossSessionStableProjection = currentExternalRevision is null &&
            storedExternalRevision.Length == 0 &&
            !string.Equals(storedDocumentId, document.DocumentId, StringComparison.Ordinal) &&
            nodes.All(node => node.NodeKey.StartsWith("pdm:", StringComparison.Ordinal));
        if (!externallyVerified && !sameUnversionedSession && !crossSessionStableProjection)
            return null;

        using var touch = connection.CreateCommand();
        touch.CommandText = "UPDATE vm_cache_documents SET last_accessed_utc=$now WHERE local_id=$local_id";
        touch.Parameters.AddWithValue("$now", DateTimeOffset.UtcNow.ToString("O"));
        touch.Parameters.AddWithValue("$local_id", localId);
        touch.ExecuteNonQuery();
        return new(nodes, maxDepth, externallyVerified ? "verified" : "verifying");
    }

    public void Replace(IVisMockupDocument document, int maxDepth, IReadOnlyList<CachedTreeNode> nodes)
    {
        var identity = Identity(document);
        var serialized = JsonSerializer.SerializeToUtf8Bytes(
            nodes.OrderBy(node => node.Depth).ThenBy(node => node.ParentNodeKey).ThenBy(node => node.ChildOrder)
                .ThenBy(node => node.NodeKey));
        var byteSize = serialized.LongLength;
        if (!EnsureCapacity(identity, byteSize)) return;
        var treeHash = "sha256:" + Convert.ToHexString(SHA256.HashData(serialized)).ToLowerInvariant();
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
                    document_local_id,generation,root_subtree_hash,freshness,max_depth,node_count,byte_size,completed_utc)
                VALUES($document_local_id,$generation,$tree_hash,$freshness,$max_depth,$node_count,$byte_size,$now)
                """;
            insertGeneration.Parameters.AddWithValue("$document_local_id", localId);
            insertGeneration.Parameters.AddWithValue("$generation", generation);
            insertGeneration.Parameters.AddWithValue("$tree_hash", treeHash);
            insertGeneration.Parameters.AddWithValue("$freshness", externalRevision.Length == 0 ? "uncertain" : "fresh");
            insertGeneration.Parameters.AddWithValue("$max_depth", maxDepth);
            insertGeneration.Parameters.AddWithValue("$node_count", nodes.Count);
            insertGeneration.Parameters.AddWithValue("$byte_size", byteSize);
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
                    child_order,depth,printable_name,occurrence_id,has_more,cad_id,control_key)
                VALUES($document_local_id,$generation,$node_key,$parent_key,
                    $child_order,$depth,$name,$occurrence_id,$has_more,$cad_id,$control_key)
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
            insertNode.Parameters.AddWithValue("$cad_id", node.CadId);
            insertNode.Parameters.AddWithValue("$control_key", ControlKey(identity,node.CadId));
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

    public void ReplaceProjection(IVisMockupDocument document, VisMockupPlmxmlProjection projection)
    {
        if (projection.Nodes.Count == 0 ||
            !projection.Nodes.Any(node => string.Equals(
                node.StableOccurrenceKey, projection.RootStableOccurrenceKey, StringComparison.Ordinal)))
            throw new InvalidDataException("vismockup_cache_projection_invalid");
        var parents = projection.Nodes
            .Where(node => node.ParentStableOccurrenceKey is not null)
            .Select(node => node.ParentStableOccurrenceKey!)
            .ToHashSet(StringComparer.Ordinal);
        Replace(document, 64, projection.Nodes.Select(node => new CachedTreeNode(
            node.StableOccurrenceKey,
            node.ParentStableOccurrenceKey,
            node.ChildOrder,
            node.Depth,
            node.PrintableName,
            node.CatiaOccurrenceName,
            parents.Contains(node.StableOccurrenceKey))).ToArray());
    }

    internal static string ControlKey(string sourceHash, string cadId) =>
        string.IsNullOrEmpty(cadId) ? "" : "cad:" + Convert.ToHexString(SHA256.HashData(
            System.Text.Encoding.UTF8.GetBytes(sourceHash + "\0" + cadId))).ToLowerInvariant();

    public string ResolveCadNodeKey(IVisMockupDocument document, string controlKey)
    {
        using var connection = Open();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT n.cad_id,n.printable_name FROM vm_cache_nodes n
            JOIN vm_cache_documents d ON d.local_id=n.document_local_id
            WHERE d.document_identity_hash=$identity AND n.control_key=$key
              AND n.generation=(SELECT MAX(saved.generation) FROM vm_cache_nodes saved
                WHERE saved.document_local_id=d.local_id AND saved.control_key=$key)
            LIMIT 2
            """;
        command.Parameters.AddWithValue("$identity",Identity(document));
        command.Parameters.AddWithValue("$key",controlKey);
        using var reader = command.ExecuteReader();
        if (!reader.Read()) throw new ConnectorNoEffectException("vismockup_cad_locator_missing");
        var cadId = reader.GetString(0);
        var name = reader.GetString(1);
        if (string.IsNullOrEmpty(cadId) || reader.Read())
            throw new ConnectorNoEffectException("vismockup_cad_instance_ambiguous");
        reader.Close();
        // Use native indexed lookup on every operation. Do not retain raw handles
        // across insert/delete operations in an otherwise unchanged document session.
        IVisMockupNode node;
        try { node = document.FindNodeByCadId(cadId); }
        catch { throw new ConnectorNoEffectException("vismockup_cad_instance_unmapped"); }
        if (node.CadId != cadId || node.PrintableName != name)
            throw new ConnectorNoEffectException("vismockup_cad_instance_changed");
        return node.NodeKey;
    }

    public string ResolveSessionNodeKey(IVisMockupDocument document, string stableOccurrenceKey, bool verifyPrintableName = true)
    {
        if (string.IsNullOrWhiteSpace(stableOccurrenceKey))
            throw new InvalidDataException("vismockup_cache_node_identity_invalid");
        if (TryRead(document, 0) is null)
            throw new InvalidDataException("vismockup_cache_source_revision_changed");
        using var connection = Open();
        using var command = connection.CreateCommand();
        command.CommandText = """
            WITH RECURSIVE lineage(node_key,parent_key,child_order,depth,printable_name) AS (
              SELECT n.external_node_key,n.parent_external_node_key,n.child_order,n.depth,n.printable_name
              FROM vm_cache_nodes n
              JOIN vm_cache_documents d ON d.local_id=n.document_local_id
              WHERE d.document_identity_hash=$identity
                AND n.generation=d.current_generation
                AND n.external_node_key=$node_key
              UNION ALL
              SELECT p.external_node_key,p.parent_external_node_key,p.child_order,p.depth,p.printable_name
              FROM vm_cache_nodes p
              JOIN vm_cache_documents d ON d.local_id=p.document_local_id
              JOIN lineage child ON child.parent_key=p.external_node_key
              WHERE d.document_identity_hash=$identity
                AND p.generation=d.current_generation
            )
            SELECT node_key,child_order,depth,printable_name FROM lineage ORDER BY depth
            """;
        command.Parameters.AddWithValue("$identity", Identity(document));
        command.Parameters.AddWithValue("$node_key", stableOccurrenceKey);
        using var reader = command.ExecuteReader();
        var lineage = new List<(string Key, int ChildOrder, int Depth, string Name)>();
        while (reader.Read()) lineage.Add((reader.GetString(0), reader.GetInt32(1), reader.GetInt32(2), reader.GetString(3)));
        if (lineage.Count == 0 || lineage[0].Depth != 0)
            throw new InvalidDataException("vismockup_cache_node_not_found");

        var current = document.RootNode;
        for (var index = 1; index < lineage.Count; index++)
        {
            var step = lineage[index];
            var children = current.Children;
            if (step.ChildOrder < 0 || step.ChildOrder >= children.Count)
                throw new InvalidDataException("vismockup_session_node_path_changed");
            current = children[step.ChildOrder];
            if (verifyPrintableName && !string.Equals(current.PrintableName, step.Name, StringComparison.Ordinal))
                throw new InvalidDataException("vismockup_session_node_path_changed");
        }
        return current.NodeKey;
    }

    public bool IsNodeKnownForDifferentDocument(IVisMockupDocument document, string stableOccurrenceKey)
    {
        using var connection = Open();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT
              COUNT(*),
              SUM(CASE WHEN d.document_identity_hash=$identity THEN 1 ELSE 0 END)
            FROM vm_cache_nodes n
            JOIN vm_cache_documents d
              ON d.local_id=n.document_local_id AND d.current_generation=n.generation
            WHERE n.external_node_key=$node_key
            """;
        command.Parameters.AddWithValue("$identity", Identity(document));
        command.Parameters.AddWithValue("$node_key", stableOccurrenceKey);
        using var reader = command.ExecuteReader();
        if (!reader.Read()) return false;
        var total = reader.GetInt64(0);
        var matching = reader.IsDBNull(1) ? 0 : reader.GetInt64(1);
        return total > 0 && matching == 0;
    }

    private bool EnsureCapacity(string protectedIdentity, long incomingBytes)
    {
        using var connection = Open();
        using var transaction = connection.BeginTransaction();
        var total = Scalar(connection, transaction, "SELECT COALESCE(SUM(byte_size),0) FROM vm_cache_generations");
        var projected = total + incomingBytes;
        if (projected <= policy.HardLimitBytes * policy.CleanupTriggerRatio) return true;
        var target = (long)(policy.HardLimitBytes * policy.CleanupTargetRatio);

        using (var oldGenerations = connection.CreateCommand())
        {
            oldGenerations.Transaction = transaction;
            oldGenerations.CommandText = """
                SELECT g.document_local_id,g.generation,g.byte_size
                FROM vm_cache_generations g
                JOIN vm_cache_documents d ON d.local_id=g.document_local_id
                WHERE g.generation<>d.current_generation
                ORDER BY g.completed_utc,g.document_local_id,g.generation
                """;
            using var reader = oldGenerations.ExecuteReader();
            var candidates = new List<(long DocumentId, long Generation, long Bytes)>();
            while (reader.Read()) candidates.Add((reader.GetInt64(0), reader.GetInt64(1), reader.GetInt64(2)));
            reader.Close();
            foreach (var candidate in candidates)
            {
                if (projected <= target) break;
                using var delete = connection.CreateCommand();
                delete.Transaction = transaction;
                delete.CommandText = "DELETE FROM vm_cache_generations WHERE document_local_id=$document_id AND generation=$generation";
                delete.Parameters.AddWithValue("$document_id", candidate.DocumentId);
                delete.Parameters.AddWithValue("$generation", candidate.Generation);
                delete.ExecuteNonQuery();
                projected -= candidate.Bytes;
            }
        }

        using (var closedDocuments = connection.CreateCommand())
        {
            closedDocuments.Transaction = transaction;
            closedDocuments.CommandText = """
                SELECT d.local_id,COALESCE(SUM(g.byte_size),0)
                FROM vm_cache_documents d
                LEFT JOIN vm_cache_generations g ON g.document_local_id=d.local_id
                WHERE d.document_identity_hash<>$protected_identity
                GROUP BY d.local_id,d.last_accessed_utc
                ORDER BY d.last_accessed_utc,d.local_id
                """;
            closedDocuments.Parameters.AddWithValue("$protected_identity", protectedIdentity);
            using var reader = closedDocuments.ExecuteReader();
            var candidates = new List<(long DocumentId, long Bytes)>();
            while (reader.Read()) candidates.Add((reader.GetInt64(0), reader.GetInt64(1)));
            reader.Close();
            foreach (var candidate in candidates)
            {
                if (projected <= target) break;
                using var delete = connection.CreateCommand();
                delete.Transaction = transaction;
                delete.CommandText = "DELETE FROM vm_cache_documents WHERE local_id=$document_id";
                delete.Parameters.AddWithValue("$document_id", candidate.DocumentId);
                delete.ExecuteNonQuery();
                projected -= candidate.Bytes;
            }
        }
        transaction.Commit();
        using var vacuum = connection.CreateCommand();
        vacuum.CommandText = "PRAGMA incremental_vacuum";
        vacuum.ExecuteNonQuery();
        return projected <= policy.HardLimitBytes;
    }

    private static long Scalar(SqliteConnection connection, SqliteTransaction transaction, string sql)
    {
        using var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = sql;
        return Convert.ToInt64(command.ExecuteScalar());
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
        using (var journal = connection.CreateCommand())
        {
            journal.CommandText = "PRAGMA journal_mode=WAL";
            journal.ExecuteNonQuery();
        }
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
                  byte_size INTEGER NOT NULL,
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
        foreach (var column in new[] {"cad_id", "control_key"})
        {
            if (ColumnExists(connection,"vm_cache_nodes",column)) continue;
            using var addColumn = connection.CreateCommand();
            addColumn.CommandText = $"ALTER TABLE vm_cache_nodes ADD COLUMN {column} TEXT NOT NULL DEFAULT ''";
            addColumn.ExecuteNonQuery();
        }
        using (var locatorIndex = connection.CreateCommand())
        {
            locatorIndex.CommandText = "CREATE INDEX IF NOT EXISTS ix_vm_cache_nodes_control ON vm_cache_nodes(control_key,document_local_id,generation)";
            locatorIndex.ExecuteNonQuery();
        }
        if (!ColumnExists(connection, "vm_cache_generations", "byte_size"))
        {
            using var addByteSize = connection.CreateCommand();
            addByteSize.CommandText = "ALTER TABLE vm_cache_generations ADD COLUMN byte_size INTEGER NOT NULL DEFAULT 0";
            addByteSize.ExecuteNonQuery();
        }
    }

    private static bool ColumnExists(SqliteConnection connection, string table, string column)
    {
        using var command = connection.CreateCommand();
        command.CommandText = $"PRAGMA table_info({table})";
        using var reader = command.ExecuteReader();
        while (reader.Read())
            if (string.Equals(reader.GetString(1), column, StringComparison.Ordinal)) return true;
        return false;
    }
}
