"""Craft BOP Repository persistence port and deterministic in-memory reference.

The in-memory implementation is used by contract tests. The MySQL adapter is
added behind the same method surface before product routing is enabled.
"""
from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Callable, Iterator
from typing import Any, Protocol

from backend.platform_sdk.ids import next_gid


class BopRepositoryError(RuntimeError):
    pass


class BopRepositoryStore(Protocol):
    def create_repository(self, **kwargs: Any) -> dict[str, Any]: ...
    def create_personal_space(self, **kwargs: Any) -> dict[str, Any]: ...
    def get_space(self, space_gid: str, **kwargs: Any) -> dict[str, Any]: ...
    def save_space_version(self, **kwargs: Any) -> dict[str, Any]: ...
    def freeze_team_space(self, **kwargs: Any) -> dict[str, Any]: ...
    def set_baseline(self, **kwargs: Any) -> dict[str, Any]: ...
    def delete_personal_space(self, **kwargs: Any) -> dict[str, Any]: ...


def _gid(value: object, field: str) -> str:
    text = str(value or "")
    if not text.isdecimal() or int(text) <= 0:
        raise BopRepositoryError(f"{field}_invalid")
    return text


def _key(value: object) -> str:
    text = str(value or "")
    if not text or len(text) > 191:
        raise BopRepositoryError("idempotency_key_invalid")
    return text


def _hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


