using System.Text.Json;

namespace Ai00.LocalRuntime.SessionHost;

public sealed class CommandLedger
{
    private readonly object _gate = new();
    private readonly string _path;
    private readonly int _maximumEntries;
    private readonly Dictionary<string, Entry> _states = new(StringComparer.Ordinal);

    public CommandLedger(string path, int maximumEntries = 10_000)
    {
        _path = path;
        _maximumEntries = Math.Clamp(maximumEntries, 100, 100_000);
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        if (File.Exists(path))
        {
            foreach (var line in File.ReadLines(path))
            {
                try { var entry = JsonSerializer.Deserialize<Entry>(line); if (entry is not null) _states[entry.OperationId] = entry; }
                catch (JsonException) { }
            }
        }
        foreach (var operationId in _states.Values.Where(item => item.State == "started").Select(item => item.OperationId).ToArray())
            Write(new(operationId, "outcome_unknown", DateTimeOffset.UtcNow));
        Compact();
    }

    public bool TryBegin(string operationId, out string? existingState)
    {
        lock (_gate)
        {
            if (_states.TryGetValue(operationId, out var existing))
            {
                existingState = existing.State;
                return false;
            }
            Write(new(operationId, "started", DateTimeOffset.UtcNow));
            existingState = null;
            return true;
        }
    }

    public void Complete(string operationId) { lock (_gate) Write(new(operationId, "completed", DateTimeOffset.UtcNow)); }
    public void Fail(string operationId) { lock (_gate) Write(new(operationId, "failed", DateTimeOffset.UtcNow)); }
    public void MarkOutcomeUnknown(string operationId) { lock (_gate) Write(new(operationId, "outcome_unknown", DateTimeOffset.UtcNow)); }

    private void Write(Entry entry)
    {
        _states[entry.OperationId] = entry;
        File.AppendAllText(_path, JsonSerializer.Serialize(entry) + Environment.NewLine);
    }

    private void Compact()
    {
        if (_states.Count <= _maximumEntries) return;
        var retained = _states.Values.OrderByDescending(item => item.At).Take(_maximumEntries).OrderBy(item => item.At).ToArray();
        _states.Clear();
        foreach (var entry in retained) _states[entry.OperationId] = entry;
        File.WriteAllLines(_path, retained.Select(entry => JsonSerializer.Serialize(entry)));
    }

    private sealed record Entry(string OperationId, string State, DateTimeOffset At);
}
