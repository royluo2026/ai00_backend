using System.Net.Http.Json;

namespace Ai00.Connector.Service;

public sealed class HttpArtifactTransport(HttpClient http) : IArtifactTransport
{
    public async Task DownloadToAsync(Uri source, string destination, CancellationToken cancellationToken)
    {
        using var response = await http.GetAsync(source, HttpCompletionOption.ResponseHeadersRead, cancellationToken);
        response.EnsureSuccessStatusCode();
        await using var input = await response.Content.ReadAsStreamAsync(cancellationToken);
        await using var output = new FileStream(
            destination, FileMode.CreateNew, FileAccess.Write, FileShare.None,
            1024 * 1024, FileOptions.Asynchronous | FileOptions.WriteThrough);
        await input.CopyToAsync(output, cancellationToken);
        await output.FlushAsync(cancellationToken);
    }

    public Task<ArtifactUploadReceipt> UploadAsync(UploadGrant grant, string path, CancellationToken cancellationToken) =>
        throw new NotSupportedException("Plan result uploads use the authenticated Connector gateway route.");

    public Task<ArtifactUploadReceipt?> QueryUploadAsync(string uploadSessionId, CancellationToken cancellationToken) =>
        Task.FromResult<ArtifactUploadReceipt?>(null);
}
