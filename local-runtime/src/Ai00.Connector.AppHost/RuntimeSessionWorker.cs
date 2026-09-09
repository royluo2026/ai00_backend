using System.Net;
using System.Net.Http.Json;
using System.Net.WebSockets;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Ai00.Connector.Adapters.VisMockup;
using Ai00.Connector.Contracts.V2;
using Microsoft.Extensions.Hosting;
namespace Ai00.Connector.AppHost;

public sealed class RuntimeTransport(HttpClient http,Uri origin)
{
    private const string Prefix="api/v1/simulation/connectors/v2/";
    public Uri Endpoint(string path)=>new(origin,Prefix+path);
    public async Task<JsonElement> SendAsync(HttpMethod method,string path,object? body,CancellationToken ct,RuntimeSession? session=null,string? credential=null)
    {
        using var request=new HttpRequestMessage(method,Endpoint(path));
        if(body!=null)request.Content=body is string rawJson ? new StringContent(rawJson,Encoding.UTF8,"application/json") : JsonContent.Create(body);
        if(credential!=null)request.Headers.Add("X-AI00-Device-Credential",credential);
        if(session!=null)foreach(var header in Headers(session))request.Headers.Add(header.Key,header.Value);
        using var response=await http.SendAsync(request,HttpCompletionOption.ResponseHeadersRead,ct);
        if((int)response.StatusCode>=500||response.StatusCode is HttpStatusCode.RequestTimeout or HttpStatusCode.TooManyRequests)
            throw new RuntimeTransportException("cloud_temporarily_unavailable",true);
        await using var stream=await response.Content.ReadAsStreamAsync(ct);
        using var bytes=new MemoryStream();var buffer=new byte[8192];
        while(true){var count=await stream.ReadAsync(buffer,ct);if(count==0)break;if(bytes.Length+count>4*1024*1024)throw new InvalidDataException("cloud_response_size_invalid");bytes.Write(buffer,0,count);}
        var json=CanonicalJsonV2.Parse(Encoding.UTF8.GetString(bytes.ToArray()));
        if(!response.IsSuccessStatusCode)
        {
            var code=json.TryGetProperty("detail",out var detail)&&detail.ValueKind==JsonValueKind.Object&&detail.TryGetProperty("code",out var item)?item.GetString():"cloud_request_failed";
            throw new RuntimeTransportException(code??"cloud_request_failed");
        }
        if(!json.GetProperty("success").GetBoolean())throw new InvalidDataException("cloud_response_invalid");
        return json.GetProperty("data").Clone();
    }
    internal static Dictionary<string,string> Headers(RuntimeSession session)=>new()
    {
        ["X-AI00-Device-ID"]=session.DeviceId,["X-AI00-Runtime-Generation"]=session.Generation.ToString(System.Globalization.CultureInfo.InvariantCulture),
        ["X-AI00-Runtime-Instance-ID"]=session.InstanceId,["X-AI00-Runtime-Type"]="electron",["X-AI00-Runtime-Session"]=session.Token
    };
    public async Task WaitForWakeAsync(RuntimeSession session,CancellationToken ct)
    {
        using var timeout=CancellationTokenSource.CreateLinkedTokenSource(ct);timeout.CancelAfter(TimeSpan.FromSeconds(25));
        try
        {
            using var socket=new ClientWebSocket();
            foreach(var header in Headers(session))socket.Options.SetRequestHeader(header.Key,header.Value);
            var endpoint=new UriBuilder(Endpoint("plans/wake")){Scheme="wss"};
            await socket.ConnectAsync(endpoint.Uri,timeout.Token);
            var buffer=new byte[256];
            while(true)
            {
                var count=0;WebSocketReceiveResult frame;
                do
                {
                    if(count==buffer.Length)throw new InvalidDataException("wake_size_invalid");
                    frame=await socket.ReceiveAsync(new ArraySegment<byte>(buffer,count,buffer.Length-count),timeout.Token);
                    if(frame.MessageType!=WebSocketMessageType.Text)throw new InvalidDataException("wake_type_invalid");
                    count+=frame.Count;
                }while(!frame.EndOfMessage);
                var message=CanonicalJsonV2.Parse(Encoding.UTF8.GetString(buffer,0,count));
                if(message.EnumerateObject().Count()!=1)throw new InvalidDataException("wake_command_forbidden");
                var type=message.GetProperty("type").GetString();
                if(type=="plan_available")return;
                if(type is not ("ready" or "keepalive"))throw new InvalidDataException("wake_command_forbidden");
            }
        }
        catch(OperationCanceledException)when(!ct.IsCancellationRequested){}
        catch(WebSocketException){await Task.Delay(TimeSpan.FromSeconds(5),ct);}
    }
}
public sealed class RuntimeTransportException(string code,bool transient=false):Exception(code)
{
    public bool Transient{get;}=transient;
}

