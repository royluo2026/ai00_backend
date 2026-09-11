using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using Ai00.Connector.Contracts;
using Ai00.Connector.Contracts.V2;

namespace Ai00.Connector.AppHost;

public interface IAppArtifactMaterializer
{
    Task<JsonElement> MaterializeAsync(
        string planId, string leaseId, ConnectorStepV2 step,
        RuntimeSession session, CancellationToken cancellationToken);
}

public sealed class AppArtifactMaterializer(RuntimeTransport transport, string artifactRoot) : IAppArtifactMaterializer
{
    private static readonly Regex SafeIdentity = new("^[A-Za-z0-9_.-]{1,191}$", RegexOptions.CultureInvariant);
    private readonly string root = PrepareRoot(artifactRoot);

    public async Task<JsonElement> MaterializeAsync(
        string planId, string leaseId, ConnectorStepV2 step,
        RuntimeSession session, CancellationToken cancellationToken)
    {
        if (step.OperationId is not ("vismockup.model.open@1" or "vismockup.model.insert@1" or "vismockup.model.attach@1"))
            return step.Payload.Clone();

        var artifact = ArtifactRef(step);
        var artifactId = Text(artifact, "artifact_id");
        var mediaType = Text(artifact, "media_type");
        var expectedHash = Text(artifact, "sha256");
        var expectedSize = artifact.GetProperty("byte_size").GetInt64();
        Validate(artifactId, mediaType, expectedHash, expectedSize);

        JsonElement dependencies = default;
        var packaged = step.OperationId == "vismockup.model.open@1" &&
            step.Payload.TryGetProperty("package_dependencies", out dependencies);
        var packageRoot = packaged ? PackageRoot(planId) : root;
        var path = packaged ? Path.Combine(packageRoot, "environment" + Extension(mediaType)) : PathFor(artifactId, mediaType);
        await DownloadArtifactAsync(planId, leaseId, artifact, path, session, cancellationToken);
        if (packaged)
        {
            if (dependencies.ValueKind != JsonValueKind.Array) throw new ConnectorNoEffectException("artifact_package_invalid");
            foreach (var dependency in dependencies.EnumerateArray())
            {
                var relative = Text(dependency, "package_path").Replace('/', Path.DirectorySeparatorChar);
                var dependencyPath = Path.GetFullPath(Path.Combine(packageRoot, relative));
                if (!dependencyPath.StartsWith(packageRoot + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                    throw new ConnectorNoEffectException("artifact_path_invalid");
                await DownloadArtifactAsync(planId, leaseId, dependency.GetProperty("artifact_ref"), dependencyPath, session, cancellationToken);
            }
        }

        var payload = JsonNode.Parse(step.Payload.GetRawText())!.AsObject();
        if (step.OperationId == "vismockup.model.attach@1")
            payload["binding"]!.AsObject()["local_artifact_path"] = path;
        else
            payload["local_artifact_path"] = path;
        payload.Remove("package_dependencies");
        return JsonSerializer.SerializeToElement(payload);
    }

    private async Task DownloadArtifactAsync(string planId, string leaseId, JsonElement artifact, string path,
        RuntimeSession session, CancellationToken cancellationToken)
    {
        var artifactId = Text(artifact, "artifact_id"); var mediaType = Text(artifact, "media_type");
        var expectedHash = Text(artifact, "sha256"); var expectedSize = artifact.GetProperty("byte_size").GetInt64();
        Validate(artifactId, mediaType, expectedHash, expectedSize);
        var grant = await transport.SendAsync(HttpMethod.Get,
            $"plans/{Uri.EscapeDataString(planId)}/artifacts/{Uri.EscapeDataString(artifactId)}?lease_id={Uri.EscapeDataString(leaseId)}",
            null, cancellationToken, session);
        var returned = grant.GetProperty("artifact_ref");
        if (!JsonNode.DeepEquals(JsonNode.Parse(returned.GetRawText()), JsonNode.Parse(artifact.GetRawText())))
            throw new ConnectorNoEffectException("artifact_ref_mismatch");
        var downloadUrl = grant.GetProperty("download_url").GetString();
        if (string.IsNullOrWhiteSpace(downloadUrl)) throw new ConnectorNoEffectException("artifact_download_unavailable");
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        if (await IsValidAsync(path, expectedHash, expectedSize, cancellationToken)) return;
        var temporary = path + ".partial-" + Guid.NewGuid().ToString("N");
        try
        {
            await transport.DownloadAsync(new Uri(downloadUrl, UriKind.RelativeOrAbsolute), temporary, expectedSize, session, cancellationToken);
            if (!await IsValidAsync(temporary, expectedHash, expectedSize, cancellationToken))
                throw new ConnectorNoEffectException("artifact_integrity_failed");
            File.Move(temporary, path, true);
        }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }

    private static JsonElement ArtifactRef(ConnectorStepV2 step) => step.OperationId == "vismockup.model.attach@1"
        ? step.Payload.GetProperty("binding").GetProperty("model_ref").GetProperty("artifact_ref")
        : step.Payload.GetProperty("artifact_ref");
    private static string Text(JsonElement value, string name) =>
        value.GetProperty(name).GetString() ?? throw new ConnectorNoEffectException("artifact_ref_invalid");
    private static void Validate(string artifactId, string mediaType, string hash, long size)
    {
        if (!SafeIdentity.IsMatch(artifactId) || hash.Length != 64 || hash.Any(character => !Uri.IsHexDigit(character)) ||
            size < 0 || size > 2L * 1024 * 1024 * 1024 || Extension(mediaType) is null)
            throw new ConnectorNoEffectException("artifact_ref_invalid");
    }
    private string PathFor(string artifactId, string mediaType)
    {
        var path = Path.GetFullPath(Path.Combine(root, artifactId + Extension(mediaType)));
        if (!path.StartsWith(root, StringComparison.OrdinalIgnoreCase)) throw new ConnectorNoEffectException("artifact_path_invalid");
        return path;
    }
    private string PackageRoot(string planId)
    {
        if (!SafeIdentity.IsMatch(planId)) throw new ConnectorNoEffectException("artifact_path_invalid");
        var path = Path.GetFullPath(Path.Combine(root, planId));
        if (!path.StartsWith(root, StringComparison.OrdinalIgnoreCase)) throw new ConnectorNoEffectException("artifact_path_invalid");
        Directory.CreateDirectory(path); return path;
    }
    private static string? Extension(string mediaType) => mediaType switch
    {
        "model/jt" or "model/vnd.jt" => ".jt",
        "model/plmxml" or "application/plmxml+xml" or "application/vnd.siemens.plmxml+xml" => ".plmxml",
        "model/step" => ".stp",
        _ => null,
    };
    private static string PrepareRoot(string value)
    {
        var path = Path.GetFullPath(value).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        Directory.CreateDirectory(path);
        return path;
    }
    private static async Task<bool> IsValidAsync(string path, string hash, long size, CancellationToken cancellationToken)
    {
        var info = new FileInfo(path);
        if (!info.Exists || info.Length != size) return false;
        await using var stream = File.OpenRead(path);
        return string.Equals(Convert.ToHexString(await SHA256.HashDataAsync(stream, cancellationToken)), hash, StringComparison.OrdinalIgnoreCase);
    }
}
