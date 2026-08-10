using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Ai00.LocalRuntime.Contracts;

public sealed record CommandEnvelope(
    [property: JsonPropertyName("command_id")] string CommandId,
    [property: JsonPropertyName("lease_id")] string LeaseId,
    [property: JsonPropertyName("capability")] string Capability,
    [property: JsonPropertyName("version")] int Version,
    [property: JsonPropertyName("payload")] JsonElement Payload,
    [property: JsonPropertyName("payload_hash")] string PayloadHash,
    [property: JsonPropertyName("expires_at")] DateTimeOffset ExpiresAt);

public sealed record CommandCompletion(
    string LeaseId, bool Success, object? Result = null, string Error = "");
public sealed record PipeCommand(CommandEnvelope Command, string Mac);

public static class PipeSecurity
{
    public static string Sign(CommandEnvelope command, string secret)
    {
        if (secret.Length < 32) throw new InvalidOperationException("Pipe secret must contain at least 32 characters");
        using var hmac = new HMACSHA256(Encoding.UTF8.GetBytes(secret));
        return Convert.ToBase64String(hmac.ComputeHash(JsonSerializer.SerializeToUtf8Bytes(command)));
    }
    public static bool Verify(PipeCommand envelope, string secret)
    {
        try { return CryptographicOperations.FixedTimeEquals(Convert.FromBase64String(envelope.Mac), Convert.FromBase64String(Sign(envelope.Command, secret))); }
        catch { return false; }
    }
}

public static class RuntimeCapabilities
{
    public static readonly IReadOnlySet<string> Allowed = new HashSet<string>(StringComparer.Ordinal)
    {
        "vismockup.status", "vismockup.launch", "vismockup.open_file",
        "vismockup.visibility", "vismockup.capture"
    };
}
