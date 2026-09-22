using System.Text;
using System.Text.Json;
using Ai00.Connector.Contracts.V2;
namespace Ai00.Connector.AppHost;

public sealed record ViewerInteractionJournalEntry(string GrantId,string InteractionId,string RequestId,long Sequence,
    string RequestDigest,string OperationId,ViewerInteractionResponse? Outcome=null,bool Acknowledged=false);

// Separate from the plan journal. Admission and outcome are flushed before dispatch/response.
public sealed class ViewerInteractionJournal
{
    private readonly object sync=new();
    private readonly Dictionary<(string,string),ViewerInteractionJournalEntry> entries=new();
    private readonly Dictionary<string,long> watermarks=new(StringComparer.Ordinal);
    private readonly HashSet<string> requestIds=new(StringComparer.Ordinal);
    private readonly HashSet<string> closedSessions=new(StringComparer.Ordinal);
    private int unacknowledged;
    private int pendingOutcomes;
    private bool unknown;
    private readonly int maxRequests;
    private readonly long maxBytes;
    private bool broken;
    private readonly SemaphoreSlim uploadSignal=new(0,1);
    public async Task WaitForUploadAsync(CancellationToken ct)=>await uploadSignal.WaitAsync(TimeSpan.FromSeconds(2),ct);
    public string Path {get;}
    public bool HasUnknown {get{lock(sync)return broken||unknown;}}
    public ViewerInteractionJournal(string path,int maxRequests=10000,long maxBytes=64*1024*1024)
    {
        Path=System.IO.Path.GetFullPath(path);this.maxRequests=maxRequests;this.maxBytes=maxBytes;
        if(!File.Exists(Path))return;
        try
        {
            if(new FileInfo(Path).Length>maxBytes)throw new InvalidDataException("journal_backpressure");
            var bytes=File.ReadAllBytes(Path);
            var truncated=bytes.Length>0&&bytes[^1]!=10;
            if(truncated)
            {
                // Preserve the original tail until acknowledged compaction. Only
                // complete admissions can be interpreted; none may be replayed.
                broken=true;
                bytes=bytes[..(Array.LastIndexOf(bytes,(byte)10)+1)];
            }
            foreach(var line in new UTF8Encoding(false,true).GetString(bytes).Split('\n',StringSplitOptions.RemoveEmptyEntries))
            {
                var entry=JsonSerializer.Deserialize<ViewerInteractionJournalEntry>(line)??throw new InvalidDataException("journal_invalid");
                entries[(entry.InteractionId,entry.RequestId)]=entry;
                requestIds.Add(entry.RequestId);
                watermarks[entry.InteractionId]=Math.Max(watermarks.GetValueOrDefault(entry.InteractionId),entry.Sequence);
            }
            foreach(var item in entries.Values.Where(e=>e.Outcome is null).ToArray())
            {
                var recovered=item with{Outcome=new(item.RequestId,"outcome_unknown",error_code:"process_recovery_outcome_unknown",timings:new{total_ms=0,com_ms=0,journal_ms=0})};
                if(!truncated)Append(recovered);
                entries[(item.InteractionId,item.RequestId)]=recovered;
            }
            unacknowledged=entries.Values.Count(e=>!e.Acknowledged);
            pendingOutcomes=entries.Values.Count(e=>!e.Acknowledged&&e.Outcome is not null);
            unknown=entries.Values.Any(e=>e.Outcome?.status=="outcome_unknown");
        }
        catch(Exception error) when(error is IOException or UnauthorizedAccessException or InvalidDataException or JsonException or DecoderFallbackException){broken=true;}
    }
    public ViewerInteractionJournalEntry? Find(string interaction,string request){lock(sync)return entries.GetValueOrDefault((interaction,request));}
    public long Watermark(string interaction){lock(sync)return watermarks.GetValueOrDefault(interaction);}
    public void Admit(ViewerInteractionRequest request,ViewerInteractionGrant grant)
    {
        lock(sync)
        {
            if(broken)throw new InvalidDataException("journal_unavailable");
            // Reserve enough disk for the maximum bounded terminal response before a write.
            if(unacknowledged>=maxRequests || (File.Exists(Path)?new FileInfo(Path).Length:0)+2*ViewerInteractionProtocol.MaximumBytes>maxBytes)throw new InvalidDataException("journal_backpressure");
            if(requestIds.Contains(request.RequestId))throw new InvalidDataException("request_id_conflict");
            var sequence=request.Document.GetProperty("sequence").GetInt64();
            if(sequence<=watermarks.GetValueOrDefault(request.InteractionId))throw new InvalidDataException("sequence_stale");
            var entry=new ViewerInteractionJournalEntry(grant.GrantId,request.InteractionId,request.RequestId,sequence,request.Digest,request.Document.GetProperty("operation_id").GetString()!);
            Append(entry);entries.Add((request.InteractionId,request.RequestId),entry);watermarks[request.InteractionId]=sequence;
            requestIds.Add(request.RequestId);unacknowledged++;
        }
    }
    public void Complete(string interaction,string request,ViewerInteractionResponse outcome)
    {
        lock(sync)
        {
            var key=(interaction,request);
            if(entries[key].Outcome is not null)throw new InvalidDataException("outcome_already_recorded");
            var entry=entries[key] with{Outcome=outcome};
            Append(entry);entries[key]=entry;
            pendingOutcomes++;unknown|=outcome.status=="outcome_unknown";
            if(pendingOutcomes>=128&&uploadSignal.CurrentCount==0)uploadSignal.Release();
        }
    }
    public IReadOnlyList<ViewerInteractionJournalEntry> ReadPendingUpload()
    {lock(sync)return entries.Values.Where(e=>!e.Acknowledged && e.Outcome is not null).Take(128).ToArray();}
    public void AcknowledgeBatch(IReadOnlyCollection<string> requestIds)
    {
        lock(sync)
        {
            if(requestIds.Any(id=>!entries.Values.Any(e=>e.RequestId==id&&e.Outcome is not null)))throw new InvalidDataException("audit_ack_invalid");
            var retained=entries.Values.Where(e=>!e.Acknowledged&&!requestIds.Contains(e.RequestId)).ToArray();
            var temporary=Path+".compact-"+Guid.NewGuid().ToString("N");
            try
            {
                using(var stream=new FileStream(temporary,FileMode.CreateNew,FileAccess.Write,FileShare.None,4096,FileOptions.WriteThrough))
                {foreach(var entry in retained){stream.Write(JsonSerializer.SerializeToUtf8Bytes(entry));stream.WriteByte(10);}stream.Flush(true);}
                File.Move(temporary,Path,true);
                foreach(var pair in entries.ToArray())if(requestIds.Contains(pair.Value.RequestId)&&!pair.Value.Acknowledged)
                {
                    entries[pair.Key]=pair.Value with{Acknowledged=true};unacknowledged--;pendingOutcomes--;
                    if(closedSessions.Contains(pair.Key.Item1))entries.Remove(pair.Key);
                }
            }
            finally{if(File.Exists(temporary))File.Delete(temporary);}
        }
    }
    public void CloseSession(string interaction)
    {lock(sync){closedSessions.Add(interaction);foreach(var pair in entries.Where(e=>e.Key.Item1==interaction&&e.Value.Acknowledged).ToArray())entries.Remove(pair.Key);}}
    private void Append(ViewerInteractionJournalEntry entry)
    {
        try
        {
            Directory.CreateDirectory(System.IO.Path.GetDirectoryName(Path)!);
            using var stream=new FileStream(Path,FileMode.Append,FileAccess.Write,FileShare.Read,4096,FileOptions.WriteThrough);
            stream.Write(JsonSerializer.SerializeToUtf8Bytes(entry));stream.WriteByte(10);stream.Flush(true);
        }
        catch(Exception error) when(error is IOException or UnauthorizedAccessException){broken=true;throw;}
    }
}
