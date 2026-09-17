using System.Security.AccessControl;
using System.Security.Principal;
using Ai00.Connector.Adapters.VisMockup;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class TeamcenterWorkerContractTests
{
    [Fact]
    public void Search_uses_exact_id_then_batched_contains_fallback()
    {
        var script = File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "teamcenter_readonly_worker.js"));
        var stages = new[] {
            "executeBatch([['items_tag.item_id',query]]);",
            "['items_tag.item_id','*'+query+'*']",
            "['object_name','*'+query+'*']",
        };
        var previous = -1;
        foreach (var stage in stages)
        {
            var current = script.IndexOf(stage, StringComparison.Ordinal);
            Assert.True(current > previous, $"missing or unordered query stage: {stage}");
            previous = current;
        }
        Assert.Contains("if(!ordered.length)executeBatch", script);
        Assert.Contains("executeSavedQueries(Java.to(inputs", script);
        Assert.DoesNotContain("entries.push(queryEntry('item_revision_id'))", script);
        Assert.Contains("display(revision,'item_revision_id')===revisionId", script);
        Assert.Contains("dmSearch.getProperties(Java.to(itemValues", script);
        Assert.Contains("teamcenter_session_expired", script);
        Assert.Contains("teamcenter_authentication_failed", script);
        Assert.Contains("maxNumToReturn=5001", script.Replace(" ", ""));
        Assert.Contains("objects.length>5000", script.Replace(" ", ""));
        Assert.Contains("teamcenter_search_too_broad", script);
    }

    [Fact]
    public void Visualization_material_directory_inherits_only_current_user_access()
    {
        if (!OperatingSystem.IsWindows()) return;
        var root = Path.Combine(Path.GetTempPath(), "ai00-tc-material-" + Guid.NewGuid().ToString("N"));
        try
        {
            TeamcenterProcessWorker.SecureVisualizationMaterialRoot(root);
            var sid = WindowsIdentity.GetCurrent().User!;
            var rules = new DirectoryInfo(root).GetAccessControl().GetAccessRules(true, true, typeof(SecurityIdentifier));
            Assert.NotEmpty(rules.Cast<FileSystemAccessRule>());
            Assert.All(rules.Cast<FileSystemAccessRule>(), rule => Assert.Equal(sid, rule.IdentityReference));
            Assert.True(new DirectoryInfo(root).GetAccessControl().AreAccessRulesProtected);
        }
        finally { if (Directory.Exists(root)) Directory.Delete(root, true); }
    }

}
