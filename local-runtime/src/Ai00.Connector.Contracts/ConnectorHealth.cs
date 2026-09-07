using System.Text.Json.Serialization;

namespace Ai00.Connector.Contracts;

public sealed record SessionHostPresence(
    [property: JsonPropertyName("windows_sid")] string WindowsSid,
    [property: JsonPropertyName("session_id")] int SessionId,
    [property: JsonPropertyName("process_id")] int ProcessId,
    [property: JsonPropertyName("adapter")] AdapterManifest Adapter,
    [property: JsonPropertyName("reported_at")] DateTimeOffset ReportedAt);

public sealed record SessionHostStartRequest(
    [property: JsonPropertyName("device_id")] string DeviceId,
    [property: JsonPropertyName("user_id")] string UserId,
    [property: JsonPropertyName("windows_sid")] string WindowsSid);

public static class SessionHostPresencePath
{
    public static string For(string windowsSid)
    {
        var digest = System.Security.Cryptography.SHA256.HashData(
            System.Text.Encoding.UTF8.GetBytes(windowsSid));
        return Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),
        "AI00", "SessionHost", Convert.ToHexString(digest).ToLowerInvariant() + ".json");
    }
}
