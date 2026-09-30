from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from backend.capabilities.models_next import CapabilitySpec
from backend.capabilities.registry_next import CapabilityRegistry
from backend.capability_v2.authorization import AuthorizationDecision
from backend.capability_v2.catalog import CatalogResolver, build_release
from backend.capability_v2.catalog_store import InMemoryCatalogStore
from backend.capability_v2.contracts import (
    ActorIdentity, AutomationLevel, CapabilityDescriptorV2, ConsumerDescriptor,
    ConsumerIdentity, ConsumerType, ExecutionBudget, ExposurePolicy, InvocationEnvelope,
    TenantIdentity,
)
from backend.capability_v2.gateway import CapabilityGatewayService
from backend.capability_v2.metrics import InMemoryCapabilityMetrics
from backend.capability_v2.resource_budget import (
    MemoryPressureSampler, ResourceAdmissionController,
)


class _Policy:
    def authorize(self, *_args):
        return AuthorizationDecision(allowed=True, code="allowed", policy_version="test")
    def approve(self, *_args):
        return None
    def project(self, _descriptor, _identity, data):
        return data


def _gateway(handler, budget: ExecutionBudget, *, ratio: float | None = None):
    descriptor = CapabilityDescriptorV2(
        id="craft.routing.get", major_version=1, owner_domain="craft",
        title="Get routing", description="Return one routing.",
        use_when="A routing is needed.", do_not_use_when="A write is needed.",
        exposure=ExposurePolicy(web=True), automation_level=AutomationLevel.A2,
        authorization_policy="craft.routing.read",
        input_schema={
            "type": "object", "properties": {"query": {"type": "string"}},
            "additionalProperties": False,
        },
        output_schema={
            "type": "object", "properties": {"routing_id": {"type": "string"}},
            "required": ["routing_id"], "additionalProperties": False,
        },
        schema_hash="sha256:" + "a" * 64,
        execution_budget=budget,
    )
    registry = CapabilityRegistry()
    registry.register(CapabilitySpec(
        id=descriptor.id, owner="craft",
        input_schema=descriptor.input_schema, output_schema=descriptor.output_schema,
    ), handler)
    release = build_release([descriptor])
    store = InMemoryCatalogStore(); store.publish(release)
    current = int(1000 * ratio) if ratio is not None else 100
    sampler = MemoryPressureSampler(
        file_reader=lambda path: str(current if path.endswith("memory.current") else 1000),
        rss_reader=lambda: 123,
    )
    admission = ResourceAdmissionController(sampler)
    metrics = InMemoryCapabilityMetrics()
    gateway = CapabilityGatewayService(
        CatalogResolver(store, registry), _Policy(), admission=admission, metrics=metrics,
        admission_timeout_seconds=0.01,
    ).bind_release(release.release_id)
    identity = ConsumerIdentity(
        actor=ActorIdentity(
            user_id="user_1", authentication_method="jwt",
            authenticated_at=datetime.now(UTC),
        ),
        tenant=TenantIdentity(tenant_id="tenant_1", membership="member"),
        consumer=ConsumerDescriptor(type=ConsumerType.WEB, consumer_id="secret.consumer"),
    )
    envelope = InvocationEnvelope(
        capability_id=descriptor.id, major_version=1, catalog_release=release.release_id,
        payload={}, identity=identity, request_id="request_1", trace_id="trace_1",
    )
    return gateway, envelope, admission, metrics


def test_gateway_rejects_oversized_input_before_dispatch():
    calls = []
    gateway, envelope, _admission, _metrics = _gateway(
        lambda *_args: calls.append(True), ExecutionBudget(max_input_bytes=1),
    )

    result = asyncio.run(gateway.invoke(envelope))

    assert result.error.code == "capability_input_limit_exceeded"
    assert calls == []


def test_gateway_rejects_oversized_output_and_releases_admission_lease():
    gateway, envelope, admission, metrics = _gateway(
        lambda *_args: {"routing_id": "x" * 100}, ExecutionBudget(max_output_bytes=32),
    )

    result = asyncio.run(gateway.invoke(envelope))

    assert result.error.code == "capability_output_limit_exceeded"
    assert result.error.retryable is False
    assert admission.in_flight("craft.routing.get@1") == 0
    assert metrics.recent()[-1].output_bytes > 32


def test_gateway_maps_memory_pressure_and_never_logs_payload_or_raw_consumer_key():
    gateway, envelope, admission, metrics = _gateway(
        lambda *_args: {"routing_id": "r1"}, ExecutionBudget(memory_class="large"),
        ratio=0.85,
    )

    result = asyncio.run(gateway.invoke(envelope))

    assert result.error.code == "resource_pressure"
    assert result.error.retryable is True
    assert admission.in_flight("craft.routing.get@1") == 0
    record = metrics.recent()[-1]
    assert record.consumer_key_hash != "secret.consumer"
    assert not hasattr(record, "payload")
    assert not hasattr(record, "result")