public sealed class OutcomeDelivery(RuntimeTransport transport,AppPlanJournal journal,Func<DateTimeOffset>? clock=null)
{
    public async Task DeliverAsync(OutcomeV2 outcome,RuntimeSession? original,Func<CancellationToken,Task<RuntimeSession>> registerRecovery,CancellationToken ct)
    {
        DateTimeOffset Now()=>(clock??(()=>DateTimeOffset.UtcNow))();
        RuntimeSession? recovery=null;
        if(original is not null&&(original.DeviceId!=outcome.DeviceId||original.TenantId!=outcome.TenantId||original.Generation!=outcome.RuntimeGeneration||original.InstanceId!=outcome.RuntimeInstanceId))original=null;
        while(true)
        {
            var useRecovery=original is null||original.ExpiresAt<=Now();
            try
            {
                if(useRecovery&&(recovery is null||recovery.ExpiresAt<=Now()))recovery=await registerRecovery(ct);
                if(await TryDeliverAsync(outcome,useRecovery?recovery!:original!,useRecovery,ct))return;
            }
            catch(RuntimeTransportException e)when(e.Message=="runtime_session_invalid")
            {
                if(useRecovery)recovery=null;else original=null;
            }
            catch(RuntimeTransportException e)when(e.Message=="plan_lease_invalid")
            {
                original=null; recovery=null;
            }
            catch(RuntimeTransportException e)when(e.Transient||e.Message is "runtime_session_active" or "reconciliation_session_active"){}
            catch(HttpRequestException){}
            await Task.Delay(TimeSpan.FromSeconds(5),ct);
        }
    }
    public async Task<bool> TryDeliverAsync(OutcomeV2 outcome,RuntimeSession session,bool acknowledgementOnly,CancellationToken ct)
    {
        if(outcome.OverallStatus is not ("succeeded" or "failed_without_effect"))throw new InvalidDataException("normal_terminal_outcome_required");
        var stored=journal.Events.Last(e=>e.PlanId==outcome.PlanId&&e.Kind=="outcome").Data;
        if(stored!=outcome.ToJson())throw new InvalidDataException("stored_outcome_mismatch");
        using var timeout=CancellationTokenSource.CreateLinkedTokenSource(ct);timeout.CancelAfter(TimeSpan.FromSeconds(15));
        try
        {
            var result=await transport.SendAsync(HttpMethod.Post,"plans/"+Uri.EscapeDataString(outcome.PlanId)+(acknowledgementOnly?"/acknowledge":"/outcome"),stored,timeout.Token,session);
            if(!result.TryGetProperty("accepted",out var accepted)||accepted.ValueKind!=JsonValueKind.True)throw new InvalidDataException("outcome_acknowledgement_invalid");
            journal.Append("acknowledged",outcome.PlanId,"{}");return true;
        }
        catch(RuntimeTransportException e)when(e.Transient){return false;}
        catch(HttpRequestException){return false;}
        catch(IOException){return false;}
        catch(OperationCanceledException)when(!ct.IsCancellationRequested){return false;}
    }
}

