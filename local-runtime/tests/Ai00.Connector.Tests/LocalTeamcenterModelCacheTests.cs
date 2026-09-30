using Ai00.Connector.Adapters.VisMockup;
using Xunit;
namespace Ai00.Connector.Tests;
public class LocalTeamcenterModelCacheTests
{
    [Fact]
    public async Task Two_clients_never_share_hits_and_corruption_is_redownloaded()
    {
        var root=Path.Combine(Path.GetTempPath(),"tc-local-cache-"+Guid.NewGuid().ToString("N"));
        try {
            var count=0;var key=new string('a',64);
            async Task<string> Fetch(CancellationToken ct){Interlocked.Increment(ref count);var path=Path.Combine(root,Guid.NewGuid()+".jt");Directory.CreateDirectory(root);await File.WriteAllBytesAsync(path,new byte[32],ct);return path;}
            var a=new LocalTeamcenterModelCache(Path.Combine(root,"client-a"));
            var b=new LocalTeamcenterModelCache(Path.Combine(root,"client-b"));
            var first=await a.ResolveAsync(key,Fetch,default);
            Assert.Equal(1,count);
            Assert.True((await a.ResolveAsync(key,Fetch,default)).CacheHit);Assert.Equal(1,count);
            Assert.False((await b.ResolveAsync(key,Fetch,default)).CacheHit);Assert.Equal(2,count);
            File.WriteAllText(first.Path,"corrupt");
            Assert.False((await a.ResolveAsync(key,Fetch,default)).CacheHit);Assert.Equal(3,count);
            Assert.True((await b.ResolveAsync(key,Fetch,default)).CacheHit);Assert.Equal(3,count);
        } finally {if(Directory.Exists(root))Directory.Delete(root,true);}
    }
    [Fact]
    public async Task Caller_cannot_supply_a_path_as_cache_key()
    {
        var root=Path.Combine(Path.GetTempPath(),"tc-local-cache-"+Guid.NewGuid().ToString("N"));
        try {
            var cache=new LocalTeamcenterModelCache(root);
            await Assert.ThrowsAnyAsync<Exception>(()=>cache.ResolveAsync("../outside",_=>throw new Exception("must not fetch"),default));
        } finally {if(Directory.Exists(root))Directory.Delete(root,true);}
    }
}
