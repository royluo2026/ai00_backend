using Ai00.Connector.Adapters.VisMockup;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class TeamcenterLeafSourceTests
{
    [Fact]
    public void DirectModel_dataset_matches_its_resolved_JT_and_requires_a_new_document()
    {
        var path=Path.GetTempFileName();
        try
        {
            File.WriteAllText(path,"HostPath=http://tc.example/tc\nOperation=Open\nVisDoc_UID=dataset-1\nVisDoc_Type=DirectModel\n");
            File.WriteAllText(path+".source.json","{\"dataset_uid\":\"dataset-1\",\"file_uid\":\"file-1\",\"file_name\":\"bolt_01.jt\"}");
            var source=TeamcenterVisualizationSource.ReadMaterial(path);
            Assert.True(source.RequiresNewDocument);
            Assert.True(source.Matches(Live));
            Assert.False(source.Matches(Live.Replace("bolt_01.jt","other.jt")));
            Assert.False(source.Matches(Live.Replace("tc.example","other.example")));
            Assert.False(source.Matches("http://tc.example/tc?VisDoc_UID=other?VisDoc_Type=DirectModel"));
            File.WriteAllText(path+".source.json","{\"dataset_uid\":\"other\",\"file_uid\":\"file-1\",\"file_name\":\"bolt_01.jt\"}");
            Assert.Throws<Ai00.Connector.Contracts.ConnectorNoEffectException>(()=>TeamcenterVisualizationSource.ReadMaterial(path));
        }
        finally { File.Delete(path); File.Delete(path+".source.json"); }
    }

    // Sanitized fixture for the direct-JT source shape observed in VisMockup 14.2.
    private const string Material = "HostPath=http://tc.example/tc\nOperation=Open\nTitle=bolt/01;1\noriginal_file_name=bolt_01.jt\nref_name=JTPART\nFileTypeID=DirectModel.Document\n";
    private const string Live = "http://tc.example/tc?Title=bolt/01;1?original_file_name=bolt_01.jt?ref_name=JTPART?FileTypeID=DirectModel.Document?Operation=Open";

    [Fact]
    public void Direct_JT_material_matches_complete_runtime_source_without_assembly_uid()
    {
        var path=Path.GetTempFileName();
        try
        {
            File.WriteAllText(path,Material);
            var source=TeamcenterVisualizationSource.ReadMaterial(path);
            Assert.True(source.Matches(Live));
            Assert.False(source.Matches(Live.Replace("tc.example","other.example")));
            Assert.False(source.Matches(Live.Replace("bolt_01.jt","bolt_02.jt")));
            Assert.False(source.Matches(Live.Replace("bolt/01;1","bolt/02;1")));
            Assert.False(source.Matches(Live.Replace("JTPART","OTHER")));
            Assert.False(source.Matches(Live.Replace("?ref_name=JTPART","")));
            Assert.False(source.Matches(Live+"?original_file_name=bolt_01.jt"));
            Assert.False(source.Matches(Live+"?VisDoc_UID=unrelated?VisDoc_Type=BOMView%20Revision"));
        }
        finally { File.Delete(path); }
    }
}
