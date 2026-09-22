using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace Ai00.Connector.Contracts.V2;

public sealed class ViewerInteractionGrant : ProtocolV2Record
{
    public const string ProtocolName="ai00.viewer.interaction.grant.v1";
    private ViewerInteractionGrant(JsonElement value):base(value) { }
    public string GrantId=>Text("grant_id");
    public long Generation=>Document.GetProperty("grant_generation").GetInt64();
    public string SessionNonce=>Text("session_nonce");
    public string DeviceId=>Text("device_id");
    public string TenantId=>Text("tenant_id");
    public string RuntimeInstanceId=>Text("runtime_instance_id");
    public string SourceAssociationId=>Text("source_association_id");
    public string DocumentSession=>Text("document_session");
    public DateTimeOffset IssuedAt=>ProtocolV2Schema.Timestamp(Document,"issued_at");
    public DateTimeOffset ExpiresAt=>ProtocolV2Schema.Timestamp(Document,"expires_at");
    public string KeyId=>Text("key_id");
    public JsonElement Operations=>Document.GetProperty("operations");
    public static ViewerInteractionGrant ParseAndVerify(string json,string publicJwk)
    {
        ProtocolV2Schema.Require(Encoding.UTF8.GetByteCount(json)<=65536,"grant_size_invalid");
        var value=CanonicalJsonV2.Parse(json);
        ProtocolV2Schema.Closed(value,"protocol grant_id grant_generation session_nonce actor_id tenant_id device_id runtime_instance_id workspace_gid document_gid source_association_id document_session operations policy_version issued_at expires_at audience key_id signature");
        ProtocolV2Schema.Require(ProtocolV2Schema.Text(value,"protocol")==ProtocolName && ProtocolV2Schema.Text(value,"audience")=="ai00.connector.viewer-interaction","grant_purpose_invalid");
        foreach(var field in new[]{"grant_id","actor_id","tenant_id","device_id","runtime_instance_id","source_association_id","policy_version","key_id"})
            ProtocolV2Schema.Text(value,field,"[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,255}");
        foreach(var field in new[]{"workspace_gid","document_gid"})ProtocolV2Schema.Text(value,field,"[1-9][0-9]{0,19}");
        ProtocolV2Schema.Text(value,"session_nonce","[0-9a-f]{64}");
        ProtocolV2Schema.Text(value,"document_session","sha256:[0-9a-f]{64}");
        var generation=value.GetProperty("grant_generation");
        ProtocolV2Schema.Require(generation.TryGetInt64(out var number)&&number is >=1 and <=9007199254740991,"grant_generation_invalid");
        var issued=ProtocolV2Schema.Timestamp(value,"issued_at");var expires=ProtocolV2Schema.Timestamp(value,"expires_at");
        ProtocolV2Schema.Require(expires>issued && expires-issued<=TimeSpan.FromSeconds(60),"grant_interval_invalid");
        var operations=value.GetProperty("operations");
        ProtocolV2Schema.Require(operations.ValueKind==JsonValueKind.Array && operations.GetArrayLength() is >=1 and <=2,"grant_operations_invalid");
        var seen=new HashSet<string>(StringComparer.Ordinal);
        foreach(var op in operations.EnumerateArray())
        {
            ProtocolV2Schema.Closed(op,"id contract_hash");
            var id=ProtocolV2Schema.Text(op,"id");
            ProtocolV2Schema.Require(id is "vismockup.node.visibility.change@1" or "vismockup.node.selection.change@1" && seen.Add(id),"grant_operation_invalid");
            ProtocolV2Schema.Text(op,"contract_hash","sha256:[0-9a-f]{64}");
        }
        var jwk=CanonicalJsonV2.Parse(publicJwk);ProtocolV2Schema.Closed(jwk,"kty crv x y");
        ProtocolV2Schema.Require(ProtocolV2Schema.Text(jwk,"kty")=="EC" && ProtocolV2Schema.Text(jwk,"crv")=="P-256","p256_public_jwk_required");
        using var key=ECDsa.Create(new ECParameters{Curve=ECCurve.NamedCurves.nistP256,Q=new ECPoint{
            X=ProtocolV2Signatures.Decode(ProtocolV2Schema.Text(jwk,"x"),32),Y=ProtocolV2Signatures.Decode(ProtocolV2Schema.Text(jwk,"y"),32)}});
        byte[] data=[..Encoding.UTF8.GetBytes(ProtocolName+"\n"),..ProtocolV2Signatures.Project(value,"signature")];
        ProtocolV2Schema.Require(key.VerifyData(data,ProtocolV2Signatures.DecodeSignature(ProtocolV2Schema.Text(value,"signature")),HashAlgorithmName.SHA256,DSASignatureFormat.IeeeP1363FixedFieldConcatenation),"signature_invalid");
        return new(value);
    }
}
