"""Acceptance contracts owned by the independently maintained Knowledge domain."""
from __future__ import annotations

import ast
import json
from pathlib import Path

from backend.capability_v2.bootstrap import get_capability_registry


ROOT = Path(__file__).resolve().parents[2]
capability_registry = get_capability_registry()


def _mapped_stable_knowledge_ids() -> set[str]:
    document = json.loads(
        (ROOT / "docs/governance/user-function-registry.json").read_text(encoding="utf-8")
    )
    return {
        row["target_capability"]
        for row in document["functions"].values()
        if row["domain"] == "Knowledge"
        and row["stability"] == "stable"
        and row["classification"] == "mapped"
        and row.get("target_capability")
    }


def test_all_stable_knowledge_capabilities_have_typed_output_contracts():
    incomplete = {
        capability_id
        for capability_id in _mapped_stable_knowledge_ids()
        if not capability_registry.get(capability_id).spec.output_schema.get("properties")
    }
    assert incomplete == set()


def test_stable_knowledge_reads_are_plugin_callable():
    unavailable = {
        capability_id
        for capability_id in _mapped_stable_knowledge_ids()
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
    for capability_id in _mapped_stable_knowledge_ids():
        registration = capability_registry.get(capability_id)
        if registration.spec.deprecated:
            continue
        descriptor = registration.descriptor
        assert descriptor is not None, capability_id
        assert descriptor.lifecycle_status.value == "stable", capability_id
        assert descriptor.exposure.plugin is True, capability_id
        assert descriptor.exposure.agent is True, capability_id
        assert descriptor.domain_errors_complete is True, capability_id


def test_reviewed_knowledge_operations_are_explicit_and_closed():
    for capability_id in (
        "knowledge.entry.change.apply",
        "knowledge.space.change.apply",
        "knowledge.document.archive",
        "knowledge.personalization.change.apply",
        "knowledge.personalization.read",
    ):
        schema = capability_registry.get(capability_id).descriptor.input_schema
        assert schema["properties"]["operation"]["enum"], capability_id
        assert schema["properties"]["arguments"]["additionalProperties"] is False, capability_id


def test_knowledge_writes_require_gateway_idempotency_and_external_outcome_tracking():
    for capability_id in _mapped_stable_knowledge_ids():
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


def test_legacy_knowledge_entry_get_route_uses_knowledge_capability():
    source = (ROOT / "plugins/knowledge/knowledge_backend/api/knowledge_entries_legacy.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "get_knowledge_entry")
    names = {node.id for node in ast.walk(function) if isinstance(node, ast.Name)}
    literals = {node.value for node in ast.walk(function) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    assert "get_conn" not in names
    assert "knowledge.get" in literals


def test_legacy_knowledge_entry_list_route_uses_search_capability():
    source = (ROOT / "plugins/knowledge/knowledge_backend/api/knowledge_entries_legacy.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "list_knowledge_entries")
    names = {node.id for node in ast.walk(function) if isinstance(node, ast.Name)}
    literals = {node.value for node in ast.walk(function) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    assert "get_conn" not in names
    assert "knowledge.search" in literals


def test_knowledge_search_supports_legacy_list_filters_and_full_projection(monkeypatch):
    from backend.capability_v2.provider_contracts import CapabilityContext
    from plugins.knowledge.knowledge_backend.capabilities import knowledge_next

    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, sql, params):
            self.sql, self.params = sql, params
        def fetchall(self):
            return [{
                "gid": "k1", "display_id": "K1", "title": "Guide", "entry_type": "guide",
                "status": "draft", "share_scope": "team", "list_gid": "list1",
                "source_gid": None, "source_label": "", "maintainer_gid": "u1",
                "contributors": "[]", "attachments": "[]", "tags": "[\"tag\"]",
                "content_ref": "{}", "content_md": "Body", "related_part_nos": "[]",
                "related_operation_gids": "[]", "creator_gid": "u1", "source_project_gid": None,
                "context_class_gid": "class1", "created_at": "2026-08-20T00:00:00Z",
                "updated_at": "2026-08-20T01:00:00Z",
            }]

    class Conn:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def cursor(self): return Cursor()

    monkeypatch.setattr(
        "plugins.knowledge.knowledge_backend.data.connection.get_knowledge_conn",
        lambda: Conn(),
    )
    monkeypatch.setattr(
        "backend.platform_sdk.identity.get_active_team_member_gids",
        lambda _team_gid: [],
    )
    result = knowledge_next.search_knowledge(
        {
            "query": "",
            "limit": 200,
            "entry_type": "guide",
            "list_gid": "list1",
            "context_class_gid": "class1",
            "include_content": True,
        },
        CapabilityContext(user_gid="u1", team_gid="team1"),
    )
    item = result.data["items"][0]
    assert item["content_md"] == "Body"
    assert item["list_gid"] == "list1"
    assert item["context_class_gid"] == "class1"
