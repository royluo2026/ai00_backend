using System.Globalization;
using System.Numerics;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace Ai00.Connector.Contracts.V2;

public sealed class ProtocolV2Exception(string code, Exception? inner = null) : Exception(code, inner);

// Typed views can only be constructed after the entire original JSON passes the
// closed validator. The cloned JsonElement retains exact timestamps and integers.
public abstract class ProtocolV2Record
{
    public JsonElement Document { get; }
    private protected ProtocolV2Record(JsonElement document) => Document = document;
    protected string Text(string name) => Document.GetProperty(name).GetString()!;
    protected BigInteger Integer(string name) => BigInteger.Parse(Document.GetProperty(name).GetRawText(), CultureInfo.InvariantCulture);
    public string ToJson() => Document.GetRawText();
}

public sealed class ExecutionPlanV2 : ProtocolV2Record
{
    private ExecutionPlanV2(JsonElement value) : base(value) { }
    public static ExecutionPlanV2 ParseAndVerify(string json, string publicJwk)
    {
        var value = CanonicalJsonV2.Parse(json);
        ProtocolV2Schema.Plan(value);
        ProtocolV2Signatures.Verify(value, publicJwk);
        return new(value);
    }
    public string Protocol => Text("protocol");
    public string PlanId => Text("plan_id");
    public string PlanHash => Text("plan_hash");
    public string CapabilityId => Text("capability_id");
    public BigInteger MajorVersion => Integer("major_version");
    public string CapabilityVersionGid => Text("capability_version_gid");
    public string BusinessDefinitionHash => Text("business_definition_hash");
    public string CatalogRelease => Text("catalog_release");
    public string TenantId => Text("tenant_id");
    public string ActorId => Text("actor_id");
    public string DeviceId => Text("device_id");
    public BigInteger RuntimeGeneration => Integer("runtime_generation");
    public string RuntimeInstanceId => Text("runtime_instance_id");
    public string AdapterId => Text("adapter_id");
    public BigInteger AdapterMajor => Integer("adapter_major");
    public JsonElement TargetProduct => Document.GetProperty("target_product");
    public string NormalizedInputHash => Text("normalized_input_hash");
    public string? ConfirmationReceiptId => Document.GetProperty("confirmation_receipt_id").GetString();
    public string IdempotencyKey => Text("idempotency_key");
    public IReadOnlyList<ConnectorStepV2> Steps => Array.AsReadOnly(Document.GetProperty("steps").EnumerateArray().Select(s => new ConnectorStepV2(s)).ToArray());
    public DateTimeOffset IssuedAt => ProtocolV2Schema.Timestamp(Document, "issued_at");
    public DateTimeOffset ExpiresAt => ProtocolV2Schema.Timestamp(Document, "expires_at");
    public string KeyId => Text("key_id");
}

public sealed class ConnectorStepV2 : ProtocolV2Record
{
    internal ConnectorStepV2(JsonElement value) : base(value) { }
    public string StepId => Text("step_id");
    public string OperationId => Text("operation_id");
    public string ContractHash => Text("contract_hash");
    public IReadOnlyList<string> DependsOn => Array.AsReadOnly(Document.GetProperty("depends_on").EnumerateArray().Select(d => d.GetString()!).ToArray());
    public JsonElement Payload => Document.GetProperty("payload");
    public string PayloadHash => Text("payload_hash");
    public int TimeoutSeconds => Document.GetProperty("timeout_seconds").GetInt32();
    public string SideEffectClassification => Text("side_effect_classification");
    public string? PostConditionProbeId => Document.GetProperty("post_condition_probe_id").GetString();
}

public sealed class OutcomeV2 : ProtocolV2Record
{
    private OutcomeV2(JsonElement value) : base(value) { }
    public static OutcomeV2 ParseAndVerify(string json, string publicJwk)
    {
        var value = CanonicalJsonV2.Parse(json);
        ProtocolV2Schema.Outcome(value);
        ProtocolV2Signatures.Verify(value, publicJwk);
        return new(value);
    }
    public string PlanId => Text("plan_id");
    public string PlanHash => Text("plan_hash");
    public string LeaseId => Text("lease_id");
    public string TenantId => Text("tenant_id");
    public string DeviceId => Text("device_id");
    public BigInteger RuntimeGeneration => Integer("runtime_generation");
    public string RuntimeInstanceId => Text("runtime_instance_id");
    public string OverallStatus => Text("overall_status");
    public BigInteger JournalSequence => Integer("journal_sequence");
    public DateTimeOffset ReportedAt => ProtocolV2Schema.Timestamp(Document, "reported_at");
    public string DeviceKeyId => Text("device_key_id");
    public JsonElement Steps => Document.GetProperty("steps");
}

