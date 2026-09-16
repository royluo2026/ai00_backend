using System.Diagnostics;
using System.Security.Cryptography;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.Encodings.Web;
using Ai00.Connector.Contracts;
using Microsoft.Data.Sqlite;

namespace Ai00.Connector.Adapters.VisMockup;

public static class TeamcenterReadOnlyPolicy
{
    public static readonly string[] WorkerCommands = ["status", "revision_rules", "search", "observe", "launch"];
    public static readonly string[] AllowedServiceTokens =
        ["login", "logout", "loadObjects", "getItemFromId", "getProperties", "getRevisionRules", "getSavedQueries", "executeSavedQueries", "createBOMWindows", "expandPSAllLevels", "closeBOMWindows", "expandGRMRelationsForPrimary", "createLaunchInfo"];
    public static readonly string[] ForbiddenServiceTokens =
        ["setProperties", "saveBOMWindows", "createObjects", "deleteObjects", "setDatasetFile", "getFileWriteTickets", "commitDatasetFiles"];
}

public sealed record TeamcenterSourceSelector(
    [property: JsonPropertyName("endpoint_id")] string EndpointId,
    [property: JsonPropertyName("object_uid")] string ObjectUid,
    [property: JsonPropertyName("item_revision_uid")] string ItemRevisionUid,
    [property: JsonPropertyName("bom_view_uid")] string BomViewUid,
    [property: JsonPropertyName("revision_rule")] string RevisionRule,
    [property: JsonPropertyName("configuration_date")] string ConfigurationDate)
{
    [JsonIgnore] public string IdentityHash
    {
        get
        {
            var canonical = JsonSerializer.Serialize(new SortedDictionary<string, string>(StringComparer.Ordinal) {
                ["bom_view_uid"] = BomViewUid, ["configuration_date"] = ConfigurationDate,
                ["endpoint_id"] = EndpointId, ["item_revision_uid"] = ItemRevisionUid,
                ["object_uid"] = ObjectUid, ["revision_rule"] = RevisionRule,
            }, new JsonSerializerOptions { Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping });
            return "sha256:" + Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(canonical))).ToLowerInvariant();
        }
    }
}

public sealed record TeamcenterGeometryReference(
    [property: JsonPropertyName("dataset_uid")] string DatasetUid,
    [property: JsonPropertyName("file_uid")] string FileUid,
    [property: JsonPropertyName("file_name")] string FileName,
    [property: JsonPropertyName("relation_type")] string RelationType);

public sealed record TeamcenterOccurrence(
    [property: JsonPropertyName("occurrence_id")] string OccurrenceId,
    [property: JsonPropertyName("parent_occurrence_id")] string? ParentOccurrenceId,
    [property: JsonPropertyName("depth")] int Depth,
    [property: JsonPropertyName("child_order")] int ChildOrder,
    [property: JsonPropertyName("name")] string Name,
    [property: JsonPropertyName("item_uid")] string ItemUid,
    [property: JsonPropertyName("item_id")] string ItemId,
    [property: JsonPropertyName("item_revision_uid")] string ItemRevisionUid,
    [property: JsonPropertyName("revision_id")] string RevisionId,
    [property: JsonPropertyName("component_type")] string ComponentType,
    [property: JsonPropertyName("owning_user")] string OwningUser,
    [property: JsonPropertyName("owning_group")] string OwningGroup,
    [property: JsonPropertyName("transform")] double[]? Transform,
    [property: JsonPropertyName("bbox")] double[]? Bbox,
    [property: JsonPropertyName("geometry_refs")] TeamcenterGeometryReference[] GeometryRefs,
    [property: JsonPropertyName("absolute_transform")] double[]? AbsoluteTransform = null,
    [property: JsonPropertyName("transform_unit")] string TransformUnit = "m",
    [property: JsonPropertyName("transform_convention")] string TransformConvention = "teamcenter_plmxml_4x4_row_major",
    [property: JsonPropertyName("bbox_unit")] string BboxUnit = "m",
    [property: JsonPropertyName("torque_raw")] string? TorqueRaw = null,
    [property: JsonPropertyName("torque_importance")] string? TorqueImportance = null,
    [property: JsonPropertyName("weight_raw")] string? WeightRaw = null,
    [property: JsonPropertyName("unit_weight_raw")] string? UnitWeightRaw = null);

public sealed record TeamcenterObservationResult(
    [property: JsonPropertyName("observation_id")] string ObservationId,
    [property: JsonPropertyName("source_identity_hash")] string SourceIdentityHash,
    [property: JsonPropertyName("captured_at")] DateTimeOffset CapturedAt,
    [property: JsonPropertyName("node_count")] int NodeCount,
    [property: JsonPropertyName("page_count")] int PageCount,
    [property: JsonPropertyName("complete")] bool Complete);

public sealed record TeamcenterObservationPage(
    [property: JsonPropertyName("observation_id")] string ObservationId,
    [property: JsonPropertyName("cursor")] int Cursor,
    [property: JsonPropertyName("next_cursor")] int? NextCursor,
    [property: JsonPropertyName("nodes")] IReadOnlyList<TeamcenterOccurrence> Nodes,
    [property: JsonPropertyName("page_hash")] string PageHash);

public sealed record TeamcenterLaunchResult(
    [property: JsonPropertyName("launch_id")] string LaunchId,
    [property: JsonPropertyName("runner_started")] bool RunnerStarted,
    [property: JsonPropertyName("expected_visdoc_uid")] string ExpectedVisdocUid,
    [property: JsonPropertyName("source_identity_hash")] string SourceIdentityHash);

