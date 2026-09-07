using System.Numerics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Ai00.Connector.Contracts.V2;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class ProtocolV2VectorTests
{
    internal static JsonObject Vector => JsonNode.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory,
        "connector_execution_plan_v2.json")))!.AsObject();
    private static string Json(JsonNode? node) => node!.ToJsonString();

    [Fact]
    public void PythonPlanAndOutcomeVectorsVerifyAndCanonicalBytesMatch()
    {
        var v = Vector;
        var plan = ExecutionPlanV2.ParseAndVerify(Json(v["plan"]), Json(v["plan_public_jwk"]));
        Assert.Equal(v["plan"]!["plan_hash"]!.GetValue<string>(), plan.PlanHash);
        Assert.Equal(v["canonical_plan_without_hash_or_signature_hex"]!.GetValue<string>(),
            Convert.ToHexString(ProtocolV2Signatures.PlanHashBytes(Json(v["plan"]))).ToLowerInvariant());
        Assert.Equal(v["canonical_plan_without_signature_hex"]!.GetValue<string>(),
            Convert.ToHexString(ProtocolV2Signatures.SignatureBytes(Json(v["plan"]))).ToLowerInvariant());
        OutcomeV2.ParseAndVerify(Json(v["outcome"]), Json(v["device_public_jwk"]));
    }

    [Fact]
    public void FixtureRejectionsFailClosed()
    {
        var v = Vector;
        foreach (var entry in v["rejection_cases"]!.AsObject())
        {
            var plan = v["plan"]!.DeepClone().AsObject();
            plan[entry.Value!["field"]!.GetValue<string>()] = entry.Value["value"]!.DeepClone();
            Assert.Throws<ProtocolV2Exception>(() => ExecutionPlanV2.ParseAndVerify(Json(plan), Json(v["plan_public_jwk"])));
        }
    }

    [Fact]
    public void EveryPlanAndOutcomeFieldIsRequiredAndEveryObjectIsClosed()
    {
        var v = Vector;
        foreach (var record in new[] { "plan", "outcome" })
        {
            foreach (var path in record == "plan" ? new[] { "", "target_product", "steps" } : new[] { "", "steps" })
            {
                JsonObject At(JsonObject root) => path == "" ? root : path == "steps" ? root[path]![0]!.AsObject() : root[path]!.AsObject();
                var source = v[record]!.AsObject();
                foreach (var field in At(source).Select(p => p.Key).Append("unknown"))
                {
                    var changed = source.DeepClone().AsObject();
                    if (field == "unknown") At(changed)[field] = true;
                    else At(changed).Remove(field);
                    Assert.Throws<ProtocolV2Exception>(() => Validate(record, Json(changed)));
                }
            }
        }
    }

    [Theory]
    [InlineData("major_version", "\"2\"")]
    [InlineData("major_version", "2.0")]
    [InlineData("runtime_generation", "true")]
    [InlineData("runtime_generation", "0")]
    [InlineData("issued_at", "\"2026-09-07T01:02:03+00:00\"")]
    [InlineData("issued_at", "\"2026-09-07T01:02:03.00000001Z\"")]
    [InlineData("issued_at", "\"2026-02-30T01:02:03Z\"")]
    [InlineData("plan_hash", "\"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\"")]
    public void PlanRejectsCoercionAndMalformedValues(string field, string value)
    {
        var plan = Vector["plan"]!.DeepClone();
        plan![field] = JsonNode.Parse(value);
        Assert.Throws<ProtocolV2Exception>(() => Validate("plan", Json(plan)));
    }

    [Fact]
    public void DuplicateMembersAndMalformedJsonFailClosed()
    {
        var plan = Json(Vector["plan"]);
        foreach (var bad in new[] { "null", "[]", "{", plan.Replace("\"plan_id\":", "\"plan_id\":\"duplicate\",\"plan_id\":"),
            plan.Replace("\"allow_launch\":", "\"allow_launch\":false,\"allow_launch\":") })
            Assert.Throws<ProtocolV2Exception>(() => Validate("plan", bad));
    }

    [Fact]
    public void OnlyCanonicalPublicP256JwkIsAccepted()
    {
        var v = Vector;
        foreach (var field in new[] { "d", "kid", "crv", "x", "y" })
        {
            var jwk = v["plan_public_jwk"]!.DeepClone();
            jwk![field] = field == "crv" ? "P-384" : "invalid";
            Assert.Throws<ProtocolV2Exception>(() => ExecutionPlanV2.ParseAndVerify(Json(v["plan"]), Json(jwk)));
        }
        Assert.Throws<ProtocolV2Exception>(() => ExecutionPlanV2.ParseAndVerify(Json(v["plan"]), Json(v["device_public_jwk"])));
    }

    [Theory]
    [InlineData("[333333333.33333329,1e30,4.50,2e-3,1e-27,-0.0]", "[333333333.3333333,1e+30,4.5,0.002,1e-27,0]")]
    [InlineData("[1e20,100000000000000000000,9007199254740992,1e-6,1e-7]", "[100000000000000000000,100000000000000000000,9007199254740992,0.000001,1e-7]")]
    [InlineData("{\"\\ue000\":1,\"\\ud800\\udc00\":2}", "{\"𐀀\":2,\"\":1}")]
    [InlineData("{\"text\":\"é中文<>&/\\n\\u000f\"}", "{\"text\":\"é中文<>&/\\n\\u000f\"}")]
    public void JcsMatchesPythonNumberAndUnicodeRules(string json, string expected)
    {
        Assert.Equal(expected, Encoding.UTF8.GetString(CanonicalJsonV2.Serialize(json)));
        Assert.Equal(expected, Encoding.UTF8.GetString(CanonicalJsonV2.Serialize(expected)));
    }

    [Theory]
    [InlineData("9007199254740993")]
    [InlineData("1e400")]
    [InlineData("\"\\ud800\"")]
    [InlineData("{\"\\udfff\":1}")]
    [InlineData("{\"a\":1,\"a\":2}")]
    public void JcsRejectsLossyIntegersNonfiniteSurrogatesAndDuplicates(string json) =>
        Assert.Throws<ProtocolV2Exception>(() => CanonicalJsonV2.Serialize(json));

    [Fact]
    public void PlanUsesExact100nsTimestampOrderingAndPreservesLargePayloadInteger()
    {
        var plan = Vector["plan"]!.DeepClone().AsObject();
        plan["issued_at"] = "2026-09-07T01:02:03.0000001Z";
        plan["expires_at"] = "2026-09-07T01:02:03.0000002Z";
        plan["steps"]![0]!["payload"] = JsonNode.Parse("{\"number\":100000000000000000000}");
        plan["steps"]![0]!["payload_hash"] = "sha256:" + Hash(CanonicalJsonV2.Serialize(Json(plan["steps"]![0]!["payload"])));
        using var key = TestKey("plan");
        SignPlan(plan, key);
        ExecutionPlanV2.ParseAndVerify(Json(plan), Json(Vector["plan_public_jwk"]));
        plan["issued_at"] = "2026-09-07T01:02:03.1Z";
        plan["expires_at"] = "2026-09-07T01:02:03.1000000Z";
        SignPlan(plan, key);
        Assert.Throws<ProtocolV2Exception>(() => Validate("plan", Json(plan)));
    }

    [Theory]
    [InlineData("dependency")]
    [InlineData("duplicate_dependency")]
    [InlineData("payload_hash")]
    [InlineData("probe")]
    [InlineData("timeout")]
    [InlineData("range")]
    [InlineData("steps")]
    public void ResignedInvalidPlansStillFailSchemaValidation(string change)
    {
        var plan = Vector["plan"]!.DeepClone().AsObject();
        var step = plan["steps"]![0]!;
        switch (change)
        {
            case "dependency": step["depends_on"] = new JsonArray("step-00001"); break;
            case "duplicate_dependency": step["depends_on"] = new JsonArray("prior", "prior"); break;
            case "payload_hash": step["payload_hash"] = "sha256:" + new string('0', 64); break;
            case "probe": step["side_effect_classification"] = "write"; break;
            case "timeout": step["timeout_seconds"] = 901; break;
            case "range": plan["target_product"]!["minimum_version"] = "15.0.0"; break;
            case "steps": plan["steps"] = new JsonArray(); break;
        }
        using var key = TestKey("plan");
        SignPlan(plan, key);
        Assert.Throws<ProtocolV2Exception>(() => Validate("plan", Json(plan)));
    }

    [Fact]
    public void OutcomeSignerCreatesLowSSignatureAndRejectsInvalidResult()
    {
        using var key = TestKey("device");
        var outcome = Vector["outcome"]!.DeepClone().AsObject();
        outcome.Remove("signature");
        var signed = OutcomeV2Signer.Sign(Json(outcome), key);
        var parsed = OutcomeV2.ParseAndVerify(signed, Json(Vector["device_public_jwk"]));
        Assert.Equal("succeeded", parsed.OverallStatus);
        // Independent BCL verification of the actual signature and fixture key.
        var node = JsonNode.Parse(signed)!;
        var signature = Decode(node["signature"]!.GetValue<string>());
        Assert.Equal(64, signature.Length);
        Assert.True(new BigInteger(signature.AsSpan(32), true, true) <= Order / 2);
        Assert.True(key.VerifyData(ProtocolV2Signatures.SignatureBytes(signed), signature,
            HashAlgorithmName.SHA256, DSASignatureFormat.IeeeP1363FixedFieldConcatenation));
        outcome["steps"]![0]!["result_hash"] = "sha256:" + new string('0', 64);
        Assert.Throws<ProtocolV2Exception>(() => OutcomeV2Signer.Sign(Json(outcome), key));
    }

    [Theory]
    [InlineData("time")]
    [InlineData("error")]
    [InlineData("status")]
    [InlineData("duplicate")]
    [InlineData("unknown")]
    public void OutcomeSignerRejectsMalformedClosedRecords(string change)
    {
        using var key = TestKey("device");
        var outcome = Vector["outcome"]!.DeepClone().AsObject();
        outcome.Remove("signature");
        var step = outcome["steps"]![0]!;
        switch (change)
        {
            case "time": step["started_at"] = "2026-09-07T01:02:05.0000002Z"; step["completed_at"] = "2026-09-07T01:02:05.0000001Z"; break;
            case "error": step["error_code"] = "unexpected"; break;
            case "status": step["status"] = "failed_without_effect"; break;
            case "duplicate": outcome["steps"]!.AsArray().Add(step.DeepClone()); break;
            case "unknown": outcome["unknown"] = true; break;
        }
        Assert.Throws<ProtocolV2Exception>(() => OutcomeV2Signer.Sign(Json(outcome), key));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void JcsDepthCountsRootArrayAndObjectAsOne(bool objectRoot)
    {
        var accepted = NestedContainers(64, objectRoot);
        Assert.Equal(accepted, Encoding.UTF8.GetString(CanonicalJsonV2.Serialize(accepted)));
        var rejected = NestedContainers(65, objectRoot);
        Assert.Throws<ProtocolV2Exception>(() => CanonicalJsonV2.Serialize(rejected));
        using var document = JsonDocument.Parse(rejected, new JsonDocumentOptions { MaxDepth = 128 });
        Assert.Throws<ProtocolV2Exception>(() => CanonicalJsonV2.Serialize(document.RootElement));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void PlanAndOutcomeDepthIncludesRecordStepsArrayAndStep(bool objectRoot)
    {
        var v = Vector;
        var plan = v["plan"]!.DeepClone().AsObject();
        var payload = NestedContainers(61, objectRoot);
        plan["steps"]![0]!["payload"] = JsonNode.Parse(payload);
        plan["steps"]![0]!["payload_hash"] = "sha256:" + Hash(Encoding.UTF8.GetBytes(payload));
        using var planKey = TestKey("plan");
        SignPlan(plan, planKey);
        var planJson = Json(plan);
        ExecutionPlanV2.ParseAndVerify(planJson, Json(v["plan_public_jwk"]));
        Assert.Equal(64, ContainerDepth(JsonDocument.Parse(planJson).RootElement));
        var tooDeepPlan = planJson.Replace(payload, NestedContainers(62, objectRoot), StringComparison.Ordinal);
        Assert.Throws<ProtocolV2Exception>(() => ExecutionPlanV2.ParseAndVerify(tooDeepPlan, Json(v["plan_public_jwk"])));
        Assert.Throws<ProtocolV2Exception>(() => ProtocolV2Signatures.PlanHashBytes(tooDeepPlan));
        Assert.Throws<ProtocolV2Exception>(() => ProtocolV2Signatures.SignatureBytes(tooDeepPlan));

        var outcome = v["outcome"]!.DeepClone().AsObject();
        outcome.Remove("signature");
        outcome["steps"]![0]!["result"] = JsonNode.Parse(payload);
        outcome["steps"]![0]!["result_hash"] = "sha256:" + Hash(Encoding.UTF8.GetBytes(payload));
        using var outcomeKey = TestKey("device");
        var signed = OutcomeV2Signer.Sign(Json(outcome), outcomeKey);
        OutcomeV2.ParseAndVerify(signed, Json(v["device_public_jwk"]));
        Assert.Equal(64, ContainerDepth(JsonDocument.Parse(signed).RootElement));
        var tooDeepOutcome = Json(outcome).Replace(payload, NestedContainers(62, objectRoot), StringComparison.Ordinal);
        Assert.Throws<ProtocolV2Exception>(() => OutcomeV2Signer.Sign(tooDeepOutcome, outcomeKey));
        Assert.Throws<ProtocolV2Exception>(() => OutcomeV2.ParseAndVerify(
            signed.Replace(payload, NestedContainers(62, objectRoot), StringComparison.Ordinal), Json(v["device_public_jwk"])));
    }

    private static string NestedContainers(int depth, bool objectRoot) =>
        string.Concat(Enumerable.Repeat(objectRoot ? "{\"nested\":" : "[", depth)) + "0" +
        string.Concat(Enumerable.Repeat(objectRoot ? "}" : "]", depth));

    private static int ContainerDepth(JsonElement value) => value.ValueKind switch
    {
        JsonValueKind.Object => 1 + value.EnumerateObject().Select(p => ContainerDepth(p.Value)).DefaultIfEmpty(0).Max(),
        JsonValueKind.Array => 1 + value.EnumerateArray().Select(ContainerDepth).DefaultIfEmpty(0).Max(),
        _ => 0,
    };

    internal static readonly BigInteger Order = BigInteger.Parse("0FFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551", System.Globalization.NumberStyles.HexNumber);
    internal static byte[] Decode(string value) => Convert.FromBase64String(value.Replace('-', '+').Replace('_', '/') + new string('=', (4 - value.Length % 4) % 4));
    internal static string Encode(byte[] value) => Convert.ToBase64String(value).TrimEnd('=').Replace('+', '-').Replace('/', '_');
    internal static ECDsa TestKey(string name)
    {
        var jwk = Vector["test_only_private_keys"]![name + "_private_jwk"]!;
        return ECDsa.Create(new ECParameters { Curve = ECCurve.NamedCurves.nistP256,
            Q = new ECPoint { X = Decode(jwk["x"]!.GetValue<string>()), Y = Decode(jwk["y"]!.GetValue<string>()) },
            D = Decode(jwk["d"]!.GetValue<string>()) });
    }
    private static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    internal static void SignPlan(JsonObject plan, ECDsa key)
    {
        plan["plan_hash"] = Hash(ProtocolV2Signatures.PlanHashBytes(Json(plan)));
        var raw = key.SignData(ProtocolV2Signatures.SignatureBytes(Json(plan)), HashAlgorithmName.SHA256,
            DSASignatureFormat.IeeeP1363FixedFieldConcatenation);
        var s = new BigInteger(raw.AsSpan(32), true, true);
        if (s > Order / 2)
        {
            Array.Clear(raw, 32, 32);
            var low = (Order - s).ToByteArray(true, true);
            low.CopyTo(raw, 64 - low.Length);
        }
        plan["signature"] = Encode(raw);
    }
    private static void Validate(string record, string json)
    {
        var v = Vector;
        if (record == "plan") ExecutionPlanV2.ParseAndVerify(json, Json(v["plan_public_jwk"]));
        else OutcomeV2.ParseAndVerify(json, Json(v["device_public_jwk"]));
    }
}
