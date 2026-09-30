using Ai00.Connector.AppHost;
using Xunit;
namespace Ai00.Connector.Tests;
public class ViewerInteractionProtocolTests
{
    [Fact]
    public void Document_root_accepts_only_source_identity_and_kind()
    {
        const string json="""{"type":"resolve_nodes","request_id":"root-1","interaction_id":"session","source_nodes":[{"source_node_id":"assembly","kind":"document_root"}]}""";
        Assert.Equal("resolve_nodes",ViewerInteractionProtocol.ParseRequest(json).Type);
        Assert.ThrowsAny<Exception>(()=>ViewerInteractionProtocol.ParseRequest(json.Replace("\"kind\":\"document_root\"","\"kind\":\"document_root\",\"occurrence_path\":[]")));
        Assert.ThrowsAny<Exception>(()=>ViewerInteractionProtocol.ParseRequest(json.Replace("\"kind\":\"document_root\"","\"kind\":\"document_root\",\"node_key\":\"10\"")));
    }

    [Theory]
    [InlineData("null")]
    [InlineData("[]")]
    [InlineData("{}")]
    public void MalformedFramesBecomeHandledProtocolErrors(string json)=>Assert.Throws<InvalidDataException>(()=>ViewerInteractionProtocol.ParseRequest(json));
    [Theory]
    [InlineData("request_id","bad request")]
    [InlineData("targets","bad target")]
    public void RejectsIdentitiesTheAuditReceiverCannotPersist(string field,string invalid)
    {
        var request=ViewerInteractionExecutionTests.Rig.Request().Document.GetRawText();
        request=field=="request_id"?request.Replace("r1",invalid):request.Replace("ref1",invalid);
        Assert.ThrowsAny<Exception>(()=>ViewerInteractionProtocol.ParseRequest(request));
    }
    [Fact] public void ResolvesTeamcenterEdgesButRejectsStringsAndExtraFields()
    {
        var json="""{"type":"resolve_nodes","request_id":"r1","interaction_id":"session","source_nodes":[{"source_node_id":"n1","kind":"occurrence_path","occurrence_path":[{"occurrence_uid":"occ","item_revision_uid":"rev"}]}]}""";
        Assert.Equal("resolve_nodes",ViewerInteractionProtocol.ParseRequest(json).Type);
        Assert.ThrowsAny<Exception>(()=>ViewerInteractionProtocol.ParseRequest(json.Replace("{\"occurrence_uid\":\"occ\",\"item_revision_uid\":\"rev\"}","\"occ\"")));
        Assert.ThrowsAny<Exception>(()=>ViewerInteractionProtocol.ParseRequest(json.Replace("\"type\":","\"pid\":123,\"type\":")));
    }
    [Theory]
    [InlineData("toggle")]
    [InlineData("run_script")]
    public void RejectsArbitraryActions(string action) => Assert.ThrowsAny<Exception>(()=>ViewerInteractionProtocol.ParseRequest("""{"type":"execute","request_id":"r","interaction_id":"i","sequence":1,"structure_epoch":1,"operation_id":"vismockup.node.visibility.change@1","targets":["ref"],"arguments":{"action":"ACTION"}}""".Replace("ACTION",action)));
    [Fact] public async Task OversizeAndTruncatedFramesAreRejected()
    {
        using var oversized=new MemoryStream(System.Text.Encoding.UTF8.GetBytes(new string('a',65537)+"\n"));
        await Assert.ThrowsAsync<InvalidDataException>(()=>ViewerInteractionProtocol.ReadFrameAsync(oversized,default));
        using var truncated=new MemoryStream(System.Text.Encoding.UTF8.GetBytes("{}"));
        await Assert.ThrowsAsync<EndOfStreamException>(()=>ViewerInteractionProtocol.ReadFrameAsync(truncated,default));
    }
}
