using System.Diagnostics;
using System.Text;
using System.Text.Json;
using Ai00.Connector.Contracts;

namespace Ai00.Connector.Adapters.VisMockup;

internal interface ITeamcenterVisualizationLauncher
{
    Task LaunchAsync(string materialPath, CancellationToken ct);
}

// VVI material and the live document use the same source identity, but the
// latter separates fields with '?' (not an ordinary URL query string).
internal sealed record TeamcenterVisualizationSource(Uri Endpoint, string DocumentUid, string DocumentType,
    string Title = "", string FileName = "", string ReferenceName = "", string FileUid = "")
{
    internal bool RequiresNewDocument => DocumentUid.Length == 0 || FileName.Length > 0;
    internal string? VerifiedSourceKey => DocumentUid.Length > 0 &&
        (DocumentType != "DirectModel" || FileUid.Length > 0)
        ? CanonicalJson.Hash(new { endpoint=Endpoint.AbsoluteUri, document_uid=DocumentUid,
            document_type=DocumentType, file_uid=FileUid, file_name=FileName, reference_name=ReferenceName }) : null;
    private static bool IsIdentityField(string key) => key is "VisDoc_UID" or "VisDoc_Type"
        or "Title" or "original_file_name" or "ref_name" or "FileTypeID" or "Operation";
    internal static TeamcenterVisualizationSource ReadMaterial(string path)
    {
        if (new FileInfo(path).Length > 1024 * 1024)
            throw new ConnectorNoEffectException("teamcenter_visualization_material_invalid");
        var fields = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var line in File.ReadLines(path, Encoding.UTF8))
        {
            var separator = line.IndexOf('=');
            if (separator <= 0) continue;
            var key = line[..separator].Trim();
            if (key != "HostPath" && !IsIdentityField(key)) continue;
            if (!fields.TryAdd(key, line[(separator + 1)..].Trim()))
                throw new ConnectorNoEffectException("teamcenter_visualization_material_invalid");
        }
        if (fields.GetValueOrDefault("Operation") != "Open"
            || !TryCreate(fields.GetValueOrDefault("HostPath"), fields, out var source))
            throw new ConnectorNoEffectException("teamcenter_visualization_material_invalid");
        if (source!.DocumentType == "DirectModel")
        {
            // Produced by the authenticated worker in the secured per-operation
            // material directory. Never infer a dataset from a display title.
            var evidencePath = path + ".source.json";
            try
            {
                if (!File.Exists(evidencePath) || new FileInfo(evidencePath).Length > 16384)
                    throw new ConnectorNoEffectException("teamcenter_direct_model_evidence_unavailable");
                using var evidence = JsonDocument.Parse(File.ReadAllText(evidencePath, Encoding.UTF8));
                var values = new Dictionary<string, string>(StringComparer.Ordinal);
                foreach (var property in evidence.RootElement.EnumerateObject())
                    if (property.Value.ValueKind != JsonValueKind.String || !values.TryAdd(property.Name, property.Value.GetString()!))
                        throw new JsonException();
                if (values.Count != 3 || values.GetValueOrDefault("dataset_uid") != source.DocumentUid
                    || !values.TryGetValue("file_uid", out var fileUid) || string.IsNullOrWhiteSpace(fileUid) || fileUid.Length > 128
                    || !values.TryGetValue("file_name", out var fileName) || string.IsNullOrWhiteSpace(fileName)
                    || fileName.Length > 512 || fileName.Any(char.IsControl) || fileName.IndexOfAny(['/', '\\']) >= 0
                    || !fileName.EndsWith(".jt", StringComparison.OrdinalIgnoreCase))
                    throw new JsonException();
                source = source with { FileName = fileName, ReferenceName = "JTPART", FileUid = fileUid };
            }
            catch (Exception error) when (error is JsonException or InvalidOperationException or IOException or UnauthorizedAccessException)
            { throw new ConnectorNoEffectException("teamcenter_direct_model_evidence_invalid"); }
        }
        return source;
    }

    internal bool Matches(string liveSource)
    {
        var parts = liveSource.Split('?');
        var fields = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var part in parts.Skip(1))
        {
            var separator = part.IndexOf('=');
            if (separator <= 0) continue;
            var key = part[..separator];
            if (!IsIdentityField(key)) continue;
            if (!fields.TryAdd(key, part[(separator + 1)..])) return false;
        }
        if (!TryCreate(parts[0], fields, out var live) || Endpoint != live!.Endpoint) return false;
        if (DocumentType == "DirectModel" && FileName.Length > 0)
            return live.DocumentUid.Length > 0
                ? DocumentUid == live.DocumentUid && DocumentType == live.DocumentType
                : FileName == live.FileName && ReferenceName == live.ReferenceName;
        return this == live;
    }

    private static bool TryCreate(string? endpoint, Dictionary<string, string> fields, out TeamcenterVisualizationSource? source)
    {
        source = null;
        if (!Uri.TryCreate(endpoint, UriKind.Absolute, out var uri) || uri.Scheme is not ("http" or "https")
            || uri.UserInfo.Length != 0 || uri.Query.Length != 0 || uri.Fragment.Length != 0)
            return false;
        if (fields.ContainsKey("VisDoc_UID") || fields.ContainsKey("VisDoc_Type"))
        {
            if (!fields.TryGetValue("VisDoc_UID", out var uid) || string.IsNullOrWhiteSpace(uid) || uid.Length > 128
                || !fields.TryGetValue("VisDoc_Type", out var type) || string.IsNullOrWhiteSpace(type) || type.Length > 256)
                return false;
            source = new(uri, Uri.UnescapeDataString(uid), Uri.UnescapeDataString(type));
            return true;
        }
        // File metadata alone is not a persistent identity. The caller must also
        // prove a unique, newly opened document in the retained application.
        if (fields.GetValueOrDefault("Operation") != "Open"
            || fields.GetValueOrDefault("FileTypeID") != "DirectModel.Document"
            || !fields.TryGetValue("Title", out var title) || string.IsNullOrWhiteSpace(title) || title.Length > 2048
            || !fields.TryGetValue("original_file_name", out var file) || string.IsNullOrWhiteSpace(file) || file.Length > 512
            || !fields.TryGetValue("ref_name", out var reference) || reference != "JTPART")
            return false;
        file = Uri.UnescapeDataString(file);
        if (file.IndexOfAny(['/', '\\', '\0']) >= 0 || !file.EndsWith(".jt", StringComparison.OrdinalIgnoreCase))
            return false;
        source = new(uri, "", "", Uri.UnescapeDataString(title), file, reference);
        return true;
    }
}

