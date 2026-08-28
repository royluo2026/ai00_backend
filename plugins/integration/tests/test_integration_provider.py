import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

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
    "integration.field_mapping.batch.update",
    "integration.field_mapping.search",
    "integration.mapping.archive",
    "integration.mapping.create",
    "integration.mapping.get",
    "integration.mapping.preview",
    "integration.mapping.search",
    "integration.mapping.source_columns.discover",
    "integration.mapping.import.start",
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


def test_provider_publishes_seventeen_native_governed_capabilities():
    class Registry:
        def __init__(self):
            self.items = []

        def register(self, spec, handler, *, descriptor=None):
            self.items.append((spec, handler, descriptor))

    registry = Registry()
    register_capabilities(registry)
    registrations = {spec.id: (spec, handler, descriptor) for spec, handler, descriptor in registry.items}
    assert set(registrations) == CAPABILITY_IDS
    for capability_id, (spec, _, descriptor) in registrations.items():
        assert descriptor.owner_domain == "integration", capability_id
        assert descriptor.lifecycle_status == "stable"
        assert descriptor.exposure.plugin and descriptor.exposure.agent and descriptor.exposure.mcp
        assert descriptor.input_schema["additionalProperties"] is False
        assert descriptor.output_schema["additionalProperties"] is False
        assert descriptor.domain_errors_complete is True
        assert spec.confirmation == ("none" if spec.risk.value == "read" else "user")


EXACT_TARGETS = {
    "integration.connector.search",
    "integration.connector.create",
    "integration.connector.update",
    "integration.connector.schema.discover",
    "integration.connector.connection.test",
    "integration.mapping.search",
    "integration.field_mapping.search",
    "integration.mapping.source_columns.discover",
    "integration.mapping.preview",
    "integration.mapping.create",
    "integration.field_mapping.batch.update",
    "integration.mapping.import.start",
}


def _assert_closed(schema):
    if schema.get("type") == "object":
        assert schema.get("additionalProperties") is False
        for child in schema.get("properties", {}).values():
            _assert_closed(child)
    if schema.get("type") == "array":
        _assert_closed(schema["items"])
    for branch in schema.get("oneOf", ()):
        _assert_closed(branch)


def _registrations():
    class Registry:
        def __init__(self):
            self.items = []

        def register(self, spec, handler, *, descriptor=None):
            self.items.append((spec, handler, descriptor))

    registry = Registry()
    register_capabilities(registry)
    return {spec.id: (spec, descriptor) for spec, _, descriptor in registry.items}


def test_twelve_exact_targets_have_recursively_closed_stable_v1_contracts():
    registrations = _registrations()
    assert EXACT_TARGETS <= registrations.keys()
    for capability_id in EXACT_TARGETS:
        spec, descriptor = registrations[capability_id]
        assert spec.version == 1 and descriptor.lifecycle_status == "stable"
        _assert_closed(spec.input_schema)
        _assert_closed(spec.output_schema)
        assert not ({"password", "credentials", "filter_sql", "config"} & set(spec.input_schema["properties"]))


def test_exact_limits_and_secret_or_unknown_input_rejection_are_schema_enforced():
    registrations = _registrations()
    create = registrations["integration.connector.create"][0].input_schema
    valid_connector = {
        "name": "ERP", "connector_type": "postgresql", "host": "db.example.com", "port": 5432,
        "database_name": "erp", "username": "reader", "credential_enrollment_handle": "once-1",
        "idempotency_key": "create-1",
    }
    Draft202012Validator(create).validate(valid_connector)
    for bad in (
        {**valid_connector, "password": "secret"},
        {**valid_connector, "credentials": {"password": "secret"}},
        {**valid_connector, "unknown": True},
        {**valid_connector, "credential_ref": "vault://ref"},
    ):
        with pytest.raises(ValidationError):
            Draft202012Validator(create).validate(bad)

    for capability_id in (
        "integration.connector.search", "integration.connector.schema.discover",
        "integration.mapping.search", "integration.field_mapping.search",
        "integration.mapping.source_columns.discover", "integration.mapping.preview",
    ):
        limit = registrations[capability_id][0].input_schema["properties"]["limit"]
        assert limit["minimum"] == 1 and limit["maximum"] == 200

    batch = registrations["integration.field_mapping.batch.update"][0].input_schema
    assert batch["properties"]["items"]["minItems"] == 1
    assert batch["properties"]["items"]["maxItems"] == 200
    field = batch["properties"]["items"]["items"]
    assert set(field["properties"]) == {"source_field", "target_field", "transform_expression"}


def test_mapping_writes_require_exact_target_version_release_and_idempotency():
    registrations = _registrations()
    create = registrations["integration.mapping.create"][0].input_schema
    assert {
        "target_capability_id", "target_major_version", "minimum_catalog_release", "idempotency_key"
    } <= set(create["required"])
    assert "filter_sql" not in create["properties"] and "config" not in create["properties"]
    assert {
        "mapping_gid", "expected_revision", "items", "idempotency_key"
    } <= set(registrations["integration.field_mapping.batch.update"][0].input_schema["required"])
    assert {
        "mapping_gid", "idempotency_key"
    } <= set(registrations["integration.mapping.import.start"][0].input_schema["required"])


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
