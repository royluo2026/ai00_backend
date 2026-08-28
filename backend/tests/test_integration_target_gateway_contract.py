import asyncio
from datetime import UTC, datetime

import pytest

from backend.capabilities.registry_next import CapabilityRegistry
from backend.capability_v2.authorization import AuthorizationDecision
from backend.capability_v2.catalog import CatalogResolver, build_release
from backend.capability_v2.catalog_store import InMemoryCatalogStore
from backend.capability_v2.contracts import (
    ActorIdentity, ConsumerDescriptor, ConsumerIdentity, ConsumerType, CorrelationRef,
    InvocationEnvelope, TenantIdentity,
)
from backend.capability_v2.domain_client import DomainCapabilityClient
from backend.capability_v2.gateway import CapabilityGatewayService
from backend.capability_v2.policies import GatewayPolicyError
from backend.capability_v2.outcomes import InMemoryOutcomeStore
from backend.capability_v2.operations import InMemoryOperationStore, OperationService
from backend.capability_v2.reliability import InMemoryRateLimiter, ReliabilityCoordinator
from plugins.integration.integration_backend.application.sync import SyncService, TargetAdapter
from plugins.integration.integration_backend.capabilities.descriptors import specs as integration_specs
from plugins.integration.integration_backend.capabilities.provider import descriptor_for
from plugins.integration.integration_backend.capabilities import register_capabilities
from plugins.integration.integration_backend.capabilities.wiring import IntegrationProviderAdapters
from plugins.integration.tests.test_integration_mapping_commands import (
    BoundCatalog, VALID_BINDING, bound_mapping_payload,
)
from plugins.integration.tests.test_integration_owner_services import (
    CONTEXT, MemoryRepository, _seed_connector_and_mapping, app,
)
from plugins.integration.tests.test_integration_provider import (
    ProviderCatalog, ProviderRepository, ProviderRuntime, ProviderVault,
)
from plugins.knowledge.knowledge_backend.application.reference_data import ReferenceDataService
from plugins.knowledge.knowledge_backend.capabilities import reference_data
from plugins.knowledge.knowledge_backend.capabilities.reference_data import (
    register_reference_data_capabilities,
)


class _Policy:
    def authorize(self, *_args):
        return AuthorizationDecision(allowed=True, code="allowed", policy_version="test")

    def approve(self, *_args):
        return None

    def project(self, _descriptor, _identity, data):
        return data


class _ReferenceRepository:
    def __init__(self):
        self.published = []

    def publish(self, dataset_gid, expected_version, schema, rows, actor_gid, tenant_gid):
        self.published.append({
            "dataset_gid": dataset_gid, "expected_version": expected_version,
            "schema": schema, "rows": rows, "actor_gid": actor_gid,
            "tenant_gid": tenant_gid,
        })
        return {
            "dataset_gid": dataset_gid, "version_gid": "version-8",
            "version_no": expected_version + 1, "immutable": True,
        }


def _identity():
    return ConsumerIdentity(
        actor=ActorIdentity(
            service_id="integration-sync", authentication_method="service-token",
            authenticated_at=datetime.now(UTC),
        ),
        tenant=TenantIdentity(tenant_id="team-1", membership="service"),
        consumer=ConsumerDescriptor(
            type=ConsumerType.WORKER, consumer_id="domain.integration",
        ),
    )


def test_production_registry_registration_installs_startable_and_safely_stoppable_import_worker():
    repository = ProviderRepository()
    repository.claim_next_import_run = lambda _worker: None
    registry = CapabilityRegistry()
    register_capabilities(registry, adapter_factory=lambda: IntegrationProviderAdapters(
        repository=repository, credential_enrollment=ProviderVault(), catalog=ProviderCatalog(),
        connector_runtime=ProviderRuntime(), target_client=DomainCapabilityClient(object()),
        worker_identity_factory=lambda run: ConsumerIdentity(
            actor=ActorIdentity(
                user_id=run["owner_gid"], authentication_method="persisted-integration-operation",
                authenticated_at=datetime.now(UTC),
            ),
            tenant=TenantIdentity(
                tenant_id=run.get("team_gid") or f"user:{run['owner_gid']}",
                membership="persisted-operation",
            ),
            consumer=ConsumerDescriptor(
                type=ConsumerType.WORKER, consumer_id="domain.integration.import-worker",
            ),
        ),
    ))

    assert registry.lifecycle_names() == ("integration.import-worker",)

    async def exercise():
        await registry.start_lifecycles()
        await asyncio.sleep(0)
        await registry.stop_lifecycles()

    asyncio.run(exercise())


