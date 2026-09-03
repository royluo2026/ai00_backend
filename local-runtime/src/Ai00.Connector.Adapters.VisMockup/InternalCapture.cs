using System.Buffers.Binary;
using System.Security.Cryptography;
using System.Text.RegularExpressions;
using Ai00.Connector.Contracts;

namespace Ai00.Connector.Adapters.VisMockup;

public sealed record CaptureRequest(
    string CaptureRunId,
    string StepId,
    string OperationId,
    int Attempt,
    CaptureProfile Profile);

public sealed record LocalCaptureArtifact(
    string Path,
    string MediaType,
    string Sha256,
    long ByteSize,
    int Width,
    int Height,
    int Attempt);

public sealed class InternalCapture(string root)
{
    private static readonly Regex SafeIdentity = new("^[A-Za-z0-9_.-]{1,191}$", RegexOptions.CultureInvariant);
    private readonly string _root = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;

    public LocalCaptureArtifact Capture(IVisMockupDocument document, CaptureRequest request)
    {
        if (!SafeIdentity.IsMatch(request.CaptureRunId) || !SafeIdentity.IsMatch(request.StepId) || request.Attempt < 1)
            throw new ConnectorException("capture_request_invalid");
        if (request.Profile.Format != "png") throw new ConnectorException("capture_format_unsupported");
        var directory = Path.Combine(_root, request.CaptureRunId);
        Directory.CreateDirectory(directory);
        var path = Path.Combine(directory, $"{request.StepId}-attempt-{request.Attempt}.png");
        if (File.Exists(path)) throw new ConnectorException("capture_attempt_exists", path);
        document.ApplyCaptureProfile(request.Profile);
        document.CaptureImage(path);
        var info = new FileInfo(path);
        if (!info.Exists || info.Length < 24) throw new ConnectorException("capture_failed", path);
        Span<byte> header = stackalloc byte[24];
        using (var stream = info.OpenRead()) stream.ReadExactly(header);
        if (!header[..8].SequenceEqual(new byte[] { 137, 80, 78, 71, 13, 10, 26, 10 }))
            throw new ConnectorException("capture_invalid_png", path);
        var width = BinaryPrimitives.ReadInt32BigEndian(header[16..20]);
        var height = BinaryPrimitives.ReadInt32BigEndian(header[20..24]);
        if (width != request.Profile.Width || height != request.Profile.Height)
            throw new ConnectorException("capture_dimension_mismatch", path);
        using var hashStream = info.OpenRead();
        var hash = Convert.ToHexString(SHA256.HashData(hashStream)).ToLowerInvariant();
        return new(path, "image/png", hash, info.Length, width, height, request.Attempt);
    }
}
