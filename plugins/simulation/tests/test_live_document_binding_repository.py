"""Repository behavior on real SQLite transactions; not MySQL lock verification."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import hashlib
import itertools
import json
import sqlite3

import pytest

from plugins.simulation.simulation_backend.data import workspace_repository as module


@pytest.fixture
def database(tmp_path, monkeypatch):
    path = tmp_path / "binding.db"
    with sqlite3.connect(path) as db:
        db.executescript("""
        CREATE TABLE workmanship_sim_workspaces (
          gid TEXT PRIMARY KEY, tenant_gid TEXT, owner_gid TEXT, name TEXT,
          review_type TEXT, version_label TEXT, status TEXT, visibility TEXT,
          primary_project_gid TEXT, cache_revision_hash TEXT, row_version INTEGER, removed_at TEXT);
        ALTER TABLE workmanship_sim_workspaces ADD COLUMN updated_at TEXT;
        CREATE TABLE workmanship_sim_workspace_versions (
          gid TEXT PRIMARY KEY, workspace_gid TEXT, tenant_gid TEXT, owner_gid TEXT,
          sequence INTEGER, status TEXT, row_version INTEGER, removed_at TEXT);
        CREATE TABLE workmanship_sim_workspace_heads (workspace_gid TEXT PRIMARY KEY, version_gid TEXT, row_version INTEGER);
        CREATE TABLE workmanship_sim_workspace_projects (workspace_gid TEXT, project_gid TEXT, sort_order INTEGER);
        CREATE TABLE workmanship_sim_live_document_bindings (
          tenant_gid TEXT, actor_gid TEXT, session_identity_hash TEXT, connector_device_id TEXT,
          document_session TEXT, workspace_gid TEXT, state TEXT DEFAULT 'importing',
          updated_at TEXT,
          PRIMARY KEY(tenant_gid,actor_gid,session_identity_hash));
        CREATE TABLE workmanship_sim_live_document_adoptions (
          tenant_gid TEXT, actor_gid TEXT, idempotency_key TEXT, request_hash TEXT, response_json TEXT,
          PRIMARY KEY(tenant_gid,actor_gid,idempotency_key));
        CREATE TABLE workmanship_sim_vm_documents (
          gid TEXT PRIMARY KEY, workspace_gid TEXT, tenant_gid TEXT, owner_gid TEXT,
          document_role TEXT, primary_slot INTEGER, display_name TEXT, media_type TEXT,
          artifact_ref_json TEXT, content_sha256 TEXT, portability TEXT,
          connector_device_id TEXT, sort_order INTEGER, source_kind TEXT,
          source_identity_hash TEXT, status TEXT, row_version INTEGER, removed_at TEXT,
          UNIQUE(workspace_gid,source_identity_hash), UNIQUE(workspace_gid,primary_slot));
        CREATE TABLE workmanship_sim_materialization_verifications (
          workspace_gid TEXT, state TEXT, updated_at TEXT);
        CREATE TABLE workmanship_sim_workspace_idempotency (
          workspace_gid TEXT, idempotency_key TEXT, request_hash TEXT, response_json TEXT, expires_at TEXT,
          PRIMARY KEY(workspace_gid,idempotency_key));
        CREATE TABLE workmanship_sim_workspace_hierarchies (
          gid TEXT PRIMARY KEY, workspace_gid TEXT, tenant_gid TEXT, owner_gid TEXT, name TEXT,
          projection_identity TEXT, source_refs_json TEXT, status TEXT, sort_order INTEGER,
          row_version INTEGER, removed_at TEXT, updated_at TEXT);
        CREATE TABLE workmanship_sim_workspace_nodes (
          gid TEXT PRIMARY KEY, workspace_gid TEXT, tenant_gid TEXT, owner_gid TEXT, hierarchy_gid TEXT,
          parent_gid TEXT, node_type TEXT, name TEXT, sort_order INTEGER, source_bop_node_gid TEXT,
          row_version INTEGER, removed_at TEXT);
        """)

    class Cursor:
        def __init__(self, db): self.db = db
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def execute(self, sql, params=()):
            sql = sql.replace("%s", "?").replace(" FOR UPDATE", "").replace("NOW(6)", "CURRENT_TIMESTAMP")
            sql = sql.replace("DATE_ADD(CURRENT_TIMESTAMP,INTERVAL 24 HOUR)", "datetime(CURRENT_TIMESTAMP,'+24 hours')")
            if " ON DUPLICATE KEY UPDATE " in sql:
                sql = sql.split(" ON DUPLICATE KEY UPDATE ")[0] + " ON CONFLICT DO NOTHING"
            self.value = self.db.execute(sql, params)
        def executemany(self, sql, params):
            sql = sql.replace("%s", "?").replace(" FOR UPDATE", "").replace("NOW(6)", "CURRENT_TIMESTAMP")
            self.value = self.db.executemany(sql, params)
        def fetchone(self):
            row = self.value.fetchone()
            return dict(row) if row else None
        def fetchall(self): return [dict(row) for row in self.value.fetchall()]
        @property
        def rowcount(self): return self.value.rowcount

    class Connection:
        def __init__(self, db): self.db = db
        def cursor(self): return Cursor(self.db)

    @contextmanager
    def connect():
        db = sqlite3.connect(path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            db.execute("BEGIN IMMEDIATE")
            yield Connection(db)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    monkeypatch.setattr(module, "get_simulation_conn", connect)
    monkeypatch.setattr(module, "next_gid", itertools.count(100).__next__)
    return path


def adopt(**overrides):
    request = dict(tenant_gid="20", actor_gid="30", connector_device_id="device-A",
                   document_session="process-incarnation/document-A", name="Live model",
                   document_display_name="W10-ENG00001/00;1-工程分支(Top Engineering) (视图)",
                   idempotency_key="request-A")
    request.update(overrides)
    return module.WorkspaceRepository().adopt_live_document(**request)


def lookup(**overrides):
    request = dict(tenant_gid="20", actor_gid="30", connector_device_id="device-A",
                   document_session="process-incarnation/document-A")
    request.update(overrides)
    return module.WorkspaceRepository().find_live_document_binding(**request)


def count(database, table):
    with sqlite3.connect(database) as db:
        return db.execute("SELECT COUNT(*) FROM workmanship_sim_" + table).fetchone()[0]


def test_adopt_reuse_and_durable_replay(database):
    first = adopt()
    assert first["state"] == "importing"
    assert first["created"] is True
    assert adopt() == first
    reused = adopt(idempotency_key="request-B", name="renamed window")
    assert reused["workspace_gid"] == first["workspace_gid"]
    assert reused["created"] is False
    assert lookup()["workspace_gid"] == first["workspace_gid"]
    assert first["model_document_gid"]
    for table in ("workspaces", "workspace_versions", "workspace_heads", "live_document_bindings"):
        assert count(database, table) == 1
    assert count(database, "vm_documents") == 1
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT document_role,display_name,media_type,source_kind,portability,artifact_ref_json,content_sha256 FROM workmanship_sim_vm_documents").fetchone() == (
            "primary", "W10-ENG00001/00;1-工程分支(Top Engineering) (视图)",
            "application/vnd.siemens.teamcenter.visualization-document", "live_document", "device_bound", None, "")
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT status,visibility,primary_project_gid FROM workmanship_sim_workspaces").fetchone() == ("draft", "private", None)


def test_adopted_live_document_is_immediately_searchable_as_primary_model(database):
    created = adopt()

    result = module.WorkspaceRepository().search_model_documents(
        workspace_gid=created["workspace_gid"], tenant_gid="20", actor_gid="30"
    )

    assert result == {"items": [{
        "document_gid": created["model_document_gid"],
        "workspace_gid": created["workspace_gid"],
        "role": "primary",
        "display_name": "W10-ENG00001/00;1-工程分支(Top Engineering) (视图)",
        "media_type": "application/vnd.siemens.teamcenter.visualization-document",
        "source_kind": "live_document",
        "source_identity_hash": "sha256:" + hashlib.sha256(
            json.dumps(["device-A", "process-incarnation/document-A"],
                       ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "content_sha256": None,
        "portability": "device_bound",
        "connector_device_id": "device-A",
        "sort_order": 0,
        "row_version": 1,
        "artifact_ref": None,
    }]}


@pytest.mark.parametrize("changed", [{"name": "other"}, {"document_session": "new"}, {"connector_device_id": "new"}])
def test_idempotency_payload_conflict(database, changed):
    adopt()
    with pytest.raises(module.WorkspaceRepositoryError, match="idempotency_conflict"):
        adopt(**changed)
    assert count(database, "workspaces") == 1


@pytest.mark.parametrize("scope", [{"actor_gid": "31"}, {"tenant_gid": "21"}, {"connector_device_id": "device-B"}, {"document_session": "other-incarnation"}])
def test_lookup_does_not_leak_other_scope(database, scope):
    first = adopt()
    assert lookup(**scope) is None
    second = adopt(idempotency_key="request-B", **scope)
    assert second["workspace_gid"] != first["workspace_gid"]


@pytest.mark.parametrize("damage", [
    "UPDATE workmanship_sim_workspaces SET removed_at='removed'",
    "UPDATE workmanship_sim_workspaces SET owner_gid='31'",
    "UPDATE workmanship_sim_live_document_bindings SET state='stale'",
    "DELETE FROM workmanship_sim_workspace_heads",
    "UPDATE workmanship_sim_workspace_versions SET removed_at='removed'",
])
def test_stale_binding_refuses_replay_and_new_adoption(database, damage):
    adopt()
    with sqlite3.connect(database) as db: db.execute(damage)
    for key in ("request-A", "request-B"):
        with pytest.raises(module.WorkspaceRepositoryError, match="live_document_binding_stale"):
            adopt(idempotency_key=key)
    with pytest.raises(module.WorkspaceRepositoryError, match="live_document_binding_stale"):
        lookup()
    assert count(database, "workspaces") == 1


def test_failure_rolls_back_workspace_version_head_binding_and_request(database):
    with sqlite3.connect(database) as db:
        db.execute("CREATE TRIGGER fail_head BEFORE INSERT ON workmanship_sim_workspace_heads BEGIN SELECT RAISE(ABORT, 'injected failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match="injected failure"):
        adopt()
    for table in ("workspaces", "workspace_versions", "workspace_heads", "live_document_bindings", "live_document_adoptions", "vm_documents"):
        assert count(database, table) == 0
    with sqlite3.connect(database) as db: db.execute("DROP TRIGGER fail_head")
    assert adopt()["created"] is True


@pytest.mark.parametrize("keys", [("same", "same"), ("first", "second")])
def test_two_concurrent_same_session_requests_create_once(database, keys):
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda key: adopt(idempotency_key=key), keys))
    assert results[0]["workspace_gid"] == results[1]["workspace_gid"]
    assert count(database, "workspaces") == 1


def test_ordinary_workspace_create_compatibility(database):
    result = module.WorkspaceRepository().create(name="Regular", review_type="node_review",
        version_label="V2", status="draft", visibility="private", project_gids=["50"],
        primary_project_gid="50", tenant_gid="20", owner_gid="30")
    assert result["name"] == "Regular"
    assert result["project_gids"] == ["50"]
    assert count(database, "workspace_projects") == 1
    assert count(database, "live_document_bindings") == 0


def test_signed_inventory_page_populates_left_hierarchy_without_deleting_or_reloading(database):
    created = adopt()
    page = {"document_session": "process-incarnation/document-A", "start_index": 0,
        "next_index": None, "total_hierarchies": 1, "hierarchies": [{
            "native_index": 1, "name": "AI00_RUNTIME_PROBE", "snapshot_hash": "sha256:" + "a" * 64,
            "complete": True, "nodes": [
                {"node_key": "root", "parent_key": None, "child_order": 0, "name": "AI00_RUNTIME_PROBE"},
                {"node_key": "lamp", "parent_key": "root", "child_order": 0, "name": "LAU-53010242/03;1-后背门灯总成"},
            ]}]}
    result = module.WorkspaceRepository().apply_live_hierarchy_inventory(
        workspace_gid=created["workspace_gid"], tenant_gid="20", actor_gid="30",
        connector_device_id="device-A", document_session="process-incarnation/document-A",
        inventory_operation_id="inventory-1", page=page, idempotency_key="inventory-page-0")
    assert result["complete"] is True
    assert result["imported_hierarchy_count"] == 1
    assert count(database, "workspace_hierarchies") == 1
    assert count(database, "workspace_nodes") == 2
    assert module.WorkspaceRepository().apply_live_hierarchy_inventory(
        workspace_gid=created["workspace_gid"], tenant_gid="20", actor_gid="30",
        connector_device_id="device-A", document_session="process-incarnation/document-A",
        inventory_operation_id="inventory-1", page=page, idempotency_key="inventory-page-0") == result
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT state FROM workmanship_sim_live_document_bindings").fetchone()[0] == "bound"
