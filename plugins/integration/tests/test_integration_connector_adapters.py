import asyncio

import pytest

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext
from plugins.integration.integration_backend.application.service import IntegrationApplication
from plugins.integration.integration_backend.capabilities import register_capabilities
from plugins.integration.integration_backend.capabilities.wiring import IntegrationProviderAdapters
from plugins.integration.tests.test_integration_owner_services import (
    Catalog, FixedIdentity, MemoryRepository, Runtime, Vault, _seed_connector_and_mapping,
)


CONTEXT = CapabilityContext(user_gid="actor-1", team_gid="team-1", request_id="adapter-equivalence")
CONNECTOR = {
    "gid": "connector-1",
    "revision": 1,
    "name": "ERP",
    "connector_type": "postgresql",
    "host": "8.8.8.8",
    "port": 5432,
    "database_name": "erp",
    "username": "reader",
    "status": "untested",
    "owner_gid": "actor-1",
    "team_gid": "team-1",
    "credential_ref": "vault://integration/existing",
}


class Registry:
    def __init__(self):
        self.handlers = {}

    def register(self, spec, handler, *, descriptor=None):
        self.handlers[spec.id] = handler


def adapters(seed=False):
    repository = MemoryRepository()
    if seed:
        repository.connectors[CONNECTOR["gid"]] = dict(CONNECTOR)
    return IntegrationProviderAdapters(
        repository=repository,
        credential_enrollment=Vault(),
        catalog=Catalog(),
        connector_runtime=Runtime(),
        operation_identity=FixedIdentity(),
    )


def application(value):
    return IntegrationApplication(
        value.repository,
        credential_enrollment=value.credential_enrollment,
        catalog=value.catalog,
        connector_runtime=value.connector_runtime,
        operation_identity=value.operation_identity,
    )


def test_provider_adapter_matches_owner_service_cross_team_binding_denials():
    direct_adapters = adapters()
    provider_adapters = adapters()
    for value in (direct_adapters, provider_adapters):
        _seed_connector_and_mapping(value.repository)
        value.repository.connectors["connector-1"]["team_gid"] = "team-2"
        value.repository.mappings["mapping-1"]["team_gid"] = "team-2"
    registry = Registry()
    register_capabilities(registry, adapter_factory=lambda: provider_adapters)
    context = CapabilityContext(
        user_gid="actor-1", team_gid="team-2", request_id="adapter-cross-team"
    )
    direct = application(direct_adapters)

    direct_projection = asyncio.run(direct.invoke(
        "integration.mapping_target.search", {"ontology_object_gids": ["concept-part"]}, context
    ))
    provider_projection = asyncio.run(registry.handlers["integration.mapping_target.search"](
        {"ontology_object_gids": ["concept-part"]}, context
    ))
    create_payload = {
        "datasource_gid": "connector-1", "name": "Parts", "source_object": "parts",
        "target_binding_id": "ontology:concept-part", "field_mappings": [],
        "idempotency_key": "adapter-cross-team-create",
    }
    import_payload = {
        "mapping_gid": "mapping-1", "idempotency_key": "adapter-cross-team-import",
    }

    assert direct_projection == provider_projection == {"items": []}
    invokers = (
        lambda capability_id, payload: direct.invoke(capability_id, payload, context),
        lambda capability_id, payload: registry.handlers[capability_id](payload, context),
    )
    for invoke in invokers:
        with pytest.raises(CapabilityBusinessError) as create_rejected:
            asyncio.run(invoke("integration.mapping.create", create_payload))
        with pytest.raises(CapabilityBusinessError) as import_rejected:
            asyncio.run(invoke("integration.mapping.import.start", import_payload))
        assert create_rejected.value.code == "target_binding_unavailable"
        assert import_rejected.value.code == "target_binding_unavailable"


@pytest.mark.parametrize(
    ("capability_id", "payload", "seed"),
    (
        ("integration.connector.search", {"query": "ERP", "limit": 200}, True),
        (
            "integration.connector.create",
            {
                "name": "MES",
                "connector_type": "mysql",
                "host": "9.9.9.9",
                "port": 3306,
                "database_name": "mes",
                "username": "integration_reader",
                "credential_enrollment_handle": "enroll-once-1",
                "idempotency_key": "connector-create-1",
            },
            False,
        ),
        (
            "integration.connector.update",
            {"gid": "connector-1", "expected_revision": 1, "name": "ERP revised", "idempotency_key": "connector-update-1"},
            True,
        ),
        ("integration.connector.schema.discover", {"gid": "connector-1", "limit": 200}, True),
        ("integration.connector.connection.test", {"gid": "connector-1"}, True),
        ("integration.mapping_target.search", {"ontology_object_gids": ["concept-part"]}, False),
    ),
)
def test_provider_adapter_matches_owner_service_projection(capability_id, payload, seed):
    direct_adapters = adapters(seed)
    provider_adapters = adapters(seed)
    registry = Registry()
    register_capabilities(registry, adapter_factory=lambda: provider_adapters)

    direct = asyncio.run(application(direct_adapters).invoke(capability_id, payload, CONTEXT))
    through_provider = asyncio.run(registry.handlers[capability_id](payload, CONTEXT))

    assert through_provider == direct
