using System.Text.Json;
using Ai00.Connector.AppHost;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class AppPlanJournalTests
{
    [Fact]
    public void Appends_events_without_rewriting_existing_snapshot()
    {
        var root = Path.Combine(Path.GetTempPath(), "ai00-app-journal-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            var path = Path.Combine(root, "journal");
            var original = new[] { new AppJournalEvent(1, "legacy", "plan-1", "{}") };
            File.WriteAllText(path, JsonSerializer.Serialize(original));
            var before = File.ReadAllBytes(path);

            var journal = new AppPlanJournal(path);
            journal.Append("outcome", "plan-2", "{}");

            Assert.Equal(before, File.ReadAllBytes(path));
            Assert.Equal(new[] { "legacy", "outcome" }, new AppPlanJournal(path).Events.Select(item => item.Kind));
        }
        finally
        {
            Directory.Delete(root, true);
        }
    }
}