def test_provider_failure_releases_lease_for_next_invocation():
    attempts = 0
    def handler(*_args):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("boom")
        return {"routing_id": "r1"}
    gateway, envelope, admission, _metrics = _gateway(
        handler,
        ExecutionBudget(max_parallel_per_consumer=1, max_parallel_per_tenant=1),
    )

    first = asyncio.run(gateway.invoke(envelope))
    second = asyncio.run(gateway.invoke(envelope))

    assert first.error.code == "provider_failed"
    assert second.ok is True
    assert admission.in_flight("craft.routing.get@1") == 0


def test_cancelled_provider_is_measured_and_releases_lease():
    async def scenario():
        started = asyncio.Event()
        async def handler(*_args):
            started.set()
            await asyncio.Event().wait()
        gateway, envelope, admission, metrics = _gateway(
            handler, ExecutionBudget(max_parallel_per_consumer=1, max_parallel_per_tenant=1),
        )
        task = asyncio.create_task(gateway.invoke(envelope))
        await started.wait()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("cancelled invocation did not propagate cancellation")
        assert admission.in_flight("craft.routing.get@1") == 0
        assert metrics.recent()[-1].cancelled is True
        assert metrics.recent()[-1].error_code == "cancelled"

    asyncio.run(scenario())


def test_write_capacity_rejection_leaves_no_claim_and_exact_key_retries_once():
    from backend.tests.test_capability_gateway_pipeline import _descriptor,_gateway as write_gateway,_envelope
    from backend.capability_v2.contracts import SideEffectLevel
    from backend.capability_v2.outcomes import InMemoryOutcomeStore
    from backend.capability_v2.reliability import ReliabilityCoordinator,InMemoryRateLimiter,idempotency_scope
    async def scenario():
        entered=asyncio.Event();release=asyncio.Event();calls=[]
        async def handler(payload,context):
            calls.append(context.idempotency_key)
            if context.idempotency_key=='busy':
                entered.set();await release.wait()
            return {'routing_id':'r1'}
        descriptor=_descriptor().model_copy(update=dict(side_effect_level=SideEffectLevel.WRITE,
            idempotency_policy='required',consistency_policy='eventual',execution_budget=ExecutionBudget(max_parallel_per_consumer=1,max_parallel_per_tenant=1)))
        store=InMemoryOutcomeStore();reliability=ReliabilityCoordinator(store,InMemoryRateLimiter(limit=100))
        gateway,catalog=write_gateway(descriptor,handler,_Policy(),reliability)
        gateway._admission_timeout_seconds=0.01
        busy=_envelope(catalog).model_copy(update=dict(idempotency_key='busy'))
        retry=busy.model_copy(update=dict(idempotency_key='retry',request_id='request_retry'))
        task=asyncio.create_task(gateway.invoke(busy));await entered.wait()
        rejected=await gateway.invoke(retry)
        assert rejected.error.code=='capacity_unavailable' and rejected.error.retryable
        assert store.find_by_idempotency(idempotency_scope(retry)) is None
        assert calls==['busy']
        still_running=await gateway.invoke(busy)
        assert still_running.error.code=='idempotency_in_progress'
        release.set();assert (await task).ok
        assert (await gateway.invoke(retry)).ok
        # Completed replay bypasses busy capacity and never redispatches.
        held=await gateway._admission.acquire(capability_key='craft.routing.get@1',tenant_key=retry.identity.tenant.tenant_id,
            consumer_key=gateway._consumer_key(retry),budget=descriptor.execution_budget,timeout_seconds=0)
        try:assert (await gateway.invoke(retry)).ok
        finally:await held.release()
        assert calls==['busy','retry'] and gateway._admission.in_flight('craft.routing.get@1')==0
    asyncio.run(scenario())


def test_write_reliability_rejection_releases_preacquired_capacity():
    from backend.tests.test_capability_gateway_pipeline import _descriptor,_gateway as write_gateway,_envelope
    from backend.capability_v2.contracts import SideEffectLevel
    from backend.capability_v2.outcomes import InMemoryOutcomeStore
    from backend.capability_v2.reliability import ReliabilityCoordinator,InMemoryRateLimiter
    descriptor=_descriptor().model_copy(update=dict(side_effect_level=SideEffectLevel.WRITE,
        idempotency_policy='required',consistency_policy='eventual'))
    gateway,catalog=write_gateway(descriptor,lambda *_:{'routing_id':'r1'},_Policy(),
        ReliabilityCoordinator(InMemoryOutcomeStore(),InMemoryRateLimiter(limit=0)))
    result=asyncio.run(gateway.invoke(_envelope(catalog).model_copy(update=dict(idempotency_key='limited'))))
    assert result.error.code=='rate_limit_exceeded'
    assert gateway._admission.in_flight('craft.routing.get@1')==0
