using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Ai00.Connector.Adapters.VisMockup;
using Ai00.Connector.Contracts;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class VisMockupDocumentIdentityTests
{
    private const string Operation = "vismockup.document.identity.read@1";
    private sealed class IdentityCom : IVisMockupCom
    {
        public VisMockupProcessState Process = new(true, "14.2", 123, 638900000000000001);
        public FakeApplication Application = new("14.2", new FakeDocument("42", "same-source", null!));
        public Action<int>? OnConnect;
        public Action<int>? OnInspect;
        public int Connections, Inspections;
        public bool Available = true;
        public VisMockupProcessState InspectProcess()
        {
            Assert.Equal(ApartmentState.STA, Thread.CurrentThread.GetApartmentState());
            OnInspect?.Invoke(++Inspections);
            return Process;
        }
        public bool TryGetActiveApplication(out IVisMockupApplication? application)
        {
            Assert.Equal(ApartmentState.STA, Thread.CurrentThread.GetApartmentState());
            OnConnect?.Invoke(++Connections);
            application = Available ? Application : null;
            return Available;
        }
        public void Launch() => throw new Exception("must not launch");
        public IVisMockupApplication WaitForActiveApplication(TimeSpan timeout) => throw new Exception("must not wait");
    }

    private static VisMockupAdapter Adapter(StaDispatcher sta, IdentityCom com) =>
        new(sta, new AllowedPathPolicy([Path.GetTempPath()]), com);
    private static async Task<JsonElement> Read(VisMockupAdapter adapter, CancellationToken token = default) =>
        JsonSerializer.SerializeToElement((await adapter.ExecuteAsync(new(Operation,
            JsonSerializer.SerializeToElement(new { })), token)).Data);

    [Fact]
    public void ProcessIdentityIgnoresAHeadlessEmbeddingInstance()
    {
        Assert.Equal((20, 200L), WindowsVisMockupCom.SelectProcessIdentity([
            (10, 100L, false),
            (20, 200L, true),
        ]));
        Assert.Null(WindowsVisMockupCom.SelectProcessIdentity([
            (10, 100L, true),
            (20, 200L, true),
        ]));
        Assert.Null(WindowsVisMockupCom.SelectProcessIdentity([
            (10, 100L, false),
            (20, 200L, false),
        ]));
        Assert.Equal((10, 100L), WindowsVisMockupCom.SelectProcessIdentity([
            (10, 100L, false),
        ]));
    }

    [Fact]
    public void ProcessIdentityKeepsThePreviouslyAttachedIncarnationAfterEmbeddingRemovesItsMainWindow()
    {
        Assert.Equal((20, 200L), WindowsVisMockupCom.SelectProcessIdentity([
            (10, 100L, false),
            (20, 200L, false),
        ], (20, 200L)));
        Assert.Null(WindowsVisMockupCom.SelectProcessIdentity([
            (10, 100L, false),
            (20, 201L, false),
        ], (20, 200L)));
    }

    [Fact]
    public async Task IdentityIsStableAndChangesOnRestartAndDocumentSwitchWithSameSourceAndTitle()
    {
        using var sta = new StaDispatcher();
        var com = new IdentityCom();
        var adapter = Adapter(sta, com);
        var first = await Read(adapter);
        Assert.Equal(first.GetRawText(), (await Read(adapter)).GetRawText());
        Assert.Equal("638900000000000001", first.GetProperty("process_started_utc_ticks").GetString());
        Assert.Equal(4, first.EnumerateObject().Count());
        Assert.Equal(CanonicalJson.Hash(new { process_id = 123,
            process_started_utc_ticks = "638900000000000001", document_handle = "42" }),
            first.GetProperty("document_session").GetString());
        com.Application.ActiveDocument = new FakeDocument("42", "different-source", null!);
        Assert.Equal(first.GetRawText(), (await Read(adapter)).GetRawText());
        com.Process = com.Process with { ProcessStartUtcTicks = 638900000000000002 };
        var restarted = await Read(adapter);
        Assert.NotEqual(first.GetProperty("document_session").GetString(), restarted.GetProperty("document_session").GetString());
        com.Application.ActiveDocument = new FakeDocument("43", "same-source", null!);
        Assert.NotEqual(restarted.GetProperty("document_session").GetString(), (await Read(adapter)).GetProperty("document_session").GetString());
        var document = (FakeDocument)com.Application.ActiveDocument;
        Assert.Equal(0, document.ExportPlmxmlCalls);
        Assert.Equal(0, document.CaptureImageCalls);
        Assert.Equal(0, document.InsertDocumentCalls);
        Assert.Null(com.Application.LastOpenedDocument);
        Assert.False(document.Closed);
    }

    [Theory]
    [InlineData(null, null)]
    [InlineData(123, null)]
    [InlineData(null, 123L)]
    [InlineData(0, 123L)]
    [InlineData(123, 0L)]
    public async Task RefusesUnavailableOrAmbiguousProcessIncarnation(int? pid, long? ticks)
    {
        using var sta = new StaDispatcher();
        var com = new IdentityCom { Process = new(true, "14.2", pid, ticks) };
        var error = await Assert.ThrowsAsync<ConnectorException>(() => Read(Adapter(sta, com)));
        Assert.Equal("vismockup_process_identity_unavailable", error.Code);
    }

    [Theory]
    [InlineData("restart")]
    [InlineData("switch")]
    [InlineData("missing")]
    [InlineData("unavailable")]
    [InlineData("closed")]
    [InlineData("ambiguous_after")]
    [InlineData("stopped")]
    public async Task RefusesIdentityChangesAndMissingDocument(string scenario)
    {
        using var sta = new StaDispatcher();
        var com = new IdentityCom();
        com.OnConnect = count => { if (count == 2 && scenario == "switch")
            com.Application.ActiveDocument = new FakeDocument("43", "same-source", null!); };
        com.OnInspect = count => { if (count == 2 && scenario == "restart")
            com.Process = com.Process with { ProcessStartUtcTicks = 99 };
            if (count == 2 && scenario == "ambiguous_after") com.Process = com.Process with { ProcessId = null }; };
        if (scenario == "missing") com.Application.ActiveDocument = new FakeDocument("", "same-source", null!);
        if (scenario == "unavailable") com.Available = false;
        if (scenario == "closed") com.Application.ActiveDocument = null;
        if (scenario == "stopped") com.Process = com.Process with { Running = false };
        await Assert.ThrowsAsync<ConnectorException>(() => Read(Adapter(sta, com)));
    }

    [Fact]
    public async Task CancellationIsObservedBeforeAndAfterStaReadAndInputIsClosed()
    {
        using var sta = new StaDispatcher();
        var com = new IdentityCom();
        var adapter = Adapter(sta, com);
        using var cancellation = new CancellationTokenSource();
        cancellation.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => Read(adapter, cancellation.Token));
        Assert.Equal(0, com.Inspections);
        using var during = new CancellationTokenSource();
        com.OnInspect = count => { if (count == 2) during.Cancel(); };
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => Read(adapter, during.Token));
        await Assert.ThrowsAsync<ConnectorException>(() => adapter.ExecuteAsync(new(Operation,
            JsonSerializer.SerializeToElement(new { allow_launch = true })), default));
        await Assert.ThrowsAsync<InvalidOperationException>(() => adapter.ExecuteAsync(new(
            "vismockup.document.identity.read@2", JsonSerializer.SerializeToElement(new { })), default));
    }

    [Fact]
    public void ManifestPinComesFromCanonicalClosedContract()
    {
        var root = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", "..", ".."));
        using var descriptor = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "docs", "contracts", Operation + ".json")));
        var canonical = JsonSerializer.Serialize(descriptor.RootElement);
        var hash = "sha256:" + Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(canonical))).ToLowerInvariant();
        using var sta = new StaDispatcher();
        var manifest = Adapter(sta, new IdentityCom()).Manifest;
        Assert.Equal(hash, manifest.Operations.Single(item => item.OperationId == Operation).ContractHash);
        Assert.True(manifest.Supports(Operation, hash));
        Assert.False(manifest.Supports(Operation, "sha256:" + new string('0', 64)));
        Assert.False(manifest.HasOperation("vismockup.document.identity.read@2"));
        Assert.False(descriptor.RootElement.GetProperty("input").GetProperty("additionalProperties").GetBoolean());
        Assert.False(descriptor.RootElement.GetProperty("output").GetProperty("additionalProperties").GetBoolean());
    }
}
