using System.Diagnostics;
using System.Text.Json;
using System.Text.RegularExpressions;
namespace Ai00.Connector.Adapters.VisMockup;

// Native documents may lazily reopen JT after the Connector has restarted.
// Persist a conservative process lease; never remove a live process's package.
internal static class LocalModelPackages
{
    internal sealed record Lease(int ProcessId,long Started);
    internal static void Protect(string directory,int processId,long started)
    {
        File.WriteAllText(Path.Combine(directory,"native-process.json"),JsonSerializer.Serialize(new Lease(processId,started)));
        Directory.SetLastWriteTimeUtc(directory,DateTime.UtcNow);
    }
    private static bool Alive(Lease lease)
    {
        try {using var process=Process.GetProcessById(lease.ProcessId);return process.StartTime.ToUniversalTime().Ticks==lease.Started;}
        catch(ArgumentException){return false;}
        catch {return true;} // An inaccessible process is not proof that its documents closed.
    }
    internal static void Trim(string root,TimeSpan age,Func<Lease,bool>? alive=null)
    {
        if(!Directory.Exists(root))return;
        var prefix=Path.GetFullPath(root)+Path.DirectorySeparatorChar;
        foreach(var directory in new DirectoryInfo(root).EnumerateDirectories())
        {
            if(!Regex.IsMatch(directory.Name,"\\A[a-f0-9]{64}\\z")||DateTime.UtcNow-directory.LastWriteTimeUtc<=age)continue;
            try {
                if(!directory.FullName.StartsWith(prefix,StringComparison.OrdinalIgnoreCase)||(directory.Attributes&FileAttributes.ReparsePoint)!=0)continue;
                var leaseFile=Path.Combine(directory.FullName,"native-process.json");
                if(File.Exists(leaseFile)){
                    var lease=JsonSerializer.Deserialize<Lease>(File.ReadAllText(leaseFile));
                    if(lease is null||(alive??Alive)(lease))continue;
                }
                // Reject nested junctions before recursive deletion; do not traverse them.
                bool Plain(DirectoryInfo item){foreach(var entry in item.EnumerateFileSystemInfos()){
                    if((entry.Attributes&FileAttributes.ReparsePoint)!=0)return false;
                    if(entry is DirectoryInfo child&&!Plain(child))return false;
                }return true;}
                if(Plain(directory))directory.Delete(true);
            }catch(IOException){}catch(UnauthorizedAccessException){}catch(JsonException){}
        }
    }
}
