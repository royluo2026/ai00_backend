using Ai00.Connector.Contracts;
using Ai00.Connector.Service;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class ArtifactTransferTests : IDisposable
{
    private readonly string _directory = Path.Combine(Path.GetTempPath(), "ai00-artifact-tests", Guid.NewGuid().ToString("N"));

    [Fact]
    public async Task HashMismatchDeletesMaterializedInputAndFailsClosed()
    {
        var files = new TemporaryFileStore(_directory);
        var transfer = new ArtifactTransfer(new StubTransport("wrong bytes"u8.ToArray()), files);
        var artifact = new ConnectorArtifactRef("artifact-1", "model/jt", new string('a', 64), 11, 1);

        var error = await Assert.ThrowsAsync<ConnectorException>(() =>
            transfer.DownloadAsync(artifact, new Uri("https://ai00.invalid/download"), default));

        Assert.Equal("artifact_integrity_failed", error.Code);
        Assert.NotNull(error.LocalPath);
        Assert.False(File.Exists(error.LocalPath));
    }

    [Fact]
    public async Task ValidInputIsStoredOnlyUnderConnectorRoot()
    {
        var bytes = "model bytes"u8.ToArray();
        var hash = Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(bytes)).ToLowerInvariant();
        var transfer = new ArtifactTransfer(new StubTransport(bytes), new TemporaryFileStore(_directory));

        var result = await transfer.DownloadAsync(
            new("artifact-1", "model/jt", hash, bytes.Length, 1),
            new Uri("https://ai00.invalid/download"), default);

        Assert.StartsWith(Path.GetFullPath(_directory), result.CachePath, StringComparison.OrdinalIgnoreCase);
    }

    public void Dispose()
    {
        if (Directory.Exists(_directory)) Directory.Delete(_directory, true);
    }

    private sealed class StubTransport(byte[] bytes) : IArtifactTransport
    {
        public Task DownloadToAsync(Uri source, string destination, CancellationToken cancellationToken) => File.WriteAllBytesAsync(destination, bytes, cancellationToken);
        public Task<ArtifactUploadReceipt> UploadAsync(UploadGrant grant, string path, CancellationToken cancellationToken) => throw new NotSupportedException();
        public Task<ArtifactUploadReceipt?> QueryUploadAsync(string uploadSessionId, CancellationToken cancellationToken) => throw new NotSupportedException();
    }
}
