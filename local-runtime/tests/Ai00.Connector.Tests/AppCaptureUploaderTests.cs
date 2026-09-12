using System.Net;
using System.Security.Cryptography;
using System.Text;
using Ai00.Connector.Adapters.VisMockup;
using Ai00.Connector.AppHost;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class AppCaptureUploaderTests
{
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

    private sealed class UploadHandler(string hash, int size) : HttpMessageHandler
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
                    $"{{\"success\":true,\"data\":{{\"artifact_ref\":{{\"artifact_id\":\"artifact-1\",\"media_type\":\"image/png\",\"sha256\":\"{hash}\",\"byte_size\":{size},\"version\":1}}}}}}")
            };
        }
    }
}
