"""Base-owned grant service shared by REST and Capability providers."""
from __future__ import annotations

from typing import Any

from backend.db.connection import get_conn
from backend.utils.gid import next_gid


GRANT_TYPES = {"team_admin", "project_owner", "section_lead"}


class GrantServiceError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _active_grants(user_gid: str) -> list[dict[str, Any]]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid,grant_type,scope_gid,granted_at,expires_at,note "
                "FROM workmanship_auth_permission_grants WHERE grantee_gid=%s "
                "AND (expires_at IS NULL OR expires_at > NOW())",
                (user_gid,),
            )
            return [dict(row) for row in cur.fetchall()]


def can_manage(user: dict[str, Any], scope_gid: str | None = None) -> bool:
    role = user.get("org_role") or user.get("system_role", "external")
    if role == "super_admin" or user.get("system_role") in {"super_admin", "team_admin"}:
        return True
    return any(
        grant.get("grant_type") == "team_admin"
        and (scope_gid is None or grant.get("scope_gid") == scope_gid)
        for grant in _active_grants(str(user["gid"]))
    )


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


def _project(row: dict[str, Any]) -> dict[str, Any]:
    value = {
        "gid": str(row["gid"]),
        "grantee_gid": str(row["grantee_gid"]),
        "grant_type": str(row["grant_type"]),
        "scope_gid": _text(row.get("scope_gid")),
        "granted_by": str(row["granted_by"]),
        "expires_at": _text(row.get("expires_at")),
        "note": str(row.get("note") or ""),
        "granted_at": _text(row.get("granted_at")),
    }
    if "grantee_name" in row:
        value["grantee_name"] = _text(row.get("grantee_name"))
    return value


def list_grants(*, actor: dict[str, Any], user_gid: str | None = None) -> dict[str, Any]:
    if not can_manage(actor):
        raise GrantServiceError("permission_denied", "权限不足")
    with get_conn() as conn:
        with conn.cursor() as cur:
            base = (
                "SELECT g.*,u.name AS grantee_name FROM workmanship_auth_permission_grants g "
                "LEFT JOIN workmanship_auth_users u ON u.gid=g.grantee_gid "
                "WHERE (g.expires_at IS NULL OR g.expires_at > NOW())"
            )
            if user_gid:
                cur.execute(base + " AND g.grantee_gid=%s ORDER BY g.granted_at DESC", (user_gid,))
            else:
                cur.execute(base + " ORDER BY g.granted_at DESC LIMIT 500")
            rows = cur.fetchall()
    return {"grants": [_project(dict(row)) for row in rows]}


def create_grant(
    *, actor: dict[str, Any], grantee_gid: str, grant_type: str,
    scope_gid: str | None = None, expires_at: str | None = None, note: str = "",
) -> dict[str, Any]:
    if grant_type not in GRANT_TYPES:
        raise GrantServiceError("invalid_grant_type", f"未知 grant_type: {grant_type}")
    if not can_manage(actor, scope_gid):
        raise GrantServiceError("permission_denied", "权限不足")
    gid = next_gid()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO workmanship_auth_permission_grants
                   (gid,grantee_gid,grant_type,scope_gid,granted_by,expires_at,note)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)
                   ON DUPLICATE KEY UPDATE granted_by=VALUES(granted_by),
                   expires_at=VALUES(expires_at),note=VALUES(note),granted_at=NOW()""",
                (gid, grantee_gid, grant_type, scope_gid, actor["gid"], expires_at, note),
            )
            cur.execute("SELECT * FROM workmanship_auth_permission_grants WHERE gid=%s", (gid,))
            row = cur.fetchone()
        conn.commit()
    if not row:
        raise GrantServiceError("grant_persistence_failed", "授权写入未返回记录")
    return {"grant": _project(dict(row))}


def revoke_grant(*, actor: dict[str, Any], gid: str) -> dict[str, bool]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM workmanship_auth_permission_grants WHERE gid=%s", (gid,))
            row = cur.fetchone()
            if not row:
                raise GrantServiceError("resource_not_found", "Grant 不存在")
            if not can_manage(actor, dict(row).get("scope_gid")):
                raise GrantServiceError("permission_denied", "权限不足")
            cur.execute("DELETE FROM workmanship_auth_permission_grants WHERE gid=%s", (gid,))
        conn.commit()
    return {"ok": True}


__all__ = ["GrantServiceError", "can_manage", "create_grant", "list_grants", "revoke_grant"]
