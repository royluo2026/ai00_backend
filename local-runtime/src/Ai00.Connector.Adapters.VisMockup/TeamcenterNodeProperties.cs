using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using Ai00.Connector.Contracts;
using Microsoft.Data.Sqlite;

namespace Ai00.Connector.Adapters.VisMockup;

public sealed record TeamcenterNodeProperties(
    [property: JsonPropertyName("name")] string? Name,
    [property: JsonPropertyName("item_id")] string? ItemId,
    [property: JsonPropertyName("revision_id")] string? RevisionId,
    [property: JsonPropertyName("component_type")] string? ComponentType,
    [property: JsonPropertyName("owning_user")] string? OwningUser,
    [property: JsonPropertyName("owning_group")] string? OwningGroup,
    [property: JsonPropertyName("weight_raw")] string? WeightRaw,
    [property: JsonPropertyName("unit_weight_raw")] string? UnitWeightRaw,
    [property: JsonPropertyName("torque_raw")] string? TorqueRaw,
    [property: JsonPropertyName("torque_importance")] string? TorqueImportance,
    [property: JsonPropertyName("occurrence_uid")] string? OccurrenceUid);

public sealed record TeamcenterNodePropertiesResult(
    [property: JsonPropertyName("source_identity_hash")] string SourceIdentityHash,
    [property: JsonPropertyName("captured_at")] DateTimeOffset CapturedAt,
    [property: JsonPropertyName("cache_hit")] bool CacheHit,
    [property: JsonPropertyName("properties")] TeamcenterNodeProperties Properties);

public sealed partial class TeamcenterReadOnlyRuntime
{
    private const string NodePropertiesProjection = "node-properties-v1";

    public async Task<object> ReadNodePropertiesAsync(JsonElement payload, CancellationToken ct)
    {
        Closed(payload, "source_selector", "occurrence_path");
        var selector = ReadSelector(payload.GetProperty("source_selector"));
        var path = ReadNodePropertyPath(payload.GetProperty("occurrence_path"));
        await gate.WaitAsync(ct);
        try
        {
            var principal = RequirePrincipal();
            var key = NodePropertiesHash(JsonSerializer.Serialize(new
            {
                principal,
                source = selector.IdentityHash,
                path,
                projection = NodePropertiesProjection,
            }));
            using var db = new SqliteConnection(connectionString);
            db.Open();
            using (var schema = db.CreateCommand())
            {
                schema.CommandText = """
                    CREATE TABLE IF NOT EXISTS tc_node_property_cache (
                      cache_key TEXT PRIMARY KEY,
                      source_identity_hash TEXT NOT NULL,
                      captured_at TEXT NOT NULL,
                      payload_json TEXT NOT NULL
                    )
                    """;
                schema.ExecuteNonQuery();
            }

            using (var read = db.CreateCommand())
            {
                read.CommandText = "SELECT source_identity_hash,captured_at,payload_json FROM tc_node_property_cache WHERE cache_key=$key";
                read.Parameters.AddWithValue("$key", key);
                using var reader = read.ExecuteReader();
                if (reader.Read())
                {
                    try
                    {
                        var sourceHash = reader.GetString(0);
                        if (sourceHash != selector.IdentityHash
                            || !DateTimeOffset.TryParse(reader.GetString(1), out var captured)
                            || captured == default)
                            throw new ConnectorException("teamcenter_node_properties_cache_invalid");
                        var properties = ReadCachedNodeProperties(reader.GetString(2), path);
                        return new TeamcenterNodePropertiesResult(sourceHash, captured, true, properties);
                    }
                    catch (ConnectorException) { throw; }
                    catch (Exception error) when (error is JsonException or NotSupportedException or FormatException)
                    {
                        throw new ConnectorException("teamcenter_node_properties_cache_invalid");
                    }
                }
            }

            var credentials = RequireCredentials();
            var result = await worker.ReadNodePropertiesAsync(
                selector, path, credentials.User, credentials.Password, ct);
            if (result is null || result.SourceIdentityHash != selector.IdentityHash
                || result.CacheHit || result.CapturedAt == default
                || !ValidNodeProperties(result.Properties, path))
                throw new ConnectorException("teamcenter_worker_response_invalid");

            using (var write = db.CreateCommand())
            {
                write.CommandText = """
                    INSERT INTO tc_node_property_cache(cache_key,source_identity_hash,captured_at,payload_json)
                    VALUES($key,$source,$captured,$payload)
                    ON CONFLICT(cache_key) DO UPDATE SET
                      source_identity_hash=excluded.source_identity_hash,
                      captured_at=excluded.captured_at,
                      payload_json=excluded.payload_json
                    """;
                write.Parameters.AddWithValue("$key", key);
                write.Parameters.AddWithValue("$source", result.SourceIdentityHash);
                write.Parameters.AddWithValue("$captured", result.CapturedAt.ToString("O"));
                write.Parameters.AddWithValue("$payload", JsonSerializer.Serialize(result.Properties));
                write.ExecuteNonQuery();
            }
            return result;
        }
        catch (ConnectorException error) when (InvalidatesSession(error))
        {
            ClearCredentials();
            throw;
        }
        finally { gate.Release(); }
    }

