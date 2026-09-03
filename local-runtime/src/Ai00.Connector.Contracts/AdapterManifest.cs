using System.Reflection;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Ai00.Connector.Contracts;

public sealed record AdapterOperationContract(
    [property: JsonPropertyName("operation_id")] string OperationId,
    [property: JsonPropertyName("contract_hash")] string ContractHash);

public sealed record AdapterManifest(
    [property: JsonPropertyName("adapter_id")] string AdapterId,
    [property: JsonPropertyName("adapter_major")] int AdapterMajor,
    [property: JsonPropertyName("product_id")] string ProductId,
    [property: JsonPropertyName("product_version")] string ProductVersion,
    [property: JsonPropertyName("operations")] IReadOnlyList<AdapterOperationContract> Operations)
{
    public bool HasOperation(string operationId) =>
        Operations.Any(item => string.Equals(item.OperationId, operationId, StringComparison.Ordinal));

    public bool Supports(string operationId, string contractHash) =>
        Operations.Any(item =>
            string.Equals(item.OperationId, operationId, StringComparison.Ordinal) &&
            string.Equals(item.ContractHash, contractHash, StringComparison.Ordinal));
}

public sealed record AdapterHealth(bool Ready, string Status);

public sealed record AdapterOperation(string OperationId, JsonElement Payload);

public sealed record AdapterResult(bool Ok, object? Data = null, string ErrorCode = "");

public interface IConnectorAdapter
{
    AdapterManifest Manifest { get; }
    Task<AdapterHealth> ProbeAsync(CancellationToken cancellationToken);
    Task<AdapterResult> ExecuteAsync(AdapterOperation operation, CancellationToken cancellationToken);
}

public interface IAdapterSignatureVerifier
{
    void RequireTrusted(AdapterManifest manifest, string assemblyPath);
}

public sealed class ConnectorException(string code, string? localPath = null) : Exception(code)
{
    public string Code { get; } = code;
    public string? LocalPath { get; } = localPath;
}

public sealed class AdapterManifestLoader(
    IAdapterSignatureVerifier signatureVerifier,
    IEnumerable<string> administratorAllowlistedDirectories)
{
    private readonly string[] _allowedDirectories = administratorAllowlistedDirectories
        .Select(path => Path.GetFullPath(path).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar)
        .ToArray();

    public AdapterManifest LoadBuiltIn(Assembly assembly, string resourceName)
    {
        using var stream = assembly.GetManifestResourceStream(resourceName)
            ?? throw new ConnectorException("adapter_manifest_missing");
        var manifest = Read(stream);
        signatureVerifier.RequireTrusted(manifest, assembly.Location);
        return manifest;
    }

    public AdapterManifest LoadExternal(string manifestPath, string assemblyPath)
    {
        var fullManifest = Path.GetFullPath(manifestPath);
        var fullAssembly = Path.GetFullPath(assemblyPath);
        if (!_allowedDirectories.Any(root =>
                fullManifest.StartsWith(root, StringComparison.OrdinalIgnoreCase) &&
                fullAssembly.StartsWith(root, StringComparison.OrdinalIgnoreCase)))
            throw new ConnectorException("adapter_not_allowlisted");
        using var stream = File.OpenRead(fullManifest);
        var manifest = Read(stream);
        signatureVerifier.RequireTrusted(manifest, fullAssembly);
        return manifest;
    }

    private static AdapterManifest Read(Stream stream)
    {
        var manifest = JsonSerializer.Deserialize<AdapterManifest>(stream)
            ?? throw new ConnectorException("adapter_manifest_invalid");
        if (string.IsNullOrWhiteSpace(manifest.AdapterId) || manifest.AdapterMajor < 1 ||
            string.IsNullOrWhiteSpace(manifest.ProductId) || string.IsNullOrWhiteSpace(manifest.ProductVersion) ||
            manifest.Operations.Count == 0 ||
            manifest.Operations.Select(item => item.OperationId).Distinct(StringComparer.Ordinal).Count() != manifest.Operations.Count)
            throw new ConnectorException("adapter_manifest_invalid");
        return manifest;
    }
}
