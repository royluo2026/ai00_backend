from datetime import UTC, datetime

import pytest

from backend.capability_v2.provider_contracts import CapabilityContext
from plugins.simulation.simulation_backend.application.vm_retention import VmRetentionService
from plugins.simulation.simulation_backend.capabilities.vm_checkpoints import VmCheckpointProvider
from plugins.simulation.simulation_backend.capabilities.vm_diffs import VmDiffProvider
from plugins.simulation.simulation_backend.capabilities.workspaces import WorkspaceProvider
from plugins.simulation.simulation_backend.domain.cache_lease import CacheLeaseError, verify_cache_lease
from plugins.simulation.simulation_backend.domain.vm_identity import VmObservation


NOW = datetime(2026, 9, 10, 10, 0, tzinfo=UTC)
HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64


def observation(revision):
    return VmObservation(
        occurrence_gid="501",
        source_instance_id="vm-node-1",
        session_gid="601",
        kind="part",
        model_number="W10-PART",
        bom_line="10",
        revision=revision,
        catia_occurrence_name="W10-PART.1",
        normalized_transform=("0",),
    )


class WorkspaceRepository:
    def get(self, workspace_gid, **_scope):
        return {
            "workspace_gid": str(workspace_gid),
            "owner_gid": "11",
            "primary_project_gid": "44",
            "row_version": 7,
            "cache_revision_hash": HASH_A,
        }


class VersionRepository:
    def __init__(self):
        self.requests = {
            "capture-a": {"hash": HASH_A, "snapshot_gid": "801", "observations": [observation("A")]},
            "capture-b": {"hash": HASH_B, "snapshot_gid": "802", "observations": [observation("B")]},
        }
        self.checkpoints = {}
        self.reports = {}
        self.items = {}
        self.pruned = []

    def create_from_request(self, *, snapshot_request_id, snapshot_hash, workspace_gid, created_by, scope, name, note, idempotency_key, **_scope):
        source = self.requests[snapshot_request_id]
        assert source["hash"] == snapshot_hash
        key = (workspace_gid, created_by, idempotency_key)
        if key not in self.checkpoints:
            gid = str(901 + len(self.checkpoints))
            self.checkpoints[key] = {
                "checkpoint_gid": gid,
                "snapshot_gid": source["snapshot_gid"],
                "workspace_gid": workspace_gid,
                "scope": scope,
                "name": name,
                "note": note,
                "created_by": created_by,
                "row_version": 1,
                "archived_at": None,
                "observations": source["observations"],
            }
        return {key: value for key, value in self.checkpoints[key].items() if key != "observations"}

    def load_checkpoint_snapshot(self, checkpoint_gid, **_scope):
        row = next((row for row in self.checkpoints.values() if row["checkpoint_gid"] == checkpoint_gid), None)
        return None if row is None else {
            "snapshot_gid": row["snapshot_gid"],
            "workspace_gid": row["workspace_gid"],
            "observations": row["observations"],
        }

    def persist_report(self, *, workspace_gid, before_snapshot_gid, after_snapshot_gid, algorithm_version, report_kind, diff, **_scope):
        key = (before_snapshot_gid, after_snapshot_gid, algorithm_version)
        if key not in self.reports:
            gid = str(1001 + len(self.reports))
            self.reports[key] = {
                "report_gid": gid,
                "workspace_gid": workspace_gid,
                "before_snapshot_gid": before_snapshot_gid,
                "after_snapshot_gid": after_snapshot_gid,
                "algorithm_version": algorithm_version,
                "report_kind": report_kind,
                "status": "completed",
                "summary": diff.summary,
                "row_version": 1,
                "created_at": NOW.isoformat(),
                "archived_at": None,
            }
            self.items[gid] = diff.items
        return self.reports[key]

    def search_items(self, report_gid, *, offset, page_size, **_scope):
        page = self.items[report_gid][offset : offset + page_size]
        return {
            "items": [{"sequence": offset + index + 1, **item.__dict__} for index, item in enumerate(page)],
            "next_cursor": None,
        }

    def list_retention_candidates(self, **_scope):
        return [
            {"snapshot_gid": "801", "captured_at": NOW, "sequence": 1},
            {"snapshot_gid": "802", "captured_at": NOW, "sequence": 2},
        ]

    def protected_snapshot_gids(self, **_scope):
        return {row["snapshot_gid"] for row in self.checkpoints.values()}

    def prune_snapshot_payload(self, snapshot_gid, **_scope):
        self.pruned.append(snapshot_gid)

    def compact_automatic_reports_for_snapshot(self, *_args, **_scope):
        raise AssertionError("manual evidence must not be compacted")


def context():
    return CapabilityContext(user_gid="11", team_gid="22", active_roles=("member",))


def checkpoint(provider, request_id, snapshot_hash):
    return provider.create(
        {
            "snapshot_request_id": request_id,
            "snapshot_hash": snapshot_hash,
            "workspace_gid": "33",
            "scope": "personal",
            "name": request_id,
            "note": "",
            "idempotency_key": request_id,
        },
        context(),
    ).data


def test_exact_checkpoints_flow_into_one_deterministic_diff_and_survive_retention():
    repository = VersionRepository()
    checkpoints = VmCheckpointProvider(repository, WorkspaceRepository())
    before = checkpoint(checkpoints, "capture-a", HASH_A)
    after = checkpoint(checkpoints, "capture-b", HASH_B)

    reports = VmDiffProvider(repository)
    report = reports.generate(
        {
            "before_checkpoint_gid": before["checkpoint_gid"],
            "after_checkpoint_gid": after["checkpoint_gid"],
            "report_kind": "manual",
            "algorithm_version": "vm-diff-v1",
            "idempotency_key": "compare-once",
        },
        context(),
    ).data
    items = reports.search_items({"report_gid": report["report_gid"], "page_size": 200}, context()).data

    assert report["summary"] == {"revision_upgraded": 1}
    assert [item["change_type"] for item in items["items"]] == ["revision_upgraded"]
    assert VmRetentionService(repository, repository, clock=lambda: NOW).run(
        document_gid="701", tenant_gid="22", owner_gid="11"
    )["pruned"] == 0
    assert repository.pruned == []


def test_expired_workspace_lease_cannot_authorize_cached_display(monkeypatch):
    monkeypatch.setenv("AI00_SIMULATION_EXPORT_SIGNING_KEY", "integration-test-key")
    lease = WorkspaceProvider(WorkspaceRepository(), clock=lambda: NOW).cache_lease_get(
        {"workspace_gid": "33", "expires_in_seconds": 60}, context()
    ).data["read_lease"]

    with pytest.raises(CacheLeaseError, match="cache_lease_expired"):
        verify_cache_lease(lease, now_epoch=int(NOW.timestamp()) + 61)
