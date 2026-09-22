using Ai00.Connector.Contracts.V2;
namespace Ai00.Connector.AppHost;

// Runtime identity is populated only after authenticated runtime registration.
public sealed class ViewerInteractionRuntimeContext
{
    private readonly object sync=new();
    private RuntimeSession? session;
    public string? DeviceKeyId {get;private set;}
    public RuntimeSession? Current {get{lock(sync)return session;}}
    public void Update(RuntimeSession value,string deviceKeyId){lock(sync){session=value;DeviceKeyId=deviceKeyId;}}
    public void Clear(){lock(sync){session=null;DeviceKeyId=null;}}
}

public sealed class ViewerInteractionSession
{
    private readonly object sync=new();
    private readonly HashSet<string> retired=new(StringComparer.Ordinal);
    private ViewerInteractionGrant? grant;
    private ViewerInteractionGrant? dispatch;
    private TimeSpan deadline;
    public ViewerInteractionGrant? Current {get{lock(sync)return grant;}}
    public void Install(ViewerInteractionGrant value,RuntimeSession? runtime,DateTimeOffset now,TimeSpan monotonic)
    {
        lock(sync)
        {
            if(!Matches(value,runtime,now))throw new InvalidDataException("interaction_scope_denied");
            if(value.IssuedAt>now || value.ExpiresAt<=now)throw new InvalidDataException("authorization_expired");
            if(retired.Contains(value.SessionNonce)||retired.Count>=10000)throw new InvalidDataException("interaction_closed");
            if(grant is not null)
            {
                if(grant.SessionNonce!=value.SessionNonce)throw new InvalidDataException("interaction_already_open");
                if(value.Generation<=grant.Generation || value.IssuedAt<grant.IssuedAt)throw new InvalidDataException("grant_generation_stale");
                foreach(var field in new[]{"actor_id","tenant_id","device_id","runtime_instance_id","workspace_gid","document_gid","source_association_id","document_session","policy_version","operations"})
                    if(!CanonicalJsonV2.Serialize(grant.Document.GetProperty(field)).SequenceEqual(CanonicalJsonV2.Serialize(value.Document.GetProperty(field))))throw new InvalidDataException("interaction_scope_denied");
            }
            grant=value;deadline=monotonic+(value.ExpiresAt-now);
        }
    }
    public string? Validate(string interactionId,RuntimeSession? runtime,DateTimeOffset now,TimeSpan monotonic)
    {
        lock(sync)
        {
            if(grant is null || grant.SessionNonce!=interactionId)return "interaction_closed";
            if(!Matches(grant,runtime,now))return "interaction_scope_denied";
            if(now>=grant.ExpiresAt||monotonic>=deadline)return "authorization_expired";
            return null;
        }
    }
    public void Invalidate(string reason){lock(sync){if(grant is not null)retired.Add(grant.SessionNonce);grant=null;}}
    public IDisposable BeginDispatch(ViewerInteractionGrant expected)
    {lock(sync){dispatch=expected;return new DispatchLease(this);}}
    public bool IsDispatchAuthorized(RuntimeSession? runtime,DateTimeOffset now,TimeSpan monotonic)
    {
        lock(sync)return dispatch is not null&&grant is not null&&dispatch.SessionNonce==grant.SessionNonce
            && dispatch.SourceAssociationId==grant.SourceAssociationId&&dispatch.DocumentSession==grant.DocumentSession
            && Validate(dispatch.SessionNonce,runtime,now,monotonic) is null;
    }
    private sealed class DispatchLease(ViewerInteractionSession owner):IDisposable
    {public void Dispose(){lock(owner.sync)owner.dispatch=null;}}
    private static bool Matches(ViewerInteractionGrant value,RuntimeSession? runtime,DateTimeOffset now)=>runtime is not null && runtime.DeviceId==value.DeviceId && runtime.TenantId==value.TenantId && runtime.InstanceId==value.RuntimeInstanceId && runtime.ExpiresAt>now;
}
