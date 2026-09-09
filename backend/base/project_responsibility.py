"""Base-owned project responsibility authority.

The managed head is the cut-over marker: before it exists, reads preserve the
legacy single project manager; after the first replace (including an empty
replace), only the managed assignment set is authoritative.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from typing import Any, Iterable

from backend.db.connection import get_conn
from backend.utils.gid import next_gid


class ProjectManagerError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _gids(values: Iterable[str]) -> list[str]:
    result = sorted({str(value).strip() for value in values if str(value).strip()})
    if len(result) > 50:
        raise ProjectManagerError("invalid_input", "项目经理最多 50 人")
    return result


def _digest(value: dict[str, Any]) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class SqlProjectManagerRepository:
    def read(self, tenant_gid: str, project_gid: str) -> dict[str, Any]:
        with get_conn() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT revision,managed FROM workmanship_base_project_manager_heads "
                    "WHERE tenant_gid=%s AND project_gid=%s",
                    (tenant_gid, project_gid),
                )
                head = cursor.fetchone()
                if head:
                    cursor.execute(
                        "SELECT user_gid FROM workmanship_base_project_manager_assignments "
                        "WHERE tenant_gid=%s AND project_gid=%s ORDER BY user_gid",
                        (tenant_gid, project_gid),
                    )
                    return {"revision": int(head["revision"]), "managed": True,
                            "user_gids": [str(row["user_gid"]) for row in cursor.fetchall()]}
                cursor.execute(
                    "SELECT user_gid FROM workmanship_auth_project_members "
                    "WHERE project_gid=%s AND role='project_manager' ORDER BY created_at,gid LIMIT 1",
                    (project_gid,),
                )
                legacy = cursor.fetchone()
                return {"revision": 0, "managed": False,
                        "user_gids": [str(legacy["user_gid"])] if legacy else []}

    def active_users(self, user_gids: list[str]) -> dict[str, dict[str, Any]]:
        if not user_gids:
            return {}
        placeholders = ",".join(["%s"] * len(user_gids))
        with get_conn() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT gid,name,avatar_url,is_active FROM workmanship_auth_users "
                    f"WHERE is_active=1 AND gid IN ({placeholders})", user_gids,
                )
                return {str(row["gid"]): dict(row) for row in cursor.fetchall()}

    def replace(self, *, tenant_gid: str, project_gid: str, user_gids: list[str],
                expected_revision: int, actor_gid: str, idempotency_key: str,
                command_digest: str) -> dict[str, Any]:
        with get_conn() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT command_digest,result_json FROM workmanship_base_project_manager_operations "
                    "WHERE tenant_gid=%s AND actor_gid=%s AND idempotency_key=%s FOR UPDATE",
                    (tenant_gid, actor_gid, idempotency_key),
                )
                operation = cursor.fetchone()
                if operation:
                    if str(operation["command_digest"]) != command_digest:
                        raise ProjectManagerError("idempotency_conflict", "幂等键已用于不同请求")
                    return json.loads(operation["result_json"])
                cursor.execute(
                    "SELECT revision FROM workmanship_base_project_manager_heads "
                    "WHERE tenant_gid=%s AND project_gid=%s FOR UPDATE",
                    (tenant_gid, project_gid),
                )
                head = cursor.fetchone()
                revision = int(head["revision"]) if head else 0
                if revision != expected_revision:
                    raise ProjectManagerError("version_conflict", "项目经理配置已被其他人修改")
                if head:
                    cursor.execute(
                        "UPDATE workmanship_base_project_manager_heads SET revision=revision+1,updated_at=NOW() "
                        "WHERE tenant_gid=%s AND project_gid=%s",
                        (tenant_gid, project_gid),
                    )
                else:
                    cursor.execute(
                        "INSERT INTO workmanship_base_project_manager_heads "
                        "(tenant_gid,project_gid,revision,managed) VALUES (%s,%s,1,1)",
                        (tenant_gid, project_gid),
                    )
                cursor.execute(
                    "DELETE FROM workmanship_base_project_manager_assignments "
                    "WHERE tenant_gid=%s AND project_gid=%s", (tenant_gid, project_gid),
                )
                for user_gid in user_gids:
                    cursor.execute(
                        "INSERT INTO workmanship_base_project_manager_assignments "
                        "(gid,tenant_gid,project_gid,user_gid,created_by) VALUES (%s,%s,%s,%s,%s)",
                        (str(next_gid()), tenant_gid, project_gid, user_gid, actor_gid),
                    )
                result = {"revision": revision + 1, "managed": True, "user_gids": user_gids}
                cursor.execute(
                    "INSERT INTO workmanship_base_project_manager_operations "
                    "(gid,tenant_gid,actor_gid,project_gid,idempotency_key,command_digest,result_json) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (str(next_gid()), tenant_gid, actor_gid, project_gid, idempotency_key,
                     command_digest, json.dumps(result, ensure_ascii=False)),
                )
                return result


class ProjectManagerService:
    def __init__(self, repository: Any | None = None) -> None:
        self.repository = repository or SqlProjectManagerRepository()

    def read(self, tenant_gid: str, project_gid: str) -> dict[str, Any]:
        raw = self.repository.read(tenant_gid, project_gid)
        profiles = self.repository.active_users(raw["user_gids"])
        managers = [
            {"gid": gid, "name": str(profiles[gid].get("name") or ""),
             "avatar_url": str(profiles[gid].get("avatar_url") or "")}
            for gid in raw["user_gids"] if gid in profiles
        ]
        return {"project_gid": project_gid, "revision": raw["revision"],
                "managed": bool(raw["managed"]), "managers": managers}

    def replace(self, *, tenant_gid: str, actor_gid: str, project_gid: str,
                user_gids: Iterable[str], expected_revision: int,
                idempotency_key: str) -> dict[str, Any]:
        gids = _gids(user_gids)
        if expected_revision < 0 or not idempotency_key.strip():
            raise ProjectManagerError("invalid_input", "修订号或幂等键无效")
        profiles = self.repository.active_users(gids)
        if len(profiles) != len(gids):
            raise ProjectManagerError("resource_not_found", "项目经理必须是有效人员")
        digest = _digest({"project_gid": project_gid, "user_gids": gids,
                          "expected_revision": expected_revision})
        raw = self.repository.replace(
            tenant_gid=tenant_gid, project_gid=project_gid, user_gids=gids,
            expected_revision=expected_revision, actor_gid=actor_gid,
            idempotency_key=idempotency_key, command_digest=digest,
        )
        result_profiles = self.repository.active_users(raw["user_gids"])
        return {"project_gid": project_gid, "revision": raw["revision"], "managed": True,
                "managers": [{"gid": gid, "name": str(result_profiles[gid].get("name") or ""),
                              "avatar_url": str(result_profiles[gid].get("avatar_url") or "")}
                             for gid in raw["user_gids"]]}


__all__ = ["ProjectManagerError", "ProjectManagerService", "SqlProjectManagerRepository"]

