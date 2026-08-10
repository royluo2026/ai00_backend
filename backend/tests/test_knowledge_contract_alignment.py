from pathlib import Path
from unittest.mock import patch

import pytest

from backend.capabilities.knowledge_context_next import retrieve_context
from backend.capabilities.knowledge_documents_next import register_knowledge_document_capabilities, revise_document
from backend.capabilities.models_next import CapabilityBusinessError, CapabilityContext
from backend.capabilities.registry_next import CapabilityRegistry


def _registry() -> CapabilityRegistry:
    registry = CapabilityRegistry()
    register_knowledge_document_capabilities(registry)
    return registry


def test_team_collaboration_reads_and_revisions_need_no_document_acl_permission():
    registry = _registry()
    assert registry.get("knowledge.document.get").spec.permissions == ()
    assert registry.get("knowledge.document.revise").spec.permissions == ()
    assert registry.get("knowledge.document.create").spec.permissions == ()
    ids = {spec.id for spec in registry.list()}
    assert {
        "knowledge.document.search",
        "knowledge.document.acl.list",
        "knowledge.document.acl.grant",
        "knowledge.document.acl.revoke",
    } <= ids


def test_approved_names_and_deprecated_aliases_are_explicit():
    registry = _registry()
    for capability_id in (
        "knowledge.space.search",
        "knowledge.document.history.get",
        "knowledge.document.restore",
    ):
        assert registry.get(capability_id).spec.deprecated is False
    aliases = {
        "knowledge.space.list": "knowledge.space.search",
        "knowledge.document.revisions": "knowledge.document.history.get",
        "knowledge.document.rollback": "knowledge.document.restore",
    }
    for alias, replacement in aliases.items():
        spec = registry.get(alias).spec
        assert spec.deprecated is True
        assert spec.replaced_by == replacement
        assert spec.plugin_callable is False


def test_revise_contract_requires_base_revision_gid():
    spec = _registry().get("knowledge.document.revise").spec
    assert "base_revision_gid" in spec.input_schema["required"]


def test_context_retrieval_is_bounded_and_returns_fixed_refs_only():
    candidates = [
        {
            "document_gid": f"d{i}",
            "revision_gid": f"r{i}",
            "title": f"Doc {i}",
            "summary": "short",
            "retrieval_method": "explicit_attachment",
            "evidence": None,
        }
        for i in range(12)
    ]
    with patch(
        "backend.capabilities.knowledge_context_next.explicit_attachment_candidates",
        return_value=candidates,
    ):
        result = retrieve_context(
            {"query": "fastener", "limit": 10},
            CapabilityContext(user_gid="u1", team_gid="t1"),
        )

    assert len(result.data["items"]) == 10
    assert all(item.get("revision_gid") for item in result.data["items"])
    assert all("markdown" not in item for item in result.data["items"])


def test_context_limit_above_ten_is_rejected():
    with pytest.raises(ValueError, match="limit"):
        retrieve_context(
            {"query": "x", "limit": 11},
            CapabilityContext(user_gid="u1", team_gid="t1"),
        )


def test_stale_revision_is_rejected_before_ois_write():
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, *_args): return None
        def fetchone(self):
            return {
                "gid": "d1", "title": "D", "space_gid": "s1",
                "current_revision_gid": "r2", "before_sha256": "a" * 64,
            }

    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def cursor(self): return Cursor()

    with patch("backend.knowledge.data.connection.get_knowledge_conn", return_value=Connection()), patch(
        "backend.capabilities.knowledge_documents_next.store_markdown_revision"
    ) as store:
        with pytest.raises(CapabilityBusinessError) as caught:
            revise_document(
                {"document_gid": "d1", "base_revision_gid": "r1", "markdown": "new"},
                CapabilityContext(user_gid="u1", team_gid="t1"),
            )
    assert caught.value.code == "revision_conflict"
    assert caught.value.details["current_revision_gid"] == "r2"
    store.assert_not_called()

def test_revision_attribution_migration_is_oceanbase_replay_safe():
    root = Path(__file__).resolve().parents[2]
    migration = root / "backend/db/migrations/202608060002_knowledge_revision_attribution.sql"
    sql = migration.read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS channel" in sql
    assert "ADD COLUMN IF NOT EXISTS agent_run_gid" in sql
    assert "ADD COLUMN IF NOT EXISTS before_sha256" in sql
    assert "RETURNING" not in sql.upper()
    assert "::" not in sql
