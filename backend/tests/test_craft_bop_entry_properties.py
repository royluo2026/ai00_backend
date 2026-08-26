import asyncio
from datetime import UTC, datetime

import pytest

from backend.capabilities.registry_next import CapabilityRegistry
from backend.capabilities.validation_next import validate_payload
from backend.capability_v2.authorization import AuthorizationDecision
from backend.capability_v2.catalog import CatalogResolver, build_release
from backend.capability_v2.catalog_store import InMemoryCatalogStore
from backend.capability_v2.contracts import (
    ActorIdentity, ConsumerDescriptor, ConsumerIdentity, ConsumerType,
    InvocationEnvelope, TenantIdentity,
)
from backend.capability_v2.gateway import CapabilityGatewayService
from backend.capability_v2.outcomes import InMemoryOutcomeStore
from backend.capability_v2.provider_contracts import CapabilityBusinessError
from backend.capability_v2.reliability import InMemoryRateLimiter, ReliabilityCoordinator
from plugins.craft.craft_backend.capabilities import register_capabilities
from plugins.craft.craft_backend.capabilities import bop_entry_change


def test_json_object_base_normalizes_sql_and_json_null() -> None:
    assert bop_entry_change._json_object_base_expr("ext") == (
        "CASE WHEN ext IS NULL OR JSON_TYPE(ext)='NULL' "
        "THEN JSON_OBJECT() ELSE ext END"
    )


def test_property_projection_is_scoped_to_the_entry_node_type(monkeypatch) -> None:
    monkeypatch.setattr(
        bop_entry_change,
        "active_projection",
        lambda: {
            "concept": [
                {"kind": "concept", "stable_gid": "concept.process", "node_type_binding": "process"},
                {"kind": "concept", "stable_gid": "concept.operation", "node_type_binding": "operation"},
            ],
            "property": [
                {"kind": "property", "stable_gid": "prop.sequence", "class_stable_gid": "concept.process", "name": "sequence_color", "mapped_column": "sequence_color", "storage_hint": "entity_table"},
                {"kind": "property", "stable_gid": "prop.secret", "class_stable_gid": "concept.operation", "name": "operation_secret", "storage_hint": "meta"},
                {"kind": "property", "stable_gid": "prop.derived", "class_stable_gid": "concept.process", "name": "computed", "storage_hint": "derived"},
            ],
            "relation": [],
            "constraint": [],
        },
    )

    mapped = bop_entry_change._property_contracts("process")

    assert set(mapped) == {"sequence_color", "computed"}
    assert mapped["sequence_color"]["db_key"] == "sequence_color"
    assert mapped["computed"]["storage_hint"] == "derived"


def test_property_projection_without_storage_hint_uses_automatic_routing(monkeypatch) -> None:
    monkeypatch.setattr(
        bop_entry_change,
        "active_projection",
        lambda: {
            "concept": [{"stable_gid": "concept.process", "node_type_binding": "process"}],
            "property": [{"stable_gid": "prop.sequence", "class_stable_gid": "concept.process", "name": "sequence_color"}],
        },
    )

    assert bop_entry_change._property_contracts("process")["sequence_color"]["storage_hint"] == "auto"


def test_gateway_contract_accepts_named_dynamic_property_updates() -> None:
    registry = CapabilityRegistry()
    register_capabilities(registry)
    registration = next(
        item for item in registry.snapshot()
        if item.spec.id == "craft.bop.entry.change.apply"
    )

    validate_payload(registration.descriptor.input_schema, {
        "operation": "update",
        "entry_gid": "entry-1",
        "properties": [{"name": "sequence_color", "value": "red"}],
    })


def test_gateway_invokes_named_dynamic_property_update() -> None:
    source_registry = CapabilityRegistry()
    register_capabilities(source_registry)
    source = next(
        item for item in source_registry.snapshot()
        if item.spec.id == "craft.bop.entry.change.apply"
    )
    dispatched = []
    registry = CapabilityRegistry()
    registry.register(source.spec, lambda payload, _context: dispatched.append(payload) or {
        "data": {}, "version_gid": "version-1",
    })
    release = build_release([source.descriptor])
    store = InMemoryCatalogStore()
    store.publish(release)

    class _Policy:
        def authorize(self, *_args):
            return AuthorizationDecision(allowed=True, code="allowed", policy_version="test")
        def approve(self, *_args):
            return None
        def project(self, _descriptor, _identity, data):
            return data

    gateway = CapabilityGatewayService(
        CatalogResolver(store, registry),
        _Policy(),
        reliability=ReliabilityCoordinator(InMemoryOutcomeStore(), InMemoryRateLimiter(limit=10)),
    )
    envelope = InvocationEnvelope(
        capability_id=source.spec.id,
        major_version=1,
        catalog_release=release.release_id,
        payload={
            "operation": "update", "entry_gid": "entry-1",
            "properties": [{"name": "sequence_color", "value": "red"}],
        },
        identity=ConsumerIdentity(
            actor=ActorIdentity(user_id="user-1", authentication_method="jwt", authenticated_at=datetime.now(UTC)),
            tenant=TenantIdentity(tenant_id="tenant-1", membership="member", active_roles=("member",)),
            consumer=ConsumerDescriptor(type=ConsumerType.WEB, consumer_id="test.web"),
        ),
        request_id="request-1",
        trace_id="trace-1",
        idempotency_key="entry-property-1",
    )

    result = asyncio.run(gateway.invoke(envelope))

    assert result.ok is True, result.error
    assert dispatched == [envelope.payload]


