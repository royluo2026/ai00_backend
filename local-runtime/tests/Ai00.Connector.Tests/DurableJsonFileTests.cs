using System.Text.Json;
using Ai00.Connector.Contracts;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class DurableJsonFileTests
{
    [Fact]
    public async Task Write_retries_a_transient_windows_replacement_lock()
    {
        if (!OperatingSystem.IsWindows()) return;
        var root=Path.Combine(Path.GetTempPath(),"ai00-durable-json-"+Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        var path=Path.Combine(root,"journal.json");
        await File.WriteAllTextAsync(path,"[1]");
        var blocker=new FileStream(path,FileMode.Open,FileAccess.Read,FileShare.Read);
        var release=Task.Run(async()=>{await Task.Delay(200);blocker.Dispose();});
        try
        {
            DurableJsonFile.Write(path,new[]{1,2});
            await release;
            Assert.Equal(new[]{1,2},JsonSerializer.Deserialize<int[]>(await File.ReadAllTextAsync(path)));
        }
        finally
        {
            blocker.Dispose();
            Directory.Delete(root,true);
        }
    }
}
