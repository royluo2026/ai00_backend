from types import SimpleNamespace

import pytest

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext
from plugins.simulation.simulation_backend.capabilities.vm_checkpoints import VmCheckpointProvider


HASH = "sha256:" + "a" * 64


def context(*, user="11", team="22", roles=()):
    return CapabilityContext(user_gid=user, team_gid=team, active_roles=roles)


class Repository:
    def __init__(self):
        self.rows = {}
        self.requests = {"request-1": {"status": "completed", "snapshot_hash": HASH}}
        self.technical_hashes = {HASH}

    def create_from_request(self, **values):
        request = self.requests.get(values["snapshot_request_id"])
        if not request:
            raise RuntimeError("document_snapshot_not_found")
        if request["status"] != "completed":
            raise RuntimeError("document_snapshot_not_completed")
        if request["snapshot_hash"] != values["snapshot_hash"]:
            raise RuntimeError("snapshot_hash_mismatch")
        if values["snapshot_hash"] not in self.technical_hashes:
            raise RuntimeError("vm_snapshot_projection_required")
        key = (values["workspace_gid"], values["created_by"], values["idempotency_key"])
        digest = (values["snapshot_request_id"], values["snapshot_hash"], values["scope"], values["name"], values["note"])
        if key in self.rows:
            if self.rows[key]["digest"] != digest:
                raise RuntimeError("idempotency_conflict")
            return self.rows[key]["data"]
        data = {"checkpoint_gid": str(len(self.rows) + 100), "snapshot_gid": "90", "workspace_gid": values["workspace_gid"],
                "scope": values["scope"], "name": values["name"], "note": values["note"],
                "created_by": values["created_by"], "row_version": 1, "archived_at": None}
        self.rows[key] = {"digest": digest, "data": data}
        return data

    def search(self, **values):
        return {"items": [row["data"] for row in self.rows.values()], "next_cursor": None}

    def archive(self, **values):
        row = next((item["data"] for item in self.rows.values() if item["data"]["checkpoint_gid"] == values["checkpoint_gid"]), None)
        if not row:
            raise RuntimeError("vm_checkpoint_not_found")
        row = {**row, "archived_at": "2026-09-10T00:00:00Z", "row_version": row["row_version"] + 1}
        return row


class Workspaces:
    def get(self, workspace_gid, **scope):
        if workspace_gid != "33":
            return None
        return {"workspace_gid": "33", "owner_gid": "11", "primary_project_gid": "44", "visibility": "shared"}


def provider(repository=None, *, may_share=lambda *_: False):
    return VmCheckpointProvider(repository or Repository(), Workspaces(), may_create_shared=may_share)


def payload(**changes):
    return {"snapshot_request_id": "request-1", "snapshot_hash": HASH, "workspace_gid": "33",
            "scope": "personal", "name": "睡前快照", "note": "", "idempotency_key": "once", **changes}


def test_reader_can_create_personal_checkpoint_and_retry_is_idempotent():
    target = provider()
    first = target.create(payload(), context())
    second = target.create(payload(), context())
    assert first.data == second.data
    assert first.evidence[0].digest == HASH


@pytest.mark.parametrize("change,code", [
    ({"snapshot_request_id": "missing"}, "document_snapshot_not_found"),
    ({"snapshot_hash": "sha256:" + "b" * 64}, "snapshot_hash_mismatch"),
])
def test_creation_re_reads_completed_request_and_exact_hash(change, code):
    with pytest.raises(CapabilityBusinessError) as error:
        provider().create(payload(**change), context())
    assert error.value.code == code


def test_creation_requires_the_authoritative_technical_projection():
    repository = Repository()
    repository.technical_hashes.clear()
    with pytest.raises(CapabilityBusinessError) as error:
        provider(repository).create(payload(), context())
    assert error.value.code == "vm_snapshot_projection_required"


def test_shared_baseline_is_limited_to_owner_project_manager_or_super_admin():
    target = provider(may_share=lambda workspace, ctx: "super_admin" in ctx.active_roles)
    with pytest.raises(CapabilityBusinessError) as error:
        target.create(payload(scope="shared_baseline"), context(user="12"))
    assert error.value.code == "vm_checkpoint_shared_forbidden"
    assert target.create(payload(scope="shared_baseline"), context(user="12", roles=("super_admin",))).data["scope"] == "shared_baseline"


def test_search_is_bounded_and_archive_never_hard_deletes():
    target = provider()
    created = target.create(payload(), context()).data
    assert target.search({"workspace_gid": "33", "page_size": 20}, context()).data["items"]
    archived = target.archive({"checkpoint_gid": created["checkpoint_gid"], "workspace_gid": "33",
                               "expected_row_version": 1, "idempotency_key": "archive-once"}, context()).data
    assert archived["archived_at"] and archived["row_version"] == 2

