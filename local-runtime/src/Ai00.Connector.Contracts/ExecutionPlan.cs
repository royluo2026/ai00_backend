using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Ai00.Connector.Contracts;

public sealed record ConnectorTargetProduct(
    [property: JsonPropertyName("product_id")] string ProductId,
    [property: JsonPropertyName("minimum_version")] string MinimumVersion,
    [property: JsonPropertyName("maximum_version_exclusive")] string MaximumVersionExclusive);

public sealed record ConnectorStep(
    [property: JsonPropertyName("step_id")] string StepId,
    [property: JsonPropertyName("operation_id")] string OperationId,
    [property: JsonPropertyName("contract_hash")] string ContractHash,
    [property: JsonPropertyName("depends_on")] IReadOnlyList<string> DependsOn,
    [property: JsonPropertyName("payload")] JsonElement Payload,
    [property: JsonPropertyName("payload_hash")] string PayloadHash,
    [property: JsonPropertyName("timeout_seconds")] int TimeoutSeconds)
{
    public object CanonicalDocument() => new Dictionary<string, object?>
    {
        ["step_id"] = StepId,
        ["operation_id"] = OperationId,
        ["contract_hash"] = ContractHash,
        ["depends_on"] = DependsOn,
        ["payload"] = Payload,
        ["payload_hash"] = PayloadHash,
        ["timeout_seconds"] = TimeoutSeconds,
    };
}

public sealed record ConnectorExecutionPlan(
    [property: JsonPropertyName("protocol")] string Protocol,
    [property: JsonPropertyName("plan_id")] string PlanId,
    [property: JsonPropertyName("tenant_id")] string TenantId,
    [property: JsonPropertyName("user_id")] string UserId,
    [property: JsonPropertyName("device_id")] string DeviceId,
    [property: JsonPropertyName("capability_version_gid")] string CapabilityVersionGid,
    [property: JsonPropertyName("business_definition_hash")] string BusinessDefinitionHash,
    [property: JsonPropertyName("adapter_id")] string AdapterId,
    [property: JsonPropertyName("adapter_major")] int AdapterMajor,
    [property: JsonPropertyName("target_product")] ConnectorTargetProduct TargetProduct,
    [property: JsonPropertyName("steps")] IReadOnlyList<ConnectorStep> Steps,
    [property: JsonPropertyName("issued_at")] DateTimeOffset IssuedAt,
    [property: JsonPropertyName("expires_at")] DateTimeOffset ExpiresAt,
    [property: JsonPropertyName("plan_hash")] string PlanHash)
{
    public const string ProtocolVersion = "ai00.connector.execution-plan.v1";

    public object CanonicalDocument(bool includeHash = false)
    {
        var document = new Dictionary<string, object?>
        {
            ["protocol"] = Protocol,
            ["plan_id"] = PlanId,
            ["tenant_id"] = TenantId,
            ["user_id"] = UserId,
            ["device_id"] = DeviceId,
            ["capability_version_gid"] = CapabilityVersionGid,
            ["business_definition_hash"] = BusinessDefinitionHash,
            ["adapter_id"] = AdapterId,
            ["adapter_major"] = AdapterMajor,
            ["target_product"] = new Dictionary<string, object?>
            {
                ["product_id"] = TargetProduct.ProductId,
                ["minimum_version"] = TargetProduct.MinimumVersion,
                ["maximum_version_exclusive"] = TargetProduct.MaximumVersionExclusive,
            },
            ["steps"] = Steps.Select(item => item.CanonicalDocument()).ToArray(),
            ["issued_at"] = CanonicalJson.UtcTimestamp(IssuedAt),
            ["expires_at"] = CanonicalJson.UtcTimestamp(ExpiresAt),
        };
        if (includeHash) document["plan_hash"] = PlanHash;
        return document;
    }

    public string ComputeHash() => CanonicalJson.Hash(CanonicalDocument());
}

public sealed record PlanValidationContext(
    string DeviceId,
    string UserId,
    DateTimeOffset UtcNow,
    string KeyId,
    string Signature,
    IReadOnlyDictionary<string, string> SigningKeys);

public sealed record PlanValidationResult(bool IsValid, string ErrorCode)
{
    public static PlanValidationResult Success() => new(true, "");
    public static PlanValidationResult Fail(string code) => new(false, code);
}

