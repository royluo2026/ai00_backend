using System.Net;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text;
using Ai00.Connector.Adapters.VisMockup;
using Ai00.Connector.AppHost;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class AppCaptureUploaderTests
{
    [Theory]
    [InlineData("model/jt",true)]
    [InlineData("image/png",false)]
    public async Task OnlyJtUploadsUseTheArtifactTransport(string media,bool usesArtifact)
    {
        var normal=new UploadHandler(new string('a',64),32,media);
        var artifact=new UploadHandler(new string('a',64),32,media);
        var transport=new RuntimeTransport(new HttpClient(normal),new Uri("https://gateway.example.com"),new HttpClient(artifact));
        using var content=new MemoryStream(new byte[32]);
        await transport.UploadCaptureAsync("plan","lease","step",content,new string('a',64),32,
            OutcomeUnknownRecoveryTests.Session(),CancellationToken.None,media);
        Assert.Equal(usesArtifact,artifact.HasSessionHeader);
        Assert.Equal(!usesArtifact,normal.HasSessionHeader);
    }
    [Fact]
    public async Task UploadsOnlyAVerifiedLocalCaptureThroughTheBoundV2Lease()
    {
        var root = Path.Combine(Path.GetTempPath(), "ai00-app-capture-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            var path = Path.Combine(root, "capture.png");
            var bytes = Encoding.UTF8.GetBytes(new string('p', 32));
            await File.WriteAllBytesAsync(path, bytes);
            var hash = Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
            var handler = new UploadHandler(hash, bytes.Length);
            var uploader = new AppCaptureUploader(
                new RuntimeTransport(new HttpClient(handler), new Uri("https://gateway.example.com")), root);
            var capture = new LocalCaptureArtifact(path, "image/png", hash, bytes.Length, 1920, 1080, 1);

            var result = await uploader.UploadAsync("plan-1", "lease-1", "step-1", capture,
                OutcomeUnknownRecoveryTests.Session(), CancellationToken.None);

            Assert.Equal("artifact-1", result.GetProperty("artifact_id").GetString());
            Assert.Equal("/api/v1/simulation/connectors/v2/plans/plan-1/steps/step-1/result-artifact?lease_id=lease-1",
                handler.Path);
            Assert.Equal(bytes, handler.Bytes);
            Assert.True(handler.HasSessionHeader);

            await Assert.ThrowsAsync<Ai00.Connector.Contracts.ConnectorNoEffectException>(() =>
                uploader.UploadAsync("plan-1", "lease-1", "step-1",
                    capture with { Path = Path.Combine(Path.GetTempPath(), "outside.png") },
                    OutcomeUnknownRecoveryTests.Session(), CancellationToken.None));
        }
        finally { Directory.Delete(root, true); }
    }

    [Fact]
    public async Task ModelArtifactUsesSameImmutableUploadAndChecksActualHash()
    {
        var root=Path.Combine(Path.GetTempPath(),"ai00-app-model-upload-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(root);
        var bytes=new byte[32];var file=Path.Combine(root,"model.jt");await File.WriteAllBytesAsync(file,bytes);
        var hash=Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
        var uploader=new AppCaptureUploader(new RuntimeTransport(new HttpClient(new UploadHandler(hash,bytes.Length,"model/jt")),new Uri("https://gateway.example.com")),root,root);
        var model=new LocalModelArtifact(file,"model/jt",hash,bytes.Length,JsonSerializer.SerializeToElement(new{batch_id="batch"}),"node","revision",JsonSerializer.SerializeToElement(new{file_uid="fixed"}),"2026-09-28T00:00:00Z");
        var result=await uploader.UploadModelAsync("plan","lease","step",model,OutcomeUnknownRecoveryTests.Session(),CancellationToken.None);
        Assert.Equal("model/jt",result.GetProperty("media_type").GetString());
        await Assert.ThrowsAsync<Ai00.Connector.Contracts.ConnectorNoEffectException>(()=>uploader.UploadModelAsync("plan","lease","step",model with{Sha256=new string('0',64)},OutcomeUnknownRecoveryTests.Session(),CancellationToken.None));
    }
    private sealed class UploadHandler(string hash, int size,string mediaType="image/png") : HttpMessageHandler
    {
        public string Path { get; private set; } = "";
        public byte[] Bytes { get; private set; } = [];
        public bool HasSessionHeader { get; private set; }
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            Path = request.RequestUri!.PathAndQuery;
            HasSessionHeader = request.Headers.GetValues("X-AI00-Runtime-Session").Single() == "session-secret";
            Bytes = await request.Content!.ReadAsByteArrayAsync(ct);
            return new(HttpStatusCode.OK)
            {
                Content = new StringContent(
                    $"{{\"success\":true,\"data\":{{\"artifact_ref\":{{\"artifact_id\":\"artifact-1\",\"media_type\":\"{mediaType}\",\"sha256\":\"{hash}\",\"byte_size\":{size},\"version\":1}}}}}}")
            };
        }
    }
}
