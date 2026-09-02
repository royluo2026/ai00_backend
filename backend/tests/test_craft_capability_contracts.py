"""Acceptance contracts for the independently owned Craft provider."""
from __future__ import annotations

import ast
from pathlib import Path

from backend.capabilities.registry_next import CapabilityRegistry
from backend.domain_ports.craft import CraftCommandPort, CraftQueryPort
from plugins.craft.craft_backend.capabilities import register_capabilities
from plugins.craft.craft_backend.capabilities.gbop_descriptors import GBOP_CAPABILITY_IDS
from plugins.craft.craft_backend.capabilities.reviewed_ids import (
    CRAFT_REVIEWED_CAPABILITIES,
    DEPRECATED_REVIEWED_CAPABILITIES,
)
from plugins.craft.craft_backend.capabilities.rule_descriptors import RULE_CAPABILITY_IDS


STABLE_CAPABILITIES = {
    "craft.bop.draft.change.apply",
    "craft.bop.draft.change.preview",
    "craft.bop.execution_structure.get",
    "craft.bop.execution_structure.preview",
    "craft.bop.entry.detail.get",
    "craft.bop.import.preview",
    "craft.bop.linked_parts.get",
    "craft.bop.structure.outline.get",
    "craft.bop.version.archive",
    "craft.bop.version.compare",
    "craft.bop.version.create",
    "craft.bop.version.get",
    "craft.bop.version.list",
    "craft.bop.work_package.get",
    "craft.gbop.item.knowledge.list",
    "craft.gbop.item.search",
    "craft.gbop.item.usage.get",
    "craft.pbom.part.search",
    "craft.pbom.draft.change.apply",
    "craft.pbom.draft.change.preview",
    "craft.pbom.import.preview",
    "craft.pbom.version.archive",
    "craft.pbom.version.compare",
    "craft.pbom.version.create",
    "craft.pbom.version.get",
    "craft.pbom.version.publish",
    "craft.pbom.version.search",
    "craft.pbom.version.submit",
    "craft.library.read",
    "craft.library.change.apply",
    "craft.standard_operation.read",
    "craft.standard_operation.change.apply",
    "craft.vpps_audit.read",
    "craft.vpps_audit.change.apply",
    "craft.rule.engine.evaluate",
    "craft.bop.pbom.change_point.get",
    "craft.rule.library.read",
    "craft.rule.library.change.apply",
    "craft.gbop.catalog.read",
    "craft.gbop.navigation.read",
    "craft.gbop.process_hierarchy.read",
    "craft.gbop.navigation.change.apply",
    "craft.gbop.station_autolink.preview",
    "craft.ebom.legacy_read",
    "craft.ebom.vpps_check.read",
    "craft.ebom.part.bulk_create",
    "craft.ebom.part.create",
    "craft.ebom.part.delete",
    "craft.ebom.part.update",
    "craft.ebom.snapshot.delete",
    "craft.ebom.snapshot.status.update",
    "craft.ebom.snapshot.update",
    "craft.ebom.snapshot.vpps_stats.update",
    "craft.bop.fork_preset.read",
    "craft.bop.entry.search",
    "craft.bop.alt_hierarchy.read",
    "craft.bop.line_operation_catia.read",
    "craft.bop.pbom_lifecycle.read",
    "craft.bop.lifecycle.read",
    "craft.bop.lifecycle.state.read",
    "craft.bop.version.legacy_read",
    "craft.bop.entry.legacy_read",
    "craft.bop.gbop.legacy_read",
    "craft.bop.staging.read",
    "craft.bop.fork_preset.change.apply",
    "craft.bop.lifecycle.change.apply",
    "craft.bop.staging.change.apply",
    "craft.bop.version.freeze.change.apply",
    "craft.bop.version.layout.change.apply",
    "craft.bop.version.lifecycle.change.apply",
    "craft.data_exchange.lark.read",
    "craft.data_exchange.lark.write",
    "craft.bop.entry_link.change.apply",
    "craft.bop.staging.lifecycle.change.apply",
    "craft.bop.entry.change.apply",
    "craft.bop.picture.upload",
    "craft.bop.lifecycle.state.change.apply",
    "craft.bop.lifecycle.checkpoint.change.apply",
    "craft.bop.lifecycle.checkpoint.rollback.apply",
    "craft.bop.lifecycle.history.change.apply",
    "craft.bop.lifecycle.step.rollback.apply",
    "craft.bop.lifecycle.stats.refresh.apply",
    "craft.bop.template.change.apply",
    "craft.bop.version.snapshot.change.apply",
    "craft.bop.fork.change.apply",
    "craft.bop.entry.bulk.change.apply",
    "craft.bop.gbop.change.apply",
    "craft.gbop.version.change.apply",
    "craft.gbop.entity.change.apply",
    "craft.gbop.import.change.apply",
    "craft.gbop.station_autolink.change.apply",
    "craft.gbop.import.tc.change.apply",
}
STABLE_CAPABILITIES.update(GBOP_CAPABILITY_IDS)
STABLE_CAPABILITIES.update(RULE_CAPABILITY_IDS)
STABLE_CAPABILITIES.update(CRAFT_REVIEWED_CAPABILITIES)


