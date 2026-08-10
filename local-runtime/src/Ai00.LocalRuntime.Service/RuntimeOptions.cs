namespace Ai00.LocalRuntime.Service;

public sealed class RuntimeOptions
{
    public string GatewayUrl { get; set; } = "https://ai00.example.com";
    public string DeviceId { get; set; } = "";
    public string DeviceToken { get; set; } = "";
    public string Version { get; set; } = "0.1.0";
    public string PipeSecret { get; set; } = "";
    public int PollSeconds { get; set; } = 2;
}
