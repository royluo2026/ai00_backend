using System.Net;
using System.Text;
using System.Text.Json;
using Ai00.Connector.Contracts;
using Ai00.Connector.Service;
using Microsoft.Extensions.Options;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class ConnectorArtifactPipelineTests : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), "ai00-plan-artifacts", Guid.NewGuid().ToString("N"));

    [Fact]
    public async Task CaptureUploadReplacesLocalPathWithArtifactRef()
    {
        Directory.CreateDirectory(_root);
        var path = Path.Combine(_root, "capture.png");
        var bytes = "capture bytes"u8.ToArray();
        await File.WriteAllBytesAsync(path, bytes);
        var sha = Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(bytes)).ToLowerInvariant();
        var handler = new UploadHandler();
        var http = new HttpClient(handler);
        var options = Options.Create(new RuntimeOptions { GatewayUrl = "https://ai00.test", CaptureRoot = _root });
        var transfer = new ArtifactTransfer(new UnusedTransport(), new TemporaryFileStore(Path.Combine(_root, "cache")));
        var gateway = new ConnectorGatewayClient(http, options, new CredentialStore(), transfer);
        var payload = JsonSerializer.SerializeToElement(new { capture_run_id = "capture-1", operation_id = "op-1", attempt = 1, format = "png", width = 1920, height = 1080, background = "current" });
        var step = new ConnectorStep("step-1", "vismockup.view.capture@1", "sha256:" + new string('a', 64), [], payload, CanonicalJson.Hash(payload), 30);
        var plan = new ConnectorExecutionPlan("ai00.connector.execution-plan.v1", "capture-1", "tenant-1", "user-1", "device-1", "simulation.capture_run.start@1", "sha256:" + new string('b', 64), "ai00.vismockup", 1, new("siemens.vismockup", "14.0.0", "15.0.0"), [step], DateTimeOffset.UtcNow, DateTimeOffset.UtcNow.AddMinutes(1), "sha256:" + new string('c', 64));
        var local = JsonSerializer.SerializeToElement(new { path, media_type = "image/png", sha256 = sha, byte_size = bytes.Length, width = 1920, height = 1080, attempt = 1 });
        var result = new ConnectorStepResult("step-1", "completed", local, CanonicalJson.Hash(local), "", DateTimeOffset.UtcNow, DateTimeOffset.UtcNow);
        var outcome = new ConnectorPlanOutcome(plan.Protocol, plan.PlanId, "completed", [result], DateTimeOffset.UtcNow);

        var projected = await gateway.UploadCaptureResultsAsync(new("lease-1", plan, "key", "signature"), outcome, default);

        var json = JsonSerializer.SerializeToElement(projected.Steps[0].Result);
        Assert.True(json.TryGetProperty("artifact", out _));
        Assert.False(json.TryGetProperty("path", out _));
        Assert.Contains("/steps/step-1/result-artifact?lease_id=lease-1", handler.RequestUri);
        Assert.Equal(sha, handler.Sha256);
    }

    public void Dispose() { if (Directory.Exists(_root)) Directory.Delete(_root, true); }

    private sealed class CredentialStore : IDeviceCredentialStore
    {
        public string StoragePath => "unused";
        public void Save(DeviceCredential credential) => throw new NotSupportedException();
        public DeviceCredential Load() => new("device-1", "user-1", "sid-1", new string('s', 32));
    }
    private sealed class UploadHandler : HttpMessageHandler
    {
        public string RequestUri { get; private set; } = "";
        public string Sha256 { get; private set; } = "";
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            RequestUri = request.RequestUri?.PathAndQuery ?? "";
            Sha256 = request.Headers.GetValues("X-AI00-Content-SHA256").Single();
            _ = await request.Content!.ReadAsByteArrayAsync(cancellationToken);
            return new(HttpStatusCode.OK) { Content = new StringContent("{\"success\":true,\"data\":{\"artifact_ref\":{\"artifact_id\":\"artifact-1\",\"media_type\":\"image/png\",\"sha256\":\"" + Sha256 + "\",\"byte_size\":13,\"version\":1}}}", Encoding.UTF8, "application/json") };
        }
    }
    private sealed class UnusedTransport : IArtifactTransport
    {
        public Task DownloadToAsync(Uri source, string destination, CancellationToken cancellationToken) => throw new NotSupportedException();
        public Task<ArtifactUploadReceipt> UploadAsync(UploadGrant grant, string path, CancellationToken cancellationToken) => throw new NotSupportedException();
        public Task<ArtifactUploadReceipt?> QueryUploadAsync(string uploadSessionId, CancellationToken cancellationToken) => throw new NotSupportedException();
    }
}