public sealed record TeamcenterProductSearchItem(
    [property: JsonPropertyName("display_name")] string DisplayName,
    [property: JsonPropertyName("item_id")] string ItemId,
    [property: JsonPropertyName("revision_id")] string RevisionId,
    [property: JsonPropertyName("component_type")] string ComponentType,
    [property: JsonPropertyName("owning_user")] string OwningUser,
    [property: JsonPropertyName("owning_group")] string OwningGroup,
    [property: JsonPropertyName("source_selector")] TeamcenterSourceSelector SourceSelector);
public sealed record TeamcenterProductSearchResult(
    [property: JsonPropertyName("items")] IReadOnlyList<TeamcenterProductSearchItem> Items);
public sealed record TeamcenterRevisionRulesResult(
    [property: JsonPropertyName("rules")] IReadOnlyList<string> Rules);
public sealed record TeamcenterSessionStatus(string State, string MaskedUsername);

public interface ITeamcenterWorker
{
    Task ValidateCredentialsAsync(string endpointId, string username, string password, CancellationToken ct);
    Task<IReadOnlyList<string>> GetRevisionRulesAsync(string username, string password, CancellationToken ct);
    Task<TeamcenterProductSearchResult> SearchAsync(string itemId, string revisionId,
        string revisionRule, string configurationDate, string username, string password, CancellationToken ct);
    Task<IReadOnlyList<TeamcenterOccurrence>> ObserveAsync(TeamcenterSourceSelector selector,
        int maxNodes, int maxDepth, string propertyProjection, string username, string password, CancellationToken ct);
    Task<TeamcenterLaunchResult> LaunchAsync(TeamcenterSourceSelector selector, string expectedVisdocUid,
        string username, string password, CancellationToken ct);
    Task<TeamcenterLaunchResult> ConsumeVisualizationAsync(TeamcenterSourceSelector selector, string expectedVisdocUid,
        Func<string, CancellationToken, Task> consumer, string username, string password, CancellationToken ct);
}

public sealed class TeamcenterReadOnlyRuntime : IDisposable
{
    private readonly ITeamcenterWorker worker;
    private readonly string connectionString;
    private readonly SemaphoreSlim gate = new(1, 1);
    private readonly object credentialState = new();
    private char[] username = [];
    private char[] password = [];
    private string endpointId = "";

    public TeamcenterReadOnlyRuntime(ITeamcenterWorker worker, string cachePath)
    {
        this.worker = worker;
        var fullPath = Path.GetFullPath(cachePath);
        Directory.CreateDirectory(Path.GetDirectoryName(fullPath)!);
        connectionString = new SqliteConnectionStringBuilder { DataSource = fullPath,
            Mode = SqliteOpenMode.ReadWriteCreate, Pooling = false }.ToString();
        Initialize();
    }

    public static TeamcenterReadOnlyRuntime CreateInstalled(string stateRoot)
    {
        var java = @"C:\openjre11\bin\java.exe";
        var script = Path.Combine(AppContext.BaseDirectory, "teamcenter_readonly_worker.js");
        var launcher = Path.Combine(AppContext.BaseDirectory, "teamcenter_visualization_launch.js");
        var compatibilityAsset = Path.Combine(AppContext.BaseDirectory, "teamcenter_visualization_compat.json");
        var lib = @"D:\Siemens\Teamcenter14\TCIC_V5\racless\lib";
        if (!File.Exists(java) || !File.Exists(script) || !File.Exists(launcher)
            || !File.Exists(compatibilityAsset) || !Directory.Exists(lib))
            return new TeamcenterReadOnlyRuntime(new UnavailableTeamcenterWorker(),
                Path.Combine(stateRoot, "teamcenter-structure-cache.db"));
        try
        {
            var compatibilityRoot = PrepareVisualizationCompatibility(compatibilityAsset, stateRoot);
            var jars = new[] { compatibilityRoot }.Concat(Directory.EnumerateFiles(lib, "*.jar")
                .Order(StringComparer.OrdinalIgnoreCase)).ToArray();
            var materialRoot = Path.Combine(stateRoot, "teamcenter-visualization");
            TeamcenterProcessWorker.SecureVisualizationMaterialRoot(materialRoot);
            return new TeamcenterReadOnlyRuntime(new TeamcenterProcessWorker(java, script, launcher, jars, materialRoot),
                Path.Combine(stateRoot, "teamcenter-structure-cache.db"));
        }
        catch
        {
            return new TeamcenterReadOnlyRuntime(new UnavailableTeamcenterWorker(),
                Path.Combine(stateRoot, "teamcenter-structure-cache.db"));
        }
    }

