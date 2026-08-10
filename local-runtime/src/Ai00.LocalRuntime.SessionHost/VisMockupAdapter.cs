using System.Diagnostics;
using System.Runtime.InteropServices;

namespace Ai00.LocalRuntime.SessionHost;

public sealed class VisMockupAdapter(StaDispatcher sta, AllowedPathPolicy paths, string executable)
{
    private const string ProgId = "VFFrame.Application";
    private object? _application;
    private dynamic Connect()
    {
        var type = Type.GetTypeFromProgID(ProgId, throwOnError: true)!;
        _application ??= Activator.CreateInstance(type) ?? throw new COMException("Unable to create VisMockup COM application");
        return _application;
    }
    public Task<object> StatusAsync() => sta.InvokeAsync<object>(() =>
    {
        try { dynamic app = Connect(); _ = app.Documents; return new { connected = true, platform = "windows" }; }
        catch (Exception ex) { _application = null; return new { connected = false, platform = "windows", error = ex.Message }; }
    });
    public async Task<object> LaunchAsync()
    {
        var status = await StatusAsync();
        if ((bool)(status.GetType().GetProperty("connected")?.GetValue(status) ?? false)) return new { status = "already_running" };
        var fullExe = Path.GetFullPath(executable);
        if (!File.Exists(fullExe)) throw new FileNotFoundException("VisMockup executable not found", fullExe);
        Process.Start(new ProcessStartInfo(fullExe) { UseShellExecute = true });
        return new { status = "starting" };
    }
    public Task<object> OpenFileAsync(string filePath) => sta.InvokeAsync<object>(() =>
    {
        var safePath = paths.ValidateModelPath(filePath); dynamic app = Connect(); app.Documents.Open(safePath); return new { opened = true };
    });
    public Task<object> VisibilityAsync(string action) => sta.InvokeAsync<object>(() =>
    {
        dynamic app = Connect(); dynamic documents = app.Documents;
        if ((int)documents.Count <= 0) throw new InvalidOperationException("No active VisMockup document");
        dynamic view = documents.Item(1).ActiveView;
        switch (action) { case "all_on": view.AllNodesOn(); break; case "all_off": view.AllNodesOff(); break; case "deselect": view.DeSelectAllNodes(); break; default: throw new InvalidOperationException("Unsupported visibility action"); }
        return new { action };
    });
    public Task<object> CaptureAsync() => sta.InvokeAsync<object>(() =>
    {
        dynamic app = Connect(); dynamic documents = app.Documents;
        if ((int)documents.Count <= 0) throw new InvalidOperationException("No active VisMockup document");
        var directory = Path.Combine(Path.GetTempPath(), "AI00", "captures"); Directory.CreateDirectory(directory);
        var path = Path.Combine(directory, $"vismockup_{DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()}.png");
        documents.Item(1).ActiveView.CaptureImage(path);
        return new { path, exists = File.Exists(path) };
    });
}