def test_production_registry_exposes_fatal_import_worker_health_and_supervision_signal_before_shutdown(caplog):
    repository = ProviderRepository()

    def fail_claim(_worker):
        raise ValueError("secret tenant-7 configuration")

    repository.claim_next_import_run = fail_claim
    registry = CapabilityRegistry()
    register_capabilities(registry, adapter_factory=lambda: IntegrationProviderAdapters(
        repository=repository, credential_enrollment=ProviderVault(), catalog=ProviderCatalog(),
        connector_runtime=ProviderRuntime(), target_client=DomainCapabilityClient(object()),
        worker_identity_factory=lambda run: _identity(),
    ))

    async def exercise():
        await registry.start_lifecycles()
        for _ in range(20):
            if registry.lifecycle_health("integration.import-worker")["status"] == "fatal":
                break
            await asyncio.sleep(0.005)
        health = registry.lifecycle_health("integration.import-worker")
        signals = registry.lifecycle_signals("integration.import-worker")
        assert health["status"] == "fatal"
        assert health["consecutive_errors"] == 0
        assert health["last_error_code"] == "ValueError"
        assert health["last_poll_at"] is not None
        assert health["last_success_at"] is None
        assert health["next_retry_at"] is None
        assert signals[-1]["event"] == "lifecycle_worker_failed"
        assert signals[-1]["error_code"] == "ValueError"
        assert "secret" not in repr((health, signals))
        with pytest.raises(TypeError):
            health["status"] = "healthy"
        records = [record for record in caplog.records if record.getMessage() == "integration_import_worker_fatal"]
        assert records[-1].event_type == "lifecycle_worker_failed"
        assert records[-1].error_code == "ValueError"
        assert "secret" not in records[-1].getMessage()
        await registry.stop_lifecycles()

    asyncio.run(exercise())


def test_production_registry_keeps_transient_health_visible_then_clears_it_after_recovery():
    repository = ProviderRepository()
    calls = 0

    def transient_then_idle(_worker):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ConnectionError("password=not-public")
        return None

    repository.claim_next_import_run = transient_then_idle
    registry = CapabilityRegistry()
    register_capabilities(registry, adapter_factory=lambda: IntegrationProviderAdapters(
        repository=repository, credential_enrollment=ProviderVault(), catalog=ProviderCatalog(),
        connector_runtime=ProviderRuntime(), target_client=DomainCapabilityClient(object()),
        worker_identity_factory=lambda run: _identity(),
    ))

    async def exercise():
        await registry.start_lifecycles()
        for _ in range(20):
            degraded = registry.lifecycle_health("integration.import-worker")
            if degraded["status"] == "degraded":
                break
            await asyncio.sleep(0.005)
        assert degraded["consecutive_errors"] == 1
        assert degraded["last_error_code"] == "ConnectionError"
        assert degraded["last_poll_at"] is not None
        assert degraded["next_retry_at"] is not None
        assert "password" not in repr(degraded)
        for _ in range(80):
            recovered = registry.lifecycle_health("integration.import-worker")
            if recovered["status"] == "healthy":
                break
            await asyncio.sleep(0.005)
        assert recovered["consecutive_errors"] == 0
        assert recovered["last_error_code"] is None
        assert recovered["last_success_at"] is not None
        assert recovered["next_retry_at"] is None
        await registry.stop_lifecycles()

    asyncio.run(exercise())


