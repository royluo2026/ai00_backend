using System.Security.Cryptography;
using System.Text.Json;
using System.Text.RegularExpressions;
using Ai00.Connector.Contracts;
namespace Ai00.Connector.Adapters.VisMockup;
internal sealed record LocalTcFile(string Path,string Sha256,long ByteSize,bool CacheHit);
internal sealed class LocalTeamcenterModelCache
{
    private readonly string root;
    private static readonly SemaphoreSlim[] Gates=Enumerable.Range(0,64).Select(_=>new SemaphoreSlim(1,1)).ToArray();
    internal LocalTeamcenterModelCache(string directory){root=System.IO.Path.GetFullPath(directory);TeamcenterProcessWorker.SecureVisualizationMaterialRoot(root);}
    internal async Task<LocalTcFile> ResolveAsync(string key,Func<CancellationToken,Task<string>> fetch,CancellationToken ct)
    {
        if(!Regex.IsMatch(key,"\\A[a-f0-9]{64}\\z"))throw new ConnectorNoEffectException("cache_file_identity_invalid");
        var gate=Gates[Convert.ToByte(key[..2],16)%Gates.Length];await gate.WaitAsync(ct);
        try {
            var path=System.IO.Path.Combine(root,key+".jt");var record=path+".json";
            if(File.Exists(path)&&File.Exists(record))
            {
                try {
                    RejectLink(path);RejectLink(record);
                    var prior=JsonSerializer.Deserialize<LocalTcFile>(await File.ReadAllTextAsync(record,ct));
                    var info=new FileInfo(path);
                    if(prior is not null&&prior.ByteSize==info.Length&&info.Length is >=24 and <=512*1024*1024&&await Hash(path,ct)==prior.Sha256)
                    {File.SetLastWriteTimeUtc(record,DateTime.UtcNow);return prior with{Path=path,CacheHit=true};}
                } catch(JsonException){} catch(IOException){}
            }
            ct.ThrowIfCancellationRequested();var downloaded=await fetch(ct);
            RejectLink(downloaded);var size=new FileInfo(downloaded).Length;
            if(size is <24 or >512*1024*1024)throw new ConnectorNoEffectException("cache_file_integrity_failed");
            var temp=path+".partial-"+Guid.NewGuid().ToString("N");
            try {
                await using(var source=File.OpenRead(downloaded))
                await using(var target=new FileStream(temp,FileMode.CreateNew,FileAccess.Write,FileShare.None,81920,true))
                    await source.CopyToAsync(target,ct);
                var hash=await Hash(temp,ct);ct.ThrowIfCancellationRequested();
                if(new FileInfo(temp).Length!=size)throw new ConnectorNoEffectException("cache_file_integrity_failed");
                if(File.Exists(path)){RejectLink(path);File.SetAttributes(path,FileAttributes.Normal);}
                File.Move(temp,path,true);
                var result=new LocalTcFile(path,hash,size,false);
                var tempRecord=record+".partial";
                await File.WriteAllTextAsync(tempRecord,JsonSerializer.Serialize(result),ct);
                if(File.Exists(record))RejectLink(record);
                File.Move(tempRecord,record,true);
                return result;
            } finally {
                if(File.Exists(temp))File.Delete(temp);
                if(!string.Equals(downloaded,path,StringComparison.OrdinalIgnoreCase)&&File.Exists(downloaded))
                {File.SetAttributes(downloaded,FileAttributes.Normal);File.Delete(downloaded);}
            }
        } finally {gate.Release();}
    }
    // Cache files are copied into document packages; these disposable entries have no native references.
    internal void Trim(TimeSpan maximumAge,long maximumBytes)
    {
        var records=new DirectoryInfo(root).EnumerateFiles("*.jt").OrderBy(f=>File.Exists(f.FullName+".json")?File.GetLastWriteTimeUtc(f.FullName+".json"):f.LastWriteTimeUtc).ToArray();
        var size=records.Sum(f=>f.Length);
        foreach(var file in records)
        {
            var key=System.IO.Path.GetFileNameWithoutExtension(file.Name);
            if(!Regex.IsMatch(key,"\\A[a-f0-9]{64}\\z"))continue;
            var touched=File.Exists(file.FullName+".json")?File.GetLastWriteTimeUtc(file.FullName+".json"):file.LastWriteTimeUtc;
            if(DateTime.UtcNow-touched<=maximumAge&&size<=maximumBytes)continue;
            var gate=Gates[Convert.ToByte(key[..2],16)%Gates.Length];if(!gate.Wait(0))continue;
            try {RejectLink(file.FullName);var length=file.Length;file.Attributes=FileAttributes.Normal;file.Delete();if(File.Exists(file.FullName+".json"))File.Delete(file.FullName+".json");size-=length;}
            catch(IOException){}finally{gate.Release();}
        }
    }
    private static void RejectLink(string path){if((File.GetAttributes(path)&FileAttributes.ReparsePoint)!=0)throw new ConnectorNoEffectException("cache_file_path_invalid");}
    internal static async Task<string> Hash(string path,CancellationToken ct){await using var f=File.OpenRead(path);return Convert.ToHexString(await SHA256.HashDataAsync(f,ct)).ToLowerInvariant();}
}
