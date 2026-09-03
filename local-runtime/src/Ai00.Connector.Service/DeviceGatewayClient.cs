using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text.Json;
using Ai00.Connector.Contracts;
using Microsoft.Extensions.Options;

namespace Ai00.Connector.Service;

public sealed class DeviceGatewayClient(HttpClient http, IOptions<RuntimeOptions> options)
{
    private readonly RuntimeOptions _options = options.Value;

    private HttpRequestMessage Request(HttpMethod method, string path, object? body = null)
    {
        if (string.IsNullOrWhiteSpace(_options.DeviceId) || string.IsNullOrWhiteSpace(_options.DeviceToken))
            throw new InvalidOperationException("Device enrollment is required");
        var request = new HttpRequestMessage(method, new Uri(new Uri(_options.GatewayUrl.TrimEnd('/') + "/"), path.TrimStart('/')));
        request.Headers.Add("X-AI00-Device-ID", _options.DeviceId);
        request.Headers.Add("X-AI00-Device-Token", _options.DeviceToken);
        if (body is not null) request.Content = JsonContent.Create(body);
        return request;
    }

    public async Task HeartbeatAsync(CancellationToken cancellationToken)
    {
        using var request = Request(HttpMethod.Post, "/api/v1/device-runtime/heartbeat", new { runtime_version = _options.Version, capabilities = RuntimeCapabilities.Allowed });
        using var response = await http.SendAsync(request, cancellationToken);
        response.EnsureSuccessStatusCode();
    }

    public async Task<SignedOperationEnvelope?> LeaseAsync(CancellationToken cancellationToken)
    {
        using var request = Request(HttpMethod.Post, "/api/v1/device-runtime/commands/lease", new { lease_seconds = 120 });
        using var response = await http.SendAsync(request, cancellationToken);
        response.EnsureSuccessStatusCode();
        var envelope = await response.Content.ReadFromJsonAsync<ApiEnvelope<SignedOperationEnvelope?>>(cancellationToken: cancellationToken);
        return envelope?.Data;
    }

    public async Task CompleteAsync(string operationId, string leaseId, OperationCompletion completion, CancellationToken cancellationToken)
    {
        var reportedAt = DateTimeOffset.UtcNow;
        reportedAt = reportedAt.AddTicks(-(reportedAt.Ticks % TimeSpan.TicksPerSecond));
        var outcome = new OperationOutcome(OperationEnvelope.ProtocolVersion, operationId, completion.Status, completion.Result, completion.ErrorCode, reportedAt);
        using var request = Request(HttpMethod.Post, $"/api/v1/device-runtime/commands/{Uri.EscapeDataString(operationId)}/complete", new
        {
            lease_id = leaseId, outcome, signature = OutcomeSecurity.Sign(outcome, _options.DeviceToken)
        });
        using var response = await http.SendAsync(request, cancellationToken);
        response.EnsureSuccessStatusCode();
    }

