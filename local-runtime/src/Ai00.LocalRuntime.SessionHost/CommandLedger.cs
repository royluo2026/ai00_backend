using System.Text.Json;

namespace Ai00.LocalRuntime.SessionHost;

public sealed class CommandLedger
{
    private readonly object _gate = new();
    private readonly string _path;
    private readonly Dictionary<string, string> _states = new(StringComparer.Ordinal);
    public CommandLedger(string path)
    {
        _path = path; Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        if (!File.Exists(path)) return;
        foreach (var line in File.ReadLines(path))
        {
            try { var entry = JsonSerializer.Deserialize<Entry>(line); if (entry is not null) _states[entry.CommandId] = entry.State; } catch { }
        }
    }
    public bool TryBegin(string commandId, out string? existingState)
    {
        lock (_gate)
        {
            if (_states.TryGetValue(commandId, out existingState)) return false;
            Write(new(commandId, "started", DateTimeOffset.UtcNow)); existingState = null; return true;
        }
    }
    public void Complete(string commandId)
    {
        lock (_gate) Write(new(commandId, "completed", DateTimeOffset.UtcNow));
    }
    private void Write(Entry entry)
    {
        _states[entry.CommandId] = entry.State;
        File.AppendAllText(_path, JsonSerializer.Serialize(entry) + Environment.NewLine);
    }
    private sealed record Entry(string CommandId, string State, DateTimeOffset At);
}
