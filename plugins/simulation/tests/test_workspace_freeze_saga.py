import hashlib
import json

import pytest

from plugins.simulation.simulation_backend.application.workspace_freeze import (
    FreezeConflict,
    WorkspaceFreezeService,
)


class MemoryRepository:
    def __init__(self):
        self.row = {
            "workspace_gid": "10",
            "version_gid": "11",
            "row_version": 4,
            "version_status": "draft",
            "nodes": [{"node_gid": "20", "name": "工序A"}],
            "bindings": [],
        }
        self.completed = None
        self.fail_complete = False
        self.orphans = []
        self.unavailable = []

    def load_freeze_source(self, **scope):
        assert scope == {"workspace_gid": "10", "tenant_gid": "1", "owner_gid": "2"}
        return dict(self.row)

    def complete_freeze(self, **values):
        if self.fail_complete:
            raise RuntimeError("db_down")
        self.completed = values
        return {"workspace_gid": "10", "version_gid": "11", "status": "frozen", **values}

    def record_orphan(self, **values):
        self.orphans.append(values)

    def record_unavailable(self, **values):
        self.unavailable.append(values)


class MemoryArtifactPort:
    def __init__(self):
        self.calls = []

    def create(self, content, media_type, context):
        self.calls.append((content, media_type, context))
        return {
            "artifact_id": "artifact_1",
            "media_type": media_type,
            "sha256": hashlib.sha256(content).hexdigest(),
            "byte_size": len(content),
        }


def _service(repository=None, artifact=None):
    return WorkspaceFreezeService(repository or MemoryRepository(), artifact or MemoryArtifactPort())


def test_freeze_pins_canonical_manifest_and_is_replay_safe():
    repository, artifacts = MemoryRepository(), MemoryArtifactPort()
    service = _service(repository, artifacts)
    first = service.freeze(
        workspace_gid="10", tenant_gid="1", owner_gid="2", expected_row_version=4,
        idempotency_key="freeze-1", algorithms={"identity": "v1", "parser": "v1"}, context=object(),
    )
    second = service.freeze(
        workspace_gid="10", tenant_gid="1", owner_gid="2", expected_row_version=4,
        idempotency_key="freeze-1", algorithms={"identity": "v1", "parser": "v1"}, context=object(),
    )
    assert first == second
    assert len(artifacts.calls) == 1
    manifest = json.loads(artifacts.calls[0][0])
    assert manifest["workspace_gid"] == "10"
    assert manifest["algorithms"] == {"identity": "v1", "parser": "v1"}
    assert repository.completed["content_hash"].startswith("sha256:")


def test_freeze_rejects_stale_or_non_draft_source_before_artifact_write():
    repository, artifacts = MemoryRepository(), MemoryArtifactPort()
    service = _service(repository, artifacts)
    with pytest.raises(FreezeConflict, match="version_conflict"):
        service.freeze(workspace_gid="10", tenant_gid="1", owner_gid="2", expected_row_version=3,
                       idempotency_key="x", algorithms={}, context=object())
    repository.row["version_status"] = "frozen"
    with pytest.raises(FreezeConflict, match="workspace_version_not_draft"):
        service.freeze(workspace_gid="10", tenant_gid="1", owner_gid="2", expected_row_version=4,
                       idempotency_key="y", algorithms={}, context=object())
    assert artifacts.calls == []


def test_finalized_artifact_is_recorded_for_reconciliation_when_db_commit_fails():
    repository = MemoryRepository()
    repository.fail_complete = True
    with pytest.raises(RuntimeError, match="db_down"):
        _service(repository).freeze(
            workspace_gid="10", tenant_gid="1", owner_gid="2", expected_row_version=4,
            idempotency_key="freeze-1", algorithms={}, context=object(),
        )
    assert repository.orphans[0]["status"] == "orphaned"
    assert repository.orphans[0]["artifact_ref"]["artifact_id"] == "artifact_1"


def test_artifact_unavailability_is_recorded_without_freezing_the_draft():
    class UnavailableArtifact:
        def create(self, *_args):
            raise RuntimeError("ois_down")

    repository = MemoryRepository()
    with pytest.raises(RuntimeError, match="ois_down"):
        _service(repository, UnavailableArtifact()).freeze(
            workspace_gid="10", tenant_gid="1", owner_gid="2", expected_row_version=4,
            idempotency_key="freeze-2", algorithms={}, context=object(),
        )
    assert repository.completed is None
    assert repository.unavailable[0]["status"] == "unavailable"