internal static class ProtocolV2Schema
{
    private const string Identity = "[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,255}";
    private const string Capability = "[a-z][a-z0-9_.-]{2,127}";
    private const string Hash = "sha256:[0-9a-f]{64}";
    private const string Status = "succeeded|failed_without_effect|outcome_unknown|manual_review_required";
    private const string TimestampPattern = "[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](?:\\.[0-9]{1,7})?Z";

    internal static void Closed(JsonElement value, string fields)
    {
        Require(value.ValueKind == JsonValueKind.Object, "object_required");
        var expected = fields.Split(' ').ToHashSet(StringComparer.Ordinal);
        foreach (var field in value.EnumerateObject()) Require(expected.Remove(field.Name), "unknown_or_duplicate_member");
        Require(expected.Count == 0, "required_member_missing");
    }
    internal static string Text(JsonElement value, string field, string? pattern = null, bool nullable = false)
    {
        var item = value.GetProperty(field);
        if (nullable && item.ValueKind == JsonValueKind.Null) return null!;
        Require(item.ValueKind == JsonValueKind.String, "string_required");
        var text = item.GetString()!;
        if (pattern != null) Require(Regex.IsMatch(text, "\\A(?:" + pattern + ")\\z", RegexOptions.CultureInvariant), "invalid_" + field);
        return text;
    }
    private static void Integer(JsonElement value, string field, int? max = null)
    {
        var item = value.GetProperty(field);
        Require(item.ValueKind == JsonValueKind.Number && Regex.IsMatch(item.GetRawText(), "\\A[0-9]+\\z"), "integer_required");
        var number = BigInteger.Parse(item.GetRawText(), CultureInfo.InvariantCulture);
        Require(number >= 1 && (max == null || number <= max), "integer_range_invalid");
    }
    internal static DateTimeOffset Timestamp(JsonElement value, string field)
    {
        var text = Text(value, field, TimestampPattern);
        Require(DateTimeOffset.TryParseExact(text, ["yyyy-MM-dd'T'HH:mm:ss'Z'", "yyyy-MM-dd'T'HH:mm:ss.FFFFFFF'Z'"],
            CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out var timestamp), "canonical_utc_timestamp_required");
        return timestamp;
    }
    internal static void Require(bool valid, string code)
    { if (!valid) throw new ProtocolV2Exception(code); }
    private static void Common(JsonElement value)
    {
        Require(Text(value, "protocol") == "ai00.connector.execution-plan.v2", "protocol_invalid");
        Require(Text(value, "signature_algorithm") == "ecdsa-p256-sha256", "signature_algorithm_invalid");
        foreach (var field in new[] { "plan_id", "tenant_id", "device_id", "runtime_instance_id" }) Text(value, field, Identity);
        Integer(value, "runtime_generation");
        Text(value, "plan_hash", "[0-9a-f]{64}");
        ProtocolV2Signatures.DecodeSignature(Text(value, "signature"));
    }
    private static JsonElement[] Steps(JsonElement value)
    {
        var steps = value.GetProperty("steps");
        Require(steps.ValueKind == JsonValueKind.Array, "array_required");
        Require(steps.GetArrayLength() is >= 1 and <= 10000, "step_count_invalid");
        return steps.EnumerateArray().ToArray();
    }
    internal static void Plan(JsonElement value)
    {
        Closed(value, "protocol plan_id capability_id major_version capability_version_gid business_definition_hash catalog_release tenant_id actor_id device_id runtime_generation runtime_instance_id adapter_id adapter_major target_product normalized_input_hash confirmation_receipt_id idempotency_key steps issued_at expires_at plan_hash signature_algorithm key_id signature");
        Common(value);
        foreach (var field in new[] { "capability_version_gid", "catalog_release", "actor_id", "idempotency_key", "key_id" }) Text(value, field, Identity);
        foreach (var field in new[] { "capability_id", "adapter_id" }) Text(value, field, Capability);
        foreach (var field in new[] { "business_definition_hash", "normalized_input_hash" }) Text(value, field, Hash);
        Integer(value, "major_version"); Integer(value, "adapter_major");
        Text(value, "confirmation_receipt_id", nullable: true);
        Require(Timestamp(value, "expires_at") > Timestamp(value, "issued_at"), "plan_expiry_must_follow_issue_time");
        var target = value.GetProperty("target_product");
        Closed(target, "product_id minimum_version maximum_version_exclusive");
        Text(target, "product_id", Capability);
        var minimum = Text(target, "minimum_version", "[0-9]+(?:\\.[0-9]+){1,3}").Split('.').Select(s => BigInteger.Parse(s, CultureInfo.InvariantCulture)).ToArray();
        var maximum = Text(target, "maximum_version_exclusive", "[0-9]+(?:\\.[0-9]+){1,3}").Split('.').Select(s => BigInteger.Parse(s, CultureInfo.InvariantCulture)).ToArray();
        var comparison = minimum.Length.CompareTo(maximum.Length);
        for (var i = 0; i < Math.Min(minimum.Length, maximum.Length); i++)
            if (minimum[i] != maximum[i]) { comparison = minimum[i].CompareTo(maximum[i]); break; }
        Require(comparison < 0, "target_product_version_range_invalid");
        var seen = new HashSet<string>(StringComparer.Ordinal);
        foreach (var step in Steps(value))
        {
            Closed(step, "step_id operation_id contract_hash depends_on payload payload_hash timeout_seconds side_effect_classification post_condition_probe_id");
            var id = Text(step, "step_id", Identity);
            Text(step, "operation_id", "[a-z][a-z0-9_.-]{2,127}@[1-9][0-9]*");
            Text(step, "contract_hash", Hash);
            Require(Text(step, "payload_hash", Hash) == CanonicalJsonV2.Hash(step.GetProperty("payload")), "payload_hash_mismatch");
            Integer(step, "timeout_seconds", 900);
            var effect = Text(step, "side_effect_classification", "read|write|destructive");
            var probe = Text(step, "post_condition_probe_id", nullable: true);
            Require(effect == "read" || probe != null, "post_condition_probe_required");
            var dependencies = step.GetProperty("depends_on");
            Require(dependencies.ValueKind == JsonValueKind.Array, "array_required");
            var dependencyIds = new HashSet<string>(StringComparer.Ordinal);
            foreach (var dependency in dependencies.EnumerateArray())
            {
                Require(dependency.ValueKind == JsonValueKind.String, "string_required");
                var dependencyId = dependency.GetString()!;
                Require(dependencyIds.Add(dependencyId), "duplicate_step_dependency");
                Require(seen.Contains(dependencyId), "invalid_step_dependency");
            }
            Require(seen.Add(id), "duplicate_step_id");
        }
        Require(Text(value, "plan_hash") == CanonicalJsonV2.HexHash(ProtocolV2Signatures.Project(value, "plan_hash", "signature")), "plan_hash_mismatch");
    }
    internal static void Outcome(JsonElement value)
    {
        Closed(value, "protocol plan_id plan_hash lease_id tenant_id device_id runtime_generation runtime_instance_id overall_status steps journal_sequence reported_at signature_algorithm device_key_id signature");
        Common(value);
        Text(value, "lease_id", Identity); Text(value, "device_key_id", Identity);
        Text(value, "overall_status", Status);
        Integer(value, "journal_sequence"); Timestamp(value, "reported_at");
        var seen = new HashSet<string>(StringComparer.Ordinal);
        foreach (var step in Steps(value))
        {
            Closed(step, "step_id started_at completed_at status result result_hash error_code reconciliation_state");
            Require(seen.Add(Text(step, "step_id", Identity)), "duplicate_step_result");
            Require(Timestamp(step, "completed_at") >= Timestamp(step, "started_at"), "step_completion_precedes_start");
            var status = Text(step, "status", Status);
            var resultHash = Text(step, "result_hash", Hash, nullable: true);
            var error = Text(step, "error_code", "[a-z0-9_.-]{1,128}", nullable: true);
            Text(step, "reconciliation_state", "not_required|pending|succeeded|failed_without_effect|manual_review_required");
            if (status == "succeeded")
            {
                Require(resultHash == CanonicalJsonV2.Hash(step.GetProperty("result")), "result_hash_mismatch");
                Require(error == null, "succeeded_step_has_error");
            }
            else Require(error != null, "error_code_required");
        }
    }
}