def test_property_transport_rejects_duplicate_names() -> None:
    with pytest.raises(ValueError, match="duplicate property"):
        bop_entry_change._property_map([
            {"name": "sequence_color", "value": "red"},
            {"name": "sequence_color", "value": "blue"},
        ])


def test_property_updates_reject_undeclared_and_derived_fields(monkeypatch) -> None:
    monkeypatch.setattr(
        bop_entry_change,
        "_property_contracts",
        lambda _node_type: {
            "sequence_color": {"name": "sequence_color", "db_key": "sequence_color", "storage_hint": "entity_table"},
            "computed": {"name": "computed", "db_key": "computed", "storage_hint": "derived"},
        },
    )

    with pytest.raises(CapabilityBusinessError, match="undeclared_property"):
        bop_entry_change._validate_property_updates("process", {"other": "x"})
    with pytest.raises(CapabilityBusinessError, match="read_only_property"):
        bop_entry_change._validate_property_updates("process", {"computed": "x"})


class _Cursor:
    def __init__(self, real_columns, *, entity_exists=True):
        self.real_columns = real_columns
        self.entity_exists = entity_exists
        self.executed = []
        self._rows = []

    def execute(self, sql, params=()):
        self.executed.append((" ".join(sql.split()), tuple(params)))
        if "information_schema.COLUMNS" in sql:
            self._rows = [{"column_name": item} for item in self.real_columns]
        elif sql.lstrip().startswith("SELECT gid FROM workmanship_"):
            self._rows = [{"gid": params[0]}] if self.entity_exists else []

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


def test_property_updates_route_to_fixed_ext_and_meta_storage() -> None:
    cursor = _Cursor({"gid", "standard_time", "ext", "updated_at"})
    contracts = {
        "standard_time": {"name": "standard_time", "db_key": "standard_time", "storage_hint": "entity_table"},
        "sequence_color": {"name": "sequence_color", "db_key": "sequence_color", "storage_hint": "entity_table"},
        "note": {"name": "note", "db_key": "note", "storage_hint": "meta"},
    }

    bop_entry_change._persist_property_updates(
        cursor,
        entry_gid="entry-1",
        entity_table="workmanship_bop_bop_process",
        entity_gid="process-1",
        contracts=contracts,
        properties={"standard_time": 12.5, "sequence_color": "red", "note": "review"},
    )

    statements = "\n".join(sql for sql, _ in cursor.executed)
    assert "SET `standard_time`=%s" in statements
    assert "JSON_TYPE(ext)='NULL'" in statements
    assert "JSON_TYPE(meta)='NULL'" in statements
    assert any(params == (12.5, "process-1") for _, params in cursor.executed)
    assert any(params == ("sequence_color", '"red"', "process-1") for _, params in cursor.executed)
    assert any(params == ("note", '"review"', "entry-1") for _, params in cursor.executed)


def test_property_updates_without_entity_use_entry_meta() -> None:
    cursor = _Cursor(set())
    contracts = {
        "sequence_color": {"name": "sequence_color", "db_key": "sequence_color", "storage_hint": "entity_table"},
    }

    bop_entry_change._persist_property_updates(
        cursor,
        entry_gid="entry-1",
        entity_table=None,
        entity_gid=None,
        contracts=contracts,
        properties={"sequence_color": "blue"},
    )

    assert any(params == ("sequence_color", '"blue"', "entry-1") for _, params in cursor.executed)


def test_property_updates_reject_stale_primary_entity_link() -> None:
    cursor = _Cursor({"gid", "ext"}, entity_exists=False)

    with pytest.raises(CapabilityBusinessError, match="linked entity"):
        bop_entry_change._persist_property_updates(
            cursor,
            entry_gid="entry-1",
            entity_table="workmanship_bop_bop_process",
            entity_gid="missing-process",
            contracts={"sequence_color": {"db_key": "sequence_color", "storage_hint": "auto"}},
            properties={"sequence_color": "blue"},
        )


def test_mandatory_cel_rule_blocks_property_write(monkeypatch) -> None:
    monkeypatch.setattr(
        bop_entry_change,
        "validate_with_proposed",
        lambda *_args, **_kwargs: [
            {"rule_gid": "rule-1", "rule_name": "limit", "message": "too large", "enforcement_level": "mandatory"},
        ],
    )

    with pytest.raises(CapabilityBusinessError, match="too large"):
        bop_entry_change._validate_property_rules(
            node_type="process",
            entry_gid="entry-1",
            properties={"standard_time": 99},
            contracts={"standard_time": {"db_key": "standard_time_seconds"}},
            conn=object(),
        )