public sealed class AppCredentialStore(string root,Uri origin)
{
    private string Path=>System.IO.Path.Combine(root,"device.v2.dpapi");
    private byte[] Entropy=>SHA256.HashData(Encoding.UTF8.GetBytes("AI00 App credential v2\n"+origin.AbsoluteUri));
    public RuntimeSession? LoadSession()
    {
        var path=System.IO.Path.Combine(root,"session.v2.dpapi");
        if(!File.Exists(path))return null;
        var clear=ProtectedData.Unprotect(File.ReadAllBytes(path),Entropy,DataProtectionScope.CurrentUser);
        try{return JsonSerializer.Deserialize<RuntimeSession>(clear)??throw new InvalidDataException("stored_session_invalid");}
        finally{CryptographicOperations.ZeroMemory(clear);}
    }
    public void SaveSession(RuntimeSession session)
    {
        var clear=JsonSerializer.SerializeToUtf8Bytes(session);
        var path=System.IO.Path.Combine(root,"session.v2.dpapi");var temp=path+".tmp-"+Guid.NewGuid().ToString("N");
        try
        {
            var cipher=ProtectedData.Protect(clear,Entropy,DataProtectionScope.CurrentUser);
            using(var stream=new FileStream(temp,FileMode.CreateNew,FileAccess.Write,FileShare.None,4096,FileOptions.WriteThrough)){stream.Write(cipher);stream.Flush(true);}
            File.Move(temp,path,true);
        }
        finally{CryptographicOperations.ZeroMemory(clear);if(File.Exists(temp))File.Delete(temp);}
    }
    public JsonElement? Load()
    {
        if(!File.Exists(Path))return null;
        var clear=ProtectedData.Unprotect(File.ReadAllBytes(Path),Entropy,DataProtectionScope.CurrentUser);
        try{return CanonicalJsonV2.Parse(Encoding.UTF8.GetString(clear));}finally{CryptographicOperations.ZeroMemory(clear);}
    }
    public void Save(byte[] clear)
    {
        var cipher=ProtectedData.Protect(clear,Entropy,DataProtectionScope.CurrentUser);
        var temp=Path+".tmp-"+Guid.NewGuid().ToString("N");
        try{using(var stream=new FileStream(temp,FileMode.CreateNew,FileAccess.Write,FileShare.None,4096,FileOptions.WriteThrough)){stream.Write(cipher);stream.Flush(true);}File.Move(temp,Path);}
        finally{if(File.Exists(temp))File.Delete(temp);}
    }
}

