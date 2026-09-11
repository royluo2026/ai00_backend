using Ai00.Connector.Contracts;
using System.Text.Json;
namespace Ai00.Connector.Adapters.VisMockup;

public sealed class PostConditionProbes(StaDispatcher sta,IVisMockupCom com,VisMockupAdapter? adapter=null)
{
    // Recovery context supplies identifiers only. Never infer success of a write
    // from process presence or dispatch its original operation/payload again.
    public async Task<object> ObserveAsync(string probeId,JsonElement? probeInput,CancellationToken ct)
    {
        if(probeId!="vismockup.application.probe@1" && probeId!="vismockup.document.snapshot@1")throw new ConnectorException("post_condition_probe_unsupported");
        if(probeId=="vismockup.document.snapshot@1" && adapter is not null && probeInput is {ValueKind:JsonValueKind.Object} input
            && input.TryGetProperty("node_key",out var nodeKey) && input.TryGetProperty("expected_visible",out var expected))
        {
            try
            {
                var visible=await adapter.ObserveNodeVisibilityAsync(nodeKey.GetString()!).WaitAsync(TimeSpan.FromSeconds(10),ct);
                return new{classification=visible==expected.GetBoolean()?"succeeded":"failed_without_effect",
                    observed_result=(object)new{node_key=nodeKey.GetString(),visible}};
            }
            catch(ConnectorException error) when(error.Code=="vismockup_recovery_node_unavailable")
            {
                // Visibility is an in-memory document property. Once no open
                // document contains the signed target node, no effect remains.
                return new{classification="failed_without_effect",
                    observed_result=(object)new{node_key=nodeKey.GetString(),document_open=false}};
            }
            catch(Exception error) when(error is ConnectorException or TimeoutException)
            {return new{classification="inconclusive",observed_result=(object?)null};}
        }
        if(probeId=="vismockup.document.snapshot@1" && probeInput is {ValueKind:JsonValueKind.Object} globalInput
            && globalInput.TryGetProperty("expected_all_visible",out var expectedAll))
        {
            try
            {
                return await sta.InvokeAsync<object>(()=>
                {
                    if(!com.TryGetActiveApplication(out var app)||app!.ActiveDocument is not {} document)
                        return new{classification="failed_without_effect",observed_result=(object)new{document_open=false}};
                    var keys=document.AllNodeKeys;
                    if(keys.Count==0)return new{classification="inconclusive",observed_result=(object?)null};
                    var expectedVisible=expectedAll.GetBoolean();
                    var matches=keys.All(key=>document.IsNodeVisible(key)==expectedVisible);
                    return new{classification=matches?"succeeded":"failed_without_effect",
                        observed_result=(object)new{all_visible=expectedVisible&&matches,all_hidden=!expectedVisible&&matches,node_count=keys.Count}};
                }).WaitAsync(TimeSpan.FromSeconds(10),ct);
            }
            catch(Exception error) when(error is ConnectorException or TimeoutException)
            {return new{classification="inconclusive",observed_result=(object?)null};}
        }
        return await sta.InvokeAsync<object>(()=>
        {
            if(!com.TryGetActiveApplication(out var app))return new{classification="inconclusive",observed_result=(object?)null};
            if(probeId=="vismockup.application.probe@1")return new{classification="inconclusive",observed_result=(object)new{process_ready=true}};
            if(app!.ActiveDocument is not {} document)return new{classification="inconclusive",observed_result=(object?)null};
            return new{classification="inconclusive",observed_result=(object)new DocumentSnapshotReader().Read(document,1000,8)};
        }).WaitAsync(TimeSpan.FromSeconds(10),ct);
    }
}