class MemoryBopRepositoryStore:
    """Executable reference for repository invariants and Provider tests."""

    def __init__(self, gid_source: Callable[[], int] = next_gid) -> None:
        self._next_gid = lambda: str(gid_source())
        self._repositories: dict[str, dict[str, Any]] = {}
        self._spaces: dict[str, dict[str, Any]] = {}
        self._heads: dict[str, dict[str, Any]] = {}
        self._versions: dict[str, dict[str, Any]] = {}
        self._operations: dict[tuple[str, str, str], tuple[str, dict[str, Any]]] = {}

    def _idempotent(
        self, operation: str, tenant_gid: str, idempotency_key: str,
        payload: dict[str, Any], effect: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        key = (tenant_gid, operation, _key(idempotency_key))
        digest = _hash(payload)
        previous = self._operations.get(key)
        if previous:
            if previous[0] != digest:
                raise BopRepositoryError("idempotency_conflict")
            return copy.deepcopy(previous[1])
        result = effect()
        self._operations[key] = (digest, copy.deepcopy(result))
        return copy.deepcopy(result)

    def create_repository(
        self, *, project_gid: str, tenant_gid: str, actor_gid: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        project_gid = _gid(project_gid, "project_gid")
        tenant_gid = _gid(tenant_gid, "tenant_gid")
        actor_gid = _gid(actor_gid, "actor_gid")
        payload = {"project_gid": project_gid, "actor_gid": actor_gid}

        def effect() -> dict[str, Any]:
            if any(
                row["tenant_gid"] == tenant_gid and row["project_gid"] == project_gid
                and row["deleted_at"] is None for row in self._repositories.values()
            ):
                raise BopRepositoryError("target_repository_exists")
            repository_gid, space_gid, head_gid = self._next_gid(), self._next_gid(), self._next_gid()
            self._repositories[repository_gid] = {
                "repository_gid": repository_gid, "tenant_gid": tenant_gid,
                "project_gid": project_gid, "baseline_version_gid": None,
                "lifecycle_status": "active", "row_version": 1, "deleted_at": None,
            }
            self._spaces[space_gid] = {
                "space_gid": space_gid, "repository_gid": repository_gid,
                "tenant_gid": tenant_gid, "space_kind": "team", "owner_user_gid": None,
                "fork_base_version_gid": None, "frozen_version_gid": None,
                "row_version": 1, "deleted_at": None,
            }
            self._heads[space_gid] = {
                "head_gid": head_gid, "space_gid": space_gid, "row_version": 1,
                "content_hash": _hash({"members": []}), "members": [],
            }
            return {**copy.deepcopy(self._repositories[repository_gid]),
                    "team_space_gid": space_gid, "head_gid": head_gid}

        return self._idempotent("repository.create", tenant_gid, idempotency_key, payload, effect)

    def create_personal_space(
        self, *, repository_gid: str, tenant_gid: str, owner_gid: str,
        actor_gid: str, idempotency_key: str,
    ) -> dict[str, Any]:
        repository_gid = _gid(repository_gid, "repository_gid")
        tenant_gid, owner_gid = _gid(tenant_gid, "tenant_gid"), _gid(owner_gid, "owner_gid")
        actor_gid = _gid(actor_gid, "actor_gid")
        payload = {"repository_gid": repository_gid, "owner_gid": owner_gid, "actor_gid": actor_gid}

        def effect() -> dict[str, Any]:
            repository = self._repositories.get(repository_gid)
            if not repository or repository["tenant_gid"] != tenant_gid or repository["deleted_at"]:
                raise BopRepositoryError("repository_not_found")
            if any(row["repository_gid"] == repository_gid and row["space_kind"] == "managed_personal"
                   and row["owner_user_gid"] == owner_gid and row["deleted_at"] is None
                   for row in self._spaces.values()):
                raise BopRepositoryError("managed_personal_space_exists")
            space_gid, head_gid = self._next_gid(), self._next_gid()
            self._spaces[space_gid] = {
                "space_gid": space_gid, "repository_gid": repository_gid,
                "tenant_gid": tenant_gid, "space_kind": "managed_personal",
                "owner_user_gid": owner_gid, "fork_base_version_gid": None,
                "frozen_version_gid": None, "row_version": 1, "deleted_at": None,
            }
            self._heads[space_gid] = {
                "head_gid": head_gid, "space_gid": space_gid, "row_version": 1,
                "content_hash": _hash({"members": []}), "members": [],
            }
            return {"space_gid": space_gid, "head_gid": head_gid, "row_version": 1}

        return self._idempotent("personal.create", tenant_gid, idempotency_key, payload, effect)

    def get_space(self, space_gid: str, *, tenant_gid: str, actor_gid: str) -> dict[str, Any]:
        space_gid, tenant_gid = _gid(space_gid, "space_gid"), _gid(tenant_gid, "tenant_gid")
        _gid(actor_gid, "actor_gid")
        space = self._spaces.get(space_gid)
        if not space or space["tenant_gid"] != tenant_gid or space["deleted_at"]:
            raise BopRepositoryError("space_not_found")
        return {**copy.deepcopy(space), "head": copy.deepcopy(self._heads[space_gid])}

    def save_space_version(
        self, *, space_gid: str, tenant_gid: str, actor_gid: str,
        expected_head_version: int, version_kind: str, source_refs: list[Any],
        algorithm_versions: dict[str, Any], idempotency_key: str,
    ) -> dict[str, Any]:
        space = self.get_space(space_gid, tenant_gid=tenant_gid, actor_gid=actor_gid)
        if version_kind not in {"saved", "frozen", "fork_base", "proposal_base"}:
            raise BopRepositoryError("version_kind_invalid")
        payload = {"space_gid": space_gid, "expected_head_version": expected_head_version,
                   "version_kind": version_kind, "source_refs": source_refs,
                   "algorithm_versions": algorithm_versions}

        def effect() -> dict[str, Any]:
            head = self._heads[space_gid]
            if head["row_version"] != expected_head_version:
                raise BopRepositoryError("resource_version_conflict")
            version_gid = self._next_gid()
            manifest_hash = _hash({"head": head["content_hash"], "source_refs": source_refs,
                                   "algorithm_versions": algorithm_versions})
            self._versions[version_gid] = {
                "version_gid": version_gid, "space_gid": space_gid,
                "repository_gid": space["repository_gid"], "tenant_gid": tenant_gid,
                "version_kind": version_kind, "manifest_hash": manifest_hash,
                "members": copy.deepcopy(head["members"]),
            }
            return copy.deepcopy(self._versions[version_gid])

        return self._idempotent("space_version.save", tenant_gid, idempotency_key, payload, effect)

    def freeze_team_space(
        self, *, space_gid: str, tenant_gid: str, actor_gid: str,
        expected_head_version: int, version_gid: str, idempotency_key: str,
    ) -> dict[str, Any]:
        space = self.get_space(space_gid, tenant_gid=tenant_gid, actor_gid=actor_gid)
        version_gid = _gid(version_gid, "version_gid")
        payload = {"space_gid": space_gid, "expected_head_version": expected_head_version,
                   "version_gid": version_gid}

        def effect() -> dict[str, Any]:
            current = self._spaces[space_gid]
            if current["space_kind"] != "team" or current["row_version"] != expected_head_version:
                raise BopRepositoryError("resource_version_conflict")
            version = self._versions.get(version_gid)
            if not version or version["space_gid"] != space_gid:
                raise BopRepositoryError("space_version_invalid")
            current["frozen_version_gid"] = version_gid
            current["row_version"] += 1
            return {"space_gid": space_gid, "frozen_version_gid": version_gid,
                    "row_version": current["row_version"]}

        return self._idempotent("space.freeze", tenant_gid, idempotency_key, payload, effect)

    def set_baseline(
        self, *, repository_gid: str, tenant_gid: str, actor_gid: str,
        expected_row_version: int, version_gid: str, idempotency_key: str,
    ) -> dict[str, Any]:
        repository_gid, tenant_gid = _gid(repository_gid, "repository_gid"), _gid(tenant_gid, "tenant_gid")
        _gid(actor_gid, "actor_gid"); version_gid = _gid(version_gid, "version_gid")
        payload = {"repository_gid": repository_gid, "expected_row_version": expected_row_version,
                   "version_gid": version_gid}

        def effect() -> dict[str, Any]:
            repository = self._repositories.get(repository_gid)
            version = self._versions.get(version_gid)
            space = self._spaces.get(version["space_gid"]) if version else None
            if not repository or repository["tenant_gid"] != tenant_gid:
                raise BopRepositoryError("repository_not_found")
            if repository["row_version"] != expected_row_version:
                raise BopRepositoryError("resource_version_conflict")
            if not version or not space or space["repository_gid"] != repository_gid or space["space_kind"] != "team":
                raise BopRepositoryError("baseline_version_invalid")
            repository["baseline_version_gid"] = version_gid
            repository["row_version"] += 1
            return copy.deepcopy(repository)

        return self._idempotent("repository.baseline", tenant_gid, idempotency_key, payload, effect)

    def delete_personal_space(
        self, *, space_gid: str, tenant_gid: str, owner_gid: str,
        expected_row_version: int, idempotency_key: str,
    ) -> dict[str, Any]:
        space_gid, tenant_gid = _gid(space_gid, "space_gid"), _gid(tenant_gid, "tenant_gid")
        owner_gid = _gid(owner_gid, "owner_gid")
        payload = {"space_gid": space_gid, "expected_row_version": expected_row_version}

        def effect() -> dict[str, Any]:
            space = self._spaces.get(space_gid)
            if not space or space["tenant_gid"] != tenant_gid or space["space_kind"] != "managed_personal" or space["owner_user_gid"] != owner_gid:
                raise BopRepositoryError("space_not_found")
            if space["row_version"] != expected_row_version:
                raise BopRepositoryError("resource_version_conflict")
            space["deleted_at"] = "logical"
            space["row_version"] += 1
            return {"space_gid": space_gid, "deleted": True, "row_version": space["row_version"]}

        return self._idempotent("personal.delete", tenant_gid, idempotency_key, payload, effect)


__all__ = ["BopRepositoryError", "BopRepositoryStore", "MemoryBopRepositoryStore"]
