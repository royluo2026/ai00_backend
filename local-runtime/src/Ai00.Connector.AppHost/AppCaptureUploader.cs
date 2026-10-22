using System.Security.Cryptography;
using System.Diagnostics;
using System.Text.Json;
using Ai00.Connector.Adapters.VisMockup;
using Ai00.Connector.Contracts;

namespace Ai00.Connector.AppHost;

public interface IAppCaptureUploader
{
    Task<JsonElement> UploadAsync(string planId,string leaseId,string stepId,
        LocalCaptureArtifact capture,RuntimeSession session,CancellationToken ct);
    Task<JsonElement> UploadModelAsync(string planId,string leaseId,string stepId,
        LocalModelArtifact model,RuntimeSession session,CancellationToken ct)=>
        Task.FromException<JsonElement>(new ConnectorException("model_artifact_upload_unavailable"));
}

public sealed class AppCaptureUploader(RuntimeTransport transport,string captureRoot,string? modelRoot=null) : IAppCaptureUploader
{
    private readonly string root=Path.GetFullPath(captureRoot).TrimEnd(Path.DirectorySeparatorChar)+Path.DirectorySeparatorChar;

    public async Task<JsonElement> UploadModelAsync(string planId,string leaseId,string stepId,
        LocalModelArtifact model,RuntimeSession session,CancellationToken ct)
    {
        if(modelRoot is null)throw new ConnectorNoEffectException("model_artifact_upload_unavailable");
        var prefix=Path.GetFullPath(modelRoot).TrimEnd(Path.DirectorySeparatorChar)+Path.DirectorySeparatorChar;
        var path=Path.GetFullPath(model.Path);
        if(!path.StartsWith(prefix,StringComparison.OrdinalIgnoreCase)||model.MediaType!="model/jt"||model.ByteSize is <24 or >512*1024*1024||model.Sha256.Length!=64)throw new ConnectorNoEffectException("model_artifact_invalid");
        var info=new FileInfo(path);
        if(!info.Exists||info.Length!=model.ByteSize||(info.Attributes&FileAttributes.ReparsePoint)!=0)throw new ConnectorNoEffectException("model_artifact_invalid");
        var hashTimer=Stopwatch.StartNew();
        await using(var check=info.OpenRead())
        {
            var hash=Convert.ToHexString(await SHA256.HashDataAsync(check,ct)).ToLowerInvariant();
            if(hash!=model.Sha256)throw new ConnectorNoEffectException("artifact_integrity_failed");
        }
        ModelFileTiming.Write("upload_hash_verified",planId,stepId,hashTimer.Elapsed.TotalMilliseconds,model.ByteSize);
        await using var content=info.OpenRead();
        var uploadTimer=Stopwatch.StartNew();
        ModelFileTiming.Write("artifact_upload_started",planId,stepId,0,model.ByteSize);
        JsonElement artifact;
        try{artifact=await transport.UploadCaptureAsync(planId,leaseId,stepId,content,model.Sha256,model.ByteSize,session,ct,"model/jt");}
        catch(Exception error)
        {
            ModelFileTiming.Write("artifact_upload_failed",planId,stepId,uploadTimer.Elapsed.TotalMilliseconds,model.ByteSize,
                error is RuntimeTransportException transportError?transportError.Message:error is OperationCanceledException?"cancelled":"artifact_upload_failed");
            throw;
        }
        ModelFileTiming.Write("artifact_upload_completed",planId,stepId,uploadTimer.Elapsed.TotalMilliseconds,model.ByteSize);
        if(artifact.GetProperty("media_type").GetString()!=model.MediaType||artifact.GetProperty("sha256").GetString()!=model.Sha256||artifact.GetProperty("byte_size").GetInt64()!=model.ByteSize||string.IsNullOrWhiteSpace(artifact.GetProperty("artifact_id").GetString()))throw new ConnectorException("artifact_upload_receipt_invalid");
        return artifact;
    }

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
        var uploadClock=Stopwatch.StartNew();
        var artifact=await transport.UploadCaptureAsync(planId,leaseId,stepId,content,
            capture.Sha256,capture.ByteSize,session,ct);
        if(artifact.ValueKind!=JsonValueKind.Object||
            artifact.GetProperty("media_type").GetString()!=capture.MediaType||
            artifact.GetProperty("sha256").GetString()!=capture.Sha256||
            artifact.GetProperty("byte_size").GetInt64()!=capture.ByteSize||
            string.IsNullOrWhiteSpace(artifact.GetProperty("artifact_id").GetString()))
            throw new ConnectorException("artifact_upload_receipt_invalid");
        Console.Error.WriteLine("AI00_CAPTURE_TIMING_V1:"+JsonSerializer.Serialize(new{
            stage="upload_confirmed",plan_id=planId,step_id=stepId,
            elapsed_ms=Math.Round(uploadClock.Elapsed.TotalMilliseconds,1),byte_size=capture.ByteSize,
        }));
        return artifact;
    }
}

internal static class ModelFileTiming
{
    internal static void Write(string stage,string planId,string stepId,double elapsedMs,long byteSize,string? errorCode=null)
    {
        Console.Error.WriteLine("AI00_MODEL_FILE_TIMING_V1:"+JsonSerializer.Serialize(new
        {
            stage,plan_id=planId,step_id=stepId,elapsed_ms=Math.Round(elapsedMs,1),byte_size=byteSize,error_code=errorCode
        }));
    }
}
