using Ai00.Connector.Adapters.VisMockup;
using Ai00.Connector.Contracts;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class VisMockupExportPlmxmlTests : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), "ai00-plmxml-export-" + Guid.NewGuid().ToString("N"));

    [Fact]
    public void ExportPinsExactDocumentHierarchyAndReturnsBoundedHash()
    {
        var document = new FakeDocument("doc-1", "tc://bom/1", FakeNode.FlatTree(1));
        var result = new PlmxmlExporter(_root).Export(document, "doc-1", 2, "step-1");
        Assert.Equal(1, document.ExportPlmxmlCalls);
        Assert.Equal(2, result.HierarchyIndex);
        Assert.Equal(64, result.Sha256.Length);
        Assert.True(result.ByteSize > 0);
    }

    [Fact]
    public void ExportRejectsWrongDocumentUnsafeStepAndOversizedArtifact()
    {
        var document = new FakeDocument("doc-1", "tc://bom/1", FakeNode.FlatTree(1));
        var exporter = new PlmxmlExporter(_root, maxBytes: 4);
        Assert.Throws<ConnectorException>(() => exporter.Export(document, "other", 0, "step-1"));
        Assert.Throws<ConnectorException>(() => exporter.Export(document, "doc-1", 0, "../escape"));
        Assert.Throws<ConnectorException>(() => exporter.Export(document, "doc-1", 0, "step-1"));
        Assert.False(File.Exists(Path.Combine(_root, "step-1.plmxml")));
    }

    public void Dispose()
    {
        if (Directory.Exists(_root)) Directory.Delete(_root, true);
    }
}
