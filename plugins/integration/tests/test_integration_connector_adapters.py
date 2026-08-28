import asyncio

import pytest

from backend.capability_v2.provider_contracts import CapabilityContext
from plugins.integration.integration_backend.application.service import IntegrationApplication
from plugins.integration.integration_backend.capabilities import register_capabilities
from plugins.integration.integration_backend.capabilities.wiring import IntegrationProviderAdapters
from plugins.integration.tests.test_integration_owner_services import Catalog, FixedIdentity, MemoryRepository, Runtime, Vault


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
