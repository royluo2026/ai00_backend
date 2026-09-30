using System.Text.Json;
using Ai00.Connector.Adapters.VisMockup;
using Ai00.Connector.Contracts.V2;
using Xunit;
namespace Ai00.Connector.Tests;
public sealed class TcCachedDocumentTests
{
    [Fact]
    public async Task Tc_dependencies_open_one_environment_keep_instance_transforms_and_reuse_only_this_clients_files()
    {
        var folder=Path.Combine(Path.GetTempPath(),"tc-local-open-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(folder);
        try {
            using var sta=new StaDispatcher();var app=CacheEnvironmentDocumentTests.Application();
            var worker=new TeamcenterModelFileTests.Worker();using var runtime=new TeamcenterReadOnlyRuntime(worker,Path.Combine(folder,"tc.db"));
            await runtime.LoginAsync("tc-production","test","test",default);
            // Match AppHost: downloaded OIS artifacts and local TC packages have different roots.
            var adapter=new VisMockupAdapter(sta,new AllowedPathPolicy([Path.Combine(folder,"artifacts")]),new FakeVisMockupCom{ExistingApplication=app,ProcessId=123,ProcessStartUtcTicks=456},Path.Combine(folder,"captures"),Path.Combine(folder,"tree.db"),runtime);
            using var fixtures=JsonDocument.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory,"Fixtures","tc-local-open.json")));
            using var contract=JsonDocument.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory,"vismockup.model.open@3.json")));
            Assert.True(adapter.Manifest.Supports("vismockup.model.open@3",CanonicalJsonV2.Hash(contract.RootElement)));
            foreach(var packet in fixtures.RootElement.EnumerateArray()) {
                var result=JsonSerializer.SerializeToElement((await adapter.ExecuteAsync(new("vismockup.model.open@3",packet),default)).Data);
                Assert.Equal("ai00.viewer.opened-tc-cache.v1",result.GetProperty("protocol").GetString());
                Assert.Single(result.GetProperty("files").EnumerateArray());
                Assert.DoesNotContain("artifact_ref",result.GetRawText());
            }
            Assert.Equal(new[]{"cache_file"},worker.Commands);
            Assert.Single(app.OpenDocuments);Assert.Single(app.LastOpenedDocument!.InsertedDocumentPaths);
            var geometry=app.LastOpenedDocument.RuntimeNodes.Values.Where(n=>n.CadId!="root").ToArray();
            Assert.Equal(2,geometry.Length);
            var positions=geometry.Select(n=>((FakeNode)n).GlobalTransform[12]).Order().ToArray();
            Assert.Equal(new[]{10d,20d},positions);
        } finally {Directory.Delete(folder,true);}
    }
}
