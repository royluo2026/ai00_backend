using System.Buffers.Binary;
using System.Security.Cryptography;
using System.Text.RegularExpressions;
using Ai00.Connector.Contracts;
using System.Text.Json.Serialization;

namespace Ai00.Connector.Adapters.VisMockup;

public sealed record CaptureRequest(
    string CaptureRunId,
    string StepId,
    string OperationId,
    int Attempt,
    CaptureProfile Profile);

public sealed record LocalCaptureArtifact(
    [property: JsonPropertyName("path")] string Path,
    [property: JsonPropertyName("media_type")] string MediaType,
    [property: JsonPropertyName("sha256")] string Sha256,
    [property: JsonPropertyName("byte_size")] long ByteSize,
    [property: JsonPropertyName("width")] int Width,
    [property: JsonPropertyName("height")] int Height,
    [property: JsonPropertyName("attempt")] int Attempt);

public sealed class InternalCapture(string root)
{
    private static readonly Regex SafeIdentity = new("^[A-Za-z0-9_.-]{1,191}$", RegexOptions.CultureInvariant);
    private readonly string _root = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;

    public LocalCaptureArtifact Capture(IVisMockupDocument document, CaptureRequest request, Action<string>? validate = null)
    {
        if (!SafeIdentity.IsMatch(request.CaptureRunId) || !SafeIdentity.IsMatch(request.StepId) || request.Attempt < 1)
            throw new ConnectorException("capture_request_invalid");
        if (request.Profile is not { Format: "png", Width: 1920, Height: 1080, Background: "current" })
            throw new ConnectorException("capture_profile_unsupported");
        var directory = Path.GetFullPath(Path.Combine(_root, request.CaptureRunId));
        if (!directory.StartsWith(_root, StringComparison.OrdinalIgnoreCase))
            throw new ConnectorException("capture_request_invalid");
        Directory.CreateDirectory(directory);
        var path = Path.Combine(directory, $"{request.StepId}-attempt-{request.Attempt}.png");
        if (File.Exists(path)) throw new ConnectorException("capture_attempt_exists", path);
        var candidate = Path.Combine(directory, $".candidate-{Guid.NewGuid():N}.png");
        try
        {
            document.ApplyCaptureProfile(request.Profile);
            document.RefreshCaptureView();
            document.CaptureImage(candidate);
            var info = new FileInfo(candidate);
            if (!info.Exists || info.Length < 24) throw new ConnectorException("capture_failed", path);
            Span<byte> header = stackalloc byte[24];
            using (var stream = info.OpenRead()) stream.ReadExactly(header);
            if (!header[..8].SequenceEqual(new byte[] { 137, 80, 78, 71, 13, 10, 26, 10 }))
                throw new ConnectorException("capture_invalid_png", path);
            var width = BinaryPrimitives.ReadInt32BigEndian(header[16..20]);
            var height = BinaryPrimitives.ReadInt32BigEndian(header[20..24]);
            if (width != request.Profile.Width || height != request.Profile.Height)
                throw new ConnectorException("capture_dimension_mismatch", path);
            validate?.Invoke(candidate);
            string hash;
            using (var hashStream = info.OpenRead())
                hash = Convert.ToHexString(SHA256.HashData(hashStream)).ToLowerInvariant();
            var byteSize = info.Length;
            File.Move(candidate, path, false);
            return new(path, "image/png", hash, byteSize, width, height, request.Attempt);
        }
        finally { if (File.Exists(candidate)) File.Delete(candidate); }
    }

    internal CapturePixels ReadPixels(IVisMockupDocument document, CaptureProfile profile)
    {
        Directory.CreateDirectory(_root);
        var path = Path.Combine(_root, $".baseline-{Guid.NewGuid():N}.png");
        try
        {
            document.ApplyCaptureProfile(profile);
            document.RefreshCaptureView();
            document.CaptureImage(path);
            return CapturePixels.Read(path, profile);
        }
        finally { if (File.Exists(path)) File.Delete(path); }
    }
}
