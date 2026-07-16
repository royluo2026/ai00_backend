"""
backend/routers/teams.py
────────────────────────
团队管理 API

端点：
  GET  /teams                    → 列出所有团队
  POST /teams                    → 创建团队（super_admin 或 team_admin 创建子团队）
  PATCH /teams/{gid}             → 更新团队（super_admin）
  PATCH /teams/{gid}/config      → 合并更新团队配置 JSON（team_admin+）
  DELETE /teams/{gid}            → 删除团队（super_admin）
  GET  /teams/{gid}/members      → 列出团队成员（已登录用户）
  POST /teams/{gid}/members      → 添加成员（team_admin+）
  DELETE /teams/{gid}/members/{user_gid}  → 移除成员（team_admin+）
"""
import json
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from backend.db.connection import get_conn
from backend.routers.deps import get_current_user, require_role
from backend.utils.gid import next_gid

router = APIRouter(prefix="/teams", tags=["teams"])

_ADMIN_ONLY = require_role("super_admin", "team_admin")
_SUPER_ONLY = require_role("super_admin")


class CreateTeamBody(BaseModel):
    name: str
    is_active: bool = True
    parent_team_gid: Optional[str] = None


class UpdateTeamBody(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None


@router.get("")
def list_teams(current_user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid, name, is_active, config, created_at, parent_team_gid "
                "FROM workmanship_auth_teams WHERE deleted_at IS NULL ORDER BY created_at"
            )
            rows = cur.fetchall()
    return {"success": True, "data": [
        {
            "gid":             r["gid"],
            "name":            r["name"],
            "is_active":       r["is_active"],
            "config":          r["config"] if isinstance(r["config"], dict) else {},
            "created_at":      str(r["created_at"]),
            "parent_team_gid": r["parent_team_gid"],
        }
        for r in rows
    ]}


@router.post("", status_code=201)
def create_team(body: CreateTeamBody, current_user: dict = Depends(get_current_user)):
    """
    super_admin 可创建任意团队；
    team_admin 只能在自己管理的团队下创建子团队（需提供 parent_team_gid）。
    """
    org_role  = current_user.get("org_role") or current_user.get("system_role", "")
    is_super  = org_role == "super_admin"

    if not is_super:
        # 非超管：必须是目标父团队的 team_admin
        if not body.parent_team_gid:
            raise HTTPException(403, "非超管必须指定 parent_team_gid")
        grants = current_user.get("grants", [])
        has_grant = any(
            g["grant_type"] == "team_admin" and g["scope_gid"] == body.parent_team_gid
            for g in grants
        )
        if not has_grant:
            raise HTTPException(403, "无权在该团队下创建子团队")

    gid = str(next_gid())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_auth_teams (gid, name, is_active, parent_team_gid, config) "
                "VALUES (%s, %s, %s, %s, %s)",
                (gid, body.name, body.is_active, body.parent_team_gid, '{}')
            )
        conn.commit()
    return {"success": True, "data": {"gid": gid, "name": body.name}}


@router.patch("/{gid}")
def update_team(gid: str, body: UpdateTeamBody, _: dict = Depends(_SUPER_ONLY)):
    updates = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.is_active is not None:
        updates["is_active"] = body.is_active
    if not updates:
        raise HTTPException(status_code=400, detail="没有需要更新的字段")

    set_clause = ", ".join(f"{k} = %s" for k in updates)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE workmanship_auth_teams SET {set_clause} WHERE gid = %s",
                list(updates.values()) + [gid]
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="团队不存在")
        conn.commit()
    return {"success": True}


@router.delete("/{gid}")
def delete_team(gid: str, _: dict = Depends(_SUPER_ONLY)):
    """软删除团队（设置 deleted_at，不物理删除数据）"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE workmanship_auth_teams SET deleted_at = NOW() WHERE gid = %s AND deleted_at IS NULL",
                (gid,),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="团队不存在或已删除")
        conn.commit()
    return {"success": True}


@router.patch("/{gid}/config")
def update_team_config(
    gid: str,
    body: dict = Body(...),
    _: dict = Depends(_ADMIN_ONLY),
):
    """增量合并更新团队配置 JSON（JSONB merge）"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE workmanship_auth_teams SET config = JSON_MERGE_PATCH(IFNULL(config,'{}'), %s) WHERE gid = %s",
                (json.dumps(body), gid),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="团队不存在")
        conn.commit()
    return {"success": True}


@router.get("/{gid}/members")
def list_team_members(gid: str, current_user: dict = Depends(get_current_user)):
    """列出该团队的所有用户（team_id = gid）"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid, name, email, avatar_url, system_role, org_role, created_at "
                "FROM workmanship_auth_users WHERE team_id = %s ORDER BY created_at",
                (gid,),
            )
            rows = cur.fetchall()
    return {"success": True, "data": [
        {
            "gid":        r["gid"],
            "name":       r["name"] or "",
            "email":      r["email"] or "",
            "avatar_url": r["avatar_url"] or "",
            "org_role":   r["org_role"] or r["system_role"] or "member",
            "created_at": str(r["created_at"]),
        }
        for r in rows
    ]}


class AddMemberBody(BaseModel):
    user_gid: Optional[str] = None
    feishu_open_id: Optional[str] = None
    name: Optional[str] = ""
    email: Optional[str] = ""
    avatar_url: Optional[str] = ""


@router.post("/{gid}/members", status_code=200)
def add_team_member(
    gid: str,
    body: AddMemberBody,
    current_user: dict = Depends(get_current_user),
):
    """将用户的 team_id 设置为该团队（team_admin 或 super_admin）。
    支持 user_gid（已有用户）或 feishu_open_id（自动创建未注册用户）。
    """
    org_role = current_user.get("org_role") or current_user.get("system_role", "")
    is_super = org_role == "super_admin"
    if not is_super:
        grants = current_user.get("grants", [])
        if not any(g["grant_type"] == "team_admin" and g["scope_gid"] == gid for g in grants):
            raise HTTPException(403, "无权添加成员")

    target_gid = body.user_gid

    # 通过 feishu_open_id 查找或创建用户
    if not target_gid and body.feishu_open_id:
        from backend.services.user_service import get_or_create
        user = get_or_create(
            body.feishu_open_id,
            body.name or body.feishu_open_id,
            body.email or "",
            body.avatar_url or "",
        )
        target_gid = user["gid"]

    if not target_gid:
        raise HTTPException(400, "请提供 user_gid 或 feishu_open_id")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE workmanship_auth_users SET team_id = %s WHERE gid = %s",
                (gid, target_gid),
            )
            if cur.rowcount == 0:
                raise HTTPException(404, "用户不存在")
        conn.commit()
    return {"success": True}


@router.delete("/{gid}/members/{user_gid}")
def remove_team_member(
    gid: str,
    user_gid: str,
    current_user: dict = Depends(get_current_user),
):
    """将用户从团队移除（team_id 置 NULL）"""
    org_role = current_user.get("org_role") or current_user.get("system_role", "")
    is_super = org_role == "super_admin"
    if not is_super:
        grants = current_user.get("grants", [])
        if not any(g["grant_type"] == "team_admin" and g["scope_gid"] == gid for g in grants):
            raise HTTPException(403, "无权移除成员")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE workmanship_auth_users SET team_id = NULL WHERE gid = %s AND team_id = %s",
                (user_gid, gid),
            )
        conn.commit()
    return {"success": True}
