using System.Text.Json;
namespace Ai00.Connector.AppHost;

// Separate from the upload journal: acknowledged audit events may be compacted,
// while local stage diagnostics remain available for troubleshooting.
internal sealed class ViewerDiagnosticLog(string path)
{
    private readonly object _sync=new();
    internal void Write(string stage,object detail)
    {
        try
        {
            lock(_sync)
            {
                Directory.CreateDirectory(Path.GetDirectoryName(path)!);
                if(File.Exists(path)&&new FileInfo(path).Length>=5*1024*1024)
                {
                    for(var index=2;index>=1;index--)
                        if(File.Exists(path+"."+index))File.Move(path+"."+index,path+"."+(index+1),true);
                    File.Move(path,path+".1",true);
                }
                File.AppendAllText(path,JsonSerializer.Serialize(new{timestamp=DateTimeOffset.UtcNow,pid=Environment.ProcessId,stage,detail})+Environment.NewLine);
            }
        }
        catch(Exception error) when(error is not (OutOfMemoryException or StackOverflowException)) { }
    }
}
