"""Continue manual cache batches through their explicit Gateway worker consumer."""
import asyncio
from contextlib import suppress
from datetime import UTC, datetime
import logging
import os
import uuid

from backend.capability_v2.contracts import ConsumerDescriptor, ConsumerType, CorrelationRef
from backend.capability_v2.domain_client import DomainCapabilityClient, DomainInvocation
from backend.capability_v2.gateway import get_default_gateway
from backend.capability_v2.identity import AuthenticatedPrincipal, authenticated_user_identity
from backend.platform_sdk.identity import get_active_identity_profile
from ..data.cloud_model_cache_repository import CloudModelCacheRepository

log=logging.getLogger(__name__)
WORKER_ID='simulation.model_cache.worker'


class CloudModelCacheWorker:
    def __init__(self,repository=None,user_loader=get_active_identity_profile,gateway_factory=get_default_gateway):
        self.repo=repository or CloudModelCacheRepository(); self.user_loader=user_loader; self.gateway_factory=gateway_factory
        self.task=None; self.last_error=None

    async def run_once(self):
        self.last_error=None
        rows=await asyncio.to_thread(self.repo.candidates)
        client=DomainCapabilityClient(self.gateway_factory())
        for row in rows:
            user=await asyncio.to_thread(self.user_loader,row['actor_gid'])
            tenant=str((user or {}).get('team_id') or f"user:{row['actor_gid']}")
            if not user or user.get('org_role')!='super_admin' or tenant!=row['tenant_gid']:
                await asyncio.to_thread(self.repo.failure,row['batch_id'],row['tenant_gid'],'cache_actor_revoked')
                continue
            principal=AuthenticatedPrincipal(user_id=str(user['gid']),authentication_method='durable_cache_trigger',authenticated_at=datetime.now(UTC))
            identity=authenticated_user_identity(user,principal).model_copy(update={'consumer':ConsumerDescriptor(type=ConsumerType.WORKER,consumer_id=WORKER_ID)})
            request_id='cache-work-'+uuid.uuid4().hex
            result=await client.invoke(DomainInvocation('simulation.model_cache.advance',1,{'batch_id':row['batch_id']},idempotency_key=request_id),identity,CorrelationRef(request_id=request_id))
            if result.error:
                self.last_error=result.error.code
                # Preserve intent on an unavailable Gateway; access revocation is terminal.
                if result.error.code in ('permission_denied','actor_inactive','cache_trigger_forbidden'):
                    await asyncio.to_thread(self.repo.failure,row['batch_id'],row['tenant_gid'],'cache_actor_revoked')
        return bool(rows)

    async def run(self):
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError: raise
            except Exception as exc:
                self.last_error=type(exc).__name__
                log.warning('Simulation cache worker unavailable (%s)',self.last_error)
            await asyncio.sleep(2)

    async def start(self):
        enabled=os.getenv('AI00_SIMULATION_MODEL_CACHE_WORKER','1' if os.getenv('AI00_DEPLOYMENT_PROFILE')=='test-governance' else '0')=='1'
        if enabled: self.task=asyncio.create_task(self.run(),name=WORKER_ID)

    async def stop(self):
        if self.task:
            self.task.cancel()
            with suppress(asyncio.CancelledError): await self.task
            self.task=None

    def health(self): return {'enabled':self.task is not None,'running':bool(self.task and not self.task.done()),'error_code':self.last_error}
