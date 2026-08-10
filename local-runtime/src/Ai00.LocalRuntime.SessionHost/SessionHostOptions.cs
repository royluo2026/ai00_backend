namespace Ai00.LocalRuntime.SessionHost;

public sealed record SessionHostOptions(string VisMockupExe, string[] AllowedRoots, string PipeSecret)
{
    public static SessionHostOptions FromEnvironment()
    {
        var exe = Environment.GetEnvironmentVariable("AI00_VISMOCKUP_EXE") ?? @"D:\Siemens\Visualization14\Products\Mockup\VisView.exe";
        var roots = (Environment.GetEnvironmentVariable("AI00_VISMOCKUP_ALLOWED_ROOTS") ?? @"D:\").Split(';', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        var pipeSecret = Environment.GetEnvironmentVariable("AI00_LOCAL_PIPE_SECRET") ?? "";
        if (pipeSecret.Length < 32) throw new InvalidOperationException("AI00_LOCAL_PIPE_SECRET must contain at least 32 characters");
        return new(exe, roots, pipeSecret);
    }
}
