import asyncio
from datetime import UTC, datetime

from backend.capability_v2.contracts import ActorIdentity, ConsumerDescriptor, ConsumerIdentity, ConsumerType, CorrelationRef, TenantIdentity
from plugins.integration.integration_backend.application.sync import SyncService, TargetAdapter


def test_import_writes_target_through_domain_capability_client():
    trace = []

    class Client:
        async def invoke(self, invocation, identity, correlation, deadline=None):
            trace.append((invocation, identity, correlation))
            return {"status": "succeeded"}

    identity = ConsumerIdentity(
        actor=ActorIdentity(service_id="integration-sync", authentication_method="service-token", authenticated_at=datetime.now(UTC)),
        tenant=TenantIdentity(tenant_id="tenant-1", membership="service"),
        consumer=ConsumerDescriptor(type=ConsumerType.WORKER, consumer_id="domain.integration"),
    )
    service = SyncService(Client(), identity)
    adapter = TargetAdapter(
        target_domain="knowledge",
        capability_id="knowledge.reference_data.change.apply",
        major_version=1,
        minimum_catalog_release="rel_test",
    )

    asyncio.run(
        service.apply_batch(
            adapter=adapter,
            payload={"dataset_gid": "rates", "expected_version": 1, "schema": {}, "rows": [{"key": "CN", "rate": 1.2}]},
            idempotency_key="sync-1:batch-1",
            correlation=CorrelationRef(request_id="req-1", trace_id="trace-1"),
        )
    )

    invocation, invoked_identity, _ = trace[-1]
    assert invocation.capability_id == "knowledge.reference_data.change.apply"
    assert invocation.major_version == 1
    assert invocation.idempotency_key == "sync-1:batch-1"
    assert invoked_identity.consumer.consumer_id == "domain.integration"
