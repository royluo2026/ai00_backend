import asyncio
from datetime import UTC, datetime

from backend.capabilities.registry_next import CapabilityRegistry
from backend.capability_v2.authorization import AuthorizationDecision
from backend.capability_v2.catalog import CatalogResolver, build_release
from backend.capability_v2.catalog_store import InMemoryCatalogStore
from backend.capability_v2.contracts import (
    ActorIdentity, ConsumerDescriptor, ConsumerIdentity, ConsumerType, CorrelationRef,
    TenantIdentity,
)
from backend.capability_v2.domain_client import DomainCapabilityClient
from backend.capability_v2.gateway import CapabilityGatewayService
from backend.capability_v2.outcomes import InMemoryOutcomeStore
from backend.capability_v2.reliability import InMemoryRateLimiter, ReliabilityCoordinator
from plugins.integration.integration_backend.application.sync import SyncService, TargetAdapter
from plugins.integration.tests.test_integration_mapping_commands import (
    BoundCatalog, VALID_BINDING, bound_mapping_payload,
)
from plugins.integration.tests.test_integration_owner_services import (
    CONTEXT, MemoryRepository, _seed_connector_and_mapping, app,
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
    service = SyncService(DomainCapabilityClient(gateway), _identity())
    adapter = TargetAdapter(
        target_domain="knowledge", capability_id=persisted["capability_id"],
        major_version=persisted["major_version"],
        minimum_catalog_release=persisted["minimum_catalog_release"],
    )

    result = asyncio.run(service.apply_batch(
        adapter=adapter, payload=payload, idempotency_key="sync-1:batch-1",
        correlation=CorrelationRef(request_id="req-1", trace_id="trace-1"),
    ))

    assert result.ok is True
    assert knowledge_repository.published == [{
        "dataset_gid": "dataset-parts", "expected_version": 7,
        "schema": {"fields": [{"name": "code", "source_field": "part_no"}]},
        "rows": [{"key": "part-1", "values": [{"field": "code", "value": "P1"}]}],
        "actor_gid": "integration-sync", "tenant_gid": "team-1",
    }]
