using System.Text;
using System.Text.Json;
using System.Security.Cryptography;
using Ai00.Connector.AppHost;
using Ai00.Connector.Contracts.V2;
using Xunit;
namespace Ai00.Connector.Tests;
public class ViewerInteractionAuditTests
{
    [Fact] public async Task BackgroundUploadUsesCurrentDeviceRuntimeAndAcksHistoricalGrantOnlyAfterResponse()
    {
        using var rig=new ViewerInteractionExecutionTests.Rig();
        await rig.Executor.ExecuteAsync(ViewerInteractionExecutionTests.Rig.Request(),default);
        using var key=new DeviceSigningKeyStore(rig.DirectoryPath).GetOrCreate();
        rig.Runtime.Update(rig.Runtime.Current! with{InstanceId="new-runtime",ExpiresAt=DateTimeOffset.UtcNow.AddHours(1)},"device-key");
        var response=new TaskCompletionSource<HttpResponseMessage>(TaskCreationOptions.RunContinuationsAsynchronously);
        var arrived=new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        using var http=new HttpClient(new Gateway(async request=>{
            Assert.EndsWith("/viewer-interaction/events",request.RequestUri!.AbsolutePath);
            Assert.Equal("new-runtime",request.Headers.GetValues("X-AI00-Runtime-Instance-ID").Single());
            using var doc=JsonDocument.Parse(await request.Content!.ReadAsStringAsync());
            Assert.Equal("new-runtime",doc.RootElement.GetProperty("runtime_instance_id").GetString());
            Assert.Equal("grant-1",doc.RootElement.GetProperty("events")[0].GetProperty("grant_id").GetString());
            arrived.SetResult();return await response.Task;}));
        using var worker=new ViewerInteractionAuditWorker(rig.Journal,rig.Runtime,new RuntimeTransport(http,new Uri("https://gateway.example.com")),key,rig.Gate);
        await worker.StartAsync(default);
        try
        {
            await arrived.Task.WaitAsync(TimeSpan.FromSeconds(5));
            Assert.Single(rig.Journal.ReadPendingUpload());
            response.SetResult(new(System.Net.HttpStatusCode.OK){Content=new StringContent("{\"success\":true,\"data\":{\"acknowledged_request_ids\":[\"r1\"]}}")});
            for(var i=0;i<100&&rig.Journal.ReadPendingUpload().Count>0;i++)await Task.Delay(10);
            Assert.Empty(rig.Journal.ReadPendingUpload());Assert.Equal(1,rig.Writes);
        }
        finally{response.TrySetCanceled();await worker.StopAsync(default);}
    }
    private sealed class Gateway(Func<HttpRequestMessage,Task<HttpResponseMessage>> send):HttpMessageHandler
    {protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken ct)=>send(request);}
    [Fact] public async Task BatchSignsPurposeSeparatedCanonicalBytesAndRequiresExactAck()
    {
        using var rig=new ViewerInteractionExecutionTests.Rig();
        await rig.Executor.ExecuteAsync(ViewerInteractionExecutionTests.Rig.Request(),default);
        using var key=new DeviceSigningKeyStore(rig.DirectoryPath).GetOrCreate();
        var batch=ViewerInteractionAuditWorker.CreateBatch(rig.Journal.ReadPendingUpload(),rig.Runtime.Current!,"device-key",key);
        var document=JsonDocument.Parse(batch).RootElement;
        Assert.Equal("ai00.viewer.interaction.events.v1",document.GetProperty("protocol").GetString());
        Assert.Single(document.GetProperty("events").EnumerateArray());
        Assert.DoesNotContain("signature",document.GetProperty("events")[0].GetRawText());
        var unsigned=document.EnumerateObject().Where(p=>p.Name!="signature").ToDictionary(p=>p.Name,p=>p.Value);
        var bytes=Encoding.UTF8.GetBytes("ai00.viewer.interaction.events.v1\n").Concat(CanonicalJsonV2.Serialize(JsonSerializer.SerializeToElement(unsigned))).ToArray();
        byte[] Decode(string text)=>Convert.FromBase64String(text.Replace('-','+').Replace('_','/')+new string('=',(4-text.Length%4)%4));
        var jwk=key.PublicJwk;
        using var verifier=ECDsa.Create(new ECParameters{Curve=ECCurve.NamedCurves.nistP256,Q=new ECPoint{X=Decode(jwk.GetProperty("x").GetString()!),Y=Decode(jwk.GetProperty("y").GetString()!)}});
        Assert.True(verifier.VerifyData(bytes,Decode(document.GetProperty("signature").GetString()!),HashAlgorithmName.SHA256,DSASignatureFormat.IeeeP1363FixedFieldConcatenation));
        Assert.Throws<InvalidDataException>(()=>rig.Journal.AcknowledgeBatch(["not-sent"]));
        Assert.Single(rig.Journal.ReadPendingUpload());
    }
}
