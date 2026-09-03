namespace Ai00.Connector.Service;

public sealed class RuntimeOptions
{
    public string GatewayUrl { get; set; } = "https://ai00.example.com";
    public string DeviceId { get; set; } = "";
    public string Version { get; set; } = "1.0.0";
    public string PipeSecret { get; set; } = "";
    public string ArtifactCacheRoot { get; set; } = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "AI00", "artifacts");
    public string CaptureRoot { get; set; } = Path.Combine(Path.GetTempPath(), "AI00", "captures");
    public int PollSeconds { get; set; } = 2;
}
