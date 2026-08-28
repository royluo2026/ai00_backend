import asyncio
from datetime import UTC, datetime

from backend.capability_v2.contracts import (
    ActorIdentity, ConsumerDescriptor, ConsumerIdentity, ConsumerType, CorrelationRef,
    TenantIdentity,
)
from plugins.integration.integration_backend.application.sync import SyncService, TargetAdapter


def test_sync_dispatches_only_the_governed_reference_dataset_target():
    trace = []

    class Client:
        async def invoke(self, invocation, identity, correlation, deadline=None):
            trace.append((invocation, identity, correlation))
            return {"status": "succeeded"}

    identity = ConsumerIdentity(
        actor=ActorIdentity(
            service_id="integration-sync", authentication_method="service-token",
            authenticated_at=datetime.now(UTC),
        ),
        tenant=TenantIdentity(tenant_id="team-1", membership="service"),
        consumer=ConsumerDescriptor(
            type=ConsumerType.WORKER, consumer_id="domain.integration",
        ),
    )
    class Catalog:
        def require_stable(self, capability_id, major_version, minimum_release):
            assert (capability_id, major_version, minimum_release) == (
                "knowledge.reference_dataset.publish", 1, "rel_test"
            )

    service = SyncService(Client(), Catalog())
    adapter = TargetAdapter(
        target_domain="knowledge", capability_id="knowledge.reference_dataset.publish",
        major_version=1, minimum_catalog_release="rel_test",
    )

    asyncio.run(service.apply_batch(
        adapter=adapter,
        payload={
            "dataset_gid": "rates", "expected_version": 1,
            "schema": {"fields": [{"name": "rate", "source_field": "rate"}]},
            "rows": [{"key": "CN", "values": [{"field": "rate", "value": 1.2}]}],
        },
        idempotency_key="sync-1:batch-1",
        correlation=CorrelationRef(request_id="req-1", trace_id="trace-1"),
        identity=identity,
    ))

    invocation, invoked_identity, _ = trace[-1]
    assert invocation.capability_id == "knowledge.reference_dataset.publish"
    assert invocation.major_version == 1
    assert invocation.idempotency_key == "sync-1:batch-1"
    assert invoked_identity.consumer.consumer_id == "domain.integration"