def test_craft_publishes_query_and_command_ports_without_implementation_imports():
    assert CraftQueryPort.__module__ == "backend.domain_ports.craft"
    assert CraftCommandPort.__module__ == "backend.domain_ports.craft"


def _registrations():
    registry = CapabilityRegistry()
    register_capabilities(registry)
    return {item.spec.id: item for item in registry.snapshot()}


def test_all_stable_craft_capabilities_have_native_open_contracts():
    registrations = _registrations()
    assert set(registrations) == STABLE_CAPABILITIES

    for capability_id in sorted(STABLE_CAPABILITIES):
        item = registrations[capability_id]
        descriptor = item.descriptor
        assert descriptor is not None, capability_id
        assert descriptor.owner_domain == "craft"
        if capability_id in DEPRECATED_REVIEWED_CAPABILITIES:
            assert descriptor.lifecycle_status == "deprecated"
            assert descriptor.input_schema["properties"]["operation"]["enum"] == []
            continue
        assert descriptor.lifecycle_status == "stable"
        assert descriptor.exposure.plugin is True
        assert descriptor.exposure.agent is True
        assert descriptor.exposure.mcp is True
        assert descriptor.input_schema["additionalProperties"] is False
        assert descriptor.output_schema["additionalProperties"] is False
        assert descriptor.output_schema["properties"]
        assert descriptor.agent_output_schema == descriptor.output_schema
        assert descriptor.domain_errors_complete is True
        assert descriptor.domain_errors
        assert item.spec.plugin_callable is True


def test_craft_write_and_revision_contracts_are_governed():
    registrations = _registrations()
    writes = {
        "craft.bop.draft.change.apply",
        "craft.bop.version.archive",
        "craft.bop.version.create",
        "craft.pbom.draft.change.apply",
        "craft.pbom.version.archive",
        "craft.pbom.version.create",
        "craft.pbom.version.publish",
        "craft.pbom.version.submit",
    }
    expected_revision = {
        "craft.bop.draft.change.preview": "expected_revision",
        "craft.bop.execution_structure.preview": "expected_revision",
        "craft.bop.version.archive": "expected_revision",
    }

    for capability_id in writes:
        descriptor = registrations[capability_id].descriptor
        assert descriptor.confirmation_policy == "user"
        assert descriptor.idempotency_policy == "required"
        assert descriptor.operation_policy == "optional"
        assert descriptor.consistency_policy == "external"

    for capability_id, payload_path in expected_revision.items():
        descriptor = registrations[capability_id].descriptor
        assert descriptor.concurrency_policy == "expected_version"
        assert descriptor.expected_version_payload_path == payload_path


