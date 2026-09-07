using Ai00.Connector.Contracts;

namespace Ai00.Connector.SessionHost;

public sealed record SessionHostOptions(
    string VisMockupExe,
    string[] AllowedRoots,
    string ArtifactCacheRoot)
{
    public static SessionHostOptions FromEnvironment()
    {
        var exe = Environment.GetEnvironmentVariable("AI00_VISMOCKUP_EXE") ?? @"D:\Siemens\Visualization14\Products\Mockup\VisView.exe";
        var roots = (Environment.GetEnvironmentVariable("AI00_VISMOCKUP_ALLOWED_ROOTS") ?? @"D:\").Split(';', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        var cacheRoot = Environment.GetEnvironmentVariable("AI00_LOCAL_ARTIFACT_CACHE") ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "AI00", "artifacts");
        return new(exe, roots, cacheRoot);
    }
}
