import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

import pytest
from jsonschema import Draft202012Validator, ValidationError

from plugins.integration.integration_backend.application.network_policy import NetworkPolicy
from plugins.integration.integration_backend.application.transform import RestrictedExpression
from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext
from plugins.integration.integration_backend.capabilities import register_capabilities
from plugins.integration.integration_backend.capabilities.wiring import IntegrationProviderAdapters
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
    "integration.mapping_target.search",
    "integration.mapping_target.upsert",
    "integration.mapping.import.start",
    "integration.mapping.update",
    "integration.sync.start",
}


class ProviderRepository:
    def __init__(self):
        self.connectors = {}
        self.mappings = {}
        self.operations = {}
        self.scopes = {}

    def create_connector(self, data):
        row = {**data, "gid": "connector-1", "revision": 1, "status": "untested"}
        self.connectors[row["gid"]] = row
        return dict(row)

    def get_connector(self, data):
        row = self.connectors.get(data["gid"])
        if row and row["owner_gid"] == data["owner_gid"] and row.get("team_gid") == data.get("team_gid"):
            return dict(row)
        return None

    def create_mapping(self, data):
        row = {**data, "revision": 1, "status": "active"}
        self.mappings[row["gid"]] = row
        return dict(row)

    def get_mapping(self, data):
        row = self.mappings.get(data["gid"])
        if row and row["owner_gid"] == data["owner_gid"] and row.get("team_gid") == data.get("team_gid"):
            return dict(row)
        return None

    def find_operation(self, owner_gid, capability_id, idempotency_key):
        return self.operations.get(self.scopes.get((owner_gid, capability_id, idempotency_key)))

    def execute_mapping_command(self, record, completed, command, data):
        existing = self.find_operation(record.owner_gid, record.capability_id, record.idempotency_key)
        if existing is not None:
            return existing, True
        assert command == "create"
        self.create_mapping(dict(data))
        self.operations[completed.operation_id] = completed
        self.scopes[(completed.owner_gid, completed.capability_id, completed.idempotency_key)] = completed.operation_id
        return completed, False

    def claim_operation(self, record):
        scope = (record.owner_gid, record.capability_id, record.idempotency_key)
        existing = self.operations.get(self.scopes.get(scope))
        if existing is not None:
            return existing, True
        self.operations[record.operation_id] = record
        self.scopes[scope] = record.operation_id
        return record, False

    def claim_import_operation(self, record, run):
        return self.claim_operation(record)

    def find_import_operation(self, owner_gid, capability_id, idempotency_key):
        return self.find_operation(owner_gid, capability_id, idempotency_key)

    def get_operation(self, operation_id, owner_gid, team_gid):
        record = self.operations.get(operation_id)
        return record if record and record.owner_gid == owner_gid and record.team_gid == team_gid else None

    def transition_operation(self, operation_id, expected_version, replacement, owner_gid, team_gid):
        current = self.get_operation(operation_id, owner_gid, team_gid)
        if current is None or current.version != expected_version:
            raise RuntimeError("unexpected transition")
        self.operations[operation_id] = replacement
        return replacement


class ProviderVault:
    def consume(self, handle, actor_gid, team_gid):
        assert (handle, actor_gid, team_gid) == ("once-1", "actor-1", "team-1")
        return "vault://integration/enrolled-1"


