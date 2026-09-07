using System.Globalization;
using System.Numerics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace Ai00.Connector.Contracts.V2;

public static class ProtocolV2Signatures
{
    internal static readonly BigInteger Order = BigInteger.Parse("0FFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551", NumberStyles.HexNumber);
    public static byte[] PlanHashBytes(string json) => Project(CanonicalJsonV2.Parse(json), "plan_hash", "signature");
    public static byte[] SignatureBytes(string json) => Project(CanonicalJsonV2.Parse(json), "signature");
    internal static byte[] Project(JsonElement value, params string[] excluded)
    {
        ProtocolV2Schema.Require(value.ValueKind == JsonValueKind.Object, "object_required");
        var projected = value.EnumerateObject().Where(p => !excluded.Contains(p.Name)).ToDictionary(p => p.Name, p => p.Value);
        return CanonicalJsonV2.Serialize(JsonSerializer.SerializeToElement(projected));
    }
    internal static string Encode(byte[] bytes) => Convert.ToBase64String(bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_');
    internal static byte[] Decode(string value, int length)
    {
        ProtocolV2Schema.Require(Regex.IsMatch(value, "\\A[A-Za-z0-9_-]+\\z"), "unpadded_base64url_required");
        byte[] bytes;
        try { bytes = Convert.FromBase64String(value.Replace('-', '+').Replace('_', '/') + new string('=', (4 - value.Length % 4) % 4)); }
        catch (FormatException error) { throw new ProtocolV2Exception("invalid_base64url", error); }
        ProtocolV2Schema.Require(bytes.Length == length && Encode(bytes) == value, "non_canonical_base64url");
        return bytes;
    }
    internal static byte[] DecodeSignature(string signature)
    {
        var bytes = Decode(signature, 64);
        var r = new BigInteger(bytes.AsSpan(0, 32), true, true);
        var s = new BigInteger(bytes.AsSpan(32), true, true);
        ProtocolV2Schema.Require(r > 0 && r < Order && s > 0 && s <= Order / 2, "low_s_p1363_signature_required");
        return bytes;
    }
    internal static void Verify(JsonElement value, string publicJwk)
    {
        var jwk = CanonicalJsonV2.Parse(publicJwk);
        ProtocolV2Schema.Closed(jwk, "kty crv x y");
        ProtocolV2Schema.Require(ProtocolV2Schema.Text(jwk, "kty") == "EC" && ProtocolV2Schema.Text(jwk, "crv") == "P-256", "p256_public_jwk_required");
        try
        {
            using var key = ECDsa.Create(new ECParameters { Curve = ECCurve.NamedCurves.nistP256,
                Q = new ECPoint { X = Decode(ProtocolV2Schema.Text(jwk, "x"), 32), Y = Decode(ProtocolV2Schema.Text(jwk, "y"), 32) } });
            ProtocolV2Schema.Require(key.VerifyData(Project(value, "signature"), DecodeSignature(value.GetProperty("signature").GetString()!),
                HashAlgorithmName.SHA256, DSASignatureFormat.IeeeP1363FixedFieldConcatenation), "signature_invalid");
        }
        catch (CryptographicException error) { throw new ProtocolV2Exception("public_key_invalid", error); }
    }
    internal static string Sign(byte[] data, ECDsa key)
    {
        // Export only public parameters, including when called with a CNG key.
        ProtocolV2Schema.Require(key.ExportParameters(false).Curve.Oid.Value == "1.2.840.10045.3.1.7", "p256_key_required");
        var bytes = key.SignData(data, HashAlgorithmName.SHA256, DSASignatureFormat.IeeeP1363FixedFieldConcatenation);
        var s = new BigInteger(bytes.AsSpan(32), true, true);
        if (s > Order / 2)
        {
            Array.Clear(bytes, 32, 32);
            var low = (Order - s).ToByteArray(true, true);
            low.CopyTo(bytes, 64 - low.Length);
        }
        return Encode(bytes);
    }
    internal static JsonElement PublicJwk(ECDsa key)
    {
        var parameters = key.ExportParameters(false);
        return JsonSerializer.SerializeToElement(new { kty = "EC", crv = "P-256", x = Encode(parameters.Q.X!), y = Encode(parameters.Q.Y!) });
    }
}

public static class OutcomeV2Signer
{
    /// <summary>Accepts the complete unsigned Outcome, with signature omitted. Hashes must already match results.</summary>
    public static string Sign(string unsignedJson, DeviceSigningKey key) => SignCore(unsignedJson, key.Sign);
    public static string Sign(string unsignedJson, ECDsa key) => SignCore(unsignedJson, data => ProtocolV2Signatures.Sign(data, key));
    private static string SignCore(string unsignedJson, Func<byte[], string> sign)
    {
        var original = CanonicalJsonV2.Parse(unsignedJson);
        ProtocolV2Schema.Require(original.ValueKind == JsonValueKind.Object && !original.TryGetProperty("signature", out _), "unsigned_outcome_required");
        var value = JsonNode.Parse(original.GetRawText())!.AsObject();
        var placeholder = new byte[64]; placeholder[31] = placeholder[63] = 1;
        value["signature"] = ProtocolV2Signatures.Encode(placeholder);
        var validated = CanonicalJsonV2.Parse(value.ToJsonString());
        ProtocolV2Schema.Outcome(validated);
        value["signature"] = sign(ProtocolV2Signatures.Project(validated, "signature"));
        return Encoding.UTF8.GetString(CanonicalJsonV2.Serialize(value.ToJsonString()));
    }
}
