using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Ai00.Connector.Contracts;

public sealed record OperationEnvelope(
    [property: JsonPropertyName("protocol")] string Protocol,
    [property: JsonPropertyName("operation_id")] string OperationId,
    [property: JsonPropertyName("tenant_id")] string TenantId,
    [property: JsonPropertyName("capability_id")] string CapabilityId,
    [property: JsonPropertyName("payload")] JsonElement Payload,
    [property: JsonPropertyName("payload_hash")] string PayloadHash,
    [property: JsonPropertyName("key_id")] string KeyId,
    [property: JsonPropertyName("issued_at")] DateTimeOffset IssuedAt,
    [property: JsonPropertyName("expires_at")] DateTimeOffset ExpiresAt)
{
    public const string ProtocolVersion = "ai00.local-operation.v2";

    public object CanonicalDocument() => new Dictionary<string, object?>
    {
        ["protocol"] = Protocol,
        ["operation_id"] = OperationId,
        ["tenant_id"] = TenantId,
        ["capability_id"] = CapabilityId,
        ["payload"] = Payload,
        ["payload_hash"] = PayloadHash,
        ["key_id"] = KeyId,
        ["issued_at"] = IssuedAt.UtcDateTime.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'"),
        ["expires_at"] = ExpiresAt.UtcDateTime.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'")
    };
}

public sealed record OperationCompletion(
    [property: JsonPropertyName("operation_id")] string OperationId,
    [property: JsonPropertyName("status")] string Status,
    [property: JsonPropertyName("result")] object? Result = null,
    [property: JsonPropertyName("error_code")] string ErrorCode = "");

public sealed record OperationOutcome(
    [property: JsonPropertyName("protocol")] string Protocol,
    [property: JsonPropertyName("operation_id")] string OperationId,
    [property: JsonPropertyName("status")] string Status,
    [property: JsonPropertyName("result")] object? Result,
    [property: JsonPropertyName("error_code")] string ErrorCode,
    [property: JsonPropertyName("reported_at")] DateTimeOffset ReportedAt)
{
    public object CanonicalDocument() => new Dictionary<string, object?>
    {
        ["protocol"] = Protocol, ["operation_id"] = OperationId, ["status"] = Status,
        ["result"] = Result, ["error_code"] = ErrorCode,
        ["reported_at"] = ReportedAt.UtcDateTime.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'")
    };
}

public sealed record SignedOperationEnvelope(
    [property: JsonPropertyName("operation")] OperationEnvelope Operation,
    [property: JsonPropertyName("signature")] string Signature,
    [property: JsonPropertyName("lease_id")] string LeaseId);

public sealed record MaterializedArtifact(
    [property: JsonPropertyName("artifact_id")] string ArtifactId,
    [property: JsonPropertyName("cache_path")] string CachePath,
    [property: JsonPropertyName("sha256")] string Sha256,
    [property: JsonPropertyName("byte_size")] long ByteSize);

public sealed record LocalExecutionRequest(
    [property: JsonPropertyName("lease")] SignedOperationEnvelope Lease,
    [property: JsonPropertyName("materialized_artifacts")] IReadOnlyList<MaterializedArtifact> MaterializedArtifacts);

public static class PipeSecurity
{
    public static string Sign(OperationEnvelope operation, string secret)
    {
        if (Encoding.UTF8.GetByteCount(secret) < 32)
            throw new InvalidOperationException("Pipe secret must contain at least 32 UTF-8 bytes");
        using var hmac = new HMACSHA256(Encoding.UTF8.GetBytes(secret));
        return "hmac-sha256:" + Convert.ToHexString(hmac.ComputeHash(CanonicalJson.Serialize(operation.CanonicalDocument()))).ToLowerInvariant();
    }

    public static bool Verify(SignedOperationEnvelope envelope, IReadOnlyDictionary<string, string> secrets)
    {
        if (!secrets.TryGetValue(envelope.Operation.KeyId, out var secret)) return false;
        var expected = Encoding.ASCII.GetBytes(Sign(envelope.Operation, secret));
        var actual = Encoding.ASCII.GetBytes(envelope.Signature ?? "");
        return expected.Length == actual.Length && CryptographicOperations.FixedTimeEquals(expected, actual);
    }
}

public static class OutcomeSecurity
{
    public static string Sign(OperationOutcome outcome, string deviceSecret)
    {
        if (Encoding.UTF8.GetByteCount(deviceSecret) < 32)
            throw new InvalidOperationException("Device secret must contain at least 32 UTF-8 bytes");
        using var hmac = new HMACSHA256(Encoding.UTF8.GetBytes(deviceSecret));
        return "hmac-sha256:" + Convert.ToHexString(hmac.ComputeHash(CanonicalJson.Serialize(outcome.CanonicalDocument()))).ToLowerInvariant();
    }
}

public static class RuntimeCapabilities
{
    public static readonly IReadOnlySet<string> Allowed = new HashSet<string>(StringComparer.Ordinal)
    {
        "vismockup.status", "vismockup.launch", "vismockup.model.open",
        "vismockup.tree", "vismockup.highlight", "vismockup.visibility", "vismockup.capture"
    };
}