def test_persisted_import_invocation_passes_real_gateway_contract_and_provider(monkeypatch):
    integration_repository = MemoryRepository()
    _seed_connector_and_mapping(integration_repository)
    integration_repository.mappings.clear()
    integration_repository.field_mappings.clear()
    application = app(integration_repository, catalog=BoundCatalog(VALID_BINDING))
    mapping = asyncio.run(application.invoke(
        "integration.mapping.create", bound_mapping_payload(), CONTEXT,
    ))
    asyncio.run(application.invoke(
        "integration.mapping.import.start",
        {"mapping_gid": mapping["gid"], "idempotency_key": "import-real-gateway"},
        CONTEXT,
    ))
    persisted = integration_repository.imports[0]["target_invocation"]
    payload = {
        **persisted["payload"],
        "rows": [{"key": "part-1", "values": [{"field": "code", "value": "P1"}]}],
    }

    knowledge_repository = _ReferenceRepository()
    monkeypatch.setattr(reference_data, "service", ReferenceDataService(knowledge_repository))
    registry = CapabilityRegistry()
    register_reference_data_capabilities(registry)
    provider = registry.get(persisted["capability_id"], persisted["major_version"])
    release = build_release([provider.descriptor])
    store = InMemoryCatalogStore()
    store.publish(release)
    gateway = CapabilityGatewayService(
        CatalogResolver(store, registry), _Policy(),
        reliability=ReliabilityCoordinator(
            InMemoryOutcomeStore(), InMemoryRateLimiter(limit=100),
        ),
    ).bind_release(release.release_id)
    class Catalog:
        def require_stable(self, capability_id, major_version, minimum_release):
            assert capability_id == persisted["capability_id"]
            assert major_version == persisted["major_version"]
            assert minimum_release == persisted["minimum_catalog_release"]

    service = SyncService(DomainCapabilityClient(gateway), Catalog())
    adapter = TargetAdapter(
        target_domain="knowledge", capability_id=persisted["capability_id"],
        major_version=persisted["major_version"],
        minimum_catalog_release=persisted["minimum_catalog_release"],
    )

    result = asyncio.run(service.apply_batch(
        adapter=adapter, payload=payload, idempotency_key="sync-1:batch-1",
        correlation=CorrelationRef(request_id="req-1", trace_id="trace-1"), identity=_identity(),
    ))

    assert result.ok is True
    assert knowledge_repository.published == [{
        "dataset_gid": "dataset-parts", "expected_version": 7,
        "schema": {"fields": [{"name": "code", "source_field": "part_no"}]},
        "rows": [{"key": "part-1", "values": [{"field": "code", "value": "P1"}]}],
        "actor_gid": "integration-sync", "tenant_gid": "team-1",
    }]


def test_real_connection_test_descriptor_gateway_rejects_missing_confirmation_and_mismatched_idempotency():
    spec = next(item for item in integration_specs() if item.id == "integration.connector.connection.test")
    descriptor = descriptor_for(spec)
    registry = CapabilityRegistry()
    registry.register(spec, lambda *_args: {
        "operation_ref": {"operation_id": "operation-1", "status": "succeeded", "version": 2}
    }, descriptor=descriptor)
    release = build_release([descriptor])
    store = InMemoryCatalogStore(); store.publish(release)

    class Policy(_Policy):
        def approve(self, _descriptor, envelope, *_args):
            if envelope.approval_reference != "confirm-1":
                raise GatewayPolicyError("confirmation_required", "Confirmation is required.")

    gateway = CapabilityGatewayService(
        CatalogResolver(store, registry), Policy(),
        reliability=ReliabilityCoordinator(InMemoryOutcomeStore(), InMemoryRateLimiter(limit=100)),
        operations=OperationService(InMemoryOperationStore()),
    ).bind_release(release.release_id)
    principal = ConsumerIdentity(
        actor=ActorIdentity(user_id="actor-1", authentication_method="session", authenticated_at=datetime.now(UTC)),
        tenant=TenantIdentity(tenant_id="team-1", membership="member"),
        consumer=ConsumerDescriptor(type=ConsumerType.WEB, consumer_id="web.integration"),
    )

    def envelope(payload, key=None, approval=None):
        return InvocationEnvelope(
            capability_id=spec.id, major_version=1, catalog_release=release.release_id,
            payload=payload, identity=principal, idempotency_key=key, approval_reference=approval,
            request_id=f"request-{key or 'missing'}", trace_id="trace-connection",
        )

    missing = asyncio.run(gateway.invoke(envelope({"gid": "connector-1", "idempotency_key": "idem-1"})))
    mismatch = asyncio.run(gateway.invoke(envelope(
        {"gid": "connector-1", "idempotency_key": "idem-payload"}, "idem-envelope", "confirm-1"
    )))
    unconfirmed = asyncio.run(gateway.invoke(envelope(
        {"gid": "connector-1", "idempotency_key": "idem-2"}, "idem-2"
    )))
    confirmed = asyncio.run(gateway.invoke(envelope(
        {"gid": "connector-1", "idempotency_key": "idem-3"}, "idem-3", "confirm-1"
    )))

    assert missing.error.code == "idempotency_key_mismatch"
    assert mismatch.error.code == "idempotency_key_mismatch"
    assert unconfirmed.error.code == "confirmation_required"
    assert confirmed.ok is True
