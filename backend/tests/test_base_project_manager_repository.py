from __future__ import annotations

import pytest

from backend.base.project_responsibility import (
    ProjectManagerError,
    ProjectManagerService,
)


class MemoryProjectManagers:
    def __init__(self) -> None:
        self.heads: dict[tuple[str, str], dict] = {}
        self.assignments: dict[tuple[str, str], list[str]] = {}
        self.legacy: dict[str, list[str]] = {}
        self.operations: dict[tuple[str, str, str], dict] = {}
        self.users = {
            "u1": {"gid": "u1", "name": "甲", "avatar_url": "a", "is_active": True},
            "u2": {"gid": "u2", "name": "乙", "avatar_url": "b", "is_active": True},
            "off": {"gid": "off", "name": "停用", "avatar_url": "", "is_active": False},
        }

    def read(self, tenant_gid: str, project_gid: str) -> dict:
        key = tenant_gid, project_gid
        head = self.heads.get(key)
        if head is None:
            return {"revision": 0, "managed": False, "user_gids": self.legacy.get(project_gid, [])[:1]}
        return {**head, "user_gids": list(self.assignments.get(key, []))}

    def active_users(self, user_gids: list[str]) -> dict[str, dict]:
        return {gid: self.users[gid] for gid in user_gids if gid in self.users and self.users[gid]["is_active"]}

    def replace(self, *, tenant_gid: str, project_gid: str, user_gids: list[str], expected_revision: int,
                actor_gid: str, idempotency_key: str, command_digest: str) -> dict:
        op_key = tenant_gid, actor_gid, idempotency_key
        previous = self.operations.get(op_key)
        if previous:
            if previous["digest"] != command_digest:
                raise ProjectManagerError("idempotency_conflict", "changed payload")
            return previous["result"]
        current = self.read(tenant_gid, project_gid)
        if current["revision"] != expected_revision:
            raise ProjectManagerError("version_conflict", "changed")
        key = tenant_gid, project_gid
        self.heads[key] = {"revision": expected_revision + 1, "managed": True}
        self.assignments[key] = list(user_gids)
        result = self.read(tenant_gid, project_gid)
        self.operations[op_key] = {"digest": command_digest, "result": result}
        return result


def test_unmanaged_falls_back_once_then_clear_stays_managed() -> None:
    repo = MemoryProjectManagers()
    repo.legacy["p1"] = ["u1"]
    service = ProjectManagerService(repo)
    assert [item["gid"] for item in service.read("t1", "p1")["managers"]] == ["u1"]

    changed = service.replace(
        tenant_gid="t1", actor_gid="admin", project_gid="p1", user_gids=[],
        expected_revision=0, idempotency_key="k1",
    )
    assert changed == {"project_gid": "p1", "revision": 1, "managed": True, "managers": []}
    assert service.read("t1", "p1")["managers"] == []


def test_replace_supports_multiple_managers_and_exact_idempotent_replay() -> None:
    repo = MemoryProjectManagers()
    service = ProjectManagerService(repo)
    command = dict(
        tenant_gid="t1", actor_gid="admin", project_gid="p1",
        user_gids=["u2", "u1", "u2"], expected_revision=0, idempotency_key="k1",
    )
    first = service.replace(**command)
    second = service.replace(**command)
    assert first == second
    assert [item["gid"] for item in first["managers"]] == ["u1", "u2"]

    with pytest.raises(ProjectManagerError) as exc:
        service.replace(**{**command, "user_gids": ["u1"]})
    assert exc.value.code == "idempotency_conflict"


def test_replace_rejects_inactive_unknown_too_many_and_stale_revision() -> None:
    repo = MemoryProjectManagers()
    service = ProjectManagerService(repo)
    base = dict(tenant_gid="t1", actor_gid="admin", project_gid="p1", expected_revision=0)
    for gids in (["off"], ["missing"], [f"u{i}" for i in range(51)]):
        with pytest.raises(ProjectManagerError):
            service.replace(**base, user_gids=gids, idempotency_key=str(len(gids)))
    service.replace(**base, user_gids=["u1"], idempotency_key="ok")
    with pytest.raises(ProjectManagerError) as exc:
        service.replace(**base, user_gids=["u2"], idempotency_key="stale")
    assert exc.value.code == "version_conflict"
