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

    [Fact]
    public void StructureExportUsesPlmxmlSaveTypeAndRestoresEveryUserOptionOnFailure()
    {
        var options = new RecordingSaveOptions
        {
            SaveExtendedInPlmxml = 9,
            CopyParts = 8,
            RetainReferences = 7,
            AskEveryTime = 6,
            SaveInsertedAssemblies = 5,
            ForceRetainReferences = 4,
            SaveLateLoadedProperties = 3,
        };

        Assert.Throws<InvalidOperationException>(() => VisMockupPlmxmlExport.Run(
            options,
            hierarchyIndex: 2,
            export: (saveType, hierarchyIndex) =>
            {
                Assert.Equal(2, saveType);
                Assert.Equal(2, hierarchyIndex);
                Assert.Equal(0, options.SaveExtendedInPlmxml);
                Assert.Equal(0, options.CopyParts);
                Assert.Equal(1, options.RetainReferences);
                Assert.Equal(0, options.AskEveryTime);
                Assert.Equal(0, options.SaveInsertedAssemblies);
                Assert.Equal(1, options.ForceRetainReferences);
                Assert.Equal(0, options.SaveLateLoadedProperties);
                throw new InvalidOperationException("export failed");
            }));

        Assert.Equal(9, options.SaveExtendedInPlmxml);
        Assert.Equal(8, options.CopyParts);
        Assert.Equal(7, options.RetainReferences);
        Assert.Equal(6, options.AskEveryTime);
        Assert.Equal(5, options.SaveInsertedAssemblies);
        Assert.Equal(4, options.ForceRetainReferences);
        Assert.Equal(3, options.SaveLateLoadedProperties);
    }

    public void Dispose()
    {
        if (Directory.Exists(_root)) Directory.Delete(_root, true);
    }

    private sealed class RecordingSaveOptions : IVisMockupPlmxmlSaveOptions
    {
        public int SaveExtendedInPlmxml { get; set; }
        public int CopyParts { get; set; }
        public int RetainReferences { get; set; }
        public int AskEveryTime { get; set; }
        public int SaveInsertedAssemblies { get; set; }
        public int ForceRetainReferences { get; set; }
        public int SaveLateLoadedProperties { get; set; }
    }
}