    public async Task<LocalExecutionRequest> PrepareAsync(SignedOperationEnvelope lease, CancellationToken cancellationToken)
    {
        var operation = lease.Operation;
        if (operation.CapabilityId != "vismockup.model.open")
            return new(lease, Array.Empty<MaterializedArtifact>());
        var artifact = operation.Payload.GetProperty("artifact_ref");
        var artifactId = artifact.GetProperty("artifact_id").GetString() ?? throw new InvalidOperationException("artifact_id_missing");
        var expectedHash = artifact.GetProperty("sha256").GetString() ?? throw new InvalidOperationException("artifact_hash_missing");
        var expectedSize = artifact.GetProperty("byte_size").GetInt64();
        var mediaType = artifact.GetProperty("media_type").GetString() ?? "";
        var extension = mediaType switch
        {
            "model/jt" => ".jt",
            "model/plmxml" or "application/vnd.siemens.plmxml+xml" => ".plmxml",
            "model/step" => ".stp",
            _ => throw new InvalidOperationException("artifact_media_type_unsupported")
        };
        var grantPath = $"/api/v1/device-runtime/commands/{Uri.EscapeDataString(operation.OperationId)}/artifacts/{Uri.EscapeDataString(artifactId)}?lease_id={Uri.EscapeDataString(lease.LeaseId)}";
        using var grantRequest = Request(HttpMethod.Get, grantPath);
        using var grantResponse = await http.SendAsync(grantRequest, cancellationToken);
        grantResponse.EnsureSuccessStatusCode();
        var grant = await grantResponse.Content.ReadFromJsonAsync<ApiEnvelope<ArtifactGrant>>(cancellationToken: cancellationToken)
            ?? throw new InvalidOperationException("artifact_grant_missing");
        var downloadUri = Uri.TryCreate(grant.Data.DownloadUrl, UriKind.Absolute, out var absolute)
            ? absolute : new Uri(new Uri(_options.GatewayUrl.TrimEnd('/') + "/"), grant.Data.DownloadUrl.TrimStart('/'));
        Directory.CreateDirectory(_options.ArtifactCacheRoot);
        var cacheRoot = Path.GetFullPath(_options.ArtifactCacheRoot);
        var finalPath = Path.Combine(cacheRoot, expectedHash + extension);
        var temporaryPath = finalPath + ".partial-" + Guid.NewGuid().ToString("N");
        try
        {
            using var response = await http.GetAsync(downloadUri, HttpCompletionOption.ResponseHeadersRead, cancellationToken);
            response.EnsureSuccessStatusCode();
            await using var source = await response.Content.ReadAsStreamAsync(cancellationToken);
            await using var destination = new FileStream(temporaryPath, FileMode.CreateNew, FileAccess.Write, FileShare.None, 1024 * 1024, FileOptions.Asynchronous | FileOptions.WriteThrough);
            using var digest = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
            var buffer = new byte[1024 * 1024];
            long size = 0;
            while (true)
            {
                var read = await source.ReadAsync(buffer, cancellationToken);
                if (read == 0) break;
                size += read;
                if (size > expectedSize) throw new InvalidOperationException("artifact_size_mismatch");
                digest.AppendData(buffer, 0, read);
                await destination.WriteAsync(buffer.AsMemory(0, read), cancellationToken);
            }
            await destination.FlushAsync(cancellationToken);
            var actualHash = Convert.ToHexString(digest.GetHashAndReset()).ToLowerInvariant();
            if (size != expectedSize || actualHash != expectedHash) throw new InvalidOperationException("artifact_integrity_failed");
            File.Move(temporaryPath, finalPath, true);
        }
        finally
        {
            if (File.Exists(temporaryPath)) File.Delete(temporaryPath);
        }
        return new(lease, new[] { new MaterializedArtifact(artifactId, finalPath, expectedHash, expectedSize) });
    }

    public async Task<OperationCompletion> FinalizeAsync(SignedOperationEnvelope lease, OperationCompletion completion, CancellationToken cancellationToken)
    {
        if (lease.Operation.CapabilityId != "vismockup.capture" || completion.Status != "completed")
            return completion;
        if (completion.Result is not JsonElement result || !result.TryGetProperty("path", out var pathElement))
            throw new InvalidOperationException("capture_result_missing");
        var path = Path.GetFullPath(pathElement.GetString() ?? "");
        var captureRoot = Path.GetFullPath(_options.CaptureRoot).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        if (!path.StartsWith(captureRoot, StringComparison.OrdinalIgnoreCase)) throw new InvalidOperationException("capture_result_invalid");
        var info = new FileInfo(path);
        if (!info.Exists || info.Length > 100 * 1024 * 1024) throw new InvalidOperationException("capture_result_invalid");
        await using var hashStream = info.OpenRead();
        var sha256 = Convert.ToHexString(await SHA256.HashDataAsync(hashStream, cancellationToken)).ToLowerInvariant();
        await using var upload = info.OpenRead();
        using var request = Request(HttpMethod.Put, $"/api/v1/device-runtime/commands/{Uri.EscapeDataString(lease.Operation.OperationId)}/result-artifact?lease_id={Uri.EscapeDataString(lease.LeaseId)}");
        request.Headers.Add("X-AI00-Content-SHA256", sha256);
        request.Headers.Add("X-AI00-Content-Length", info.Length.ToString(System.Globalization.CultureInfo.InvariantCulture));
        request.Content = new StreamContent(upload);
        request.Content.Headers.ContentType = new System.Net.Http.Headers.MediaTypeHeaderValue("image/png");
        using var response = await http.SendAsync(request, cancellationToken);
        response.EnsureSuccessStatusCode();
        var artifact = await response.Content.ReadFromJsonAsync<ApiEnvelope<ArtifactResult>>(cancellationToken: cancellationToken)
            ?? throw new InvalidOperationException("capture_artifact_missing");
        File.Delete(path);
        return new OperationCompletion(completion.OperationId, "completed", new { artifact_ref = artifact.Data.ArtifactRef });
    }

    private sealed record ApiEnvelope<T>(bool Success, T Data);
    private sealed record ArtifactGrant(
        [property: System.Text.Json.Serialization.JsonPropertyName("artifact_ref")] JsonElement ArtifactRef,
        [property: System.Text.Json.Serialization.JsonPropertyName("download_url")] string DownloadUrl);
    private sealed record ArtifactResult(
        [property: System.Text.Json.Serialization.JsonPropertyName("artifact_ref")] JsonElement ArtifactRef);
}
