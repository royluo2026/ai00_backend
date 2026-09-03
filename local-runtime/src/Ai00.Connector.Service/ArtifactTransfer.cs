using System.Security.Cryptography;
using Ai00.Connector.Contracts;
using System.Text.Json.Serialization;

namespace Ai00.Connector.Service;

public sealed record ConnectorArtifactRef(
    [property: JsonPropertyName("artifact_id")] string ArtifactId,
    [property: JsonPropertyName("media_type")] string MediaType,
    [property: JsonPropertyName("sha256")] string Sha256,
    [property: JsonPropertyName("byte_size")] long ByteSize,
    [property: JsonPropertyName("version")] int Version);

public sealed record UploadGrant(string UploadSessionId, Uri UploadUrl, long MaximumBytes);
public sealed record ArtifactUploadReceipt(string UploadSessionId, ConnectorArtifactRef Artifact);

public interface IArtifactTransport
{
    Task DownloadToAsync(Uri source, string destination, CancellationToken cancellationToken);
    Task<ArtifactUploadReceipt> UploadAsync(UploadGrant grant, string path, CancellationToken cancellationToken);
    Task<ArtifactUploadReceipt?> QueryUploadAsync(string uploadSessionId, CancellationToken cancellationToken);
}

public sealed class ArtifactTransfer(IArtifactTransport transport, TemporaryFileStore files)
{
    public async Task<MaterializedArtifact> DownloadAsync(
        ConnectorArtifactRef artifact,
        Uri downloadUrl,
        CancellationToken cancellationToken)
    {
        if (artifact.ByteSize < 0 || artifact.ByteSize > 2L * 1024 * 1024 * 1024 ||
            artifact.Sha256.Length != 64 || artifact.Sha256.Any(character => !Uri.IsHexDigit(character)))
            throw new ConnectorException("artifact_ref_invalid");
        var path = files.PathFor(artifact.ArtifactId, artifact.MediaType);
        var temporaryPath = path + ".partial-" + Guid.NewGuid().ToString("N");
        try
        {
            await transport.DownloadToAsync(downloadUrl, temporaryPath, cancellationToken);
            var info = new FileInfo(temporaryPath);
            if (!info.Exists || info.Length != artifact.ByteSize || await FileHashAsync(temporaryPath, cancellationToken) != artifact.Sha256)
                throw files.DeleteAndError(temporaryPath, "artifact_integrity_failed");
            File.Move(temporaryPath, path, true);
            return new(artifact.ArtifactId, path, artifact.Sha256, artifact.ByteSize);
        }
        catch (ConnectorException)
        {
            if (File.Exists(temporaryPath)) File.Delete(temporaryPath);
            throw;
        }
        catch
        {
            if (File.Exists(temporaryPath)) File.Delete(temporaryPath);
            throw;
        }
    }

    public async Task<ArtifactUploadReceipt> UploadOrReconcileAsync(
        UploadGrant grant,
        string path,
        CancellationToken cancellationToken)
    {
        var info = new FileInfo(path);
        if (!info.Exists || info.Length > grant.MaximumBytes)
            throw new ConnectorException("artifact_upload_invalid", path);
        try
        {
            return await transport.UploadAsync(grant, path, cancellationToken);
        }
        catch (HttpRequestException)
        {
            return await transport.QueryUploadAsync(grant.UploadSessionId, cancellationToken)
                ?? throw new ConnectorException("artifact_upload_unconfirmed", path);
        }
    }

    private static async Task<string> FileHashAsync(string path, CancellationToken cancellationToken)
    {
        await using var stream = File.OpenRead(path);
        return Convert.ToHexString(await SHA256.HashDataAsync(stream, cancellationToken)).ToLowerInvariant();
    }
}
