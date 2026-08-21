from __future__ import annotations

import asyncio
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from backend.capabilities.models_next import CapabilityContext, CapabilityOutput
from backend.capabilities.registry_next import CapabilityRegistry
from plugins.craft.craft_backend.capabilities import register_capabilities
from plugins.craft.craft_backend.capabilities.bop_writes import (
    BopWriteRepository,
    MysqlBopWriteRepository,
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

    def get_preview_by_idempotency(self, version_gid, key):
        return next((
            item for item in self.previews.values()
            if item["version_gid"] == version_gid and item.get("idempotency_key") == key
        ), None)

    def mark_applied(self, preview_gid, result):
        self.previews[preview_gid]["applied"] = result

    def get_applied(self, key):
        return self.applied.get(key)

    def put_applied(self, key, result):
        self.applied[key] = result

    def put_import_preview(self, preview):
        self.imports[preview["import_preview_gid"]] = dict(preview)

    def get_import_preview(self, preview_gid):
        preview = self.imports.get(preview_gid)
        return dict(preview["document"]) if preview else None

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
    assert all(registry.get(cap).spec.plugin_callable for cap in {
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


def test_preview_idempotency_returns_same_preview_and_rejects_payload_rebinding():
    repository = MemoryRepository()
    payload = {
        "version_gid": "v1", "expected_revision": 1, "idempotency_key": "preview-1",
        "commands": [{"kind": "version.metadata.update", "changes": {"bop_name": "A"}}],
    }
    with patch("plugins.craft.craft_backend.capabilities.bop_writes.repository", repository):
        first = preview_draft_change(payload, ctx()).data
        repeated = preview_draft_change(payload, ctx()).data
        with pytest.raises(Exception, match="idempotency"):
            preview_draft_change({
                **payload,
                "commands": [{"kind": "version.metadata.update", "changes": {"bop_name": "B"}}],
            }, ctx())
    assert repeated == first
    assert len(repository.previews) == 1


def test_apply_consumes_gateway_approved_preview_and_is_idempotent():
    repository = MemoryRepository()
    preview_payload = {
        "version_gid": "v1", "expected_revision": 1, "idempotency_key": "change-2",
        "commands": [{"kind": "entry.create", "entry": {"node_type": "operation", "title": "Torque"}}],
    }
    with patch("plugins.craft.craft_backend.capabilities.bop_writes.repository", repository):
        preview = preview_draft_change(preview_payload, ctx()).data
        applied = apply_draft_change({"preview_gid": preview["preview_gid"], "idempotency_key": "change-2"}, ctx("gateway-approved")).data
        repeated = apply_draft_change({"preview_gid": preview["preview_gid"], "idempotency_key": "change-2"}, ctx("wrong")).data
    assert applied["revision"] == 2
    assert repeated == applied
    assert len(repository.versions["v1"]["entries"]) == 2


def test_apply_cannot_replace_the_idempotency_key_bound_by_preview():
    repository = MemoryRepository()
    with patch("plugins.craft.craft_backend.capabilities.bop_writes.repository", repository):
        preview = preview_draft_change({
            "version_gid": "v1", "expected_revision": 1,
            "idempotency_key": "bound-key", "commands": [],
        }, ctx()).data
        with pytest.raises(Exception, match="idempotency"):
            apply_draft_change({
                "preview_gid": preview["preview_gid"], "idempotency_key": "replacement-key",
            }, ctx("gateway-approved"))
    assert repository.versions["v1"]["revision"] == 1


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


def test_create_preserves_legacy_version_identity_fields():
    repository = MemoryRepository()
    with patch("plugins.craft.craft_backend.capabilities.bop_writes.repository", repository):
        created = create_bop_version(
            {
                "source": "empty",
                "version_tag": "V4",
                "bop_name": "Assembly BOP",
                "version_family_gid": "family-1",
                "project_gid": "project-1",
                "factory_gid": "factory-1",
                "vehicle_model_gid": "model-1",
                "maturity": "concept",
                "takt_time": 60,
                "version_type": "working",
                "pbom_version_gid": "pbom-1",
                "owner_gid": "owner-1",
                "data_stage": "draft",
            },
            ctx(),
        ).data

    version = repository.versions[created["version_gid"]]
    assert {key: version[key] for key in (
        "bop_name", "version_family_gid", "project_gid", "factory_gid",
        "vehicle_model_gid", "maturity", "takt_time", "version_type",
        "pbom_version_gid", "owner_gid", "data_stage",
    )} == {
        "bop_name": "Assembly BOP", "version_family_gid": "family-1",
        "project_gid": "project-1", "factory_gid": "factory-1",
        "vehicle_model_gid": "model-1", "maturity": "concept", "takt_time": 60,
        "version_type": "working", "pbom_version_gid": "pbom-1",
        "owner_gid": "owner-1", "data_stage": "draft",
    }


def test_create_remaps_cloned_entry_parent_references_to_the_new_version():
    repository = MemoryRepository()
    repository.versions["v1"]["entries"].append({
        "gid": "e2", "parent_gid": "e1", "node_type": "operation",
        "sort_order": 20, "title": "Torque", "meta": {},
    })
    with patch("plugins.craft.craft_backend.capabilities.bop_writes.repository", repository):
        created = create_bop_version(
            {"source": "bop_version", "source_gid": "v1", "version_tag": "V2"}, ctx()
        ).data
    entries = repository.versions[created["version_gid"]]["entries"]
    root = next(item for item in entries if item["title"] == "Line")
    child = next(item for item in entries if item["title"] == "Torque")
    assert root["gid"] not in {"e1", "e2"}
    assert child["gid"] not in {"e1", "e2"}
    assert child["parent_gid"] == root["gid"]


class _SqlCursor:
    def __init__(self, *, update_count=1):
        self.rowcount = update_count
        self.calls = []

    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def execute(self, sql, params=()):
        self.calls.append((" ".join(sql.split()), params))
        if sql.lstrip().startswith("UPDATE workmanship_bop_bop_versions"):
            self.rowcount = self.rowcount


class _SqlConnection:
    def __init__(self, cursor):
        self._cursor = cursor; self.commits = 0; self.rollbacks = 0
    def cursor(self): return self._cursor
    def commit(self): self.commits += 1
    def rollback(self): self.rollbacks += 1


def _connection_factory(connection):
    @contextmanager
    def factory():
        yield connection
    return factory


def test_mysql_write_repository_commits_revision_entries_and_links_atomically():
    cursor = _SqlCursor(update_count=1)
    connection = _SqlConnection(cursor)
    version = {
        "gid": "v1", "revision": 1, "version_tag": "V1", "bop_name": "Assembly",
        "status": "active", "factory_gid": "factory-1", "vehicle_model_gid": "model-1",
        "maturity": "concept", "takt_time": 60, "version_type": "working",
        "pbom_version_gid": "pbom-1", "owner_gid": "owner-1", "data_stage": "draft",
        "visibility": "team", "meta": {},
        "entries": [{"gid": "e1", "node_type": "operation", "title": "Torque"}],
        "links": [{"gid": "l1", "entry_gid": "e1", "link_type": "part", "entity_gid": "p1"}],
    }
    with patch(
        "plugins.craft.craft_backend.capabilities.bop_writes.get_craft_conn",
        _connection_factory(connection),
    ):
        saved = MysqlBopWriteRepository().save_version(version, expected_revision=1)
    statements = [sql for sql, _params in cursor.calls]
    assert saved["revision"] == 2
    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert any("revision=revision+1" in sql and "revision=%s" in sql for sql in statements)
    assert any("factory_gid=%s" in sql and "vehicle_model_gid=%s" in sql for sql in statements)
    assert any("INSERT INTO workmanship_bop_bop_entries" in sql for sql in statements)
    entry_call = next(call for call in cursor.calls if "INSERT INTO workmanship_bop_bop_entries" in call[0])
    assert "child_vpps" in entry_call[0]
    assert "[]" in entry_call[1]
    assert any("INSERT INTO workmanship_bop_bop_entry_links" in sql for sql in statements)


def test_mysql_write_repository_rolls_back_on_revision_conflict():
    cursor = _SqlCursor(update_count=0)
    connection = _SqlConnection(cursor)
    with patch(
        "plugins.craft.craft_backend.capabilities.bop_writes.get_craft_conn",
        _connection_factory(connection),
    ), pytest.raises(Exception, match="revision"):
        MysqlBopWriteRepository().save_version(
            {"gid": "v1", "status": "active", "entries": [], "links": []},
            expected_revision=1,
        )
    assert connection.commits == 0
    assert connection.rollbacks == 1


def test_mysql_preview_commit_has_one_transaction_for_state_and_idempotency():
    cursor = _SqlCursor(update_count=1)
    connection = _SqlConnection(cursor)
    preview = {"preview_gid": "preview-1", "base_revision": 1}
    version = {
        "gid": "v1", "revision": 2, "version_tag": "V1", "bop_name": "Assembly",
        "status": "active", "meta": {}, "entries": [], "links": [],
    }
    result = {
        "version_gid": "v1", "revision": 2, "before_hash": "before",
        "after_hash": "after", "preview_gid": "preview-1", "idempotency_key": "idem-1",
    }
    with patch(
        "plugins.craft.craft_backend.capabilities.bop_writes.get_craft_conn",
        _connection_factory(connection),
    ):
        MysqlBopWriteRepository().commit_preview(
            preview, version, result, idempotency_key="idem-1", actor_id="u1"
        )
    statements = [sql for sql, _params in cursor.calls]
    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert any("workmanship_craft_bop_change_previews" in sql for sql in statements)
    assert any("workmanship_craft_bop_write_idempotency" in sql for sql in statements)


def test_import_preview_does_not_write_business_state():
    repository = MemoryRepository()
    document = {"version_tag": "V9", "bop_name": "Imported", "entries": [{"node_type": "operation", "title": "Torque"}]}
    with patch("plugins.craft.craft_backend.capabilities.bop_writes.repository", repository):
        result = import_preview({"document": document}, ctx())
    assert result.data["content_hash"]
    assert result.data["entry_count"] == 1
    assert repository.versions.keys() == {"v1"}
    assert set(repository.versions) == {"v1"}


def test_import_preview_is_a_production_repository_source_for_version_create():
    repository = MemoryRepository()
    del repository.imports
    repository._import_previews = {}
    repository.put_import_preview = lambda preview: repository._import_previews.__setitem__(
        preview["import_preview_gid"], dict(preview)
    )
    repository.get_import_preview = lambda preview_gid: (
        repository._import_previews.get(preview_gid) or {}
    ).get("document")
    with patch("plugins.craft.craft_backend.capabilities.bop_writes.repository", repository):
        imported = import_preview({
            "document": {"version_tag": "I1", "bop_name": "Imported", "entries": [
                {"node_type": "operation", "title": "Torque"}
            ]}
        }, ctx()).data
        created = create_bop_version({
            "source": "import_preview",
            "import_preview_gid": imported["import_preview_gid"],
            "version_tag": "V2",
        }, ctx()).data
    assert created["entries_count"] == 1
