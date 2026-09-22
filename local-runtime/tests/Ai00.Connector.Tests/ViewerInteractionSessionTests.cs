using System.Text.Json;
using Ai00.Connector.Contracts.V2;
using Ai00.Connector.AppHost;
using Xunit;

namespace Ai00.Connector.Tests;

public class ViewerInteractionSessionTests
{
    internal static ViewerInteractionGrant Resign(Action<System.Text.Json.Nodes.JsonObject> mutate)=>SignFixture(mutate).Grant;
    internal static (ViewerInteractionGrant Grant,string PublicJwk) SignFixture(Action<System.Text.Json.Nodes.JsonObject> mutate)
    {
        using var fixture=JsonDocument.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory,"viewer_interaction_v1.json")));
        var grant=System.Text.Json.Nodes.JsonNode.Parse(fixture.RootElement.GetProperty("grant").GetRawText())!.AsObject();
        grant.Remove("signature");mutate(grant);
        using var key=System.Security.Cryptography.ECDsa.Create(System.Security.Cryptography.ECCurve.NamedCurves.nistP256);
        var data=System.Text.Encoding.UTF8.GetBytes("ai00.viewer.interaction.grant.v1\n").Concat(CanonicalJsonV2.Serialize(grant.ToJsonString())).ToArray();
        var signature=key.SignData(data,System.Security.Cryptography.HashAlgorithmName.SHA256,System.Security.Cryptography.DSASignatureFormat.IeeeP1363FixedFieldConcatenation);
        var order=System.Numerics.BigInteger.Parse("0FFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551",System.Globalization.NumberStyles.HexNumber);
        var s=new System.Numerics.BigInteger(signature.AsSpan(32),true,true);
        if(s>order/2){Array.Clear(signature,32,32);var low=(order-s).ToByteArray(true,true);low.CopyTo(signature,64-low.Length);}
        string Encode(byte[] b)=>Convert.ToBase64String(b).TrimEnd('=').Replace('+','-').Replace('/','_');
        grant["signature"]=Encode(signature);var pub=key.ExportParameters(false);
        var jwk=JsonSerializer.Serialize(new{kty="EC",crv="P-256",x=Encode(pub.Q.X!),y=Encode(pub.Q.Y!)});
        return (ViewerInteractionGrant.ParseAndVerify(grant.ToJsonString(),jwk),jwk);
    }
    [Fact] public void RenewedScopeCannotAuthorizeWorkQueuedForClosedSession()
    {
        var session=new ViewerInteractionSession();var grant=Grant();
        session.Install(grant,Runtime(),Now,TimeSpan.Zero);
        using var pending=session.BeginDispatch(grant);
        Assert.True(session.IsDispatchAuthorized(Runtime(),Now,TimeSpan.Zero));
        session.Invalidate("closed");
        session.Install(Resign(g=>g["session_nonce"]=new string('b',64)),Runtime(),Now,TimeSpan.Zero);
        Assert.False(session.IsDispatchAuthorized(Runtime(),Now,TimeSpan.Zero));
    }
    [Fact] public void RenewalExtendsOnlyWithStrictlyIncreasingGenerationAndSameScope()
    {
        var session=new ViewerInteractionSession();var grant=Grant();
        session.Install(grant,Runtime(),Now,TimeSpan.Zero);
        var renewed=Resign(g=>{g["grant_generation"]=2;g["grant_id"]="grant-2";g["issued_at"]="2026-09-22T04:00:30Z";g["expires_at"]="2026-09-22T04:01:30Z";});
        session.Install(renewed,Runtime(),Now.AddSeconds(30),TimeSpan.FromSeconds(30));
        Assert.Null(session.Validate(grant.SessionNonce,Runtime(),Now.AddSeconds(61),TimeSpan.FromSeconds(61)));
        Assert.Throws<InvalidDataException>(()=>session.Install(grant,Runtime(),Now.AddSeconds(31),TimeSpan.FromSeconds(31)));
        Assert.Throws<InvalidDataException>(()=>session.Install(Resign(g=>{g["grant_generation"]=3;g["source_association_id"]="other";}),Runtime(),Now.AddSeconds(31),TimeSpan.FromSeconds(31)));
    }
    internal static readonly DateTimeOffset Now = DateTimeOffset.Parse("2026-09-22T04:00:00Z");
    internal static ViewerInteractionGrant Grant()
    {
        using var fixture = JsonDocument.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory,"viewer_interaction_v1.json")));
        return ViewerInteractionGrant.ParseAndVerify(fixture.RootElement.GetProperty("grant").GetRawText(), fixture.RootElement.GetProperty("public_jwk").GetRawText());
    }
    internal static RuntimeSession Runtime() => new("device-1","12",1,"runtime-1","token",Now.AddHours(1));
    [Fact] public void PythonFixtureVerifiesAndTamperingFails()
    {
        Assert.Equal("association-1",Grant().SourceAssociationId);
        using var fixture = JsonDocument.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory,"viewer_interaction_v1.json")));
        Assert.ThrowsAny<Exception>(()=>ViewerInteractionGrant.ParseAndVerify(fixture.RootElement.GetProperty("grant").GetRawText().Replace("association-1","association-2"),fixture.RootElement.GetProperty("public_jwk").GetRawText()));
    }
    [Fact] public void RollbackCannotExtendMonotonicDeadline()
    {
        var session=new ViewerInteractionSession();var grant=Grant();
        session.Install(grant,Runtime(),Now,TimeSpan.Zero);
        Assert.Null(session.Validate(grant.SessionNonce,Runtime(),Now.AddSeconds(-30),TimeSpan.FromSeconds(59)));
        Assert.Equal("authorization_expired",session.Validate(grant.SessionNonce,Runtime(),Now.AddSeconds(-30),TimeSpan.FromSeconds(61)));
    }
    [Fact] public void DuplicateGenerationAndRestartAreRejected()
    {
        var session=new ViewerInteractionSession();var grant=Grant();
        session.Install(grant,Runtime(),Now,TimeSpan.Zero);
        Assert.Throws<InvalidDataException>(()=>session.Install(grant,Runtime(),Now,TimeSpan.FromSeconds(1)));
        Assert.Equal("interaction_scope_denied",session.Validate(grant.SessionNonce,Runtime() with{InstanceId="new-process"},Now,TimeSpan.Zero));
        session.Invalidate("closed");
        Assert.Throws<InvalidDataException>(()=>session.Install(grant,Runtime(),Now,TimeSpan.Zero));
    }
}