public sealed class RuntimeSessionWorker(DiagnosticPipeHost diagnostics,RuntimeTransport transport,DeviceSigningKey key,
    AppCredentialStore credentials,AppPlanJournal journal,VisMockupAdapter adapter,PostConditionProbes probes,
    HostManifest manifest,IHostApplicationLifetime lifetime):BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken ct)
    {
        await diagnostics.Ready.WaitAsync(ct);
        var credential=credentials.Load()??await PairAsync(ct);
        ValidateCredential(credential);
        var deviceId=credential.GetProperty("device_id").GetString()!;var tenantId=credential.GetProperty("tenant_gid").GetString()!;
        var generation=credential.GetProperty("runtime_generation").GetInt64();var secret=credential.GetProperty("device_credential").GetString()!;
        var keyId=credential.GetProperty("device_key_id").GetString()!;
        var executor=new PlanExecutionWorker(journal,adapter,key,keyId,manifest.PlanKeys);
        var savedSession=credentials.LoadSession();
        var recovered=executor.Recover();
        if(recovered.Count>0)
        {
            foreach(var outcome in recovered)
            {
                if(outcome.OverallStatus is "succeeded" or "failed_without_effect")
                {
                    await DeliverNormalAsync(outcome,savedSession,deviceId,tenantId,generation,secret,ct);
                    continue;
                }
                await diagnostics.SendAsync(new{type="diagnostic",code="recovery_required"},ct);
                await ReconcileAsync(outcome,deviceId,tenantId,generation,secret,keyId,ct);
                lifetime.StopApplication();return;
            }
        }
        var session=savedSession is not null&&savedSession.ExpiresAt>DateTimeOffset.UtcNow ? savedSession : await RegisterAsync(deviceId,tenantId,generation,secret,null,ct);
        credentials.SaveSession(session);
        while(!ct.IsCancellationRequested)
        {
            JsonElement leased;
            try
            {
                if(session.ExpiresAt-DateTimeOffset.UtcNow<TimeSpan.FromMinutes(2))
                {
                    var renewed=await transport.SendAsync(HttpMethod.Post,"runtime/renew",null,ct,session);
                    session=session with{ExpiresAt=renewed.GetProperty("expires_at").GetDateTimeOffset()};
                    credentials.SaveSession(session);
                }
                await transport.SendAsync(HttpMethod.Post,"heartbeat",null,ct,session);
                leased=await transport.SendAsync(HttpMethod.Post,"plans/lease",new{lease_seconds=120},ct,session);
            }
            catch(RuntimeTransportException e)when(e.Transient){await Task.Delay(TimeSpan.FromSeconds(5),ct);continue;}
            catch(HttpRequestException){await Task.Delay(TimeSpan.FromSeconds(5),ct);continue;}
            if(leased.ValueKind==JsonValueKind.Null){await transport.WaitForWakeAsync(session,ct);continue;}
            var lease=new LeasedPlan(leased.GetProperty("lease_id").GetString()!,leased.GetProperty("lease_until").GetDateTimeOffset(),leased.GetProperty("plan").GetRawText());
            var outcome=await executor.ExecuteAsync(lease,session,ct);
            if(outcome.OverallStatus is "succeeded" or "failed_without_effect")
            {
                await DeliverNormalAsync(outcome,session,deviceId,tenantId,generation,secret,ct);
                if(session.ExpiresAt<=DateTimeOffset.UtcNow){lifetime.StopApplication();return;}
                continue;
            }
            // Persisted first. A failed send leaves recovery work, never an execution retry.
            using var reportTimeout=new CancellationTokenSource(TimeSpan.FromSeconds(15));
            await transport.SendAsync(HttpMethod.Post,"plans/"+Uri.EscapeDataString(outcome.PlanId)+"/outcome",outcome.Document,reportTimeout.Token,session);
            if(outcome.OverallStatus is "outcome_unknown" or "manual_review_required")
            {
                await diagnostics.SendAsync(new{type="diagnostic",code="recovery_required"},ct);
                // COM may still run. Exit; a new process can acquire a recovery-only session after expiry.
                lifetime.StopApplication();return;
            }
            journal.Append("acknowledged",outcome.PlanId,"{}");
        }
    }
    private Task DeliverNormalAsync(OutcomeV2 outcome,RuntimeSession? original,string deviceId,string tenantId,long generation,string secret,CancellationToken ct) =>
        new OutcomeDelivery(transport,journal).DeliverAsync(outcome,original,token=>RegisterAsync(deviceId,tenantId,generation,secret,outcome.PlanId,token),ct);
    private void ValidateCredential(JsonElement credential)
    {
        var keyId="device-key-"+CanonicalJsonV2.HexHash(CanonicalJsonV2.Serialize(key.PublicJwk));
        if(credential.GetProperty("protocol").GetString()!="ai00.connector.execution-plan.v2"||credential.GetProperty("runtime_type").GetString()!="electron"||credential.GetProperty("device_key_id").GetString()!=keyId)throw new InvalidDataException("device_credential_binding_invalid");
    }
    private async Task<JsonElement> PairAsync(CancellationToken ct)
    {
        using var bootstrap=new BootstrapEncryptionKey();
        var publicKey=JsonNode.Parse(bootstrap.PublicJwk.GetRawText())!.AsObject();publicKey["alg"]="RSA-OAEP-256";
        var created=await transport.SendAsync(HttpMethod.Post,"pairings",new{device_signing_jwk=key.PublicJwk,bootstrap_encryption_jwk=publicKey,nonce=Convert.ToHexString(RandomNumberGenerator.GetBytes(32)).ToLowerInvariant()},ct);
        var id=created.GetProperty("pairing_id").GetString()!;
        await diagnostics.SendAsync(new{type="pairing_state",pairing_id=id,state="created"},ct);
        var decrypted=bootstrap.Decrypt(Decode(created.GetProperty("encrypted_challenge").GetString()!));
        try
        {
            var challenge=created.GetProperty("signing_challenge").GetString()!;
            if(!challenge.StartsWith("ai00.app-pairing.v2:"+id+":",StringComparison.Ordinal)||challenge.Length>1024)throw new InvalidDataException("pairing_challenge_invalid");
            while(DateTimeOffset.UtcNow<created.GetProperty("expires_at").GetDateTimeOffset())
            {
                try
                {
                    var result=await transport.SendAsync(HttpMethod.Post,"pairings/"+Uri.EscapeDataString(id)+"/activate",new{signing_challenge=challenge,signature=key.Sign(Encoding.UTF8.GetBytes(challenge)),decrypted_challenge=Encoding.UTF8.GetString(decrypted)},ct);
                    var envelope=result.GetProperty("encrypted_credential_envelope");
                    if(envelope.GetProperty("algorithm").GetString()!="RSA-OAEP-256+A256GCM")throw new InvalidDataException("bootstrap_algorithm_invalid");
                    var aesKey=bootstrap.Decrypt(Decode(envelope.GetProperty("encrypted_key").GetString()!));
                    var ciphertext=Decode(envelope.GetProperty("ciphertext").GetString()!);var clear=new byte[ciphertext.Length-16];
                    try
                    {
                        using var aes=new AesGcm(aesKey,16);aes.Decrypt(Decode(envelope.GetProperty("nonce").GetString()!),ciphertext.AsSpan(0,clear.Length),ciphertext.AsSpan(clear.Length),clear);
                        var credential=CanonicalJsonV2.Parse(Encoding.UTF8.GetString(clear));ValidateCredential(credential);credentials.Save(clear);
                        await diagnostics.SendAsync(new{type="pairing_state",pairing_id=id,state="activated"},ct);return credential;
                    }
                    finally{CryptographicOperations.ZeroMemory(aesKey);CryptographicOperations.ZeroMemory(clear);}
                }
                catch(RuntimeTransportException e)when(e.Message=="pairing_not_approved"||e.Transient){await Task.Delay(TimeSpan.FromSeconds(5),ct);}
                catch(HttpRequestException){await Task.Delay(TimeSpan.FromSeconds(5),ct);}
            }
            await diagnostics.SendAsync(new{type="pairing_state",pairing_id=id,state="expired"},ct);
            throw new InvalidDataException("pairing_expired");
        }
        finally{CryptographicOperations.ZeroMemory(decrypted);}
    }
    private async Task<RuntimeSession> RegisterAsync(string deviceId,string tenantId,long generation,string credential,string? planId,CancellationToken ct)
    {
        var instance="app-"+Guid.NewGuid().ToString("N");
        var challenge=await transport.SendAsync(HttpMethod.Post,"runtime/challenge",new{device_id=deviceId,generation,runtime_instance_id=instance,runtime_type="electron",plan_id=planId},ct,credential:credential);
        var text=challenge.GetProperty("challenge").GetString()!;
        if(!text.StartsWith("ai00.runtime-possession.v2:",StringComparison.Ordinal)||text.Length>1024||challenge.GetProperty("expires_at").GetDateTimeOffset()<=DateTimeOffset.UtcNow)throw new InvalidDataException("runtime_challenge_invalid");
        var result=await transport.SendAsync(HttpMethod.Post,planId==null?"runtime/register":"runtime/reconciliation/register",new{device_id=deviceId,generation,runtime_instance_id=instance,runtime_type="electron",plan_id=planId,challenge=text,signature=key.Sign(Encoding.UTF8.GetBytes(text))},ct,credential:credential);
        if(result.GetProperty("device_id").GetString()!=deviceId||result.GetProperty("runtime_generation").GetInt64()!=generation||result.GetProperty(planId==null?"runtime_instance_id":"recovery_instance_id").GetString()!=instance)throw new InvalidDataException("runtime_session_binding_invalid");
        return new(deviceId,tenantId,generation,instance,result.GetProperty("session_token").GetString()!,result.GetProperty("expires_at").GetDateTimeOffset());
    }
    private async Task ReconcileAsync(OutcomeV2 outcome,string deviceId,string tenantId,long generation,string credential,string keyId,CancellationToken ct)
    {
        RuntimeSession session;
        while(true)
        {
            try{session=await RegisterAsync(deviceId,tenantId,generation,credential,outcome.PlanId,ct);break;}
            catch(RuntimeTransportException e)when(e.Message is "runtime_session_active" or "runtime_session_conflict" or "reconciliation_session_active"){await Task.Delay(TimeSpan.FromSeconds(10),ct);}
        }
        var context=await transport.SendAsync(HttpMethod.Get,"plans/"+Uri.EscapeDataString(outcome.PlanId)+"/probe",null,ct,session);
        if(context.GetProperty("scope").GetString()!="read_only_post_condition_probe"||context.GetProperty("plan_id").GetString()!=outcome.PlanId||context.GetProperty("plan_hash").GetString()!=outcome.PlanHash||context.GetProperty("lease_id").GetString()!=outcome.LeaseId||context.GetProperty("device_id").GetString()!=session.DeviceId||context.GetProperty("tenant_id").GetString()!=session.TenantId||context.GetProperty("runtime_generation").GetInt64()!=session.Generation||context.GetProperty("runtime_instance_id").GetString()!=outcome.RuntimeInstanceId||context.GetProperty("recovery_instance_id").GetString()!=session.InstanceId)throw new InvalidDataException("recovery_context_invalid");
        var observations=new List<object>();
        foreach(var probe in context.GetProperty("required_probes").EnumerateArray())
        {
            object observation;
            try{observation=await probes.ObserveAsync(probe.GetProperty("probe_id").GetString()!,ct);}
            catch(Ai00.Connector.Contracts.ConnectorException){observation=new{classification="inconclusive",observed_result=(object?)null};}
            var observed=JsonSerializer.SerializeToElement(observation);
            observations.Add(new{step_id=probe.GetProperty("step_id").GetString(),probe_id=probe.GetProperty("probe_id").GetString(),classification=observed.GetProperty("classification").GetString(),observed_result=observed.GetProperty("observed_result")});
        }
        var evidence=JsonSerializer.SerializeToNode(new{protocol="ai00.connector.reconciliation-evidence.v2",scope="read_only_post_condition_probe",plan_id=outcome.PlanId,plan_hash=outcome.PlanHash,lease_id=outcome.LeaseId,tenant_id=session.TenantId,device_id=session.DeviceId,runtime_generation=session.Generation,runtime_instance_id=outcome.RuntimeInstanceId,recovery_instance_id=session.InstanceId,recovery_session_id=context.GetProperty("recovery_session_id").GetString(),nonce=context.GetProperty("nonce").GetString(),probes=observations,journal_sequence=context.GetProperty("next_journal_sequence").GetInt64(),reported_at=PlanExecutionWorker.Timestamp(DateTimeOffset.UtcNow),device_key_id=keyId,signature_algorithm="ecdsa-p256-sha256"})!.AsObject();
        evidence["signature"]=key.Sign(CanonicalJsonV2.Serialize(evidence.ToJsonString()));
        journal.Append("reconciliation_evidence",outcome.PlanId,evidence.ToJsonString());
        await transport.SendAsync(HttpMethod.Post,"plans/"+Uri.EscapeDataString(outcome.PlanId)+"/reconcile",evidence,ct,session);
        journal.Append("reconciled",outcome.PlanId,"{}");
        // Inconclusive observations deliberately remain blocked for cloud/manual resolution.
        journal.Append("manual_review_required",outcome.PlanId,"{}");
    }
    private static byte[] Decode(string text)=>Convert.FromBase64String(text.Replace('-','+').Replace('_','/')+new string('=',(4-text.Length%4)%4));
}