public static class PlanSecurity
{
    public static string Sign(ConnectorExecutionPlan plan, string secret)
    {
        if (Encoding.UTF8.GetByteCount(secret) < 32)
            throw new InvalidOperationException("Plan secret must contain at least 32 UTF-8 bytes");
        using var hmac = new HMACSHA256(Encoding.UTF8.GetBytes(secret));
        return "hmac-sha256:" + Convert.ToHexString(hmac.ComputeHash(CanonicalJson.Serialize(plan.CanonicalDocument(true)))).ToLowerInvariant();
    }

    public static bool Verify(ConnectorExecutionPlan plan, PlanValidationContext context)
    {
        if (!context.SigningKeys.TryGetValue(context.KeyId, out var secret)) return false;
        var expected = Encoding.ASCII.GetBytes(Sign(plan, secret));
        var actual = Encoding.ASCII.GetBytes(context.Signature ?? "");
        return expected.Length == actual.Length && CryptographicOperations.FixedTimeEquals(expected, actual);
    }
}

public static class PlanValidator
{
    public static PlanValidationResult Validate(
        ConnectorExecutionPlan plan,
        AdapterManifest manifest,
        PlanValidationContext context)
    {
        if (plan.Protocol != ConnectorExecutionPlan.ProtocolVersion)
            return PlanValidationResult.Fail("connector_version_incompatible");
        if (plan.ComputeHash() != plan.PlanHash)
            return PlanValidationResult.Fail("plan_hash_mismatch");
        if (!ValidateSteps(plan, out var stepError))
            return PlanValidationResult.Fail(stepError);
        if (!PlanSecurity.Verify(plan, context))
            return PlanValidationResult.Fail("plan_signature_invalid");
        if (plan.ExpiresAt <= context.UtcNow || plan.ExpiresAt <= plan.IssuedAt)
            return PlanValidationResult.Fail("plan_expired");
        if (plan.DeviceId != context.DeviceId || plan.UserId != context.UserId)
            return PlanValidationResult.Fail("plan_identity_mismatch");
        if (plan.AdapterId != manifest.AdapterId || plan.AdapterMajor != manifest.AdapterMajor)
            return PlanValidationResult.Fail("adapter_unavailable");
        if (plan.TargetProduct.ProductId != manifest.ProductId ||
            CompareVersions(manifest.ProductVersion, plan.TargetProduct.MinimumVersion) < 0 ||
            CompareVersions(manifest.ProductVersion, plan.TargetProduct.MaximumVersionExclusive) >= 0)
            return PlanValidationResult.Fail("connector_version_incompatible");
        foreach (var step in plan.Steps)
        {
            if (!manifest.HasOperation(step.OperationId))
                return PlanValidationResult.Fail("adapter_operation_not_allowed");
            if (!manifest.Supports(step.OperationId, step.ContractHash))
                return PlanValidationResult.Fail("adapter_contract_mismatch");
        }
        return PlanValidationResult.Success();
    }

    private static bool ValidateSteps(ConnectorExecutionPlan plan, out string error)
    {
        if (plan.Steps.Count is < 1 or > 10_000)
        { error = "step_count_invalid"; return false; }
        var seen = new HashSet<string>(StringComparer.Ordinal);
        foreach (var step in plan.Steps)
        {
            if (!seen.Add(step.StepId)) { error = "duplicate_step_id"; return false; }
            if (step.DependsOn.Count != step.DependsOn.Distinct(StringComparer.Ordinal).Count())
            { error = "duplicate_step_dependency"; return false; }
            if (step.DependsOn.Any(item => !seen.Contains(item)))
            { error = "invalid_step_dependency"; return false; }
            if (CanonicalJson.Hash(step.Payload) != step.PayloadHash)
            { error = "payload_hash_mismatch"; return false; }
            if (step.TimeoutSeconds is < 1 or > 900)
            { error = "step_timeout_invalid"; return false; }
        }
        error = "";
        return true;
    }

    private static int CompareVersions(string left, string right)
    {
        static int[] Parse(string value) => value.Split('.').Select(int.Parse).Concat([0, 0, 0, 0]).Take(4).ToArray();
        var a = Parse(left);
        var b = Parse(right);
        for (var index = 0; index < 4; index++)
        {
            var result = a[index].CompareTo(b[index]);
            if (result != 0) return result;
        }
        return 0;
    }
}
