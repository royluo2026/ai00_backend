using Ai00.Connector.Adapters.VisMockup;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class VisMockupOpenProvenanceTests
{
    [Fact]
    public void Unrelated_new_active_document_is_not_open_provenance()
    {
        var expected=Path.GetFullPath("requested.jt");
        var unrelated=new FakeDocument("new-unrelated-handle",Path.GetFullPath("other.jt"),FakeNode.FlatTree(1));
        Assert.False(WindowsVisMockupCom.MatchesOpenedSource(unrelated,expected,null));
        var requested=new FakeDocument("requested-handle",expected,FakeNode.FlatTree(1));
        Assert.True(WindowsVisMockupCom.MatchesOpenedSource(requested,expected,null));
    }

    [Fact]
    public void Tc_live_source_requires_exact_uid_not_same_display_filename()
    {
        var source=new TeamcenterVisualizationSource(new Uri("http://tc.example/tc"),"dataset-a","DirectModel",
            FileName:"bolt.jt",ReferenceName:"JTPART",FileUid:"file-a");
        bool Matches(string live)=>WindowsVisMockupCom.MatchesOpenedSource(new FakeDocument("new",live,FakeNode.FlatTree(1)),Path.GetFullPath("material.vvi"),source);
        Assert.False(Matches("http://tc.example/tc?VisDoc_UID=dataset-b?VisDoc_Type=DirectModel"));
        Assert.False(Matches("http://tc.example/tc?Operation=Open?FileTypeID=DirectModel.Document?Title=Bolt?original_file_name=bolt.jt?ref_name=JTPART"));
        Assert.True(Matches("http://tc.example/tc?VisDoc_UID=dataset-a?VisDoc_Type=DirectModel"));
    }
}