class ProviderCatalog:
    def __init__(self):
        self.calls = []

    def require_stable(self, capability_id, major_version, minimum_release):
        self.calls.append((capability_id, major_version, minimum_release))

    def resolve_mapping_target(self, binding_id, *, actor_gid, team_gid):
        if (actor_gid, team_gid) != ("actor-1", "team-1"):
            raise LookupError("target binding is outside principal scope")
        return {
            "binding_id": binding_id, "target_domain": "knowledge",
            "target_capability_id": "knowledge.reference_dataset.publish",
            "target_major_version": 1, "minimum_catalog_release": "rel_20260828",
            "input_contract": "knowledge.reference_dataset.publish.v1",
            "resource_gid": "dataset-parts", "expected_version": 7,
        }

    def project_mapping_targets_for_ontology_objects(
        self, ontology_object_gids, *, actor_gid, team_gid
    ):
        if (actor_gid, team_gid) != ("actor-1", "team-1"):
            return []
        if "concept-part" not in ontology_object_gids:
            return []
        return [{
            **self.resolve_mapping_target(
                "ontology:concept-part", actor_gid=actor_gid, team_gid=team_gid
            ),
            "ontology_object_gid": "concept-part",
        }]

    def upsert_mapping_target(self, **data):
        return {**data, "expected_version": data["target_expected_version"], "revision": 1}

    def validate_mapping_target(self, candidate):
        return dict(candidate)


class ProviderRuntime:
    async def test(self, connector, *, timeout_seconds, result_limit):
        assert connector["gid"] == "connector-1"
        assert (timeout_seconds, result_limit) == (15, 1)
        return {"reachable": True, "message": "configured runtime"}

    async def discover(self, connector, *, timeout_seconds, result_limit):
        return {"objects": []}

    async def source_columns(self, connector, mapping, *, timeout_seconds, result_limit):
        return {"columns": []}

    async def preview(self, connector, mapping, *, timeout_seconds, result_limit):
        return {"rows": [], "truncated": False}


class SyncProviderRuntime:
    def __init__(self):
        self.called = False

    def _result(self):
        self.called = True
        return {}

    def test(self, *_args, **_kwargs):
        return self._result()

    def discover(self, *_args, **_kwargs):
        return self._result()

    def source_columns(self, *_args, **_kwargs):
        return self._result()

    def preview(self, *_args, **_kwargs):
        return self._result()


class SlowProviderRuntime(ProviderRuntime):
    def __init__(self):
        self.arguments = None
        self.cancelled = False

    async def test(self, connector, *, timeout_seconds, result_limit):
        self.arguments = (connector["gid"], timeout_seconds, result_limit)
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise


class ProviderIdentity:
    def __init__(self):
        self.value = 0

    def new_id(self, kind):
        self.value += 1
        return f"{kind}-{self.value}"

    def now(self):
        return datetime(2026, 8, 28, tzinfo=UTC)


def provider_factory():
    catalog = ProviderCatalog()
    return IntegrationProviderAdapters(
        repository=ProviderRepository(),
        credential_enrollment=ProviderVault(),
        catalog=catalog,
        connector_runtime=ProviderRuntime(),
        operation_identity=ProviderIdentity(),
    )


def test_integration_is_an_official_independent_domain():
    root = Path(__file__).parents[3]
    document = json.loads((root / "backend/capability_v2/official_domains.json").read_text(encoding="utf-8"))
    integration = next(item for item in document["domains"] if item["domain_id"] == "integration")
    assert integration["artifact"]["module"] == "integration_backend.capabilities"
    assert integration["database"]["database_name"] == "ai00_integration"
    assert integration["database"]["migration_path"] == "backend/db/migrations/domains/integration"


def test_provider_publishes_eighteen_native_governed_capabilities():
    class Registry:
        def __init__(self):
            self.items = []

        def register(self, spec, handler, *, descriptor=None):
            self.items.append((spec, handler, descriptor))

    registry = Registry()
    register_capabilities(registry, adapter_factory=provider_factory)
    registrations = {spec.id: (spec, handler, descriptor) for spec, handler, descriptor in registry.items}
    assert set(registrations) == CAPABILITY_IDS
    for capability_id, (spec, _, descriptor) in registrations.items():
        assert descriptor.owner_domain == "integration", capability_id
        assert descriptor.lifecycle_status == "stable"
        assert descriptor.exposure.plugin and descriptor.exposure.agent and descriptor.exposure.mcp
        assert descriptor.input_schema["additionalProperties"] is False
        assert descriptor.output_schema["additionalProperties"] is False
        assert descriptor.domain_errors_complete is True
        expected_confirmation = "none" if spec.risk.value == "read" else (
            "admin" if capability_id == "integration.mapping_target.upsert" else "user"
        )
        assert spec.confirmation == expected_confirmation


