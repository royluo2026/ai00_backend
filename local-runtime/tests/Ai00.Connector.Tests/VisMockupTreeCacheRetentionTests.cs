using Ai00.Connector.Adapters.VisMockup;
using Microsoft.Data.Sqlite;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class VisMockupTreeCacheRetentionTests
{
    [Fact]
    public void CleanupRemovesOldGenerationsBeforeClosedDocuments()
    {
        using var fixture = new CacheFixture();
        var cache = new VisMockupTreeCache(fixture.DatabasePath);
        cache.Replace(fixture.Document("A"), 3, fixture.Nodes("A1"));
        cache.Replace(fixture.Document("A"), 3, fixture.Nodes("A2"));
        cache.Replace(fixture.Document("B"), 3, fixture.Nodes("B1"));
        var generationBytes = fixture.GenerationBytes("A", 2);
        var totalBytes = fixture.TotalBytes();
        var bounded = new VisMockupTreeCache(
            fixture.DatabasePath,
            new VisMockupTreeCachePolicy(totalBytes + generationBytes, 0.8, 0.75));

        bounded.Replace(fixture.Document("A"), 3, fixture.Nodes("A3"));

        Assert.Equal(2, fixture.GenerationCount("A"));
        Assert.Equal(1, fixture.DocumentCount("B"));
    }

    [Fact]
    public void CleanupRemovesLeastRecentlyUsedClosedDocumentWhenOldGenerationsAreGone()
    {
        using var fixture = new CacheFixture();
        var cache = new VisMockupTreeCache(fixture.DatabasePath);
        cache.Replace(fixture.Document("A"), 3, fixture.Nodes("A1"));
        cache.Replace(fixture.Document("B"), 3, fixture.Nodes("B1"));
        var generationBytes = fixture.GenerationBytes("A", 1);
        var totalBytes = fixture.TotalBytes();
        var bounded = new VisMockupTreeCache(
            fixture.DatabasePath,
            new VisMockupTreeCachePolicy(totalBytes + generationBytes, 0.8, 0.5));

        bounded.Replace(fixture.Document("A"), 3, fixture.Nodes("A2"));

        Assert.Equal(0, fixture.DocumentCount("B"));
        Assert.Equal("A2", bounded.TryRead(fixture.Document("A"), 3)!.Nodes[0].Name);
    }

    [Fact]
    public void OversizedProtectedDocumentStopsNewWritesWithoutBreakingReads()
    {
        using var fixture = new CacheFixture();
        var cache = new VisMockupTreeCache(fixture.DatabasePath);
        cache.Replace(fixture.Document("A"), 3, fixture.Nodes("A1"));
        var currentBytes = fixture.TotalBytes();
        var bounded = new VisMockupTreeCache(
            fixture.DatabasePath,
            new VisMockupTreeCachePolicy(currentBytes, 0.8, 0.6));

        bounded.Replace(fixture.Document("A"), 3, fixture.Nodes("A2"));

        Assert.Equal(1, fixture.GenerationCount("A"));
        Assert.Equal("A1", bounded.TryRead(fixture.Document("A"), 3)!.Nodes[0].Name);
    }

    private sealed class CacheFixture : IDisposable
    {
        private readonly string directory = Path.Combine(
            Path.GetTempPath(), "ai00-vm-cache-retention-tests", Guid.NewGuid().ToString("N"));

        public CacheFixture() => Directory.CreateDirectory(directory);

        public string DatabasePath => Path.Combine(directory, "tree.db");

        public FakeDocument Document(string name)
        {
            var path = Path.Combine(directory, $"{name}.vfz");
            if (!File.Exists(path)) File.WriteAllText(path, name);
            return new FakeDocument($"session-{name}", path, FakeNode.FlatTree(1));
        }

        public CachedTreeNode[] Nodes(string name) => [new("root", null, 0, 0, name, "", false)];

        public long TotalBytes() => Scalar("SELECT COALESCE(SUM(byte_size),0) FROM vm_cache_generations");

        public long GenerationBytes(string documentName, long generation) => Scalar(
            "SELECT g.byte_size FROM vm_cache_generations g JOIN vm_cache_documents d ON d.local_id=g.document_local_id " +
            "WHERE d.source_identity LIKE $suffix AND g.generation=$generation",
            ("$suffix", $"%{documentName}.vfz"), ("$generation", generation));

        public long GenerationCount(string documentName) => Scalar(
            "SELECT COUNT(*) FROM vm_cache_generations g JOIN vm_cache_documents d ON d.local_id=g.document_local_id " +
            "WHERE d.source_identity LIKE $suffix", ("$suffix", $"%{documentName}.vfz"));

        public long DocumentCount(string documentName) => Scalar(
            "SELECT COUNT(*) FROM vm_cache_documents WHERE source_identity LIKE $suffix",
            ("$suffix", $"%{documentName}.vfz"));

        private long Scalar(string sql, params (string Name, object Value)[] parameters)
        {
            using var connection = new SqliteConnection($"Data Source={DatabasePath};Pooling=False");
            connection.Open();
            using var command = connection.CreateCommand();
            command.CommandText = sql;
            foreach (var parameter in parameters) command.Parameters.AddWithValue(parameter.Name, parameter.Value);
            return Convert.ToInt64(command.ExecuteScalar());
        }

        public void Dispose() => Directory.Delete(directory, true);
    }
}