def test_craft_contracts_publish_stable_resource_selectors():
    registrations = _registrations()
    selected = {
        "craft.bop.version.get": ("craft-bop-version", "version_gid"),
        "craft.bop.version.archive": ("craft-bop-version", "version_gid"),
        "craft.pbom.version.get": ("craft-pbom-version", "version_gid"),
        "craft.gbop.item.usage.get": ("craft-gbop-item", "item_gid"),
    }

    for capability_id, expected in selected.items():
        descriptor = registrations[capability_id].descriptor
        assert [(item.resource_type, item.payload_path) for item in descriptor.resource_selectors] == [expected]


def test_bop_version_get_route_is_gateway_backed() -> None:
    source_path = Path("plugins/craft/craft_backend/routers/_bop/versions.py")
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    function = next(item for item in tree.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "get_version")
    names = {node.id for node in ast.walk(function) if isinstance(node, ast.Name)}
    literals = {node.value for node in ast.walk(function) if isinstance(node, ast.Constant) and isinstance(node.value, str)}

    assert "get_conn" not in names
    assert "craft.bop.version.get" in literals


def test_bop_version_list_route_is_gateway_backed() -> None:
    source_path = Path("plugins/craft/craft_backend/routers/_bop/versions.py")
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    function = next(item for item in tree.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "list_versions")
    names = {node.id for node in ast.walk(function) if isinstance(node, ast.Name)}
    literals = {node.value for node in ast.walk(function) if isinstance(node, ast.Constant) and isinstance(node.value, str)}

    assert "get_conn" not in names
    assert "craft.bop.version.list" in literals


def test_bop_version_create_route_is_gateway_backed() -> None:
    source_path = Path("plugins/craft/craft_backend/routers/_bop/versions.py")
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    function = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "create_version")
    names = {node.id for node in ast.walk(function) if isinstance(node, ast.Name)}
    literals = {node.value for node in ast.walk(function) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    assert "get_conn" not in names
    assert "craft.bop.version.create" in literals


def test_bop_version_update_route_is_gateway_backed() -> None:
    source_path = Path("plugins/craft/craft_backend/routers/_bop/versions.py")
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    function = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "update_version")
    names = {node.id for node in ast.walk(function) if isinstance(node, ast.Name)}
    literals = {node.value for node in ast.walk(function) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    assert "get_conn" not in names
    assert "craft.bop.version.get" in literals
    assert "craft.bop.draft.change.preview" in literals
    assert "craft.bop.draft.change.apply" in literals


def test_gbop_version_list_route_is_gateway_backed() -> None:
    source_path = Path("plugins/craft/craft_backend/routers/gbop.py")
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    function = next(item for item in tree.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "list_versions")
    names = {node.id for node in ast.walk(function) if isinstance(node, ast.Name)}
    literals = {node.value for node in ast.walk(function) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    assert "get_conn" not in names
    assert "craft.gbop.release.search" in literals


def test_bop_linked_parts_route_is_gateway_backed() -> None:
    source_path = Path("plugins/craft/craft_backend/routers/_bop/entries.py")
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    function = next(item for item in tree.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "get_version_linked_parts")
    names = {node.id for node in ast.walk(function) if isinstance(node, ast.Name)}
    literals = {node.value for node in ast.walk(function) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    assert "get_conn" not in names
    assert "craft.bop.linked_parts.get" in literals


def test_bop_entry_detail_legacy_route_is_gateway_backed() -> None:
    source_path = Path("plugins/craft/craft_backend/routers/_bop/entries.py")
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    function = next(item for item in tree.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "get_entry")
    names = {node.id for node in ast.walk(function) if isinstance(node, ast.Name)}
    literals = {node.value for node in ast.walk(function) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    assert "get_conn" not in names
    assert "craft.bop.entry.detail.get" in literals


def test_bop_version_pbom_route_is_gateway_backed() -> None:
    source_path = Path("plugins/craft/craft_backend/routers/_bop/entries.py")
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    function = next(item for item in tree.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "get_version_pbom")
    names = {node.id for node in ast.walk(function) if isinstance(node, ast.Name)}
    literals = {node.value for node in ast.walk(function) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    assert "get_conn" not in names
    assert "craft.bop.linked_parts.get" in literals
