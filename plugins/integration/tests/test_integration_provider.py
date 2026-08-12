import json
from pathlib import Path

import pytest

from plugins.integration.integration_backend.application.network_policy import NetworkPolicy
from plugins.integration.integration_backend.application.transform import RestrictedExpression
from plugins.integration.integration_backend.capabilities import register_capabilities
from plugins.integration.integration_backend.data.connection import _params


CAPABILITY_IDS = {
    "integration.connector.archive",
    "integration.connector.connection.test",
    "integration.connector.create",
    "integration.connector.schema.discover",
    "integration.connector.search",
    "integration.connector.update",
    "integration.mapping.archive",
    "integration.mapping.create",
    "integration.mapping.get",
    "integration.mapping.preview",
    "integration.mapping.search",
    "integration.mapping.update",
    "integration.sync.start",
}


def test_integration_is_an_official_independent_domain():
    root = Path(__file__).parents[3]
    document = json.loads((root / "backend/capability_v2/official_domains.json").read_text(encoding="utf-8"))
    integration = next(item for item in document["domains"] if item["domain_id"] == "integration")
    assert integration["artifact"]["module"] == "integration_backend.capabilities"
    assert integration["database"]["database_name"] == "ai00_integration"
    assert integration["database"]["migration_path"] == "backend/db/migrations/domains/integration"


def test_provider_publishes_thirteen_native_governed_capabilities():
    class Registry:
        def __init__(self):
            self.items = []

        def register(self, spec, handler, *, descriptor=None):
            self.items.append((spec, handler, descriptor))

    registry = Registry()
    register_capabilities(registry)
    registrations = {spec.id: (spec, handler, descriptor) for spec, handler, descriptor in registry.items}
    assert set(registrations) == CAPABILITY_IDS
    for capability_id, (_, _, descriptor) in registrations.items():
        assert descriptor.owner_domain == "integration", capability_id
        assert descriptor.lifecycle_status == "stable"
        assert descriptor.exposure.plugin and descriptor.exposure.agent and descriptor.exposure.mcp
        assert descriptor.input_schema["additionalProperties"] is False
        assert descriptor.output_schema["additionalProperties"] is False
        assert descriptor.domain_errors_complete is True


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "10.1.2.3", "169.254.169.254", "::1"])
def test_connection_policy_rejects_loopback_private_and_metadata_targets(host):
    with pytest.raises(ValueError, match="network policy"):
        NetworkPolicy().validate_host(host)


def test_integration_requires_independent_database_and_migration(monkeypatch):
    monkeypatch.delenv("AI00_INTEGRATION_DB_URL", raising=False)
    with pytest.raises(RuntimeError, match="AI00_INTEGRATION_DB_URL is required"):
        _params()
    root = Path(__file__).parents[3]
    sql = (root / "backend/db/migrations/domains/integration/0001_integration.sql").read_text(encoding="utf-8")
    assert "workmanship_int_ext_datasources" in sql
    assert "workmanship_know_" not in sql
    assert "workmanship_bop_" not in sql


def test_mapping_expression_allows_declared_field_transforms_only():
    expression = RestrictedExpression("upper(source.part_no)")
    assert expression.evaluate({"part_no": " ab-1 "}) == " AB-1 "


@pytest.mark.parametrize(
    "expression",
    ["__import__('os').system('whoami')", "source.__class__", "open('secret')", "source['x']"],
)
def test_mapping_expression_rejects_code_execution_and_dynamic_access(expression):
    with pytest.raises(ValueError, match="mapping expression"):
        RestrictedExpression(expression)
