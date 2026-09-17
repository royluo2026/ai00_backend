using System.Diagnostics;
using System.Reflection;
using System.Text.Json;
using Ai00.Connector.Adapters.VisMockup;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class TeamcenterProcessCancellationTests
{
    [Fact]
    public async Task Canceled_worker_confirms_owned_process_exit_before_returning()
    {
        var marker=Path.Combine(Path.GetTempPath(),"ai00-tc-process-"+Guid.NewGuid().ToString("N"));
        var start=new ProcessStartInfo("powershell.exe") {
            UseShellExecute=false,CreateNoWindow=true,RedirectStandardInput=true,
            RedirectStandardOutput=true,RedirectStandardError=true
        };
        start.ArgumentList.Add("-NoProfile"); start.ArgumentList.Add("-NonInteractive");
        start.ArgumentList.Add("-Command");
        start.ArgumentList.Add("[IO.File]::WriteAllText('"+marker.Replace("'","''")+"',[string]$PID); Start-Sleep -Seconds 60");
        using var cancel=new CancellationTokenSource();
        var run=typeof(TeamcenterProcessWorker).GetMethod("RunProcessAsync",BindingFlags.NonPublic|BindingFlags.Static)!;
        var pending=(Task<JsonElement>)run.Invoke(null,[start,Array.Empty<string>(),cancel.Token])!;
        Process? owned=null;
        try
        {
            using var startup=new CancellationTokenSource(TimeSpan.FromSeconds(10));
            while(!File.Exists(marker))await Task.Delay(20,startup.Token);
            owned=Process.GetProcessById(int.Parse(File.ReadAllText(marker)));
            cancel.Cancel();
            await Assert.ThrowsAnyAsync<OperationCanceledException>(()=>pending);
            Assert.True(owned.HasExited);
        }
        finally
        {
            cancel.Cancel();
            if(owned is not null) { if(!owned.HasExited)owned.Kill(true); owned.Dispose(); }
            File.Delete(marker);
        }
    }
}
