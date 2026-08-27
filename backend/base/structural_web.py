"""Public Base owner services for closed structural browser outcomes."""
from __future__ import annotations

from typing import Any

from backend.db.connection import get_conn

SYSTEM_ROLES = {
    "super_admin", "team_admin", "project_admin", "rule_admin",
    "knowledge_admin", "member", "external",
}


class StructuralWebError(ValueError):
    code = "provider_failed"


def _role(actor: dict[str, Any]) -> str:
    return str(actor.get("org_role") or actor.get("system_role") or "")


def _require_admin(actor: dict[str, Any]) -> None:
    if _role(actor) not in {"super_admin", "team_admin"}:
        error = StructuralWebError("权限不足")
        error.code = "permission_denied"
        raise error


def _team(row: dict[str, Any], *, include_feishu: bool) -> dict[str, Any]:
    value = {
        "gid": str(row["gid"]),
        "name": str(row.get("name") or ""),
        "is_active": bool(row.get("is_active")),
        "parent_team_gid": str(row["parent_team_gid"]) if row.get("parent_team_gid") is not None else None,
        "created_at": str(row.get("created_at") or ""),
    }
    if include_feishu:
        value["feishu_dept_id"] = str(row["feishu_dept_id"]) if row.get("feishu_dept_id") is not None else None
    return value


def list_organization_teams(*, actor: dict[str, Any]) -> dict[str, Any]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid,name,is_active,feishu_dept_id,parent_team_gid,created_at "
                "FROM workmanship_auth_teams ORDER BY name"
            )
            rows = cur.fetchall()
    return {"teams": [_team(dict(row), include_feishu=True) for row in rows]}


def list_teams(*, actor: dict[str, Any]) -> dict[str, Any]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid,name,is_active,parent_team_gid,created_at "
                "FROM workmanship_auth_teams WHERE deleted_at IS NULL ORDER BY created_at"
            )
            rows = cur.fetchall()
    return {"success": True, "data": [_team(dict(row), include_feishu=False) for row in rows]}


def annotation_batch(*, actor: dict[str, Any], item_gids: list[str]) -> dict[str, Any]:
    if not item_gids:
        return {"items": []}
    placeholders = ",".join(["%s"] * len(item_gids))
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT item_gid,self_status,self_schedule,self_note,self_attachments "
                f"FROM workmanship_base_self_annotations WHERE item_gid IN ({placeholders}) AND user_gid=%s",
                [*item_gids, actor["gid"]],
            )
            rows = cur.fetchall()
    return {"items": [
        {
            "item_gid": str(row["item_gid"]),
            "status": str(row.get("self_status") or ""),
            "schedule": str(row.get("self_schedule") or ""),
            "has_note": bool(row.get("self_note")),
            "attach_count": _attachment_count(row.get("self_attachments")),
        }
        for row in rows
    ]}


def _attachment_count(value: Any) -> int:
    if isinstance(value, list):
        return len(value)
    import json
    try:
        decoded = json.loads(value or "[]")
    except (TypeError, ValueError):
        return 0
    return len(decoded) if isinstance(decoded, list) else 0


def _user_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "gid": str(row["gid"]),
        "name": str(row.get("name") or ""),
        "email": str(row.get("email") or ""),
        "avatar_url": str(row.get("avatar_url") or ""),
        "system_role": str(row.get("system_role") or "member"),
        "org_role": str(row.get("org_role") or "member"),
        "external_subtype": str(row["external_subtype"]) if row.get("external_subtype") is not None else None,
        "team_id": str(row["team_id"]) if row.get("team_id") is not None else None,
        "is_active": bool(row.get("is_active")),
        "created_at": str(row.get("created_at") or ""),
    }


def _role_to_org_role(system_role: str) -> str:
    if system_role == "super_admin":
        return "super_admin"
    if system_role == "external":
        return "external"
    return "member"


def list_admin_users(*, actor: dict[str, Any]) -> dict[str, Any]:
    _require_admin(actor)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid,name,email,avatar_url,system_role,org_role,external_subtype,team_id,is_active,created_at "
                "FROM workmanship_auth_users WHERE is_active=TRUE ORDER BY created_at"
            )
            rows = cur.fetchall()
    return {"success": True, "data": [_user_summary(dict(row)) for row in rows]}


def assign_user_role(*, actor: dict[str, Any], user_gid: str, new_role: str, external_subtype: str | None) -> dict[str, Any]:
    """Assign one role within the Base provider's locked transaction.

    The operator/target lock and active-super-admin lock are both held on the
    same Base connection until the final protected-invariant check and update
    have completed.  This is the transaction advertised by the strong atomic
    capability, rather than a sequence of legacy service connections.
    """
    _require_admin(actor)
    if new_role not in SYSTEM_ROLES:
        raise StructuralWebError("未知角色")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid,system_role,is_active FROM workmanship_auth_users "
                "WHERE gid IN (%s,%s) ORDER BY gid FOR UPDATE",
                (str(actor["gid"]), user_gid),
            )
            users = {str(row["gid"]): dict(row) for row in cur.fetchall()}
            operator = users.get(str(actor["gid"]))
            target = users.get(user_gid)
            if operator is None:
                raise StructuralWebError("操作者不存在")
            if target is None:
                raise StructuralWebError("目标用户不存在")
            if operator["system_role"] not in {"super_admin", "team_admin"}:
                raise StructuralWebError("权限不足")
            if new_role == "super_admin" and operator["system_role"] != "super_admin":
                raise StructuralWebError("只有超管才能授予超管角色")
            cur.execute(
                "SELECT gid FROM workmanship_auth_users "
                "WHERE system_role='super_admin' AND is_active=TRUE FOR UPDATE"
            )
            super_admins = cur.fetchall()
            if (
                new_role != "super_admin"
                and target["system_role"] == "super_admin"
                and len(super_admins) <= 1
            ):
                raise StructuralWebError("系统中至少保留一名超级管理员")
            cur.execute(
                "UPDATE workmanship_auth_users SET system_role=%s, external_subtype=%s, "
                "org_role=%s, updated_at=NOW() WHERE gid=%s",
                (new_role, external_subtype, _role_to_org_role(new_role), user_gid),
            )
            cur.execute("SELECT * FROM workmanship_auth_users WHERE gid=%s", (user_gid,))
            row = cur.fetchone()
            if not row:
                raise StructuralWebError("目标用户不存在")
            return {"success": True, "data": _user_summary(dict(row))}


__all__ = [
    "StructuralWebError", "annotation_batch", "assign_user_role", "list_admin_users",
    "list_organization_teams", "list_teams",
]
