using System.Text.Json;
using Ai00.Connector.AppHost;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class AppPlanJournalTests
{
    [Fact]
    public void Appending_reads_only_new_tail_and_preserves_other_instances_events()
    {
        var root=Path.Combine(Path.GetTempPath(),"ai00-journal-tail-"+Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            var path=Path.Combine(root,"journal");
            var first=new AppPlanJournal(path);
            first.Append("outcome","old","cached history");
            var second=new AppPlanJournal(path);
            var prefixLength=new FileInfo(path+".events").Length;
            // A validated immutable prefix must never be read again on an append.
            // Windows byte-range locks make this an I/O regression check, not a timing guess.
            using(var prefix=new FileStream(path+".events",FileMode.Open,FileAccess.Read,FileShare.ReadWrite))
            {
                prefix.Lock(0,prefixLength);
                try
                {
                    first.Append("outcome","first","one");
                    second.Append("outcome","second","two");
                    first.Append("acknowledged","second","three");
                }
                finally{prefix.Unlock(0,prefixLength);}
            }
            Assert.Equal(new[]{"old","first","second","second"},new AppPlanJournal(path).Events.Select(e=>e.PlanId));
            Assert.Equal(new long[]{1,2,3,4},first.Events.Select(e=>e.Sequence));
        }
        finally{Directory.Delete(root,true);}
    }

    [Fact]
    public void Truncated_tail_is_rejected_before_another_event_is_written()
    {
        var root=Path.Combine(Path.GetTempPath(),"ai00-journal-truncate-"+Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            var path=Path.Combine(root,"journal");var journal=new AppPlanJournal(path);
            journal.Append("outcome","first","{}");
            File.WriteAllText(path+".events","");
            Assert.Throws<InvalidDataException>(()=>journal.Append("outcome","second","{}"));
            Assert.Empty(File.ReadAllText(path+".events"));
        }
        finally{Directory.Delete(root,true);}
    }

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
