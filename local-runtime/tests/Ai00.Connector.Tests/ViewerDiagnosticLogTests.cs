using System.Text.Json;
using Ai00.Connector.AppHost;
using Xunit;
namespace Ai00.Connector.Tests;
public class ViewerDiagnosticLogTests
{
    [Fact] public void RotatesLocallyAndPreservesStructuredCauseAfterAuditCompaction()
    {
        var directory=Path.Combine(Path.GetTempPath(),"viewer-log-"+Guid.NewGuid().ToString("N"));
        try
        {
            Directory.CreateDirectory(directory);var path=Path.Combine(directory,"viewer.jsonl");
            File.WriteAllText(path,new string(' ',5*1024*1024));
            new ViewerDiagnosticLog(path).Write("native_failed",new{request_id="r1",exception_type="TimeoutException",hresult=-1});
            Assert.True(File.Exists(path+".1"));
            using var entry=JsonDocument.Parse(File.ReadAllText(path));
            Assert.Equal("native_failed",entry.RootElement.GetProperty("stage").GetString());
            Assert.Equal("r1",entry.RootElement.GetProperty("detail").GetProperty("request_id").GetString());
        }
        finally{Directory.Delete(directory,true);}
    }
}
