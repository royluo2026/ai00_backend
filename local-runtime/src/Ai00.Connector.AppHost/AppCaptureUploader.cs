using System.Security.Cryptography;
using System.Text.Json;
using Ai00.Connector.Adapters.VisMockup;
using Ai00.Connector.Contracts;

namespace Ai00.Connector.AppHost;

public interface IAppCaptureUploader
{
    Task<JsonElement> UploadAsync(string planId,string leaseId,string stepId,
        LocalCaptureArtifact capture,RuntimeSession session,CancellationToken ct);
}

public sealed class AppCaptureUploader(RuntimeTransport transport,string captureRoot) : IAppCaptureUploader
{
    private readonly string root=Path.GetFullPath(captureRoot).TrimEnd(Path.DirectorySeparatorChar)+Path.DirectorySeparatorChar;

    public async Task<JsonElement> UploadAsync(string planId,string leaseId,string stepId,
        LocalCaptureArtifact capture,RuntimeSession session,CancellationToken ct)
    {
        var path=Path.GetFullPath(capture.Path);
        if(!path.StartsWith(root,StringComparison.OrdinalIgnoreCase)||
            capture.MediaType!="image/png"||capture.ByteSize is <24 or >100*1024*1024||
            capture.Sha256.Length!=64||capture.Width<1||capture.Height<1)
            throw new ConnectorNoEffectException("capture_result_invalid");
        var info=new FileInfo(path);
        if(!info.Exists||info.Length!=capture.ByteSize)
            throw new ConnectorNoEffectException("capture_result_invalid");
        await using(var check=info.OpenRead())
        {
            var actual=Convert.ToHexString(await SHA256.HashDataAsync(check,ct)).ToLowerInvariant();
            if(!string.Equals(actual,capture.Sha256,StringComparison.Ordinal))
                throw new ConnectorNoEffectException("artifact_integrity_failed");
        }
        await using var content=info.OpenRead();
        var artifact=await transport.UploadCaptureAsync(planId,leaseId,stepId,content,
            capture.Sha256,capture.ByteSize,session,ct);
        if(artifact.ValueKind!=JsonValueKind.Object||
            artifact.GetProperty("media_type").GetString()!=capture.MediaType||
            artifact.GetProperty("sha256").GetString()!=capture.Sha256||
            artifact.GetProperty("byte_size").GetInt64()!=capture.ByteSize||
            string.IsNullOrWhiteSpace(artifact.GetProperty("artifact_id").GetString()))
            throw new ConnectorException("artifact_upload_receipt_invalid");
        return artifact;
    }
}
