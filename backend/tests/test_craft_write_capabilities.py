from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from backend.capabilities.models_next import CapabilityContext, CapabilityOutput
from backend.capabilities.registry_next import CapabilityRegistry
from plugins.craft.craft_backend.capabilities import register_capabilities
from plugins.craft.craft_backend.capabilities.bop_writes import (
    BopWriteRepository,
    apply_draft_change,
    archive_bop_version,
    create_bop_version,
    import_preview,
    preview_draft_change,
)


class MemoryRepository(BopWriteRepository):
    def __init__(self):
        self.versions = {
            "v1": {"gid": "v1", "revision": 1, "status": "active", "version_tag": "V1", "bop_name": "Assembly", "project_gid": "p1", "version_family_gid": "f1", "entries": [{"gid": "e1", "parent_gid": None, "node_type": "line_process", "sort_order": 10, "title": "Line", "vpps": "1"}], "links": [], "meta": {}}
        }
        self.previews = {}
        self.applied = {}
        self.imports = {}
        self.tokens = {}

    def get_version(self, version_gid):
        return self.versions.get(version_gid)

    def save_version(self, version, *, expected_revision):
        updated = dict(version); updated["revision"] = expected_revision + 1; self.versions[updated["gid"]] = updated; return updated

    def create_version(self, version):
        self.versions[version["gid"]] = dict(version); return self.versions[version["gid"]]

    def put_preview(self, preview):
        self.previews[preview["preview_gid"]] = dict(preview)

    def get_preview(self, preview_gid):
        return self.previews.get(preview_gid)

    def mark_applied(self, preview_gid, result):
        self.previews[preview_gid]["applied"] = result

    def get_applied(self, key):
        return self.applied.get(key)

    def put_applied(self, key, result):
        self.applied[key] = result

    def issue_confirmation(self, preview_gid, user_gid):
        self.tokens[(preview_gid, user_gid)] = "ok"; return "ok"

    def consume_confirmation(self, preview_gid, user_gid, token):
        return self.tokens.pop((preview_gid, user_gid), None) == token

def ctx(token=None):
    return CapabilityContext(user_gid="u1", request_id="r1", confirmation_token=token, permissions=("craft.write",))


def test_registry_exposes_only_the_approved_write_slice():
    registry = CapabilityRegistry()
    register_capabilities(registry)
    ids = {spec.id for spec in registry.list()}
    assert {
        "craft.bop.draft.change.preview",
        "craft.bop.draft.change.apply",
        "craft.bop.version.create",
        "craft.bop.version.archive",
        "craft.bop.import.preview",
    } <= ids
    assert "craft.bop.version.validate" not in ids
    assert "craft.bop.version.publish" not in ids
    assert all(not registry.get(cap).spec.plugin_callable for cap in {
        "craft.bop.draft.change.preview",
        "craft.bop.draft.change.apply",
        "craft.bop.version.create",
        "craft.bop.version.archive",
        "craft.bop.import.preview",
    })


def test_preview_is_side_effect_free_and_binds_revision_and_hashes():
    repository = MemoryRepository()
    payload = {
        "version_gid": "v1",
        "expected_revision": 1,
        "idempotency_key": "change-1",
        "commands": [{"kind": "entry.create", "entry": {"node_type": "operation", "title": "Torque"}}],
    }
    with patch("plugins.craft.craft_backend.capabilities.bop_writes.repository", repository):
        result = preview_draft_change(payload, ctx())
    assert result.data["preview_gid"]
    assert result.data["version_gid"] == "v1"
    assert result.data["base_revision"] == 1
    assert result.data["before_hash"] != result.data["after_hash"]
    assert result.data["expires_at"]
    assert repository.versions["v1"]["revision"] == 1
    assert repository.versions["v1"]["entries"] == [{"gid": "e1", "parent_gid": None, "node_type": "line_process", "sort_order": 10, "title": "Line", "vpps": "1"}]


def test_preview_rejects_json_patch_sql_and_unknown_commands():
    repository = MemoryRepository()
    with patch("plugins.craft.craft_backend.capabilities.bop_writes.repository", repository):
        for commands in (
            [{"kind": "json.patch", "path": "/entries/0/title", "value": "x"}],
            [{"kind": "sql.execute", "sql": "UPDATE ..."}],
            [{"kind": "command.execute", "name": "anything"}],
        ):
            with pytest.raises(ValueError):
                preview_draft_change({"version_gid": "v1", "expected_revision": 1, "commands": commands}, ctx())


def test_apply_requires_preview_confirmation_is_one_time_and_is_idempotent():
    repository = MemoryRepository()
    preview_payload = {
        "version_gid": "v1", "expected_revision": 1, "idempotency_key": "change-2",
        "commands": [{"kind": "entry.create", "entry": {"node_type": "operation", "title": "Torque"}}],
    }
    with patch("plugins.craft.craft_backend.capabilities.bop_writes.repository", repository):
        preview = preview_draft_change(preview_payload, ctx()).data
        token = repository.issue_confirmation(preview["preview_gid"], "u1")
        applied = apply_draft_change({"preview_gid": preview["preview_gid"], "idempotency_key": "change-2"}, ctx(token)).data
        repeated = apply_draft_change({"preview_gid": preview["preview_gid"], "idempotency_key": "change-2"}, ctx("wrong")).data
    assert applied["revision"] == 2
    assert repeated == applied
    assert len(repository.versions["v1"]["entries"]) == 2


def test_apply_rejects_stale_revision_and_expired_preview():
    repository = MemoryRepository()
    with patch("plugins.craft.craft_backend.capabilities.bop_writes.repository", repository):
        preview = preview_draft_change({"version_gid": "v1", "expected_revision": 1, "commands": []}, ctx()).data
        repository.versions["v1"]["revision"] = 2
        with pytest.raises(Exception, match="revision"):
            apply_draft_change({"preview_gid": preview["preview_gid"]}, ctx("missing"))
        preview = preview_draft_change({"version_gid": "v1", "expected_revision": 2, "commands": []}, ctx()).data
        repository.previews[preview["preview_gid"]]["expires_at_epoch"] = 0
        with pytest.raises(Exception, match="expired"):
            apply_draft_change({"preview_gid": preview["preview_gid"]}, ctx("missing"))


def test_create_allows_only_governed_sources_and_archive_is_non_destructive():
    repository = MemoryRepository()
    with patch("plugins.craft.craft_backend.capabilities.bop_writes.repository", repository):
        created = create_bop_version({"source": "bop_version", "source_gid": "v1", "version_tag": "V2", "idempotency_key": "create-1"}, ctx()).data
        assert created["parent_version_gid"] == "v1"
        assert created["status"] == "active"
        assert created["entries_count"] == 1
        archived = archive_bop_version({"version_gid": created["version_gid"], "expected_revision": 1, "idempotency_key": "archive-1"}, ctx()).data
    assert archived["status"] == "archived"
    assert repository.versions[created["version_gid"]]["entries"]
    with pytest.raises(ValueError):
        create_bop_version({"source": "clone", "source_gid": "v1", "version_tag": "V3"}, ctx())


def test_import_preview_does_not_write_business_state():
    repository = MemoryRepository()
    document = {"version_tag": "V9", "bop_name": "Imported", "entries": [{"node_type": "operation", "title": "Torque"}]}
    with patch("plugins.craft.craft_backend.capabilities.bop_writes.repository", repository):
        result = import_preview({"document": document}, ctx())
    assert result.data["content_hash"]
    assert result.data["entry_count"] == 1
    assert repository.versions.keys() == {"v1"}
    assert set(repository.versions) == {"v1"}
