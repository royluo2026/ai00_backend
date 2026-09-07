using Ai00.Connector.Contracts;
namespace Ai00.Connector.Adapters.VisMockup;

public sealed class PostConditionProbes(StaDispatcher sta,IVisMockupCom com)
{
    // Recovery context supplies identifiers only. Never infer success of a write
    // from process presence or dispatch its original operation/payload again.
    public async Task<object> ObserveAsync(string probeId,CancellationToken ct)
    {
        if(probeId!="vismockup.application.probe@1" && probeId!="vismockup.document.snapshot@1")throw new ConnectorException("post_condition_probe_unsupported");
        return await sta.InvokeAsync<object>(()=>
        {
            if(!com.TryGetActiveApplication(out var app))return new{classification="inconclusive",observed_result=(object?)null};
            if(probeId=="vismockup.application.probe@1")return new{classification="inconclusive",observed_result=(object)new{process_ready=true}};
            if(app!.ActiveDocument is not {} document)return new{classification="inconclusive",observed_result=(object?)null};
            return new{classification="inconclusive",observed_result=(object)new DocumentSnapshotReader().Read(document,1000,8)};
        }).WaitAsync(TimeSpan.FromSeconds(10),ct);
    }
}
