"""Run real registered handlers through the production Gateway and role policy.

Only Catalog storage, identity records and external I/O are deterministic fixtures.
No release is published outside the private in-memory test store.
"""
import asyncio
from datetime import UTC, datetime
from unittest.mock import patch
from backend.capabilities.registry_next import CapabilityRegistry
from backend.capability_v2.catalog import CatalogResolver, build_release
from backend.capability_v2.catalog_store import InMemoryCatalogStore
from backend.capability_v2.contracts import ActorIdentity, ConsumerDescriptor, ConsumerIdentity, ConsumerType, InvocationEnvelope, TenantIdentity
from backend.capability_v2.gateway import CapabilityGatewayService
from backend.capability_v2.outcomes import InMemoryOutcomeStore
from backend.capability_v2.policies import LegacyServerGatewayPolicy
from backend.capability_v2.reliability import ApprovalService, InMemoryApprovalStore, InMemoryRateLimiter, ReliabilityCoordinator
from backend.routers.deps import build_capability_authorization_grants


class DesktopGatewayMatrix:
    def __init__(self):self.gateways={};self.users={};self.rows=[]

    def __call__(self,entry,payload,context):
        key=(entry.spec.id,entry.spec.version)
        user={'gid':context.user_gid,'team_id':context.team_gid,'system_role':'super_admin','org_role':'super_admin','is_active':True}
        self.users[context.user_gid]=user
        if key not in self.gateways:
            registry=CapabilityRegistry();registry.register(entry.spec,entry.handler,descriptor=entry.descriptor)
            release=build_release([entry.descriptor]);store=InMemoryCatalogStore();store.publish(release)
            approvals=ApprovalService(InMemoryApprovalStore())
            policy=LegacyServerGatewayPolicy(user_loader=self.users.get,grants_resolver=lambda identity,user:build_capability_authorization_grants(user,identity.tenant.tenant_id),approval_service=approvals)
            self.gateways[key]=CapabilityGatewayService(CatalogResolver(store,registry),policy,reliability=ReliabilityCoordinator(InMemoryOutcomeStore(),InMemoryRateLimiter(limit=1000))).bind_release(release.release_id)
        gateway=self.gateways[key]
        identity=ConsumerIdentity(actor=ActorIdentity(user_id=context.user_gid,authentication_method='jwt',authenticated_at=datetime.now(UTC)),tenant=TenantIdentity(tenant_id=context.team_gid,membership='member',active_roles=('super_admin',)),consumer=ConsumerDescriptor(type=ConsumerType.WEB,consumer_id='ai00.web'))
        request_id=getattr(context,'request_id',None) or 'matrix-'+str(len(self.rows))
        envelope=InvocationEnvelope(capability_id=key[0],major_version=key[1],catalog_release=gateway.catalog_release,payload=payload,identity=identity,request_id=request_id,trace_id=request_id,idempotency_key=getattr(context,'idempotency_key',None) or request_id)
        async def execute():
            with patch('backend.routers.deps._get_user_grants',return_value=[]),patch('backend.platform_sdk.project_access.list_user_project_memberships',return_value=[]):
                approval=None;pending=None
                if entry.descriptor.confirmation_policy!='none':
                    pending=await gateway.invoke(envelope)
                    assert not pending.ok and pending.error.code=='confirmation_required',pending
                    approval=await gateway.request_approval(envelope)
                    approved=envelope.model_copy(update={'approval_reference':approval.token})
                else:approved=envelope
                result=await gateway.invoke(approved)
                assert result.ok, (key,result.model_dump(mode='json'))
                return result,approval is not None,pending
        result,confirmed,pending=asyncio.run(execute())
        self.rows.append({'id':key[0],'version':key[1],'request_id':request_id,'gateway_result':result.model_dump(mode='json'),'gateway_pending':pending.model_dump(mode='json') if pending else None,'confirmation_exercised':confirmed,'policy':'LegacyServerGatewayPolicy','handler':entry.handler.__module__,'fixture_scope':'real Gateway + registered owner handler; deterministic identity/SQL/external I/O ports'})
        return result.data