    internal static string PrepareVisualizationCompatibility(string assetPath, string stateRoot)
    {
        var expected = new Dictionary<string, string>(StringComparer.Ordinal) {
            ["DataManagement.class"] = "03dea67c1ff7beb9d44e6e8b1bcf75b6cabaabe6e395db489c5296a86d760910",
            ["DataManagement$IdInfo2.class"] = "0fd1b3c826057ceee27d3dbf3b3c583fa1e107f7b8082f7e82e3f071d068c256",
            ["DataManagement$LaunchInfoResponse.class"] = "eadb0eef047ee2cd03d4db6d4a8ad0080fff5cf0d63c73cc676fa26005f45baa",
            ["DataManagement$SessionInfo2.class"] = "4b200f5f0aa0c52f32dc78c047e028919d166abfaf9c8d30e473e13d8ccb92ba",
        };
        var values = JsonSerializer.Deserialize<Dictionary<string, string>>(File.ReadAllText(assetPath))
            ?? throw new InvalidDataException("teamcenter_compatibility_asset_invalid");
        if (!values.Keys.Order().SequenceEqual(expected.Keys.Order()))
            throw new InvalidDataException("teamcenter_compatibility_asset_invalid");
        var root = Path.Combine(Path.GetFullPath(stateRoot), "teamcenter-compatibility");
        var package = Path.Combine(root, "com", "teamcenter", "services", "rac", "visualization", "_2013_05");
        Directory.CreateDirectory(package);
        foreach (var (name, digest) in expected)
        {
            var bytes = Convert.FromBase64String(values[name]);
            var actual = Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
            if (actual != digest) throw new InvalidDataException("teamcenter_compatibility_asset_invalid");
            var target = Path.Combine(package, name);
            if (!File.Exists(target) || !CryptographicOperations.FixedTimeEquals(
                    SHA256.HashData(File.ReadAllBytes(target)), SHA256.HashData(bytes)))
                File.WriteAllBytes(target, bytes);
        }
        return root;
    }

    public async Task LoginAsync(string endpoint, string user, string secret, CancellationToken ct)
    {
        if (endpoint != "tc-production" || string.IsNullOrWhiteSpace(user) || string.IsNullOrEmpty(secret)
            || user.Length > 191 || secret.Length > 1024 || user.IndexOfAny(['\r','\n']) >= 0
            || secret.IndexOfAny(['\r','\n']) >= 0)
            throw new ConnectorException("teamcenter_credentials_invalid");
        await gate.WaitAsync(ct);
        try
        {
            await worker.ValidateCredentialsAsync(endpoint, user, secret, ct);
            lock (credentialState)
            {
                ClearCredentialsUnsafe();
                endpointId = endpoint; username = user.ToCharArray(); password = secret.ToCharArray();
            }
        }
        catch (ConnectorException error) when (InvalidatesSession(error))
        {
            ClearCredentials();
            throw;
        }
        finally { gate.Release(); }
    }

    public TeamcenterSessionStatus GetSessionStatus()
    {
        lock (credentialState)
        {
            if (username.Length == 0 || password.Length == 0) return new("logged_out", "");
            var user = new string(username);
            var masked = user.Length == 1 ? user + "***"
                : user.Length == 2 ? user[0] + "***" : user[0] + "***" + user[^1];
            return new("ready", masked);
        }
    }

    public async Task LogoutAsync(CancellationToken ct)
    {
        await gate.WaitAsync(ct);
        try { ClearCredentials(); }
        finally { gate.Release(); }
    }

