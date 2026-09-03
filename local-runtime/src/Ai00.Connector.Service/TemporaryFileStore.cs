using System.Text.RegularExpressions;
using Ai00.Connector.Contracts;

namespace Ai00.Connector.Service;

public sealed class TemporaryFileStore
{
    private static readonly Regex SafeIdentity = new("^[A-Za-z0-9_.-]{1,191}$", RegexOptions.CultureInvariant);
    private readonly string _root;

    public TemporaryFileStore(string root)
    {
        _root = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        Directory.CreateDirectory(_root);
    }

    public string PathFor(string artifactId, string mediaType)
    {
        if (!SafeIdentity.IsMatch(artifactId)) throw new ConnectorException("artifact_identity_invalid");
        var extension = mediaType switch
        {
            "model/jt" => ".jt",
            "model/plmxml" or "application/vnd.siemens.plmxml+xml" => ".plmxml",
            "image/png" => ".png",
            _ => throw new ConnectorException("artifact_media_type_unsupported"),
        };
        var path = Path.GetFullPath(Path.Combine(_root, artifactId + extension));
        if (!path.StartsWith(_root, StringComparison.OrdinalIgnoreCase))
            throw new ConnectorException("artifact_path_invalid");
        return path;
    }

    public ConnectorException DeleteAndError(string path, string code)
    {
        if (File.Exists(path)) File.Delete(path);
        return new ConnectorException(code, path);
    }
}
