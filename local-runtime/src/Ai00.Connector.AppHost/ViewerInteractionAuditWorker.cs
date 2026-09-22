using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Ai00.Connector.Contracts.V2;
using Microsoft.Extensions.Hosting;
namespace Ai00.Connector.AppHost;

public sealed class ViewerInteractionAuditWorker(ViewerInteractionJournal journal,ViewerInteractionRuntimeContext context,
    RuntimeTransport transport,DeviceSigningKey key,ViewerExecutionGate gate):BackgroundService
{
    public const string Protocol="ai00.viewer.interaction.events.v1";
    public static string CreateBatch(IReadOnlyList<ViewerInteractionJournalEntry> entries,RuntimeSession runtime,string keyId,DeviceSigningKey key)
    {
        if(entries.Count is <1 or >128||entries.Any(e=>e.Outcome is null))throw new InvalidDataException("audit_batch_invalid");
        var value=JsonSerializer.SerializeToNode(new{protocol=Protocol,device_id=runtime.DeviceId,runtime_instance_id=runtime.InstanceId,device_key_id=keyId,
            events=entries.Select(e=>new{grant_id=e.GrantId,interaction_id=e.InteractionId,request_id=e.RequestId,sequence=e.Sequence,
                request_digest=e.RequestDigest,operation_id=e.OperationId,outcome=e.Outcome})})!.AsObject();
        value["signature"]=key.Sign([..Encoding.UTF8.GetBytes(Protocol+"\n"),..CanonicalJsonV2.Serialize(value.ToJsonString())]);
        var json=value.ToJsonString();
        if(Encoding.UTF8.GetByteCount(json)>1024*1024)throw new InvalidDataException("audit_batch_too_large");
        return json;
    }
    protected override async Task ExecuteAsync(CancellationToken ct)
    {
        while(!ct.IsCancellationRequested)
        {
            await journal.WaitForUploadAsync(ct);
            var runtime=context.Current;var keyId=context.DeviceKeyId;
            if(runtime is null||keyId is null||runtime.ExpiresAt<=DateTimeOffset.UtcNow)continue;
            var pending=journal.ReadPendingUpload();if(pending.Count==0)continue;
            try
            {
                string batch;
                while(true)
                {
                    try{batch=CreateBatch(pending,runtime,keyId,key);break;}
                    catch(InvalidDataException error) when(error.Message=="audit_batch_too_large"&&pending.Count>1){pending=pending.Take(pending.Count/2).ToArray();}
                }
                var result=await transport.SendAsync(HttpMethod.Post,"viewer-interaction/events",batch,ct,runtime);
                ProtocolV2Schema.Closed(result,"acknowledged_request_ids");
                var ack=result.GetProperty("acknowledged_request_ids").EnumerateArray().Select(e=>e.GetString()!).ToArray();
                if(ack.Distinct().Count()!=ack.Length||ack.Any(id=>!pending.Any(e=>e.RequestId==id)))throw new InvalidDataException("audit_ack_invalid");
                journal.AcknowledgeBatch(ack);
            }
            catch(OperationCanceledException) when(ct.IsCancellationRequested){break;}
            catch(RuntimeTransportException error) when(!error.Transient)
            {gate.Quarantine("audit_rejected");}
            catch(Exception error) when(error is HttpRequestException or OperationCanceledException or IOException or UnauthorizedAccessException or RuntimeTransportException)
            { /* Keep the durable queue; admission enforces its fixed capacity. */ }
            catch(Exception error) when(error is InvalidDataException or ProtocolV2Exception or JsonException or InvalidOperationException)
            {gate.Quarantine("audit_response_invalid");}
        }
    }
}