    public async Task<object> ObserveAsync(JsonElement payload, CancellationToken ct)
    {
        Closed(payload, "source_selector", "max_nodes", "max_depth", "property_projection");
        var selector = ReadSelector(payload.GetProperty("source_selector"));
        var maxNodes = payload.GetProperty("max_nodes").GetInt32();
        var maxDepth = payload.GetProperty("max_depth").GetInt32();
        var projection = payload.GetProperty("property_projection").GetString() ?? "";
        if (maxNodes is < 1 or > 250_000 || maxDepth is < 1 or > 128
            || projection.Length is < 1 or > 64 || selector.EndpointId != endpointId)
            throw new ConnectorException("teamcenter_observe_input_invalid");
        var credentials = RequireCredentials();
        IReadOnlyList<TeamcenterOccurrence> nodes;
        await gate.WaitAsync(ct);
        try { nodes = await worker.ObserveAsync(selector, maxNodes, maxDepth, projection,
                credentials.User, credentials.Password, ct); }
        catch (ConnectorException error) when (InvalidatesSession(error)) { ClearCredentials(); throw; }
        finally { gate.Release(); }
        ValidateNodes(nodes, maxNodes, maxDepth);
        var captured = DateTimeOffset.UtcNow;
        var seed = selector.IdentityHash + "|" + captured.ToString("O") + "|" + Guid.NewGuid().ToString("N");
        var observationId = "tcobs:" + Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(seed))).ToLowerInvariant();
        WriteObservation(observationId, selector.IdentityHash, captured, nodes);
        return new TeamcenterObservationResult(observationId, selector.IdentityHash, captured,
            nodes.Count, (nodes.Count + 999) / 1000, true);
    }

    public async Task<object> SearchAsync(JsonElement payload, CancellationToken ct)
    {
        Closed(payload, "endpoint_id", "item_id", "revision_id", "revision_rule", "configuration_date");
        var endpoint = payload.GetProperty("endpoint_id").GetString() ?? "";
        var itemId = payload.GetProperty("item_id").GetString() ?? "";
        var revisionId = payload.GetProperty("revision_id").GetString() ?? "";
        var revisionRule = payload.GetProperty("revision_rule").GetString() ?? "";
        var configurationDate = payload.GetProperty("configuration_date").GetString() ?? "";
        if (endpoint != "tc-production" || itemId.Length is < 1 or > 128 || revisionId.Length is < 1 or > 64
            || revisionRule.Length is < 1 or > 128 || !DateTimeOffset.TryParse(configurationDate, out _))
            throw new ConnectorException("teamcenter_search_input_invalid");
        var credentials = RequireCredentials();
        TeamcenterProductSearchResult found;
        await gate.WaitAsync(ct);
        try { found = await worker.SearchAsync(itemId, revisionId, revisionRule, configurationDate,
                credentials.User, credentials.Password, ct); }
        catch (ConnectorException error) when (InvalidatesSession(error)) { ClearCredentials(); throw; }
        finally { gate.Release(); }
        return new TeamcenterProductSearchResult(found.Items.Where(item =>
                string.Equals(item.ItemId, itemId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(item.RevisionId, revisionId, StringComparison.Ordinal))
            .Take(20).ToArray());
    }

    public async Task<object> GetRevisionRulesAsync(JsonElement payload, CancellationToken ct)
    {
        Closed(payload, "endpoint_id");
        if ((payload.GetProperty("endpoint_id").GetString() ?? "") != "tc-production")
            throw new ConnectorException("teamcenter_revision_rules_input_invalid");
        var credentials = RequireCredentials();
        IReadOnlyList<string> raw;
        await gate.WaitAsync(ct);
        try { raw = await worker.GetRevisionRulesAsync(credentials.User, credentials.Password, ct); }
        catch (ConnectorException error) when (InvalidatesSession(error)) { ClearCredentials(); throw; }
        finally { gate.Release(); }
        var rules = raw.Where(rule => !string.IsNullOrWhiteSpace(rule) && rule.Length <= 128)
            .Distinct(StringComparer.OrdinalIgnoreCase).OrderBy(rule => string.Equals(rule, "Latest Working", StringComparison.OrdinalIgnoreCase) ? 0 : 1)
            .ThenBy(rule => rule, StringComparer.Ordinal).ToArray();
        if (rules.Length == 0) throw new ConnectorException("teamcenter_revision_rules_unavailable");
        return new TeamcenterRevisionRulesResult(rules);
    }

    public async Task<object> SearchV2Async(JsonElement payload, CancellationToken ct)
    {
        Closed(payload, "endpoint_id", "query", "revision_id", "revision_rule", "configuration_date", "limit");
        var endpoint = payload.GetProperty("endpoint_id").GetString() ?? "";
        var query = (payload.GetProperty("query").GetString() ?? "").Trim();
        var revisionId = payload.GetProperty("revision_id").GetString() ?? "";
        var revisionRule = payload.GetProperty("revision_rule").GetString() ?? "";
        var configurationDate = payload.GetProperty("configuration_date").GetString() ?? "";
        var limit = payload.GetProperty("limit").GetInt32();
        if (endpoint != "tc-production" || query.Length is < 1 or > 128 || query.Any(char.IsControl)
            || revisionId.Length > 64 || revisionId.Any(char.IsControl) || revisionRule.Length is < 1 or > 128
            || !DateTimeOffset.TryParse(configurationDate, out _) || limit is < 1 or > 20)
            throw new ConnectorException("teamcenter_search_input_invalid");
        var credentials = RequireCredentials();
        TeamcenterProductSearchResult found;
        await gate.WaitAsync(ct);
        try { found = await worker.SearchAsync(query, revisionId, revisionRule, configurationDate,
                credentials.User, credentials.Password, ct); }
        catch (ConnectorException error) when (InvalidatesSession(error)) { ClearCredentials(); throw; }
        finally { gate.Release(); }
        return new TeamcenterProductSearchResult(RankSearchItems(found.Items, query, revisionId, limit));
    }

    public static IReadOnlyList<TeamcenterProductSearchItem> RankSearchItems(
        IEnumerable<TeamcenterProductSearchItem> items, string query, string revisionId, int limit)
    {
        static int Rank(TeamcenterProductSearchItem item, string value)
        {
            if (string.Equals(item.ItemId, value, StringComparison.OrdinalIgnoreCase)) return 0;
            if (item.ItemId.StartsWith(value, StringComparison.OrdinalIgnoreCase)) return 1;
            if (item.ItemId.Contains(value, StringComparison.OrdinalIgnoreCase)) return 2;
            return item.DisplayName.Contains(value, StringComparison.OrdinalIgnoreCase) ? 3 : int.MaxValue;
        }
        return items.Where(item => !string.IsNullOrWhiteSpace(item.SourceSelector.ItemRevisionUid)
                && (revisionId.Length == 0 || string.Equals(item.RevisionId, revisionId, StringComparison.Ordinal))
                && Rank(item, query) != int.MaxValue)
            .GroupBy(item => item.SourceSelector.ItemRevisionUid, StringComparer.Ordinal).Select(group => group.First())
            .OrderBy(item => Rank(item, query)).ThenBy(item => item.ItemId, StringComparer.OrdinalIgnoreCase)
            .ThenBy(item => item.RevisionId, StringComparer.Ordinal).Take(limit).ToArray();
    }

    public Task<TeamcenterObservationPage> ReadPageAsync(string observationId, int cursor, int pageSize, CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested();
        if (!System.Text.RegularExpressions.Regex.IsMatch(observationId, "\\Atcobs:[a-f0-9]{64}\\z")
            || cursor < 0 || pageSize is < 1 or > 1000)
            throw new ConnectorException("teamcenter_page_input_invalid");
        using var connection = new SqliteConnection(connectionString); connection.Open();
        using var count = connection.CreateCommand();
        count.CommandText = "SELECT node_count FROM tc_observations WHERE observation_id=$id";
        count.Parameters.AddWithValue("$id", observationId);
        var totalValue = count.ExecuteScalar();
        if (totalValue is null) throw new ConnectorException("teamcenter_observation_not_found");
        var total = Convert.ToInt32(totalValue);
        using var command = connection.CreateCommand();
        command.CommandText = "SELECT payload_json FROM tc_occurrences WHERE observation_id=$id ORDER BY position LIMIT $size OFFSET $cursor";
        command.Parameters.AddWithValue("$id", observationId); command.Parameters.AddWithValue("$size", pageSize);
        command.Parameters.AddWithValue("$cursor", cursor);
        var nodes = new List<TeamcenterOccurrence>();
        using var reader = command.ExecuteReader();
        while (reader.Read()) nodes.Add(JsonSerializer.Deserialize<TeamcenterOccurrence>(reader.GetString(0))
            ?? throw new InvalidDataException("teamcenter_cache_invalid"));
        var next = cursor + nodes.Count;
        var body = JsonSerializer.SerializeToUtf8Bytes(new { observation_id = observationId,
            cursor, next_cursor = next < total ? next : (int?)null, nodes });
        var hash = "sha256:" + Convert.ToHexString(SHA256.HashData(body)).ToLowerInvariant();
        return Task.FromResult(new TeamcenterObservationPage(observationId, cursor,
            next < total ? next : null, nodes, hash));
    }

    public async Task<object> ConsumeVisualizationAsync(JsonElement payload,
        Func<string, CancellationToken, Task> consumer, CancellationToken ct)
    {
        Closed(payload, "source_selector", "expected_visdoc_uid");
        var selector = ReadSelector(payload.GetProperty("source_selector"));
        var expected = payload.GetProperty("expected_visdoc_uid").GetString() ?? "";
        if (expected.Length > 128 || selector.EndpointId != endpointId)
            throw new ConnectorException("teamcenter_launch_input_invalid");
        var credentials = RequireCredentials();
        await gate.WaitAsync(ct);
        try { return await worker.ConsumeVisualizationAsync(selector, expected, consumer,
                credentials.User, credentials.Password, ct); }
        catch (ConnectorException error) when (InvalidatesSession(error)) { ClearCredentials(); throw; }
        finally { gate.Release(); }
    }

    private (string User, string Password) RequireCredentials()
    {
        lock (credentialState)
        {
            if (username.Length == 0 || password.Length == 0) throw new ConnectorException("teamcenter_login_required");
            return (new string(username), new string(password));
        }
    }

    private static TeamcenterSourceSelector ReadSelector(JsonElement value)
    {
        Closed(value, "endpoint_id", "object_uid", "item_revision_uid", "bom_view_uid", "revision_rule", "configuration_date");
        var selector = JsonSerializer.Deserialize<TeamcenterSourceSelector>(value.GetRawText())
            ?? throw new ConnectorException("teamcenter_source_selector_invalid");
        if (selector.EndpointId != "tc-production" || selector.ObjectUid.Length is < 1 or > 128
            || selector.ItemRevisionUid.Length > 128 || selector.BomViewUid.Length > 128
            || selector.RevisionRule.Length is < 1 or > 128
            || !DateTimeOffset.TryParse(selector.ConfigurationDate, out _))
            throw new ConnectorException("teamcenter_source_selector_invalid");
        return selector;
    }

    private static void Closed(JsonElement value, params string[] names)
    {
        if (value.ValueKind != JsonValueKind.Object || value.EnumerateObject().Select(item => item.Name).Order().SequenceEqual(names.Order()) is false)
            throw new ConnectorException("teamcenter_input_invalid");
    }

    private static void ValidateNodes(IReadOnlyList<TeamcenterOccurrence> nodes, int maxNodes, int maxDepth)
    {
        if (nodes.Count is < 1 || nodes.Count > maxNodes) throw new ConnectorException("teamcenter_node_count_invalid");
        var ids = new HashSet<string>(StringComparer.Ordinal);
        var depth = new Dictionary<string, int>(StringComparer.Ordinal);
        foreach (var node in nodes)
        {
            if (string.IsNullOrWhiteSpace(node.OccurrenceId) || !ids.Add(node.OccurrenceId)
                || node.Depth < 0 || node.Depth > maxDepth || node.ChildOrder < 0
                || node.Transform is { Length: not 16 } || node.AbsoluteTransform is { Length: not 16 }
                || node.Bbox is { Length: not 6 } || node.TransformUnit.Length > 32
                || node.TransformConvention.Length > 64 || node.BboxUnit.Length > 32)
                throw new ConnectorException("teamcenter_occurrence_invalid");
            if (node.ParentOccurrenceId is null)
            { if (node.Depth != 0) throw new ConnectorException("teamcenter_occurrence_invalid"); }
            else if (!depth.TryGetValue(node.ParentOccurrenceId, out var parentDepth) || node.Depth != parentDepth + 1)
                throw new ConnectorException("teamcenter_occurrence_invalid");
            depth[node.OccurrenceId] = node.Depth;
        }
    }

    private void Initialize()
    {
        using var connection = new SqliteConnection(connectionString); connection.Open();
        using var command = connection.CreateCommand();
        command.CommandText = """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS tc_observations (
              observation_id TEXT PRIMARY KEY, source_identity_hash TEXT NOT NULL,
              captured_at TEXT NOT NULL, node_count INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS tc_occurrences (
              observation_id TEXT NOT NULL, position INTEGER NOT NULL, payload_json TEXT NOT NULL,
              PRIMARY KEY(observation_id,position),
              FOREIGN KEY(observation_id) REFERENCES tc_observations(observation_id) ON DELETE CASCADE);
            """;
        command.ExecuteNonQuery();
    }

    private void WriteObservation(string observationId, string sourceHash, DateTimeOffset captured,
                                  IReadOnlyList<TeamcenterOccurrence> nodes)
    {
        using var connection = new SqliteConnection(connectionString); connection.Open();
        using var transaction = connection.BeginTransaction();
        using var manifest = connection.CreateCommand(); manifest.Transaction = transaction;
        manifest.CommandText = "INSERT INTO tc_observations VALUES ($id,$hash,$time,$count)";
        manifest.Parameters.AddWithValue("$id", observationId); manifest.Parameters.AddWithValue("$hash", sourceHash);
        manifest.Parameters.AddWithValue("$time", captured.ToString("O")); manifest.Parameters.AddWithValue("$count", nodes.Count);
        manifest.ExecuteNonQuery();
        using var item = connection.CreateCommand(); item.Transaction = transaction;
        item.CommandText = "INSERT INTO tc_occurrences VALUES ($id,$position,$payload)";
        var id = item.Parameters.Add("$id", SqliteType.Text); var position = item.Parameters.Add("$position", SqliteType.Integer);
        var payload = item.Parameters.Add("$payload", SqliteType.Text);
        for (var index = 0; index < nodes.Count; index++)
        { id.Value = observationId; position.Value = index; payload.Value = JsonSerializer.Serialize(nodes[index]); item.ExecuteNonQuery(); }
        transaction.Commit();
    }

    private void ClearCredentials()
    {
        lock (credentialState) ClearCredentialsUnsafe();
    }

    private static bool InvalidatesSession(ConnectorException error) =>
        error.Message is "teamcenter_authentication_failed" or "teamcenter_session_expired";

    private void ClearCredentialsUnsafe()
    { Array.Clear(username); Array.Clear(password); username = []; password = []; endpointId = ""; }

    public void Dispose() { ClearCredentials(); gate.Dispose(); }
}

