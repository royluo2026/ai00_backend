using System.Text.Json;
using Ai00.Connector.Adapters.VisMockup;
using Ai00.Connector.Contracts;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class VisMockupHierarchyInventoryTests
{
    private const string Operation = "vismockup.document.hierarchy_inventory.read@1";
    [Fact]
    public async Task ReadsBoundedAlternateHierarchyPageWithoutOpeningOrMutatingDocument()
    {
        var document = new FakeDocument("42", "tc://W10", FakeNode.FlatTree(1)) { HierarchyCount = 1 };
        var com = new FakeVisMockupCom { ExistingApplication = new FakeApplication("14.2", document),
            ProcessId = 123, ProcessStartUtcTicks = 638900000000000001 };
        var session = CanonicalJson.Hash(new { process_id = 123,
            process_started_utc_ticks = "638900000000000001", document_handle = "42" });
        using var sta = new StaDispatcher();
        var reader = new FakeLiveHierarchyReader(new(session, 0, null, 1,
            [new(1, "AI00_RUNTIME_PROBE", "sha256:" + new string('a', 64),
                [new("ah:1:1", null, 0, "AI00_RUNTIME_PROBE", "aps:1", ""),
                 new("ah:1:2", "ah:1:1", 0, "Lamp", "aps:2", "cps:9")], true)]));
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([Path.GetTempPath()]), com,
            Path.GetTempPath(), reader);

        var result = JsonSerializer.SerializeToElement((await adapter.ExecuteAsync(new(Operation,
            JsonSerializer.SerializeToElement(new { document_session = session, start_index = 0,
                page_size = 4, max_nodes = 1000 })), default)).Data);

        Assert.Equal(session, result.GetProperty("document_session").GetString());
        Assert.Equal(1, result.GetProperty("total_hierarchies").GetInt32());
        Assert.Equal(JsonValueKind.Null, result.GetProperty("next_index").ValueKind);
        var hierarchy = result.GetProperty("hierarchies")[0];
        Assert.Equal(1, hierarchy.GetProperty("native_index").GetInt32());
        Assert.Equal("AI00_RUNTIME_PROBE", hierarchy.GetProperty("name").GetString());
        Assert.Equal(2, hierarchy.GetProperty("nodes").GetArrayLength());
        Assert.Equal(1, reader.Calls);
        Assert.Equal(0, document.ExportPlmxmlCalls);
        Assert.Equal(0, document.InsertDocumentCalls);
        Assert.False(document.Closed);
    }

    [Fact]
    public async Task RejectsAChangedDocumentSessionBeforeExport()
    {
        var document = new FakeDocument("42", "tc://W10", FakeNode.FlatTree(1)) { HierarchyCount = 1 };
        var com = new FakeVisMockupCom { ExistingApplication = new FakeApplication("14.2", document),
            ProcessId = 123, ProcessStartUtcTicks = 638900000000000001 };
        using var sta = new StaDispatcher();
        var reader = new FakeLiveHierarchyReader(new("sha256:" + new string('1', 64), 0, null, 0, []));
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([Path.GetTempPath()]), com,
            Path.GetTempPath(), reader);
        var error = await Assert.ThrowsAsync<ConnectorException>(() => adapter.ExecuteAsync(new(Operation,
            JsonSerializer.SerializeToElement(new { document_session = "sha256:" + new string('0', 64),
                start_index = 0, page_size = 1, max_nodes = 1000 })), default));
        Assert.Equal("vismockup_document_changed", error.Code);
        Assert.Equal(0, document.ExportPlmxmlCalls);
        Assert.Equal(0, reader.Calls);
    }

    private sealed class FakeLiveHierarchyReader(LiveHierarchyInventoryPage page) : ILiveHierarchyInventoryReader
    {
        public int Calls { get; private set; }
        public LiveHierarchyInventoryPage Read(VisMockupProcessState process, string documentHandle,
            string sourceIdentity, string documentSession, int startIndex, int pageSize, int maxNodes)
        {
            Calls++;
            return page;
        }
    }
}
