using System.Text.Json.Serialization;

namespace Ai00.Connector.Contracts;

public sealed record SessionHostPresence(
    [property: JsonPropertyName("windows_sid")] string WindowsSid,
    [property: JsonPropertyName("session_id")] int SessionId,
    [property: JsonPropertyName("process_id")] int ProcessId,
    [property: JsonPropertyName("adapter")] AdapterManifest Adapter,
    [property: JsonPropertyName("reported_at")] DateTimeOffset ReportedAt);

public static class SessionHostPresencePath
{
    public static string Value => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),
        "AI00", "Connector", "session-host.json");
}
