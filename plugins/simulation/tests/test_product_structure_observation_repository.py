from contextlib import contextmanager
import itertools
import sqlite3

import pytest

from plugins.simulation.simulation_backend.data.product_structure_observation_repository import (
    ProductStructureObservationRepository,
    ProductStructureRepositoryError,
)
from plugins.simulation.simulation_backend.domain.product_structure_observation import (
    GeometryReference, ObservationPage, OccurrenceRecord, SourceSelector,
)


@pytest.fixture
def repository(tmp_path):
    path = tmp_path / "observations.db"
    with sqlite3.connect(path) as db:
        db.executescript("""
        CREATE TABLE workmanship_sim_workspaces
          (gid TEXT PRIMARY KEY, tenant_gid TEXT, owner_gid TEXT, row_version INTEGER, cache_revision_hash TEXT, removed_at TEXT);
        INSERT INTO workmanship_sim_workspaces VALUES ('10','20','30',4,'sha256:0000000000000000000000000000000000000000000000000000000000000000',NULL);
        CREATE TABLE workmanship_sim_vm_documents (
          gid TEXT PRIMARY KEY, workspace_gid TEXT, tenant_gid TEXT, owner_gid TEXT, document_role TEXT,
          primary_slot INTEGER, display_name TEXT, media_type TEXT, artifact_ref_json TEXT, content_sha256 TEXT,
          portability TEXT, connector_device_id TEXT, sort_order INTEGER, source_kind TEXT, source_identity_hash TEXT,
          status TEXT, row_version INTEGER, removed_at TEXT, UNIQUE(workspace_gid,source_identity_hash));
        CREATE TABLE workmanship_sim_online_model_sources (
          gid TEXT PRIMARY KEY, tenant_gid TEXT, owner_gid TEXT, workspace_gid TEXT, document_gid TEXT,
          insertion_instance_id TEXT, source_identity_hash TEXT, endpoint_id TEXT, object_uid TEXT,
          item_revision_uid TEXT, bom_view_uid TEXT, revision_rule TEXT, configuration_date TEXT,
          display_name TEXT, source_selector_json TEXT, inserted_at TEXT DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(workspace_gid,source_identity_hash,insertion_instance_id));
        CREATE TABLE workmanship_sim_product_structure_observations (
          gid TEXT PRIMARY KEY, tenant_gid TEXT, workspace_gid TEXT, source_gid TEXT,
          observation_id TEXT, captured_at TEXT, node_count INTEGER, page_count INTEGER,
          complete INTEGER, manifest_hash TEXT, schema_version INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(tenant_gid,observation_id));
        CREATE TABLE workmanship_sim_product_structure_chunks (
          observation_gid TEXT, page_index INTEGER, cursor_value INTEGER, node_count INTEGER,
          payload_json TEXT, page_hash TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY(observation_gid,page_index));
        """)

    class Cursor:
        def __init__(self, db): self.db = db
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def execute(self, sql, params=()):
            self.value = self.db.execute(sql.replace("%s", "?").replace(" FOR UPDATE", ""), params)
        def fetchone(self):
            row = self.value.fetchone()
            return dict(row) if row else None
        def fetchall(self): return [dict(row) for row in self.value.fetchall()]
        @property
        def rowcount(self): return self.value.rowcount

    @contextmanager
    def connect():
        db = sqlite3.connect(path)
        db.row_factory = sqlite3.Row
        try:
            db.execute("BEGIN IMMEDIATE")
            yield type("Connection", (), {"cursor": lambda self: Cursor(db)})()
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    return ProductStructureObservationRepository(connect, itertools.count(100).__next__)


def selector(date="2026-09-16T00:00:00Z"):
    return SourceSelector("tc-test", "object-A", "revision-A", "view-A", "Latest Working", date)


def nodes():
    identity = (1.0,0.0,0.0,0.0,0.0,1.0,0.0,0.0,0.0,0.0,1.0,0.0,0.0,0.0,0.0,1.0)
    return (
        OccurrenceRecord("root",None,0,0,"Root","item","A","rev","01","Assembly","u","g",identity,None,()),
        OccurrenceRecord("left","root",1,0,"Same","part","P","same","01","Part","u","g",identity,None,(GeometryReference("d","f","a.jt"),)),
        OccurrenceRecord("right","root",1,1,"Same","part","P","same","01","Part","u","g",identity,None,(GeometryReference("d","f","a.jt"),)),
    )


def test_repeated_same_source_creates_distinct_insertion_instances(repository):
    first = repository.register_online_source(workspace_gid="10", selector=selector(), display_name="Same",
        expected_workspace_version=4, actor_gid="30", tenant_gid="20", insertion_instance_id="insert-a")
    replay = repository.register_online_source(workspace_gid="10", selector=selector(), display_name="Renamed",
        expected_workspace_version=4, actor_gid="30", tenant_gid="20", insertion_instance_id="insert-a")
    second = repository.register_online_source(workspace_gid="10", selector=selector(), display_name="Same",
        expected_workspace_version=5, actor_gid="30", tenant_gid="20", insertion_instance_id="insert-b")
    assert first == replay
    assert first["source_gid"] != second["source_gid"]


def test_pages_are_immutable_replayable_and_publish_only_when_complete(repository):
    source = repository.register_online_source(workspace_gid="10", selector=selector(), display_name="A",
        expected_workspace_version=4, actor_gid="30", tenant_gid="20", insertion_instance_id="insert-a")
    manifest = repository.begin_observation(source_gid=source["source_gid"], workspace_gid="10",
        tenant_gid="20", actor_gid="30", observation_id="tcobs:" + "a" * 64,
        captured_at="2026-09-16T01:00:00Z", node_count=3, page_count=2)
    first = ObservationPage(0, 2, nodes()[:2])
    scope = {"tenant_gid": "20", "actor_gid": "30"}
    assert repository.append_observation_page(manifest["observation_gid"], 0, first, **scope)["replayed"] is False
    assert repository.append_observation_page(manifest["observation_gid"], 0, first, **scope)["replayed"] is True
    with pytest.raises(ProductStructureRepositoryError, match="observation_page_conflict"):
        repository.append_observation_page(manifest["observation_gid"], 0, ObservationPage(0, 1, nodes()[:1]), **scope)
    with pytest.raises(ProductStructureRepositoryError, match="observation_incomplete"):
        repository.publish_observation(manifest["observation_gid"], **scope)
    repository.append_observation_page(manifest["observation_gid"], 1, ObservationPage(2, None, nodes()[2:]), **scope)
    published = repository.publish_observation(manifest["observation_gid"], **scope)
    assert published["complete"] is True
    assert [item["occurrence_id"] for item in repository.get_observation_page(
        observation_id=manifest["observation_id"], tenant_gid="20", actor_gid="30", cursor=0, page_size=2)["nodes"]] == ["root", "left"]
