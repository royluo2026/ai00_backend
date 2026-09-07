using Ai00.Connector.AppHost;
using System.Text.Json;
using Xunit;
namespace Ai00.Connector.Tests;
public sealed class AppHostLifecycleTests
{
    [Theory]
    [InlineData("top_duplicate")] [InlineData("key_duplicate")] [InlineData("key_unknown")]
    [InlineData("jwk_duplicate")] [InlineData("jwk_unknown")] [InlineData("map_duplicate")]
    public void ManifestRejectsEveryNestedAmbiguityBeforeDeserializing(string mutation)
    {
        var jwk=ProtocolV2VectorTests.Vector["plan_public_jwk"]!.ToJsonString();
        if(mutation=="jwk_duplicate")jwk=jwk.Insert(1,"\"kty\":\"EC\",");
        if(mutation=="jwk_unknown")jwk=jwk.Insert(1,"\"private\":\"no\",");
        var manifest=new HostManifest("ai00.connector.execution-plan.v2","1.0.0","https://gateway.example.com","AI00.exe","AI00.ConnectorHost.exe",new string('a',64),"publisher",@"C:\Program Files\Vis.exe","publisher",new(){{"cloud-key",new(jwk,DateTimeOffset.UtcNow.AddDays(-1),DateTimeOffset.UtcNow.AddDays(1),false)}});
        var json=JsonSerializer.Serialize(manifest);
        if(mutation=="top_duplicate")json=json.Insert(1,"\"Protocol\":\"ignored\",");
        if(mutation=="key_duplicate")json=json.Replace("\"Revoked\":false","\"Revoked\":true,\"Revoked\":false");
        if(mutation=="key_unknown")json=json.Replace("\"Revoked\":false","\"Revoked\":false,\"Extra\":true");
        if(mutation=="map_duplicate")json=json.Replace("\"PlanKeys\":{","\"PlanKeys\":{\"cloud-key\":{},");
        Assert.ThrowsAny<Exception>(()=>HostManifest.Parse(json));
    }
    [Fact] public async Task TransportUsesOnlyV2SessionHeadersAndDoesNotSendDeviceCredential()
    {
        using var http=new HttpClient(new InspectRequest(request=>
        {
            Assert.Equal("https://gateway.example.com/api/v1/simulation/connectors/v2/plans/lease",request.RequestUri!.AbsoluteUri);
            Assert.Equal("electron",request.Headers.GetValues("X-AI00-Runtime-Type").Single());
            Assert.Equal("session-secret",request.Headers.GetValues("X-AI00-Runtime-Session").Single());
            Assert.False(request.Headers.Contains("X-AI00-Device-Credential"));
            return new HttpResponseMessage(System.Net.HttpStatusCode.OK){Content=new StringContent("{\"success\":true,\"data\":null}")};
        }));
        var transport=new RuntimeTransport(http,new Uri("https://gateway.example.com"));
        var result=await transport.SendAsync(HttpMethod.Post,"plans/lease",new{lease_seconds=120},CancellationToken.None,OutcomeUnknownRecoveryTests.Session());
        Assert.Equal(JsonValueKind.Null,result.ValueKind);
    }
    [Fact] public void CredentialCiphertextIsCurrentUserAndOriginBound()
    {
        var root=Path.Combine(Path.GetTempPath(),"ai00-credential-test-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(root);
        try
        {
            var store=new AppCredentialStore(root,new Uri("https://gateway.example.com"));
            store.Save(System.Text.Encoding.UTF8.GetBytes("{\"device_credential\":\"private-secret\"}"));
            Assert.Equal("private-secret",store.Load()!.Value.GetProperty("device_credential").GetString());
            Assert.DoesNotContain("private-secret",File.ReadAllText(Path.Combine(root,"device.v2.dpapi")));
            Assert.ThrowsAny<System.Security.Cryptography.CryptographicException>(()=>new AppCredentialStore(root,new Uri("https://other.example.com")).Load());
        }
        finally{Directory.Delete(root,true);}
    }
    private sealed class InspectRequest(Func<HttpRequestMessage,HttpResponseMessage> handle):HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken ct)=>Task.FromResult(handle(request));
    }
    [Fact] public async Task RealPipeGatesReadinessOnParentHandshakeAndStopsOnShutdown()
    {
        var args=Args;args[1]=Environment.ProcessId.ToString();args[3]="AI00.Connector."+Guid.NewGuid().ToString("N");
        var options=AppHostOptions.Parse(args);
        var identity=new DiagnosticIdentity(Environment.ProcessId,Environment.ProcessId,Environment.ProcessPath!,"publisher",new string('a',64),options.LaunchNonce);
        var lifetime=new Lifetime();using var host=new DiagnosticPipeHost(options,identity,lifetime);
        await host.StartAsync(CancellationToken.None);
        using var client=new System.IO.Pipes.NamedPipeClientStream(".",options.PipeName,System.IO.Pipes.PipeDirection.InOut,System.IO.Pipes.PipeOptions.Asynchronous);
        await client.ConnectAsync(3000);
        using var reader=new StreamReader(client);using var writer=new StreamWriter(client){AutoFlush=true};
        DiagnosticProtocol.ValidateHandshake((await reader.ReadLineAsync())!,identity);
        Assert.False(host.Ready.IsCompleted);
        await writer.WriteLineAsync(JsonSerializer.Serialize(identity));
        await host.Ready.WaitAsync(TimeSpan.FromSeconds(3));
        Assert.Equal("ready",DiagnosticProtocol.Validate((await reader.ReadLineAsync())!));
        await writer.WriteLineAsync("{\"type\":\"shutdown\"}");
        await lifetime.Stopped.Task.WaitAsync(TimeSpan.FromSeconds(3));
        await host.StopAsync(CancellationToken.None);
    }
    private sealed class Lifetime:Microsoft.Extensions.Hosting.IHostApplicationLifetime
    {
        public TaskCompletionSource Stopped{get;}=new(TaskCreationOptions.RunContinuationsAsynchronously);
        public CancellationToken ApplicationStarted=>CancellationToken.None;
        public CancellationToken ApplicationStopping=>CancellationToken.None;
        public CancellationToken ApplicationStopped=>CancellationToken.None;
        public void StopApplication()=>Stopped.TrySetResult();
    }
    private static string[] Args => ["--parent-pid","42","--pipe-name","AI00.Connector."+new string('a',32),"--launch-nonce",new string('b',64),"--manifest-path",@"C:\AI00\manifest.json","--gateway-origin","https://gateway.example.com"];
    [Fact] public void FixedArgumentsAreRequiredAndClosed()
    {
        Assert.Equal(42,AppHostOptions.Parse(Args).ParentPid);
        Assert.ThrowsAny<Exception>(()=>AppHostOptions.Parse([]));
        Assert.ThrowsAny<Exception>(()=>AppHostOptions.Parse(Args.Concat(new[]{"--command","launch"}).ToArray()));
        Assert.ThrowsAny<Exception>(()=>AppHostOptions.Parse(Args.Concat(new[]{"--parent-pid","42"}).ToArray()));
    }
    [Theory] [InlineData("http://localhost")] [InlineData("https://gateway.example.com/path")] [InlineData("https://user:pass@gateway.example.com")] [InlineData("https://gateway.example.com?token=x")]
    public void InvalidOriginsAreRejected(string origin){var a=Args;a[^1]=origin;Assert.ThrowsAny<Exception>(()=>AppHostOptions.Parse(a));}
    [Theory] [InlineData("{\"type\":\"shutdown\",\"capability_id\":\"launch\"}")] [InlineData("{\"type\":\"health\",\"token\":\"secret\"}")] [InlineData("{\"type\":\"diagnostic\",\"message\":\"arbitrary\"}")] [InlineData("{\"type\":\"execute\"}")] [InlineData("{\"type\":\"health\",\"type\":\"shutdown\"}")]
    public void DiagnosticMessagesCannotDescribeBusinessOrSecrets(string json)=>Assert.ThrowsAny<Exception>(()=>DiagnosticProtocol.Validate(json));
    [Fact] public void DiagnosticFramesAreBoundedAndClosed(){Assert.Equal("health",DiagnosticProtocol.Validate("{\"type\":\"health\"}"));Assert.ThrowsAny<Exception>(()=>DiagnosticProtocol.Validate(new string(' ',4097)));}
    [Fact] public void NonceAndAllIdentityPinsAreRequired()
    {
        var identity=new DiagnosticIdentity(42,43,@"C:\AI00\AI00.ConnectorHost.exe","publisher",new string('a',64),new string('b',64));
        DiagnosticProtocol.ValidateHandshake(JsonSerializer.Serialize(identity),identity);
        Assert.ThrowsAny<Exception>(()=>DiagnosticProtocol.ValidateHandshake(JsonSerializer.Serialize(identity with{ParentPid=7}),identity));
        Assert.ThrowsAny<Exception>(()=>DiagnosticProtocol.ValidateHandshake(JsonSerializer.Serialize(identity with{Nonce=new string('c',64)}),identity));
    }
}
