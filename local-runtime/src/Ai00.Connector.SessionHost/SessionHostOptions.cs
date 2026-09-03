namespace Ai00.Connector.SessionHost;

public sealed record SessionHostOptions(
    string VisMockupExe,
    string[] AllowedRoots,
    string ArtifactCacheRoot,
    IReadOnlyDictionary<string, string> OperationSigningKeys)
{
    public static SessionHostOptions FromEnvironment()
    {
        var exe = Environment.GetEnvironmentVariable("AI00_VISMOCKUP_EXE") ?? @"D:\Siemens\Visualization14\Products\Mockup\VisView.exe";
        var roots = (Environment.GetEnvironmentVariable("AI00_VISMOCKUP_ALLOWED_ROOTS") ?? @"D:\").Split(';', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        var cacheRoot = Environment.GetEnvironmentVariable("AI00_LOCAL_ARTIFACT_CACHE") ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "AI00", "artifacts");
        var rawKeys = Environment.GetEnvironmentVariable("AI00_LOCAL_OPERATION_KEYS") ?? "";
        var keys = rawKeys.Split(';', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .Select(value => value.Split('=', 2))
            .Where(parts => parts.Length == 2 && parts[0].Length > 0 && parts[1].Length >= 32)
            .ToDictionary(parts => parts[0], parts => parts[1], StringComparer.Ordinal);
        if (keys.Count == 0) throw new InvalidOperationException("AI00_LOCAL_OPERATION_KEYS must contain key-id=secret entries");
        return new(exe, roots, cacheRoot, keys);
    }
}