internal sealed class UnavailableTeamcenterWorker : ITeamcenterWorker
{
    private static ConnectorException Error() => new("teamcenter_runtime_unavailable");
    public Task ValidateCredentialsAsync(string endpointId, string username, string password, CancellationToken ct) => Task.FromException(Error());
    public Task<IReadOnlyList<string>> GetRevisionRulesAsync(string username, string password, CancellationToken ct) => Task.FromException<IReadOnlyList<string>>(Error());
    public Task<TeamcenterProductSearchResult> SearchAsync(string itemId, string revisionId, string revisionRule, string configurationDate, string username, string password, CancellationToken ct) => Task.FromException<TeamcenterProductSearchResult>(Error());
    public Task<IReadOnlyList<TeamcenterOccurrence>> ObserveAsync(TeamcenterSourceSelector selector, int maxNodes, int maxDepth, string propertyProjection, string username, string password, CancellationToken ct) => Task.FromException<IReadOnlyList<TeamcenterOccurrence>>(Error());
    public Task<TeamcenterLaunchResult> LaunchAsync(TeamcenterSourceSelector selector, string expectedVisdocUid, string username, string password, CancellationToken ct) => Task.FromException<TeamcenterLaunchResult>(Error());
    public Task<TeamcenterLaunchResult> ConsumeVisualizationAsync(TeamcenterSourceSelector selector, string expectedVisdocUid, Func<string, CancellationToken, Task> consumer, string username, string password, CancellationToken ct) => Task.FromException<TeamcenterLaunchResult>(Error());
}

