using Ai00.Connector.Adapters.VisMockup;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class SceneRecoveryJournalTests : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), "ai00-scene-journal-" + Guid.NewGuid().ToString("N"));
    private static readonly DateTimeOffset Now = new(2026, 9, 9, 8, 0, 0, TimeSpan.Zero);
    private static SceneState Scene(string id = "before") => SceneState.Create(id, ["part-1"], ["tool-1"], new("png", 1280, 720, "current"));

    [Fact]
    public void PendingSceneIsEncryptedDurableAndBoundToDeviceGenerationPlanAndDocument()
    {
        var path = Path.Combine(_root, "scene.journal");
        var journal = new SceneRecoveryJournal(path, clock: () => Now);
        journal.Begin("plan-1", "device-1", 7, "doc-1", Scene());
        Assert.DoesNotContain("part-1", File.ReadAllText(path));

        var reopened = new SceneRecoveryJournal(path, clock: () => Now);
        Assert.Equal("before", reopened.RequirePending("plan-1", "device-1", 7, "doc-1").Baseline.OperationId);
        Assert.Throws<InvalidDataException>(() => reopened.RequirePending("plan-1", "device-1", 8, "doc-1"));
        Assert.Throws<InvalidDataException>(() => reopened.RequirePending("plan-1", "device-1", 7, "other-doc"));
    }

    [Fact]
    public void TerminalCompletionRemovesRecoveryMaterial()
    {
        var journal = new SceneRecoveryJournal(Path.Combine(_root, "scene.journal"), clock: () => Now);
        journal.Begin("plan-1", "device-1", 1, "doc-1", Scene());
        journal.Complete("plan-1");
        Assert.Empty(journal.Pending());
    }

    [Fact]
    public void RecordAndByteQuotasAreEnforcedAndExpiredRecordsAreNotRecovered()
    {
        var path = Path.Combine(_root, "scene.journal");
        var clock = Now;
        var journal = new SceneRecoveryJournal(path, maxRecords: 1, clock: () => clock);
        journal.Begin("plan-1", "device-1", 1, "doc-1", Scene());
        Assert.Throws<InvalidDataException>(() => journal.Begin("plan-2", "device-1", 1, "doc-1", Scene("other")));
        clock = Now.AddDays(8);
        Assert.Empty(journal.Pending());

        var tiny = new SceneRecoveryJournal(Path.Combine(_root, "tiny.journal"), maxBytes: 20, clock: () => Now);
        Assert.Throws<InvalidDataException>(() => tiny.Begin("plan-1", "device-1", 1, "doc-1", Scene()));
    }

    public void Dispose()
    {
        if (Directory.Exists(_root)) Directory.Delete(_root, true);
    }
}
