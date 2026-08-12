using System.Security.Cryptography;
using System.Text.Json;
using Ai00.LocalRuntime.Contracts;
using Xunit;

namespace Ai00.LocalRuntime.Tests;

public sealed class CanonicalJsonTests
{
    [Fact]
    public void PythonAndDotnetShareCanonicalPayloadHashAndEnvelopeSignature()
    {
        using var vectors = JsonDocument.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "device_protocol_vectors.json")));
        var vector = vectors.RootElement.GetProperty("vectors")[0];
        var operation = vector.GetProperty("envelope").Deserialize<OperationEnvelope>()!;
        var payloadHash = "sha256:" + Convert.ToHexString(SHA256.HashData(CanonicalJson.Serialize(operation.Payload))).ToLowerInvariant();
        Assert.Equal(vector.GetProperty("payload_hash").GetString(), payloadHash);
        Assert.Equal(vector.GetProperty("signature").GetString(), PipeSecurity.Sign(operation, vector.GetProperty("secret").GetString()!));
        var outcome = vector.GetProperty("outcome").Deserialize<OperationOutcome>()!;
        Assert.Equal(vector.GetProperty("outcome_signature").GetString(), OutcomeSecurity.Sign(outcome, vector.GetProperty("secret").GetString()!));
    }
}