public sealed class TeamcenterProcessWorker(string javaPath, string scriptPath, string launcherPath,
    IReadOnlyList<string> classpath, string visualizationMaterialRoot) : ITeamcenterWorker
{
    private static readonly JsonSerializerOptions JsonOptions = new() { PropertyNameCaseInsensitive = false };

    internal static void SecureVisualizationMaterialRoot(string path)
    {
        if (!OperatingSystem.IsWindows()) throw new PlatformNotSupportedException("windows_required");
        var full = Path.GetFullPath(path);
        Directory.CreateDirectory(full);
        var directory = new DirectoryInfo(full);
        if ((directory.Attributes & FileAttributes.ReparsePoint) != 0)
            throw new IOException("teamcenter_visualization_material_root_invalid");
        using var identity = WindowsIdentity.GetCurrent();
        var sid = identity.User ?? throw new IOException("windows_user_required");
        var security = new DirectorySecurity();
        security.SetAccessRuleProtection(true, false);
        security.SetOwner(sid);
        security.AddAccessRule(new FileSystemAccessRule(sid, FileSystemRights.FullControl,
            InheritanceFlags.ContainerInherit | InheritanceFlags.ObjectInherit,
            PropagationFlags.None, AccessControlType.Allow));
        directory.SetAccessControl(security);
    }

    public static ProcessStartInfo CreateStartInfo(string javaPath, string scriptPath, IReadOnlyList<string> classpath)
    {
        var info = new ProcessStartInfo(javaPath) { UseShellExecute = false, CreateNoWindow = true,
            RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true,
            StandardInputEncoding = Encoding.UTF8, StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8 };
        info.ArgumentList.Add("--add-modules"); info.ArgumentList.Add("jdk.unsupported");
        info.ArgumentList.Add("-Dfile.encoding=UTF-8");
        info.ArgumentList.Add("-Djava.library.path=D:/Siemens/Teamcenter14/tccs/lib");
        info.ArgumentList.Add("-cp"); info.ArgumentList.Add(string.Join(';', classpath));
        info.ArgumentList.Add("--module"); info.ArgumentList.Add("jdk.scripting.nashorn.shell/jdk.nashorn.tools.jjs.Main");
        info.ArgumentList.Add(scriptPath);
        info.Environment.Clear();
        foreach (var key in new[] { "SystemRoot", "WINDIR", "TEMP", "TMP", "LOCALAPPDATA", "USERPROFILE", "FMS_HOME" })
            if (Environment.GetEnvironmentVariable(key) is { Length: > 0 } value) info.Environment[key] = value;
        return info;
    }

    public async Task ValidateCredentialsAsync(string endpointId, string username, string password, CancellationToken ct)
        => _ = await RunAsync("status", new { endpoint_id = endpointId }, username, password, ct);

    public async Task<IReadOnlyList<string>> GetRevisionRulesAsync(string username, string password, CancellationToken ct)
    {
        var result = await RunAsync("revision_rules", new { endpoint_id = "tc-production" }, username, password, ct);
        return result.GetProperty("rules").Deserialize<string[]>(JsonOptions)
            ?? throw new ConnectorException("teamcenter_worker_response_invalid");
    }

    public async Task<TeamcenterProductSearchResult> SearchAsync(string itemId, string revisionId,
        string revisionRule, string configurationDate, string username, string password, CancellationToken ct)
    {
        var result = await RunAsync("search", new { endpoint_id = "tc-production", item_id = itemId,
            revision_id = revisionId, revision_rule = revisionRule, configuration_date = configurationDate },
            username, password, ct);
        return result.Deserialize<TeamcenterProductSearchResult>(JsonOptions)
            ?? throw new ConnectorException("teamcenter_worker_response_invalid");
    }

    public async Task<IReadOnlyList<TeamcenterOccurrence>> ObserveAsync(TeamcenterSourceSelector selector,
        int maxNodes, int maxDepth, string propertyProjection, string username, string password, CancellationToken ct)
    {
        var result = await RunAsync("observe", new { source_selector = selector, max_nodes = maxNodes,
            max_depth = maxDepth, property_projection = propertyProjection }, username, password, ct);
        return result.GetProperty("nodes").Deserialize<TeamcenterOccurrence[]>(JsonOptions)
            ?? throw new ConnectorException("teamcenter_worker_response_invalid");
    }

    public async Task<TeamcenterLaunchResult> LaunchAsync(TeamcenterSourceSelector selector, string expectedVisdocUid,
        string username, string password, CancellationToken ct)
    {
        var result = await RunScriptAsync(launcherPath, "launch", new { source_selector = selector,
            expected_visdoc_uid = expectedVisdocUid, source_identity_hash = selector.IdentityHash }, username, password, ct);
        return result.Deserialize<TeamcenterLaunchResult>(JsonOptions)
            ?? throw new ConnectorException("teamcenter_worker_response_invalid");
    }

    public async Task<TeamcenterLaunchResult> ConsumeVisualizationAsync(TeamcenterSourceSelector selector,
        string expectedVisdocUid, Func<string, CancellationToken, Task> consumer,
        string username, string password, CancellationToken ct)
    {
        var materialRoot = Path.GetFullPath(visualizationMaterialRoot);
        SecureVisualizationMaterialRoot(materialRoot);
        var operationRoot = Path.Combine(materialRoot, Guid.NewGuid().ToString("N"));
        SecureVisualizationMaterialRoot(operationRoot);
        using var process = new Process { StartInfo = CreateStartInfo(javaPath, launcherPath, classpath) };
        try
        {
            if (!process.Start()) throw new ConnectorException("teamcenter_worker_start_failed");
        }
        catch
        {
            try { Directory.Delete(operationRoot, true); } catch { }
            throw;
        }
        var diagnosticTask = ReadBoundedAsync(process.StandardError, 8192, ct);
        Exception? consumerError = null;
        string? materialPath = null;
        try
        {
            await process.StandardInput.WriteLineAsync(username.AsMemory(), ct);
            await process.StandardInput.WriteLineAsync(password.AsMemory(), ct);
            await process.StandardInput.WriteLineAsync(JsonSerializer.Serialize(new
            {
                command = "consume",
                payload = new { source_selector = selector, expected_visdoc_uid = expectedVisdocUid,
                    source_identity_hash = selector.IdentityHash, material_root = operationRoot }
            }).AsMemory(), ct);
            await process.StandardInput.FlushAsync(ct);

            var readyLine = await ReadLineBoundedAsync(process.StandardOutput, 16 * 1024, ct);
            using var readyDocument = JsonDocument.Parse(readyLine);
            var ready = readyDocument.RootElement;
            if (ready.ValueKind != JsonValueKind.Object
                || ready.EnumerateObject().Select(item => item.Name).Order().SequenceEqual(
                    new[] { "expected_visdoc_uid", "material_path", "source_identity_hash", "type" }.Order()) is false
                || ready.GetProperty("type").GetString() != "material_ready"
                || ready.GetProperty("expected_visdoc_uid").GetString() != expectedVisdocUid
                || ready.GetProperty("source_identity_hash").GetString() != selector.IdentityHash)
                throw new ConnectorException("teamcenter_worker_response_invalid");
            materialPath = ValidateMaterialPath(operationRoot,
                ready.GetProperty("material_path").GetString() ?? "");
            try { await consumer(materialPath, ct); }
            catch (Exception error) { consumerError = error; }

            await process.StandardInput.WriteLineAsync(JsonSerializer.Serialize(new
                { type = consumerError is null ? "material_consumed" : "material_failed" }));
            await process.StandardInput.FlushAsync();
            process.StandardInput.Close();
            using var cleanupTimeout = new CancellationTokenSource(TimeSpan.FromSeconds(30));
            var finalLine = await ReadLineBoundedAsync(process.StandardOutput, 64 * 1024, cleanupTimeout.Token);
            await process.WaitForExitAsync(cleanupTimeout.Token);
            var diagnostic = await diagnosticTask;
            if (consumerError is not null)
                System.Runtime.ExceptionServices.ExceptionDispatchInfo.Capture(consumerError).Throw();
            using var finalDocument = JsonDocument.Parse(finalLine);
            var root = finalDocument.RootElement;
            if (process.ExitCode != 0 || !root.TryGetProperty("ok", out var ok) || !ok.GetBoolean())
                throw new ConnectorException(root.TryGetProperty("code", out var code)
                    ? code.GetString()! : SanitizeDiagnostic(diagnostic));
            return root.GetProperty("result").Deserialize<TeamcenterLaunchResult>(JsonOptions)
                ?? throw new ConnectorException("teamcenter_worker_response_invalid");
        }
        catch
        {
            try { if (!process.HasExited) process.Kill(true); } catch { }
            if (consumerError is not null)
                System.Runtime.ExceptionServices.ExceptionDispatchInfo.Capture(consumerError).Throw();
            throw;
        }
        finally
        {
            if (materialPath is not null)
            {
                try { File.Delete(materialPath); }
                catch { /* Java also cleans up; a later state-root sweep handles a locked file. */ }
            }
            try { if (Directory.Exists(operationRoot)) Directory.Delete(operationRoot, true); }
            catch { /* Never replace the consumer result with best-effort material cleanup. */ }
        }
    }

    private async Task<JsonElement> RunAsync(string command, object payload, string username, string password, CancellationToken ct)
    {
        if (!TeamcenterReadOnlyPolicy.WorkerCommands.Contains(command)) throw new ConnectorException("teamcenter_worker_command_forbidden");
        return await RunScriptAsync(scriptPath, command, payload, username, password, ct);
    }

    private async Task<JsonElement> RunScriptAsync(string selectedScript, string command, object payload,
        string username, string password, CancellationToken ct)
    {
        return await RunProcessAsync(CreateStartInfo(javaPath, selectedScript, classpath),
            [username, password, JsonSerializer.Serialize(new { command, payload })], ct);
    }

    private static async Task<JsonElement> RunProcessAsync(ProcessStartInfo startInfo,
        IReadOnlyList<string> inputLines, CancellationToken ct)
    {
        using var process = new Process { StartInfo = startInfo };
        if (!process.Start()) throw new ConnectorException("teamcenter_worker_start_failed");
        var diagnosticTask = ReadBoundedAsync(process.StandardError, 8192, ct);
        try
        {
            foreach (var line in inputLines) await process.StandardInput.WriteLineAsync(line.AsMemory(), ct);
            process.StandardInput.Close();
            var outputTask = ReadBoundedAsync(process.StandardOutput, 64 * 1024 * 1024, ct);
            await process.WaitForExitAsync(ct);
            var output = await outputTask;
            var diagnostic = await diagnosticTask;
            var lines = output.Split(['\r','\n'], StringSplitOptions.RemoveEmptyEntries);
            if (lines.Length != 1)
                throw new ConnectorException(process.ExitCode != 0 ? SanitizeDiagnostic(diagnostic) : "teamcenter_worker_response_invalid");
            var root = JsonDocument.Parse(lines[0]).RootElement.Clone();
            if (!root.TryGetProperty("ok", out var ok) || !ok.GetBoolean())
                throw new ConnectorException(root.TryGetProperty("code", out var code) ? code.GetString()! : "teamcenter_worker_failed");
            if (process.ExitCode != 0) throw new ConnectorException(SanitizeDiagnostic(diagnostic));
            return root.GetProperty("result").Clone();
        }
        catch { try { if (!process.HasExited) process.Kill(true); } catch { } throw; }
    }

    private static async Task<string> ReadBoundedAsync(StreamReader reader, int maximum, CancellationToken ct)
    {
        var result = new StringBuilder(); var buffer = new char[4096];
        while (true) { var count = await reader.ReadAsync(buffer.AsMemory(), ct); if (count == 0) break;
            if (result.Length + count > maximum) throw new ConnectorException("teamcenter_worker_response_too_large");
            result.Append(buffer, 0, count); }
        return result.ToString();
    }

    private static async Task<string> ReadLineBoundedAsync(StreamReader reader, int maximum, CancellationToken ct)
    {
        var line = await reader.ReadLineAsync(ct);
        if (line is null || line.Length == 0 || line.Length > maximum)
            throw new ConnectorException("teamcenter_worker_response_invalid");
        return line;
    }

    private static string ValidateMaterialPath(string materialRoot, string candidate)
    {
        if (string.IsNullOrWhiteSpace(candidate) || !Path.IsPathFullyQualified(candidate))
            throw new ConnectorException("teamcenter_visualization_material_invalid");
        var full = Path.GetFullPath(candidate);
        var rootPrefix = Path.TrimEndingDirectorySeparator(materialRoot) + Path.DirectorySeparatorChar;
        if (!full.StartsWith(rootPrefix, StringComparison.OrdinalIgnoreCase)
            || !string.Equals(Path.GetExtension(full), ".vvi", StringComparison.OrdinalIgnoreCase)
            || !File.Exists(full))
            throw new ConnectorException("teamcenter_visualization_material_invalid");
        var length = new FileInfo(full).Length;
        if (length is < 1 or > 64 * 1024 * 1024)
            throw new ConnectorException("teamcenter_visualization_material_invalid");
        return full;
    }

    private static string SanitizeDiagnostic(string value)
    {
        if (value.Contains("invalid", StringComparison.OrdinalIgnoreCase)) return "teamcenter_authentication_failed";
        if (value.Contains("timeout", StringComparison.OrdinalIgnoreCase)) return "teamcenter_timeout";
        return "teamcenter_worker_failed";
    }
}
