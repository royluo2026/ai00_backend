"""Acceptance contracts for the independently owned Craft provider."""
from __future__ import annotations

from backend.capabilities.registry_next import CapabilityRegistry
from backend.domain_ports.craft import CraftCommandPort, CraftQueryPort
from plugins.craft.craft_backend.capabilities import register_capabilities
from plugins.craft.craft_backend.capabilities.gbop_descriptors import GBOP_CAPABILITY_IDS
from plugins.craft.craft_backend.capabilities.rule_descriptors import RULE_CAPABILITY_IDS


STABLE_CAPABILITIES = {
    "craft.bop.draft.change.apply",
    "craft.bop.draft.change.preview",
    "craft.bop.execution_structure.get",
    "craft.bop.execution_structure.preview",
    "craft.bop.import.preview",
    "craft.bop.linked_parts.get",
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
}
STABLE_CAPABILITIES.update(GBOP_CAPABILITY_IDS)
STABLE_CAPABILITIES.update(RULE_CAPABILITY_IDS)


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
