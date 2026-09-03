using System.Text.Json;
using Ai00.Connector.Contracts;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class ExecutionPlanVectorTests
{
    private static ConnectorExecutionPlan LoadPlan()
    {
        using var vector = JsonDocument.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "connector_execution_plan_v1.json")));
        return vector.RootElement.GetProperty("plan").Deserialize<ConnectorExecutionPlan>()!;
    }

    [Fact]
    public void PythonPlanVectorHasIdenticalCanonicalHash()
    {
        var plan = LoadPlan();
        Assert.Equal("sha256:5ea603d81f75cf818269f050254afb60e324493c4a5faecdacbca7a31a4278b4", plan.ComputeHash());
    }

    [Fact]
    public void UnknownOperationIsRejectedBeforeAnyAdapterCall()
    {
        var plan = LoadPlan();
        var step = plan.Steps[0] with { OperationId = "vismockup.raw.com@1" };
        var unhashed = plan with { Steps = [step] };
        var changed = unhashed with { PlanHash = unhashed.ComputeHash() };
        var result = PlanValidator.Validate(changed, TestManifest(), Context(changed));
        Assert.Equal("adapter_operation_not_allowed", result.ErrorCode);
    }

    [Fact]
    public void WrongIdentityExpiryAndSignatureAreRejected()
    {
        var plan = LoadPlan();
        Assert.Equal("plan_identity_mismatch", PlanValidator.Validate(plan, TestManifest(), Context(plan) with { DeviceId = "other" }).ErrorCode);
        Assert.Equal("plan_expired", PlanValidator.Validate(plan, TestManifest(), Context(plan) with { UtcNow = plan.ExpiresAt }).ErrorCode);
        Assert.Equal("plan_signature_invalid", PlanValidator.Validate(plan, TestManifest(), Context(plan) with { Signature = "hmac-sha256:" + new string('0', 64) }).ErrorCode);
    }

    [Fact]
    public void TamperedPayloadAndDuplicateStepAreRejected()
    {
        var plan = LoadPlan();
        using var changedPayload = JsonDocument.Parse("{\"changed\":true}");
        var tamperedStep = plan.Steps[0] with { Payload = changedPayload.RootElement.Clone() };
        var tampered = plan with { Steps = [tamperedStep] };
        tampered = tampered with { PlanHash = tampered.ComputeHash() };
        Assert.Equal("payload_hash_mismatch", PlanValidator.Validate(tampered, TestManifest(), Context(tampered)).ErrorCode);

        var duplicate = plan with { Steps = [plan.Steps[0], plan.Steps[0]] };
        duplicate = duplicate with { PlanHash = duplicate.ComputeHash() };
        Assert.Equal("duplicate_step_id", PlanValidator.Validate(duplicate, TestManifest(), Context(duplicate)).ErrorCode);
    }

    private static AdapterManifest TestManifest() => new(
        "ai00.vismockup", 1, "siemens.vismockup", "14.2.0",
        [new AdapterOperationContract("vismockup.application.probe@1", "sha256:" + new string('1', 64))]);

    private static PlanValidationContext Context(ConnectorExecutionPlan plan)
    {
        const string secret = "0123456789abcdef0123456789abcdef";
        return new(plan.DeviceId, plan.UserId, plan.IssuedAt.AddMinutes(1), "key-1", PlanSecurity.Sign(plan, secret), new Dictionary<string, string> { ["key-1"] = secret });
    }
}
