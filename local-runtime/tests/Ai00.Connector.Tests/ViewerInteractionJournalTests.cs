using Ai00.Connector.AppHost;
using Xunit;
namespace Ai00.Connector.Tests;
public class ViewerInteractionJournalTests
{
    [Fact] public void PartialJournalNeverAdmitsNewWrites()
    {
        using var rig=new ViewerInteractionExecutionTests.Rig();
        rig.Journal.Admit(ViewerInteractionExecutionTests.Rig.Request(),ViewerInteractionSessionTests.Grant());
        File.AppendAllText(rig.Journal.Path,"{\"Outcome\":");
        var recovered=new ViewerInteractionJournal(rig.Journal.Path);
        Assert.True(recovered.HasUnknown);
        Assert.Equal("outcome_unknown",Assert.Single(recovered.ReadPendingUpload()).Outcome!.status);
        Assert.Throws<InvalidDataException>(()=>recovered.Admit(ViewerInteractionExecutionTests.Rig.Request("r2",2),ViewerInteractionSessionTests.Grant()));
    }
    [Fact] public async Task UnknownAckNeverUnquarantinesLiveProcessButNewRuntimeDoesNotReplay()
    {
        using var rig=new ViewerInteractionExecutionTests.Rig(()=>throw new Ai00.Connector.Contracts.ConnectorException("effect_unknown"));
        await rig.Executor.ExecuteAsync(ViewerInteractionExecutionTests.Rig.Request(),default);
        rig.Journal.AcknowledgeBatch(["r1"]);
        Assert.True(rig.Gate.IsQuarantined);Assert.True(rig.Journal.HasUnknown);
        var restarted=new ViewerInteractionJournal(rig.Journal.Path);
        Assert.Empty(restarted.ReadPendingUpload());Assert.Null(restarted.Find(new string('a',64),"r1"));
        Assert.Equal(1,rig.Writes);
    }
    [Fact] public void AcknowledgedResultsDoNotConsumeUnacknowledgedCapacity()
    {
        using var rig=new ViewerInteractionExecutionTests.Rig();
        var journal=new ViewerInteractionJournal(rig.Journal.Path,maxRequests:1);
        var request=ViewerInteractionExecutionTests.Rig.Request();
        journal.Admit(request,ViewerInteractionSessionTests.Grant());
        journal.Complete(request.InteractionId,request.RequestId,new(request.RequestId,"completed"));
        journal.AcknowledgeBatch([request.RequestId]);
        journal.Admit(ViewerInteractionExecutionTests.Rig.Request("r2",2),ViewerInteractionSessionTests.Grant());
        Assert.Equal("completed",journal.Find(request.InteractionId,request.RequestId)!.Outcome!.status);
    }
    [Fact] public void IncompleteAdmissionRecoversAsUnknownAndNeverAsUnexecuted()
    {
        using var rig=new ViewerInteractionExecutionTests.Rig();
        var request=ViewerInteractionExecutionTests.Rig.Request();
        rig.Journal.Admit(request,ViewerInteractionSessionTests.Grant());
        var recovered=new ViewerInteractionJournal(rig.Journal.Path);
        Assert.True(recovered.HasUnknown);
        Assert.Equal("outcome_unknown",recovered.Find(request.InteractionId,request.RequestId)!.Outcome!.status);
        Assert.Single(recovered.ReadPendingUpload());
    }
    [Fact] public async Task ExplicitAckReclaimsDiskButRetainsSessionDedupe()
    {
        using var rig=new ViewerInteractionExecutionTests.Rig();
        await rig.Executor.ExecuteAsync(ViewerInteractionExecutionTests.Rig.Request(),default);
        Assert.Single(rig.Journal.ReadPendingUpload());
        rig.Journal.AcknowledgeBatch(["r1"]);
        Assert.Empty(rig.Journal.ReadPendingUpload());
        await rig.Executor.ExecuteAsync(ViewerInteractionExecutionTests.Rig.Request(),default);
        Assert.Equal(1,rig.Writes);
        Assert.Equal(0,new FileInfo(rig.Journal.Path).Length);
    }
    [Fact] public void BacklogRejectsAdmissionBeforeDiskLimit()
    {
        using var rig=new ViewerInteractionExecutionTests.Rig();
        var journal=new ViewerInteractionJournal(rig.Journal.Path,maxRequests:1);
        journal.Admit(ViewerInteractionExecutionTests.Rig.Request(),ViewerInteractionSessionTests.Grant());
        Assert.Throws<InvalidDataException>(()=>journal.Admit(ViewerInteractionExecutionTests.Rig.Request("r2",2),ViewerInteractionSessionTests.Grant()));
    }
}
