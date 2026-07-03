"""
backend/routers/grants.py
──────────────────────────
职能授权（permission_grants）CRUD

GET    /api/grants?user_gid=    列出用户 grants（system.user.manage 或 team_admin grant）
GET    /api/grants/me           当前用户自己的 grants
POST   /api/grants              创建 grant（super_admin 全局；team_admin 仅本团队）
DELETE /api/grants/{gid}        撤销 grant
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from backend.db.connection import get_conn
from backend.routers.deps import get_current_user, _get_user_grants, _derive_org_role, _GRANT_PERMISSIONS
from backend.utils.gid import next_gid

router = APIRouter(tags=["grants"])

_GRANT_TYPES = {"team_admin", "project_owner", "section_lead"}


class GrantBody(BaseModel):
    grantee_gid: str
    grant_type: str
    scope_gid: Optional[str] = None
    expires_at: Optional[str] = None
    note: str = ""


def _can_manage_grants(user: dict, target_scope_gid: Optional[str] = None) -> bool:
    """检查当前用户是否有权限创建/撤销 grant。"""
    org_role = user.get("org_role") or _derive_org_role(user.get("system_role", "external"))
    if org_role == "super_admin":
        return True
    # team_admin grant 可以在本团队范围内管理
    grants = _get_user_grants(user["gid"])
    for g in grants:
        if g["grant_type"] == "team_admin":
            if target_scope_gid is None or g.get("scope_gid") == target_scope_gid:
                return True
    # 旧 system_role 兼容
    if user.get("system_role") in ("super_admin", "team_admin"):
        return True
    return False


@router.get("/api/grants/me")
def get_my_grants(current_user: dict = Depends(get_current_user)):
    """当前用户自己的 grants。"""
    return {"grants": _get_user_grants(current_user["gid"])}


@router.get("/api/grants")
def list_grants(
    user_gid: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """列出指定用户的 grants（需要 system.user.manage 或 team_admin grant）。"""
    if not _can_manage_grants(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    with get_conn() as conn:
        with conn.cursor() as cur:
            if user_gid:
                cur.execute(
                    "SELECT g.*, u.name AS grantee_name "
                    "FROM workmanship_auth_permission_grants g "
                    "LEFT JOIN workmanship_auth_users u ON u.gid = g.grantee_gid "
                    "WHERE g.grantee_gid = %s "
                    "  AND (g.expires_at IS NULL OR g.expires_at > NOW()) "
                    "ORDER BY g.granted_at DESC",
                    (user_gid,),
                )
            else:
                cur.execute(
                    "SELECT g.*, u.name AS grantee_name "
                    "FROM workmanship_auth_permission_grants g "
                    "LEFT JOIN workmanship_auth_users u ON u.gid = g.grantee_gid "
                    "WHERE (g.expires_at IS NULL OR g.expires_at > NOW()) "
                    "ORDER BY g.granted_at DESC "
                    "LIMIT 500"
                )
            return {"grants": [dict(r) for r in cur.fetchall()]}


@router.post("/api/grants", status_code=status.HTTP_201_CREATED)
def create_grant(body: GrantBody, current_user: dict = Depends(get_current_user)):
    """创建职能授权。"""
    if body.grant_type not in _GRANT_TYPES:
        raise HTTPException(status_code=400, detail=f"未知 grant_type: {body.grant_type}")
    if not _can_manage_grants(current_user, body.scope_gid):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")

    gid = next_gid()
    with get_conn() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """INSERT INTO workmanship_auth_permission_grants
                       (gid, grantee_gid, grant_type, scope_gid, granted_by, expires_at, note)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)
                       ON DUPLICATE KEY UPDATE
                         granted_by=VALUES(granted_by), expires_at=VALUES(expires_at), note=VALUES(note), granted_at=NOW()""",
                    (gid, body.grantee_gid, body.grant_type, body.scope_gid,
                     current_user["gid"], body.expires_at, body.note),
                )
                cur.execute(
                    "SELECT * FROM workmanship_auth_permission_grants WHERE gid = %s",
                    (gid,),
                )
                row = cur.fetchone()
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        conn.commit()
    return {"grant": dict(row)}


@router.delete("/api/grants/{gid}")
def delete_grant(gid: str, current_user: dict = Depends(get_current_user)):
    """撤销职能授权。"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM workmanship_auth_permission_grants WHERE gid = %s", (gid,)
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Grant 不存在")
            grant = dict(row)
            if not _can_manage_grants(current_user, grant.get("scope_gid")):
                raise HTTPException(status_code=403, detail="权限不足")
            cur.execute("DELETE FROM workmanship_auth_permission_grants WHERE gid = %s", (gid,))
        conn.commit()
    return {"ok": True}