internal sealed class TeamcenterVisualizationRunner(
    string executable = @"D:\Siemens\Teamcenter14\portal\runner.exe") : ITeamcenterVisualizationLauncher
{
    internal static string EncodePath(string path) =>
        Convert.ToHexString(Encoding.BigEndianUnicode.GetBytes(Path.GetFullPath(path)));

    internal ProcessStartInfo CreateStartInfo(string materialPath)
    {
        var fullPath = Path.GetFullPath(materialPath);
        if (!File.Exists(fullPath) || !string.Equals(Path.GetExtension(fullPath), ".vvi", StringComparison.OrdinalIgnoreCase))
            throw new ConnectorNoEffectException("teamcenter_visualization_material_invalid");
        if (!File.Exists(executable))
            throw new ConnectorNoEffectException("teamcenter_visualization_runner_unavailable");
        var info = new ProcessStartInfo(executable) {
            UseShellExecute = false,
            CreateNoWindow = true,
            WorkingDirectory = Path.GetDirectoryName(executable)!,
        };
        info.ArgumentList.Add("-mime=application/x-visnetwork");
        info.ArgumentList.Add("-encodedArgs=" + EncodePath(fullPath));
        return info;
    }

    public Task LaunchAsync(string materialPath, CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested();
        // The external runner chooses its renderer asynchronously; it cannot
        // prove capacity or participate in the retained application's guard.
        return Task.FromException(new ConnectorNoEffectException("vismockup_document_limit_unverifiable"));
    }
}
