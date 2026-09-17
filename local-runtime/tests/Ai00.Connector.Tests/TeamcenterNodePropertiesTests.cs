using System.Text.Json;
using Ai00.Connector.Adapters.VisMockup;
using Ai00.Connector.Contracts;
using Microsoft.Data.Sqlite;
using Xunit;

namespace Ai00.Connector.Tests;

public class TeamcenterNodePropertiesTests
{
    private static readonly TeamcenterOccurrenceEdge[] ChildPath = [new("occ-1", "rev-child")];

    private static JsonElement Input(
        TeamcenterOccurrenceEdge[]? path = null,
        string rule = "Latest Working",
        object? extra = null)
    {
        var selector = new TeamcenterSourceSelector(
            "tc-production", "obj", "rev-root", "", rule, "2026-09-17T00:00:00Z");
        return extra is null
            ? JsonSerializer.SerializeToElement(new { source_selector = selector, occurrence_path = path ?? ChildPath })
            : JsonSerializer.SerializeToElement(new { source_selector = selector, occurrence_path = path ?? ChildPath, extra });
    }

    [Fact]
    public async Task Adapter_dispatch_returns_exact_contract_and_output_shape()
    {
        using var runtime = new TeamcenterReadOnlyRuntime(new PropertyWorker(), Path.GetTempFileName());
        await runtime.LoginAsync("tc-production", "u", "secret", default);
        using var sta = new StaDispatcher();
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([Path.GetTempPath()]),
            new FakeVisMockupCom(), Path.GetTempPath(), Path.GetTempFileName(), runtime);
        var contract = JsonDocument.Parse(File.ReadAllText(
            Path.Combine(AppContext.BaseDirectory, "teamcenter.node_properties.read@1.json"))).RootElement;
        Assert.True(adapter.Manifest.Supports(
            "teamcenter.node_properties.read@1", CanonicalJson.Hash(contract)));

        var result = await adapter.ExecuteAsync(
            new AdapterOperation("teamcenter.node_properties.read@1", Input()), default);

