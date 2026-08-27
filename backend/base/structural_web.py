"""Public Base owner services for closed structural browser outcomes."""
from __future__ import annotations

from typing import Any

from backend.db.connection import get_conn


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
    _require_admin(actor)
    from backend.services.user_service import assign_role
    try:
        updated = assign_role(
            operator_gid=str(actor["gid"]), target_gid=user_gid,
            new_role=new_role, external_subtype=external_subtype,
        )
    except (PermissionError, ValueError) as exc:
        error = StructuralWebError(str(exc))
        error.code = "permission_denied"
        raise error from exc
    return {"success": True, "data": _user_summary(updated)}


__all__ = [
    "StructuralWebError", "annotation_batch", "assign_user_role", "list_admin_users",
    "list_organization_teams", "list_teams",
]
