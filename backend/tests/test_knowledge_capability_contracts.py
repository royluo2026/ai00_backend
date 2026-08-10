"""Acceptance contracts owned by the independently maintained Knowledge domain."""
from __future__ import annotations

import json
from pathlib import Path

from backend.capabilities.registry_next import capability_registry


ROOT = Path(__file__).resolve().parents[2]


def _stable_knowledge_ids() -> set[str]:
    document = json.loads(
        (ROOT / "docs/governance/user-function-registry.json").read_text(encoding="utf-8")
    )
    return {
        row["target_capability"]
        for row in document["functions"].values()
        if row["domain"] == "Knowledge"
        and row["stability"] == "stable"
        and row.get("target_capability")
    }


def test_all_stable_knowledge_capabilities_have_typed_output_contracts():
    incomplete = {
        capability_id
        for capability_id in _stable_knowledge_ids()
        if not capability_registry.get(capability_id).spec.output_schema.get("properties")
    }
    assert incomplete == set()


def test_stable_knowledge_reads_are_plugin_callable():
    unavailable = {
        capability_id
        for capability_id in _stable_knowledge_ids()
        if not capability_registry.get(capability_id).spec.deprecated
        and capability_registry.get(capability_id).spec.risk.value == "read"
        and not capability_registry.get(capability_id).spec.plugin_callable
    }
    assert unavailable == set()


def test_knowledge_resource_contracts_publish_prefixed_stable_refs():
    from backend.knowledge.contracts import (
        DOCUMENT_REF_SCHEMA,
        OUTBOX_REF_SCHEMA,
        PROPOSAL_REF_SCHEMA,
        REVISION_REF_SCHEMA,
        SPACE_REF_SCHEMA,
    )

    assert SPACE_REF_SCHEMA["pattern"].startswith("^knowledge-space:")
    assert DOCUMENT_REF_SCHEMA["pattern"].startswith("^knowledge-document:")
    assert REVISION_REF_SCHEMA["pattern"].startswith("^knowledge-revision:")
    assert PROPOSAL_REF_SCHEMA["pattern"].startswith("^knowledge-proposal:")
    assert OUTBOX_REF_SCHEMA["pattern"].startswith("^knowledge-outbox:")


def test_supported_knowledge_capabilities_publish_native_plugin_and_agent_contracts():
    for capability_id in _stable_knowledge_ids():
        registration = capability_registry.get(capability_id)
        if registration.spec.deprecated:
            continue
        descriptor = registration.descriptor
        assert descriptor is not None, capability_id
        assert descriptor.lifecycle_status.value == "stable", capability_id
        assert descriptor.exposure.plugin is True, capability_id
        assert descriptor.exposure.agent is True, capability_id
        assert descriptor.domain_errors_complete is True, capability_id


def test_knowledge_writes_require_gateway_idempotency_and_external_outcome_tracking():
    for capability_id in _stable_knowledge_ids():
        registration = capability_registry.get(capability_id)
        if registration.spec.deprecated or registration.spec.risk.value == "read":
            continue
        descriptor = registration.descriptor
        assert descriptor.idempotency_policy == "required", capability_id
        assert descriptor.consistency_policy == "external", capability_id
        assert descriptor.confirmation_policy != "none", capability_id


def test_generated_plugin_and_agent_catalogs_publish_supported_knowledge_tools_only():
    catalog = json.loads((ROOT / "docs/capabilities/catalog.v2.json").read_text(encoding="utf-8"))
    agent_tools = json.loads((ROOT / "docs/capabilities/agent-tools.v2.json").read_text(encoding="utf-8"))
    knowledge = {
        item["id"]: item for item in catalog["capabilities"]
        if item["owner_domain"] == "knowledge"
    }
    published_to_agent = {item["id"] for item in agent_tools["tools"]}

    for capability_id, item in knowledge.items():
        if item["lifecycle_status"] == "deprecated":
            assert item["exposure"]["plugin"] is False
            assert capability_id not in published_to_agent
        else:
            assert item["exposure"]["plugin"] is True
            assert capability_id in published_to_agent