        Assert.True(result.Ok);
        var value = Assert.IsType<TeamcenterNodePropertiesResult>(result.Data);
        Assert.Equal(new[] { "cache_hit", "captured_at", "properties", "source_identity_hash" },
            JsonSerializer.SerializeToElement(value).EnumerateObject().Select(item => item.Name).Order());
        Assert.Equal(new[] {
            "component_type", "item_id", "name", "occurrence_uid", "owning_group", "owning_user",
            "revision_id", "torque_importance", "torque_raw", "unit_weight_raw", "weight_raw",
        }, JsonSerializer.SerializeToElement(value.Properties).EnumerateObject().Select(item => item.Name).Order());
    }

    [Fact]
    public async Task Repeated_read_uses_principal_scoped_sqlite_cache_without_worker()
    {
        var cache = Path.GetTempFileName();
        var worker = new PropertyWorker();
        using var runtime = new TeamcenterReadOnlyRuntime(worker, cache);
        await runtime.LoginAsync("tc-production", "u", "secret", default);

        var first = Assert.IsType<TeamcenterNodePropertiesResult>(
            await runtime.ReadNodePropertiesAsync(Input(), default));
        worker.FailIfCalled = true;
        var second = Assert.IsType<TeamcenterNodePropertiesResult>(
            await runtime.ReadNodePropertiesAsync(Input(), default));

        Assert.False(first.CacheHit);
        Assert.True(second.CacheHit);
        Assert.Equal(first.Properties, second.Properties);
        Assert.Equal(1, worker.Calls);
    }

    [Fact]
    public async Task Cache_partitions_principal_selector_and_occurrence_path()
    {
        var worker = new PropertyWorker();
        using var runtime = new TeamcenterReadOnlyRuntime(worker, Path.GetTempFileName());
        await runtime.LoginAsync("tc-production", "u", "secret", default);

        await runtime.ReadNodePropertiesAsync(Input(), default);
        await runtime.ReadNodePropertiesAsync(Input(rule: "Released"), default);
        await runtime.ReadNodePropertiesAsync(Input([new("occ-2", "rev-child")]), default);
        await runtime.LoginAsync("tc-production", "other", "secret", default);
        await runtime.ReadNodePropertiesAsync(Input(), default);

        Assert.Equal(4, worker.Calls);
    }

    [Fact]
    public async Task Restart_requires_login_then_reuses_cache_for_same_principal()
    {
        var cache = Path.GetTempFileName();
        var worker = new PropertyWorker();
        using (var first = new TeamcenterReadOnlyRuntime(worker, cache))
        {
            await first.LoginAsync("tc-production", "u", "secret", default);
            await first.ReadNodePropertiesAsync(Input(), default);
        }

        using var reopened = new TeamcenterReadOnlyRuntime(worker, cache);
        Assert.Equal("teamcenter_login_required", (await Assert.ThrowsAsync<ConnectorException>(
            () => reopened.ReadNodePropertiesAsync(Input(), default))).Message);
        await reopened.LoginAsync("tc-production", "u", "changed", default);
        var cached = Assert.IsType<TeamcenterNodePropertiesResult>(
            await reopened.ReadNodePropertiesAsync(Input(), default));
        Assert.True(cached.CacheHit);
        Assert.Equal(1, worker.Calls);
    }

    [Fact]
    public async Task Input_is_closed_and_occurrence_path_is_bounded()
    {
        using var runtime = new TeamcenterReadOnlyRuntime(new PropertyWorker(), Path.GetTempFileName());
        await runtime.LoginAsync("tc-production", "u", "secret", default);

        Assert.Equal("teamcenter_input_invalid", (await Assert.ThrowsAsync<ConnectorException>(
            () => runtime.ReadNodePropertiesAsync(Input(extra: true), default))).Message);
        Assert.Equal("teamcenter_node_properties_input_invalid", (await Assert.ThrowsAsync<ConnectorException>(
            () => runtime.ReadNodePropertiesAsync(Input(Enumerable.Repeat(new TeamcenterOccurrenceEdge("o", "r"), 129).ToArray()), default))).Message);
        Assert.Equal("teamcenter_node_properties_input_invalid", (await Assert.ThrowsAsync<ConnectorException>(
            () => runtime.ReadNodePropertiesAsync(Input([new(new string('o', 129), "r")]), default))).Message);
        Assert.Equal("teamcenter_node_properties_input_invalid", (await Assert.ThrowsAsync<ConnectorException>(
            () => runtime.ReadNodePropertiesAsync(Input([new("o", "")]), default))).Message);
    }

    [Fact]
    public async Task Cache_payload_must_be_closed_complete_and_match_occurrence_path()
    {
        var invalidPayloads = new[]
        {
            "{",
            JsonSerializer.Serialize(new { name = "Child" }),
            JsonSerializer.Serialize(new {
                name = "Child", item_id = "W10-ENG00001", revision_id = "00;1", component_type = "Part",
                owning_user = "owner", owning_group = "group", weight_raw = "12.5", unit_weight_raw = "kg",
                torque_raw = "9", torque_importance = "high", occurrence_uid = "occ-1", extra = true,
            }),
            JsonSerializer.Serialize(new {
                name = "Child", item_id = "W10-ENG00001", revision_id = "00;1", component_type = "Part",
                owning_user = "owner", owning_group = "group", weight_raw = "12.5", unit_weight_raw = "kg",
                torque_raw = "9", torque_importance = "high", occurrence_uid = "other-occurrence",
            }),
        };

        foreach (var payloadJson in invalidPayloads)
        {
            var cache = Path.GetTempFileName();
            var worker = new PropertyWorker();
            using var runtime = new TeamcenterReadOnlyRuntime(worker, cache);
            await runtime.LoginAsync("tc-production", "u", "secret", default);
            await runtime.ReadNodePropertiesAsync(Input(), default);
            using (var connection = new SqliteConnection($"Data Source={cache};Pooling=False"))
            {
                connection.Open();
                using var corrupt = connection.CreateCommand();
                corrupt.CommandText = "UPDATE tc_node_property_cache SET payload_json = $payload";
                corrupt.Parameters.AddWithValue("$payload", payloadJson);
                Assert.Equal(1, corrupt.ExecuteNonQuery());
            }
            worker.FailIfCalled = true;

            Assert.Equal("teamcenter_node_properties_cache_invalid", (await Assert.ThrowsAsync<ConnectorException>(
                () => runtime.ReadNodePropertiesAsync(Input(), default))).Message);
            Assert.Equal(1, worker.Calls);
        }
    }

    [Fact]
    public async Task Worker_source_identity_must_match_exact_selector()
    {
        var worker = new PropertyWorker { SourceIdentityHash = "sha256:wrong" };
        using var runtime = new TeamcenterReadOnlyRuntime(worker, Path.GetTempFileName());
        await runtime.LoginAsync("tc-production", "u", "secret", default);

        Assert.Equal("teamcenter_worker_response_invalid", (await Assert.ThrowsAsync<ConnectorException>(
            () => runtime.ReadNodePropertiesAsync(Input(), default))).Message);
    }

    private sealed class PropertyWorker : ITeamcenterWorker
    {
        public int Calls;
        public bool FailIfCalled;
        public string? SourceIdentityHash;

        public Task<TeamcenterNodePropertiesResult> ReadNodePropertiesAsync(
            TeamcenterSourceSelector selector, TeamcenterOccurrenceEdge[] path,
            string username, string password, CancellationToken ct)
        {
            Calls++;
            if (FailIfCalled) throw new InvalidOperationException("worker_must_not_run");
            var properties = new TeamcenterNodeProperties(
                "Child", "W10-ENG00001", "00;1", "Part", "owner", "group",
                "12.5", "kg", "9", "high", path.LastOrDefault()?.OccurrenceUid);
            return Task.FromResult(new TeamcenterNodePropertiesResult(
                SourceIdentityHash ?? selector.IdentityHash, DateTimeOffset.UtcNow, false, properties));
        }

        public Task ValidateCredentialsAsync(string e, string u, string p, CancellationToken ct) => Task.CompletedTask;
        public Task<IReadOnlyList<string>> GetRevisionRulesAsync(string u, string p, CancellationToken ct) => throw new NotSupportedException();
        public Task<TeamcenterProductSearchResult> SearchAsync(string i, string r, string rule, string d, string u, string p, CancellationToken ct) => throw new NotSupportedException();
        public Task<IReadOnlyList<TeamcenterOccurrence>> ObserveAsync(TeamcenterSourceSelector s, int n, int d, string projection, string u, string p, CancellationToken ct) => throw new NotSupportedException();
        public Task<TeamcenterLaunchResult> LaunchAsync(TeamcenterSourceSelector s, string expected, string u, string p, CancellationToken ct) => throw new NotSupportedException();
        public Task<TeamcenterLaunchResult> ConsumeVisualizationAsync(TeamcenterSourceSelector s, string expected, string operation, Func<string, CancellationToken, Task> consumer, string u, string p, CancellationToken ct) => throw new NotSupportedException();
    }
}