EXACT_TARGETS = {
    "integration.connector.search",
    "integration.connector.create",
    "integration.connector.update",
    "integration.connector.schema.discover",
    "integration.connector.connection.test",
    "integration.mapping.search",
    "integration.mapping_target.search",
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
    register_capabilities(registry, adapter_factory=provider_factory)
    return {spec.id: (spec, descriptor) for spec, _, descriptor in registry.items}


def test_provider_fails_startup_when_required_adapter_factory_is_unavailable(monkeypatch):
    class Registry:
        def register(self, *_args, **_kwargs):
            pytest.fail("unconfigured provider must fail before registering handlers")

    monkeypatch.delenv("AI00_INTEGRATION_ADAPTER_FACTORY", raising=False)
    with pytest.raises(RuntimeError, match="AI00_INTEGRATION_ADAPTER_FACTORY"):
        register_capabilities(Registry())


def test_provider_rejects_synchronous_runtime_before_handler_publication():
    class Registry:
        def __init__(self):
            self.registered = 0

        def register(self, *_args, **_kwargs):
            self.registered += 1

    runtime = SyncProviderRuntime()
    adapters = IntegrationProviderAdapters(
        repository=ProviderRepository(), credential_enrollment=ProviderVault(),
        catalog=ProviderCatalog(), connector_runtime=runtime, operation_identity=ProviderIdentity(),
    )
    registry = Registry()

    with pytest.raises(RuntimeError, match="connector_runtime"):
        register_capabilities(registry, adapter_factory=lambda: adapters)

    assert registry.registered == 0
    assert runtime.called is False


def test_provider_rejects_catalog_binding_methods_with_optional_principal_scope():
    class UnscopedCatalog(ProviderCatalog):
        def resolve_mapping_target(self, binding_id, *, actor_gid=None, team_gid=None):
            return super().resolve_mapping_target(
                binding_id, actor_gid=actor_gid, team_gid=team_gid
            )

        def project_mapping_targets_for_ontology_objects(
            self, ontology_object_gids, *, actor_gid=None, team_gid=None
        ):
            return super().project_mapping_targets_for_ontology_objects(
                ontology_object_gids, actor_gid=actor_gid, team_gid=team_gid
            )

    adapters = IntegrationProviderAdapters(
        repository=ProviderRepository(), credential_enrollment=ProviderVault(),
        catalog=UnscopedCatalog(), connector_runtime=ProviderRuntime(),
        operation_identity=ProviderIdentity(),
    )

    with pytest.raises(RuntimeError, match="catalog"):
        register_capabilities(
            type("Registry", (), {"register": lambda *_args, **_kwargs: None})(),
            adapter_factory=lambda: adapters,
        )


def test_provider_accepts_async_runtime_and_bounds_registered_execution(monkeypatch):
    class Registry:
        def __init__(self):
            self.handlers = {}

        def register(self, spec, handler, *, descriptor=None):
            self.handlers[spec.id] = handler

    repository = ProviderRepository()
    repository.connectors["connector-1"] = {
        "gid": "connector-1", "revision": 1, "name": "ERP", "connector_type": "postgresql",
        "host": "8.8.8.8", "port": 5432, "database_name": "erp", "username": "reader",
        "credential_ref": "vault://integration/enrolled-1", "status": "untested",
        "owner_gid": "actor-1", "team_gid": "team-1",
    }
    runtime = SlowProviderRuntime()
    adapters = IntegrationProviderAdapters(
        repository=repository, credential_enrollment=ProviderVault(), catalog=ProviderCatalog(),
        connector_runtime=runtime, operation_identity=ProviderIdentity(),
    )
    monkeypatch.setattr(
        "plugins.integration.integration_backend.application.service.RUNTIME_TIMEOUT_SECONDS", 0.01
    )
    registry = Registry()
    register_capabilities(registry, adapter_factory=lambda: adapters)

    result = asyncio.run(registry.handlers["integration.connector.connection.test"](
        {"gid": "connector-1", "idempotency_key": "connection-test-timeout"},
        CapabilityContext(user_gid="actor-1", team_gid="team-1", request_id="bounded-runtime"),
    ))

    assert result["operation_ref"]["status"] == "outcome_unknown"
    assert runtime.arguments == ("connector-1", 0.01, 1)
    assert runtime.cancelled is True


def test_registered_handlers_use_configured_vault_catalog_and_bounded_runtime(monkeypatch):
    class Registry:
        def __init__(self):
            self.handlers = {}

        def register(self, spec, handler, *, descriptor=None):
            self.handlers[spec.id] = handler

    adapters = provider_factory()
    factory_module = ModuleType("integration_test_adapter_factory")
    factory_module.build = lambda: adapters
    monkeypatch.setitem(sys.modules, factory_module.__name__, factory_module)
    monkeypatch.setenv(
        "AI00_INTEGRATION_ADAPTER_FACTORY", "integration_test_adapter_factory:build"
    )
    registry = Registry()
    register_capabilities(registry)
    context = CapabilityContext(user_gid="actor-1", team_gid="team-1", request_id="provider-e2e")

    projection = asyncio.run(registry.handlers["integration.mapping_target.search"]({
        "ontology_object_gids": ["concept-part"],
    }, context))

    connector = asyncio.run(registry.handlers["integration.connector.create"]({
        "name": "ERP", "connector_type": "postgresql", "host": "8.8.8.8", "port": 5432,
        "database_name": "erp", "username": "reader", "credential_enrollment_handle": "once-1",
        "idempotency_key": "connector-create-1",
    }, context))
    mapping = asyncio.run(registry.handlers["integration.mapping.create"]({
        "datasource_gid": connector["gid"], "name": "Parts", "source_object": "parts",
        "target_binding_id": "ontology:concept-part",
        "field_mappings": [{"source_field": "part_no", "target_field": "code"}],
        "idempotency_key": "mapping-create-1",
    }, context))
    tested = asyncio.run(registry.handlers["integration.connector.connection.test"](
        {"gid": connector["gid"], "idempotency_key": "connection-test-provider"}, context
    ))
    imported = asyncio.run(registry.handlers["integration.mapping.import.start"]({
        "mapping_gid": mapping["gid"], "idempotency_key": "mapping-import-1",
    }, context))

    assert connector["gid"] == "connector-1"
    assert mapping["datasource_gid"] == "connector-1"
    assert projection["items"][0]["binding_id"] == "ontology:concept-part"
    assert adapters.catalog.calls == [
        ("knowledge.reference_dataset.publish", 1, "rel_20260828"),
        ("knowledge.reference_dataset.publish", 1, "rel_20260828"),
        ("knowledge.reference_dataset.publish", 1, "rel_20260828"),
    ]
    assert tested["reachable"] is True
    assert tested["operation_ref"]["status"] == "succeeded"
    assert imported["operation_ref"]["status"] == "accepted"


def test_registered_gateway_handlers_hide_and_reject_cross_team_bindings():
    class Registry:
        def __init__(self):
            self.handlers = {}

        def register(self, spec, handler, *, descriptor=None):
            self.handlers[spec.id] = handler

    adapters = provider_factory()
    adapters.repository.connectors["connector-1"] = {
        "gid": "connector-1", "revision": 1, "name": "ERP", "connector_type": "postgresql",
        "host": "8.8.8.8", "port": 5432, "database_name": "erp", "username": "reader",
        "status": "untested", "owner_gid": "actor-1", "team_gid": "team-2",
    }
    adapters.repository.mappings["mapping-foreign-binding"] = {
        "gid": "mapping-foreign-binding", "revision": 1, "datasource_gid": "connector-1",
        "name": "Parts", "source_object": "parts", "status": "active",
        "owner_gid": "actor-1", "team_gid": "team-2", "field_mappings": [],
        "target_binding_id": "ontology:concept-part", "target_domain": "knowledge",
        "target_capability_id": "knowledge.reference_dataset.publish", "target_major_version": 1,
        "minimum_catalog_release": "rel_20260828",
        "target_input_contract": "knowledge.reference_dataset.publish.v1",
        "target_resource_gid": "dataset-parts", "target_expected_version": 7,
    }
    registry = Registry()
    register_capabilities(registry, adapter_factory=lambda: adapters)
    context = CapabilityContext(user_gid="actor-1", team_gid="team-2", request_id="cross-team")

    projected = asyncio.run(registry.handlers["integration.mapping_target.search"]({
        "ontology_object_gids": ["concept-part"],
    }, context))
    with pytest.raises(CapabilityBusinessError) as create_rejected:
        asyncio.run(registry.handlers["integration.mapping.create"]({
            "datasource_gid": "connector-1", "name": "Parts", "source_object": "parts",
            "target_binding_id": "ontology:concept-part", "field_mappings": [],
            "idempotency_key": "cross-team-create",
        }, context))
    with pytest.raises(CapabilityBusinessError) as import_rejected:
        asyncio.run(registry.handlers["integration.mapping.import.start"]({
            "mapping_gid": "mapping-foreign-binding", "idempotency_key": "cross-team-import",
        }, context))

    assert projected == {"items": []}
    assert create_rejected.value.code == "target_binding_unavailable"
    assert import_rejected.value.code == "target_binding_unavailable"
    assert adapters.repository.operations == {}
    assert set(adapters.repository.mappings) == {"mapping-foreign-binding"}


@pytest.mark.parametrize("context", [
    CapabilityContext(user_gid="", team_gid="team-1", request_id="missing-actor"),
    CapabilityContext(user_gid="actor-1", team_gid=None, request_id="missing-team"),
])
def test_registered_gateway_binding_lookup_requires_complete_authenticated_scope(context):
    class Registry:
        def __init__(self):
            self.handlers = {}

        def register(self, spec, handler, *, descriptor=None):
            self.handlers[spec.id] = handler

    registry = Registry()
    register_capabilities(registry, adapter_factory=provider_factory)

    with pytest.raises(CapabilityBusinessError) as rejected:
        asyncio.run(registry.handlers["integration.mapping_target.search"]({
            "ontology_object_gids": ["concept-part"],
        }, context))

    assert rejected.value.code == "permission_denied"


def test_browser_targets_have_recursively_closed_stable_v1_contracts():
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
    targets = registrations["integration.mapping_target.search"][0].input_schema[
        "properties"
    ]["ontology_object_gids"]
    assert (targets["minItems"], targets["maxItems"], targets["uniqueItems"]) == (1, 200, True)


def test_mapping_writes_require_exact_target_version_release_and_idempotency():
    registrations = _registrations()
    create = registrations["integration.mapping.create"][0].input_schema
    assert {"target_binding_id", "idempotency_key"} <= set(create["required"])
    assert not ({"target_capability_id", "target_major_version", "minimum_catalog_release"} & set(create["properties"]))
    assert "filter_sql" not in create["properties"] and "config" not in create["properties"]
    assert {
        "mapping_gid", "expected_revision", "items", "idempotency_key"
    } <= set(registrations["integration.field_mapping.batch.update"][0].input_schema["required"])
    assert {
        "mapping_gid", "idempotency_key"
    } <= set(registrations["integration.mapping.import.start"][0].input_schema["required"])


def test_synchronous_mutations_require_gateway_idempotency_without_async_operation():
    registrations = _registrations()
    for capability_id in (
        "integration.connector.archive", "integration.mapping.update", "integration.mapping.archive",
    ):
        descriptor = registrations[capability_id][1]
        assert descriptor.idempotency_policy == "required", capability_id
        assert descriptor.operation_policy == "none", capability_id


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
