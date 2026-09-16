using System.Text.Json;
using Ai00.Connector.Adapters.VisMockup;
using Ai00.Connector.Contracts;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class TeamcenterReadOnlyRuntimeTests
{
    private static readonly double[] Identity =
        [1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1];

    [Fact]
    public async Task Observe_preserves_duplicate_product_references_as_distinct_occurrences()
    {
        var worker = new RecordingTeamcenterWorker
        {
            Nodes =
            [
                new("root", null, 0, 0, "Root", "i", "A", "r", "01", "Assembly", "u", "g", Identity, null, []),
                new("left", "root", 1, 0, "Same", "p", "P", "same", "01", "Part", "u", "g", Identity, null, []),
                new("right", "root", 1, 1, "Same", "p", "P", "same", "01", "Part", "u", "g", Identity, null, []),
            ]
        };
        using var runtime = new TeamcenterReadOnlyRuntime(worker, Path.GetTempFileName());
        await runtime.LoginAsync("tc-production", "user", "secret", CancellationToken.None);
        using var payload = JsonDocument.Parse("""{"source_selector":{"endpoint_id":"tc-production","object_uid":"obj","item_revision_uid":"rev","bom_view_uid":"view","revision_rule":"Latest Working","configuration_date":"2026-09-16T00:00:00Z"},"max_nodes":100,"max_depth":20,"property_projection":"simulation-default-v1"}""");

        var observed = Assert.IsType<TeamcenterObservationResult>(await runtime.ObserveAsync(payload.RootElement, CancellationToken.None));
        var page = await runtime.ReadPageAsync(observed.ObservationId, 0, 100, CancellationToken.None);

        Assert.Equal(3, page.Nodes.Count);
        Assert.Equal(new[] { "left", "right" }, page.Nodes.Skip(1).Select(item => item.OccurrenceId));
        Assert.All(page.Nodes.Skip(1), item => Assert.Equal("same", item.ItemRevisionUid));
    }

    [Fact]
    public async Task Credentials_are_not_arguments_environment_or_cache_content()
    {
        var worker = new RecordingTeamcenterWorker();
        var cache = Path.GetTempFileName();
        using (var runtime = new TeamcenterReadOnlyRuntime(worker, cache))
            await runtime.LoginAsync("tc-production", "user", "secret-value", CancellationToken.None);

        Assert.Equal("secret-value", worker.PasswordSeen);
        Assert.DoesNotContain("secret-value", await File.ReadAllTextAsync(cache));
        var start = TeamcenterProcessWorker.CreateStartInfo("C:/openjre11/bin/java.exe", "C:/worker.js", ["C:/a.jar"]);
        Assert.DoesNotContain("secret", string.Join(" ", start.ArgumentList));
        Assert.DoesNotContain(start.Environment, item => item.Value?.Contains("secret", StringComparison.Ordinal) == true);
        Assert.True(start.RedirectStandardInput);
        Assert.False(start.UseShellExecute);
    }

    [Fact]
    public async Task Login_status_is_retained_in_memory_until_logout()
    {
        using var runtime = new TeamcenterReadOnlyRuntime(new RecordingTeamcenterWorker(), Path.GetTempFileName());

        Assert.Equal(new TeamcenterSessionStatus("logged_out", ""), runtime.GetSessionStatus());
        await runtime.LoginAsync("tc-production", "user", "secret", CancellationToken.None);
        Assert.Equal(new TeamcenterSessionStatus("ready", "u***r"), runtime.GetSessionStatus());

        await runtime.LogoutAsync(CancellationToken.None);

        Assert.Equal(new TeamcenterSessionStatus("logged_out", ""), runtime.GetSessionStatus());
        using var payload = JsonDocument.Parse("""{"endpoint_id":"tc-production","item_id":"A","revision_id":"01","revision_rule":"Latest Working","configuration_date":"2026-09-16T00:00:00Z"}""");
        var error = await Assert.ThrowsAsync<ConnectorException>(
            () => runtime.SearchAsync(payload.RootElement, CancellationToken.None));
        Assert.Equal("teamcenter_login_required", error.Message);
    }

    [Fact]
    public void Policy_has_no_generic_or_persistent_write_operation()
    {
        Assert.Equal(new[] { "status", "revision_rules", "search", "observe", "launch" }, TeamcenterReadOnlyPolicy.WorkerCommands);
        Assert.Contains("executeSavedQueries", TeamcenterReadOnlyPolicy.AllowedServiceTokens);
        Assert.DoesNotContain(TeamcenterReadOnlyPolicy.ForbiddenServiceTokens,
            token => TeamcenterReadOnlyPolicy.AllowedServiceTokens.Contains(token));
    }

    [Fact]
    public async Task Revision_rules_prefer_latest_working_and_remove_duplicates()
    {
        var worker = new RecordingTeamcenterWorker
        {
            RevisionRules = ["Released", "Latest Working", "Released", ""]
        };
        using var runtime = new TeamcenterReadOnlyRuntime(worker, Path.GetTempFileName());
        await runtime.LoginAsync("tc-production", "user", "secret", CancellationToken.None);
        using var payload = JsonDocument.Parse("""{"endpoint_id":"tc-production"}""");

        var result = Assert.IsType<TeamcenterRevisionRulesResult>(
            await runtime.GetRevisionRulesAsync(payload.RootElement, CancellationToken.None));

        Assert.Equal(["Latest Working", "Released"], result.Rules);
    }

    [Fact]
    public async Task Search_v2_ranks_exact_prefix_contains_then_name_and_keeps_revision_exact()
    {
        var worker = new RecordingTeamcenterWorker
        {
            SearchItems =
            [
                SearchItem("X-100", "01", "Target in name"),
                SearchItem("A-TARGET-Z", "01", "Contains"),
                SearchItem("TARGET-200", "01", "Prefix"),
                SearchItem("TARGET", "01", "Exact"),
                SearchItem("TARGET", "02", "Wrong revision"),
            ]
        };
        using var runtime = new TeamcenterReadOnlyRuntime(worker, Path.GetTempFileName());
        await runtime.LoginAsync("tc-production", "user", "secret", CancellationToken.None);
        using var payload = JsonDocument.Parse("""{"endpoint_id":"tc-production","query":"target","revision_id":"01","revision_rule":"Latest Working","configuration_date":"2026-09-16T00:00:00Z","limit":20}""");

        var result = Assert.IsType<TeamcenterProductSearchResult>(
            await runtime.SearchV2Async(payload.RootElement, CancellationToken.None));

        Assert.Equal(["TARGET", "TARGET-200", "A-TARGET-Z", "X-100"], result.Items.Select(item => item.ItemId));
        Assert.All(result.Items, item => Assert.Equal("01", item.RevisionId));
    }

    private static TeamcenterProductSearchItem SearchItem(string itemId, string revision, string name) =>
        new(name, itemId, revision, "ItemRevision", "user", "group",
            new("tc-production", "item-" + itemId, "rev-" + itemId + "-" + revision, "", "Latest Working", "2026-09-16T00:00:00Z"));

    [Fact]
    public void Visualization_compatibility_asset_is_hash_pinned_and_materializes_only_known_classes()
    {
        var asset = Path.Combine(AppContext.BaseDirectory, "teamcenter_visualization_compat.json");
        var root = Path.Combine(Path.GetTempPath(), "ai00-tc-compat-" + Guid.NewGuid().ToString("N"));
        try
        {
            var classpath = TeamcenterReadOnlyRuntime.PrepareVisualizationCompatibility(asset, root);
            var files = Directory.GetFiles(classpath, "*.class", SearchOption.AllDirectories);
            Assert.Equal(4, files.Length);
            Assert.All(files, file => Assert.EndsWith(".class", file));
        }
        finally { if (Directory.Exists(root)) Directory.Delete(root, true); }
    }

    [Fact]
    public void Worker_search_uses_saved_query_wildcards_without_semantic_or_typo_expansion()
    {
        var script = File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "teamcenter_readonly_worker.js"));

        Assert.Contains("SavedQueryService", script);
        Assert.Contains("__Item_Revision_name_ID_and_rev", script);
        Assert.Contains("items_tag.item_id", script);
        Assert.Contains("'*'+query+'*'", script.Replace(" ", ""));
        Assert.DoesNotContain("levenshtein", script, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("semantic", script, StringComparison.OrdinalIgnoreCase);
    }

    private sealed class RecordingTeamcenterWorker : ITeamcenterWorker
    {
        public string PasswordSeen { get; private set; } = "";
        public IReadOnlyList<string> RevisionRules { get; init; } = ["Latest Working"];
        public IReadOnlyList<TeamcenterProductSearchItem> SearchItems { get; init; } = [];
        public IReadOnlyList<TeamcenterOccurrence> Nodes { get; init; } =
        [new("root", null, 0, 0, "Root", "i", "A", "r", "01", "Assembly", "u", "g", Identity, null, [])];
        public Task ValidateCredentialsAsync(string endpointId, string username, string password, CancellationToken ct)
        { PasswordSeen = password; return Task.CompletedTask; }
        public Task<IReadOnlyList<string>> GetRevisionRulesAsync(string username, string password, CancellationToken ct)
        { PasswordSeen = password; return Task.FromResult(RevisionRules); }
        public Task<TeamcenterProductSearchResult> SearchAsync(string itemId, string revisionId, string revisionRule, string configurationDate, string username, string password, CancellationToken ct)
        { PasswordSeen = password; return Task.FromResult(new TeamcenterProductSearchResult(SearchItems)); }
        public Task<IReadOnlyList<TeamcenterOccurrence>> ObserveAsync(TeamcenterSourceSelector selector, int maxNodes, int maxDepth, string propertyProjection, string username, string password, CancellationToken ct)
        { PasswordSeen = password; return Task.FromResult(Nodes); }
        public Task<TeamcenterLaunchResult> LaunchAsync(TeamcenterSourceSelector selector, string expectedVisdocUid, string username, string password, CancellationToken ct)
        { PasswordSeen = password; return Task.FromResult(new TeamcenterLaunchResult("tclaunch:" + new string('a', 64), true, expectedVisdocUid, selector.IdentityHash)); }
        public Task<TeamcenterLaunchResult> ConsumeVisualizationAsync(TeamcenterSourceSelector selector, string expectedVisdocUid, Func<string, CancellationToken, Task> consumer, string username, string password, CancellationToken ct)
        { PasswordSeen = password; return Task.FromResult(new TeamcenterLaunchResult("tclaunch:" + new string('a', 64), true, expectedVisdocUid, selector.IdentityHash)); }
    }
}
