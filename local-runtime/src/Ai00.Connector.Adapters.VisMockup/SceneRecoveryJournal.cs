using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace Ai00.Connector.Adapters.VisMockup;

public sealed record SceneRecoveryRecord(
    long Sequence,
    string PlanId,
    string DeviceId,
    long RuntimeGeneration,
    string DocumentId,
    SceneState Baseline,
    string State,
    DateTimeOffset CreatedAt);

/// <summary>Current-user encrypted recovery facts for scene-changing plans.</summary>
public sealed class SceneRecoveryJournal
{
    private static readonly byte[] Entropy = Encoding.UTF8.GetBytes("ai00.vismockup.scene-recovery.v1");
    private readonly object _gate = new();
    private readonly string _path;
    private readonly int _maxRecords;
    private readonly long _maxBytes;
    private readonly TimeSpan _retention;
    private readonly Func<DateTimeOffset> _clock;

    public SceneRecoveryJournal(
        string path, int maxRecords = 128, long maxBytes = 4 * 1024 * 1024,
        TimeSpan? retention = null, Func<DateTimeOffset>? clock = null)
    {
        _path = Path.GetFullPath(path);
        _maxRecords = maxRecords > 0 ? maxRecords : throw new ArgumentOutOfRangeException(nameof(maxRecords));
        _maxBytes = maxBytes > 0 ? maxBytes : throw new ArgumentOutOfRangeException(nameof(maxBytes));
        _retention = retention ?? TimeSpan.FromDays(7);
        _clock = clock ?? (() => DateTimeOffset.UtcNow);
    }

    public void Begin(string planId, string deviceId, long runtimeGeneration, string documentId, SceneState baseline)
    {
        if (new[] { planId, deviceId, documentId }.Any(string.IsNullOrWhiteSpace) || runtimeGeneration < 1)
            throw new InvalidDataException("scene_journal_binding_invalid");
        lock (_gate)
        {
            var records = ReadUnsafe().Where(item => item.CreatedAt >= _clock() - _retention).ToList();
            var sequence = records.Count == 0 ? 1 : checked(records.Max(item => item.Sequence) + 1);
            records.Add(new(sequence, planId, deviceId, runtimeGeneration, documentId, baseline, "pending", _clock()));
            if (records.Count > _maxRecords) throw new InvalidDataException("scene_journal_record_limit");
            WriteUnsafe(records);
        }
    }

    public SceneRecoveryRecord RequirePending(string planId, string deviceId, long generation, string documentId)
    {
        lock (_gate)
        {
            var record = ReadUnsafe().LastOrDefault(item => item.PlanId == planId && item.State == "pending")
                ?? throw new InvalidDataException("scene_recovery_not_found");
            if (record.DeviceId != deviceId || record.RuntimeGeneration != generation || record.DocumentId != documentId)
                throw new InvalidDataException("scene_journal_binding_invalid");
            return record;
        }
    }

    public void Complete(string planId)
    {
        lock (_gate)
        {
            var records = ReadUnsafe();
            if (!records.Any(item => item.PlanId == planId && item.State == "pending"))
                throw new InvalidDataException("scene_recovery_not_found");
            WriteUnsafe(records.Where(item => item.PlanId != planId).ToList());
        }
    }

    public IReadOnlyList<SceneRecoveryRecord> Pending()
    {
        lock (_gate)
            return ReadUnsafe().Where(item => item.State == "pending" && item.CreatedAt >= _clock() - _retention).ToArray();
    }

    private List<SceneRecoveryRecord> ReadUnsafe()
    {
        if (!File.Exists(_path)) return [];
        var cipher = File.ReadAllBytes(_path);
        if (cipher.LongLength > _maxBytes) throw new InvalidDataException("scene_journal_byte_limit");
        var clear = ProtectedData.Unprotect(cipher, Entropy, DataProtectionScope.CurrentUser);
        try { return JsonSerializer.Deserialize<List<SceneRecoveryRecord>>(clear) ?? []; }
        finally { CryptographicOperations.ZeroMemory(clear); }
    }

    private void WriteUnsafe(List<SceneRecoveryRecord> records)
    {
        var clear = JsonSerializer.SerializeToUtf8Bytes(records);
        try
        {
            var cipher = ProtectedData.Protect(clear, Entropy, DataProtectionScope.CurrentUser);
            if (cipher.LongLength > _maxBytes) throw new InvalidDataException("scene_journal_byte_limit");
            Directory.CreateDirectory(Path.GetDirectoryName(_path)!);
            var temporary = _path + ".tmp";
            File.WriteAllBytes(temporary, cipher);
            File.Move(temporary, _path, true);
        }
        finally { CryptographicOperations.ZeroMemory(clear); }
    }
}
