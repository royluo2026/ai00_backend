using System.Security.Cryptography;
using Ai00.Connector.Adapters.VisMockup;
using Ai00.Connector.Contracts;

namespace Ai00.Connector.SessionHost;

public sealed class CommandDispatcher(VisMockupAdapter visMockup, CommandLedger ledger, string artifactCacheRoot)
{
    public async Task<OperationCompletion> ExecuteAsync(OperationEnvelope operation, IReadOnlyList<MaterializedArtifact> artifacts)
    {
        if (operation.Protocol != OperationEnvelope.ProtocolVersion)
            return new(operation.OperationId, "failed", ErrorCode: "protocol_version_unsupported");
        if (!RuntimeCapabilities.Allowed.Contains(operation.CapabilityId))
            return new(operation.OperationId, "failed", ErrorCode: "capability_not_allowed");
        if (operation.ExpiresAt <= DateTimeOffset.UtcNow)
            return new(operation.OperationId, "failed", ErrorCode: "operation_expired");
        var actualHash = "sha256:" + Convert.ToHexString(SHA256.HashData(CanonicalJson.Serialize(operation.Payload))).ToLowerInvariant();
        if (!string.Equals(actualHash, operation.PayloadHash, StringComparison.Ordinal))
            return new(operation.OperationId, "failed", ErrorCode: "payload_hash_mismatch");
        if (!ledger.TryBegin(operation.OperationId, out var existingState))
            return new(operation.OperationId, "outcome_unknown", ErrorCode: existingState == "completed" ? "duplicate_outcome_not_retained" : "unsafe_replay_refused");

        try
        {
            object result = operation.CapabilityId switch
            {
                "vismockup.status" => await visMockup.StatusAsync(),
                "vismockup.launch" => await visMockup.LaunchAsync(),
                "vismockup.visibility" => await visMockup.VisibilityAsync(operation.Payload.GetProperty("action").GetString() ?? ""),
                "vismockup.capture" => await visMockup.CaptureAsync(),
                "vismockup.model.open" => await visMockup.OpenFileAsync(VerifyMaterializedArtifact(operation, artifacts)),
                "vismockup.tree" => await visMockup.TreeAsync(operation.Payload.TryGetProperty("max_depth", out var maxDepth) ? maxDepth.GetInt32() : 3),
                "vismockup.highlight" => await visMockup.HighlightAsync(operation.Payload.GetProperty("catia_names").EnumerateArray().Select(item => item.GetString() ?? "").Where(item => item.Length > 0).ToHashSet(StringComparer.Ordinal)),
                _ => throw new InvalidOperationException("adapter_not_available")
            };
            ledger.Complete(operation.OperationId);
            return new(operation.OperationId, "completed", result);
        }
        catch (InvalidOperationException ex) when (ex.Message is "artifact_materialization_required" or "artifact_integrity_failed" or "adapter_not_available")
        {
            ledger.Fail(operation.OperationId);
            return new(operation.OperationId, "failed", ErrorCode: ex.Message);
        }
        catch
        {
            ledger.MarkOutcomeUnknown(operation.OperationId);
            return new(operation.OperationId, "outcome_unknown", ErrorCode: "local_execution_outcome_unknown");
        }
    }

    private string VerifyMaterializedArtifact(OperationEnvelope operation, IReadOnlyList<MaterializedArtifact> artifacts)
    {
        var artifactRef = operation.Payload.GetProperty("artifact_ref");
        var artifactId = artifactRef.GetProperty("artifact_id").GetString() ?? "";
        var expectedHash = artifactRef.GetProperty("sha256").GetString() ?? "";
        var expectedSize = artifactRef.GetProperty("byte_size").GetInt64();
        var artifact = artifacts.SingleOrDefault(item => item.ArtifactId == artifactId)
            ?? throw new InvalidOperationException("artifact_materialization_required");
        var root = Path.GetFullPath(artifactCacheRoot).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        var path = Path.GetFullPath(artifact.CachePath);
        if (!path.StartsWith(root, StringComparison.OrdinalIgnoreCase) || artifact.Sha256 != expectedHash || artifact.ByteSize != expectedSize)
            throw new InvalidOperationException("artifact_integrity_failed");
        var info = new FileInfo(path);
        if (!info.Exists || info.Length != expectedSize) throw new InvalidOperationException("artifact_integrity_failed");
        using var stream = info.OpenRead();
        var actualHash = Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant();
        if (actualHash != expectedHash) throw new InvalidOperationException("artifact_integrity_failed");
        return path;
    }
}
