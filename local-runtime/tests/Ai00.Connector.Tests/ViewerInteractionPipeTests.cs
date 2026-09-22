using System.IO.Pipes;
using System.Text;
using System.Text.Json;
using Ai00.Connector.Adapters.VisMockup;
using Ai00.Connector.Contracts;
using Ai00.Connector.AppHost;
using Xunit;
namespace Ai00.Connector.Tests;
public class ViewerInteractionPipeTests
{
    [Fact] public async Task RealPipeInstallsGrantResolvesExecutesDeduplicatesQueriesAndCloses()
    {
        using var rig=new ViewerInteractionExecutionTests.Rig();
        using var sta=new StaDispatcher();
        var node=new FakeNode("11","Part","","",[]){CadId="Root:Part:"};
        var document=new FakeDocument("doc","tc://one",node);
        var adapter=new VisMockupAdapter(sta,new AllowedPathPolicy([rig.DirectoryPath]),new FakeVisMockupCom{
            ExistingApplication=new FakeApplication("14.2",document),ProcessId=123,ProcessStartUtcTicks=456});
        var session=new ViewerInteractionSession();var runtime=new ViewerInteractionRuntimeContext();var gate=new ViewerExecutionGate();
        var now=DateTimeOffset.UtcNow;
        runtime.Update(ViewerInteractionSessionTests.Runtime() with{ExpiresAt=now.AddHours(1)},"key");
        var contract=adapter.Manifest.Operations.Single(op=>op.OperationId=="vismockup.node.visibility.change@1");
        var fixture=ViewerInteractionSessionTests.SignFixture(g=>{
            g["issued_at"]=now.AddSeconds(-1).ToString("yyyy-MM-ddTHH:mm:ssZ");g["expires_at"]=now.AddSeconds(59).ToString("yyyy-MM-ddTHH:mm:ssZ");
            g["document_session"]=CanonicalJson.Hash(new{process_id=123,process_started_utc_ticks="456",document_handle="doc"});
            g["operations"]![0]!["contract_hash"]=contract.ContractHash;});
        adapter.ViewerInteractionAdmissionAllowed=()=>!gate.IsQuarantined&&session.IsDispatchAuthorized(runtime.Current,DateTimeOffset.UtcNow,ViewerInteractionPipeHost.MonotonicNow());
        var executor=new ViewerInteractionExecutor(session,runtime,gate,rig.Journal,adapter.Manifest.Supports,adapter.ExecuteViewerNodeAsync);
        var name="AI00.ViewerTest."+Guid.NewGuid().ToString("N");
        var options=new AppHostOptions(Environment.ProcessId,name,"nonce",Path.Combine(rig.DirectoryPath,"manifest.json"),new Uri("https://gateway.example.com"),true);
        var manifest=new HostManifest("protocol","1","https://gateway.example.com","parent","host","hash","publisher","vis","publisher",
            new(){{"fixture-only",new(fixture.PublicJwk,now.AddDays(-1),now.AddDays(1),false)}});
        using var host=new ViewerInteractionPipeHost(options,manifest,session,runtime,executor,rig.Journal,gate,adapter);
        using var timeout=new CancellationTokenSource(TimeSpan.FromSeconds(10));
        await host.StartAsync(timeout.Token);
        using var client=new NamedPipeClientStream(".",name+".ViewerInteraction",PipeDirection.InOut,PipeOptions.Asynchronous);
        try
        {
            await client.ConnectAsync(timeout.Token);
            async Task<JsonElement> Send(object request)
            {
                await client.WriteAsync(Encoding.UTF8.GetBytes(JsonSerializer.Serialize(request)+"\n"),timeout.Token);
                using var response=JsonDocument.Parse(await ViewerInteractionProtocol.ReadFrameAsync(client,timeout.Token));return response.RootElement.Clone();
            }
            var installed=await Send(new{type="install_grant",request_id="install",grant=fixture.Grant.Document});
            Assert.Equal("completed",installed.GetProperty("status").GetString());
            var interaction=installed.GetProperty("result").GetProperty("interaction_id").GetString()!;
            var mapping=await Send(new{type="resolve_nodes",request_id="resolve",interaction_id=interaction,source_nodes=new[]{new{source_node_id="root",kind="single_part_root"}}});
            Assert.Equal("completed",mapping.GetProperty("status").GetString());
            var result=mapping.GetProperty("result");var reference=result.GetProperty("nodes")[0].GetProperty("node_ref").GetString();
            var execute=new{type="execute",request_id="show",interaction_id=interaction,sequence=1,structure_epoch=result.GetProperty("structure_epoch").GetInt64(),operation_id=contract.OperationId,targets=new[]{reference},arguments=new{action="show"}};
            Assert.Equal("completed",(await Send(execute)).GetProperty("status").GetString());
            Assert.True(document.IsNodeVisible("11"));
            Assert.Equal("completed",(await Send(execute)).GetProperty("status").GetString());
            Assert.Equal(1,document.SetNodeVisibleCalls);
            var query=await Send(new{type="query_request",request_id="query",interaction_id=interaction,queried_request_id="show"});
            Assert.Equal("query",query.GetProperty("request_id").GetString());Assert.Equal("completed",query.GetProperty("status").GetString());
            Assert.Equal("completed",(await Send(new{type="close",request_id="close",interaction_id=interaction})).GetProperty("status").GetString());
            Assert.Null(session.Current);Assert.Single(rig.Journal.ReadPendingUpload());
        }
        finally{client.Dispose();await host.StopAsync(default);}
    }
    [Fact] public async Task NativePipeChecksOperatingSystemPeerPidAndPreventsSecondServer()
    {
        var name="AI00.ViewerTest."+Guid.NewGuid().ToString("N");
        using var server=ViewerInteractionPipeHost.CreatePipe(name);
        Assert.Throws<System.ComponentModel.Win32Exception>(()=>ViewerInteractionPipeHost.CreatePipe(name));
        using var client=new NamedPipeClientStream(".",name+".ViewerInteraction",PipeDirection.InOut,PipeOptions.Asynchronous);
        using var timeout=new CancellationTokenSource(TimeSpan.FromSeconds(5));
        var accept=server.WaitForConnectionAsync(timeout.Token);
        await client.ConnectAsync(timeout.Token);await accept;
        Assert.True(ViewerInteractionPipeHost.IsExpectedPeer(server,Environment.ProcessId));
        Assert.False(ViewerInteractionPipeHost.IsExpectedPeer(server,int.MaxValue));
        await client.WriteAsync("{\"type\":\"close\",\"request_id\":\"r\",\"interaction_id\":\"i\"}\n"u8.ToArray(),timeout.Token);
        Assert.Equal("close",ViewerInteractionProtocol.ParseRequest(await ViewerInteractionProtocol.ReadFrameAsync(server,timeout.Token)).Type);
    }
}
