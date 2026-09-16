using Ai00.Connector.Adapters.VisMockup;
using Ai00.Connector.Contracts;
using System.Text.Json;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class VisMockupCadLocatorTests
{
    [Fact]
    public async Task CachedLocatorControlsOnlyTheMatchingDuplicateInANewSession()
    {
        var directory = Path.Combine(Path.GetTempPath(), "ai00-cad-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        try
        {
            var left = new FakeNode("101", "Bolt/01", "", "", []) {CadId="Root:Left:bolt-instance-A:"};
            var right = new FakeNode("102", "Bolt/01", "", "", []) {CadId="Root:Left:bolt-instance-B:"};
            var root = new FakeNode("100", "Root", "", "", [left,right]) {CadId="Root:"};
            var old = new FakeDocument("old-session", "tc://assembly/A", root);
            var app = FakeVisMockupCom.WithDocument("unused");
            app.ActiveDocument = old;
            var com = new FakeVisMockupCom {ExistingApplication=app};
            using var sta = new StaDispatcher();
            var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([directory]), com, directory, Path.Combine(directory,"tree.db"));
            var tree = JsonSerializer.SerializeToElement(await adapter.TreeAsync(2,true));
            var control = tree.GetProperty("nodes")[2].GetProperty("control_key").GetString()!;
            Assert.StartsWith("cad:",control);
            var cachedTree = JsonSerializer.SerializeToElement(await adapter.TreeAsync(2));
            Assert.Equal(control,cachedTree.GetProperty("nodes")[2].GetProperty("control_key").GetString());
            // Snapshot/projection replacement must not erase issued instance locators.
            new VisMockupTreeCache(Path.Combine(directory,"tree.db")).ReplaceProjection(old,
                new VisMockupPlmxmlProjection("pdm:root",[
                    new("pdm:root",null,0,0,"Root","A","01","root","",[],["Root"],"")
                ],"sha256:"+new string('a',64)));
            var newLeft = left with {NodeKey="201"};
            var newRight = right with {NodeKey="202"};
            var current = new FakeDocument("new-session", "tc://assembly/A", root with {NodeKey="200",Children=[newRight,newLeft]});
            current.CadNodes[right.CadId]=newRight;
            app.ActiveDocument=current;
            await adapter.ChangeNodeVisibilityAsync(control,"show");
            Assert.Contains("202",current.VisibleNodeKeys);
            Assert.DoesNotContain("201",current.VisibleNodeKeys);
            await adapter.ChangeNodeSelectionAsync(control,"highlight");
            Assert.Equal(new[]{"202"},current.SelectedNodeKeys);
            Assert.Equal(0,current.ExportPlmxmlCalls);
            // A stale native lookup must not silently select the other same-name instance.
            current.CadNodes[right.CadId]=newLeft;
            await Assert.ThrowsAsync<ConnectorNoEffectException>(()=>adapter.ChangeNodeVisibilityAsync(control,"hide"));
            Assert.Contains("202",current.VisibleNodeKeys);
            // A locator from a different source must not fall back to name or raw node number.
            app.ActiveDocument=new FakeDocument("third-session","tc://assembly/B",root);
            await Assert.ThrowsAsync<ConnectorNoEffectException>(()=>adapter.ChangeNodeVisibilityAsync(control,"show"));
        }
        finally {Directory.Delete(directory,true);}
    }

    [Fact]
    public void CollidingInstancePathsInCacheAreRejectedRatherThanMerged()
    {
        var directory=Path.Combine(Path.GetTempPath(),"ai00-cad-duplicates-"+Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        try
        {
            var document=new FakeDocument("one","tc://assembly/A",FakeNode.FlatTree(1));
            var cache=new VisMockupTreeCache(Path.Combine(directory,"tree.db"));
            cache.Replace(document,2,[new("1",null,0,0,"Root","",true,"Root:"),
                new("2","1",0,1,"Bolt","",false,"Root:Bolt:duplicate:"),
                new("3","1",1,1,"Bolt","",false,"Root:Bolt:duplicate:")]);
            var key=VisMockupTreeCache.ControlKey(VisMockupTreeCache.Identity(document),"Root:Bolt:duplicate:");
            var error=Assert.Throws<ConnectorNoEffectException>(()=>cache.ResolveCadNodeKey(document,key));
            Assert.Equal("vismockup_cad_instance_ambiguous",error.Code);
            Assert.Equal(0,document.SetNodeVisibleCalls);
        }
        finally {Directory.Delete(directory,true);}
    }
}
