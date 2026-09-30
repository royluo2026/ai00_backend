using System.Text.RegularExpressions;
namespace Ai00.Connector.AppHost;

// The authenticated Electron parent can stop its own opens, never authorize one.
public sealed class LocalOpenCancellation
{
    private readonly object sync=new();
    private readonly Dictionary<string,DateTimeOffset> cancelled=new();
    private readonly Dictionary<string,CancellationTokenSource> active=new();
    public void Cancel(string planId)
    {
        if(!Regex.IsMatch(planId,"\\Avismockup-command-[a-f0-9]{64}\\z"))throw new InvalidDataException("cache_open_cancel_invalid");
        lock(sync){
            foreach(var old in cancelled.Where(p=>p.Value<DateTimeOffset.UtcNow.AddHours(-1)).Select(p=>p.Key).ToArray())cancelled.Remove(old);
            if(cancelled.Count>=4096&&!cancelled.ContainsKey(planId))throw new InvalidDataException("cache_open_cancel_limit");
            cancelled[planId]=DateTimeOffset.UtcNow;
            if(active.TryGetValue(planId,out var source))source.Cancel();
        }
    }
    public Scope Begin(string planId,CancellationToken ct)
    {
        lock(sync){var source=CancellationTokenSource.CreateLinkedTokenSource(ct);active.Add(planId,source);if(cancelled.ContainsKey(planId))source.Cancel();return new(this,planId,source);}
    }
    public sealed class Scope(LocalOpenCancellation owner,string planId,CancellationTokenSource source):IDisposable
    {
        public CancellationToken Token=>source.Token;
        public void Dispose(){lock(owner.sync){owner.active.Remove(planId);source.Dispose();}}
    }
}