    private static TeamcenterOccurrenceEdge[] ReadNodePropertyPath(JsonElement value)
    {
        if (value.ValueKind != JsonValueKind.Array || value.GetArrayLength() > 128)
            throw new ConnectorException("teamcenter_node_properties_input_invalid");
        try
        {
            var path = new List<TeamcenterOccurrenceEdge>();
            foreach (var edge in value.EnumerateArray())
            {
                Closed(edge, "occurrence_uid", "item_revision_uid");
                var occurrenceUid = edge.GetProperty("occurrence_uid").GetString() ?? "";
                var revisionUid = edge.GetProperty("item_revision_uid").GetString() ?? "";
                if (occurrenceUid.Length is < 1 or > 128 || revisionUid.Length is < 1 or > 128)
                    throw new ConnectorException("teamcenter_node_properties_input_invalid");
                path.Add(new TeamcenterOccurrenceEdge(occurrenceUid, revisionUid));
            }
            return path.ToArray();
        }
        catch (ConnectorException) { throw; }
        catch (Exception error) when (error is InvalidOperationException or KeyNotFoundException)
        {
            throw new ConnectorException("teamcenter_node_properties_input_invalid");
        }
    }

    private static TeamcenterNodeProperties ReadCachedNodeProperties(
        string payloadJson, TeamcenterOccurrenceEdge[] path)
    {
        using var document = JsonDocument.Parse(payloadJson);
        if (document.RootElement.ValueKind != JsonValueKind.Object)
            throw new ConnectorException("teamcenter_node_properties_cache_invalid");
        var expected = new HashSet<string>(StringComparer.Ordinal) {
            "name", "item_id", "revision_id", "component_type", "owning_user", "owning_group",
            "weight_raw", "unit_weight_raw", "torque_raw", "torque_importance", "occurrence_uid",
        };
        var members = document.RootElement.EnumerateObject().ToArray();
        if (members.Length != expected.Count
            || !members.Select(member => member.Name).ToHashSet(StringComparer.Ordinal).SetEquals(expected)
            || members.Any(member => member.Value.ValueKind is not (JsonValueKind.String or JsonValueKind.Null)))
            throw new ConnectorException("teamcenter_node_properties_cache_invalid");
        var value = JsonSerializer.Deserialize<TeamcenterNodeProperties>(payloadJson);
        if (!ValidNodeProperties(value, path))
            throw new ConnectorException("teamcenter_node_properties_cache_invalid");
        return value!;
    }

    private static bool ValidNodeProperties(
        TeamcenterNodeProperties? value, TeamcenterOccurrenceEdge[] path)
    {
        if (value is null) return false;
        var fields = new[] { value.Name, value.ItemId, value.RevisionId, value.ComponentType,
            value.OwningUser, value.OwningGroup, value.WeightRaw, value.UnitWeightRaw,
            value.TorqueRaw, value.TorqueImportance };
        return fields.All(field => field is null || field.Length <= 4096)
            && (path.Length == 0
                ? value.OccurrenceUid is null
                : value.OccurrenceUid == path[^1].OccurrenceUid);
    }

    private static string NodePropertiesHash(string value) =>
        "sha256:" + Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();
}
