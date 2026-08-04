"""
backend/routers/lists.py
────────────────────────
清单 CRUD API

GET    /api/lists          → 列出用户可见清单
POST   /api/lists          → 创建清单
PATCH  /api/lists/{gid}    → 更新清单（改名/改色/改排序/转让Owner/设置可见范围）
DELETE /api/lists/{gid}    → 软删除清单（仅 Owner 或 admin）
"""
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..data.connection import get_conn
from backend.platform_sdk.auth import get_current_user
from backend.platform_sdk.ids import next_gid

router = APIRouter(tags=["lists"])


class ListBody(BaseModel):
    name: str
    color: str = "#5b8dee"
    storage_scope: str = "cloud"
    owner_type: str = "user"       # user | team
    owner_gid: str = ""
    item_type: str = "task"        # task | issue | knowledge | rule
    sort_order: int = 0
    visibility: str = "team"       # 旧字段，兼容
    read_scope: Optional[str] = None   # 新字段；未传时从 visibility 推导
    write_scope: Optional[str] = None  # 新字段；未传时从 visibility 推导


class ListPatchBody(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    sort_order: Optional[int] = None
    owner_gid: Optional[str] = None    # 转让 owner
    visibility: Optional[str] = None   # 旧字段
    read_scope: Optional[str] = None   # 新字段
    write_scope: Optional[str] = None  # 新字段
    archive: Optional[bool] = None     # 迁移用软删除（不解绑条目）
    project_gid: Optional[str] = None  # 关联项目


_PATCH_ALLOWED = {"name", "color", "sort_order", "owner_gid", "visibility", "read_scope", "write_scope", "project_gid", "shared_team_gid"}
_ADMIN_ROLES = ("super_admin", "team_admin")


def _row_to_list(r: dict) -> dict:
    return {
        "gid":           r["gid"],
        "name":          r["name"],
        "color":         r["color"],
        "storage_scope": r["storage_scope"],
        "owner_type":    r["owner_type"],
        "owner_gid":     r["owner_gid"],
        "creator_gid":   r.get("creator_gid") or "",
        "visibility":    r.get("visibility") or "team",
        "read_scope":    r.get("read_scope")  or r.get("visibility") or "team",
        "write_scope":   r.get("write_scope") or "personal",
        "deleted_at":    str(r["deleted_at"]) if r.get("deleted_at") else None,
        "item_type":     r.get("item_type") or "task",
        "sort_order":    r["sort_order"],
        "created_at":    str(r["created_at"]),
        "project_gid":   r.get("project_gid") or None,
    }


@router.get("/api/lists")
def list_cloud_lists(
    item_type: Optional[str] = Query(default=None),
    owner_team_gid: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
    current_user: dict = Depends(get_current_user),
):
    """List visible Craft project lists using a Base-issued access projection."""
    if item_type == "bop_version":
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT gid, COALESCE(version_tag, '') AS name, maturity, takt_time,
                           status, created_at, 'cloud' AS storage_scope, 'user' AS owner_type,
                           '' AS owner_gid, 'bop_version' AS item_type
                    FROM workmanship_bop_bop_versions ORDER BY created_at DESC
                """)
                rows = [dict(row) for row in cur.fetchall()]
        colors = {'concept': '#6c7086', 'planned': '#89b4fa', 'released': '#a6e3a1', 'frozen': '#f9e2af'}
        for row in rows:
            row['color'] = colors.get(row.get('maturity'), '#5b8dee')
            if row.get('created_at') and not isinstance(row['created_at'], str):
                row['created_at'] = str(row['created_at'])
        return {"success": True, "data": rows}

    from backend.platform_sdk.access import build_access_scope

    scope = build_access_scope(current_user)
    uid = scope["user_gid"]
    team_gids = list(scope["team_gids"])
    member_gids = list(scope["team_member_gids"])
    project_gids = list(scope["project_gids"])
    if owner_team_gid and owner_team_gid not in team_gids and not scope["is_admin"]:
        raise HTTPException(status_code=403, detail="无权访问该团队清单")

    clauses = ["deleted_at IS NULL"]
    params: list = []
    if owner_team_gid:
        clauses.extend(["owner_type='team'", "owner_gid=%s"])
        params.append(owner_team_gid)
    else:
        visible = ["(owner_type='user' AND owner_gid=%s)", "visibility='public'"]
        params.append(uid)
        if team_gids:
            placeholders = ",".join(["%s"] * len(team_gids))
            visible.append(f"(owner_type='team' AND owner_gid IN ({placeholders}))")
            params.extend(team_gids)
            visible.append(f"(visibility='team' AND shared_team_gid IN ({placeholders}))")
            params.extend(team_gids)
        if member_gids:
            placeholders = ",".join(["%s"] * len(member_gids))
            visible.append(f"(visibility='team' AND shared_team_gid IS NULL AND creator_gid IN ({placeholders}))")
            params.extend(member_gids)
        if project_gids:
            placeholders = ",".join(["%s"] * len(project_gids))
            visible.append(f"(visibility='project' AND project_gid IN ({placeholders}))")
            params.extend(project_gids)
        clauses.append("(" + " OR ".join(visible) + ")")
    if item_type:
        clauses.append("item_type=%s"); params.append(item_type)
    if q:
        clauses.append("name LIKE %s"); params.append(f"%{q}%")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT * FROM workmanship_work_lists WHERE {' AND '.join(clauses)} "
                "ORDER BY owner_type,sort_order,created_at",
                params,
            )
            rows = cur.fetchall()
    return {"success": True, "data": [_row_to_list(dict(row)) for row in rows]}


def _visibility_to_read_scope(visibility: str) -> str:
    return {"public": "global", "private": "personal", "team": "team", "project": "project"}.get(visibility, "team")


def _visibility_to_write_scope(visibility: str) -> str:
    return {"public": "team", "private": "personal", "team": "team", "project": "team"}.get(visibility, "personal")


@router.post("/api/lists", status_code=201)
def create_cloud_list(body: ListBody, current_user: dict = Depends(get_current_user)):
    uid = current_user["gid"]
    gid = str(next_gid())
    owner_gid = uid if body.owner_type == "user" else body.owner_gid
    read_scope  = body.read_scope  or _visibility_to_read_scope(body.visibility)
    write_scope = body.write_scope or _visibility_to_write_scope(body.visibility)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO workmanship_work_lists
                  (gid, name, color, storage_scope, owner_type, owner_gid,
                   creator_gid, visibility, read_scope, write_scope, item_type, sort_order)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (gid, body.name, body.color, body.storage_scope,
                 body.owner_type, owner_gid, uid, body.visibility,
                 read_scope, write_scope, body.item_type, body.sort_order),
            )
        conn.commit()
    return {"success": True, "data": {"gid": gid}}


@router.patch("/api/lists/{gid}")
def update_cloud_list(gid: str, body: ListPatchBody,
                      current_user: dict = Depends(get_current_user)):
    uid = current_user["gid"]
    role = current_user.get("system_role") or current_user.get("org_role", "")
    is_team_admin = role in _ADMIN_ROLES

    # 迁移软删除：只打 deleted_at，不解绑条目（条目在另一个 DB，解绑无意义）
    if body.archive:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT owner_gid, owner_type FROM workmanship_work_lists WHERE gid = %s AND deleted_at IS NULL", (gid,)
                )
                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="清单不存在")
                if row["owner_gid"] != uid:
                    list_is_personal = row.get("owner_type") == "user"
                    if list_is_personal or not is_team_admin:
                        raise HTTPException(status_code=403, detail="仅清单 Owner 可操作个人清单")
                cur.execute("UPDATE workmanship_work_lists SET deleted_at = NOW() WHERE gid = %s", (gid,))
            conn.commit()
        return {"success": True}

    updates = {k: v for k, v in body.model_dump().items()
               if v is not None and k in _PATCH_ALLOWED}
    # project_gid 可以显式设为空字符串表示清除关联（转换为 NULL）
    if body.project_gid == "" and "project_gid" not in updates:
        updates["project_gid"] = None
    # 若传了 visibility 但未传新字段，同步推导新字段
    if "visibility" in updates and "read_scope" not in updates:
        updates["read_scope"] = _visibility_to_read_scope(updates["visibility"])
    if "visibility" in updates and "write_scope" not in updates:
        updates["write_scope"] = _visibility_to_write_scope(updates["visibility"])
    if not updates:
        raise HTTPException(status_code=400, detail="无更新字段")

    with get_conn() as conn:
        with conn.cursor() as cur:
            # 转让 owner 时，需是 owner 本人或管理员
            if "owner_gid" in updates:
                cur.execute(
                    "SELECT owner_gid, owner_type FROM workmanship_work_lists WHERE gid = %s AND deleted_at IS NULL", (gid,)
                )
                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="清单不存在")
                if row["owner_gid"] != uid:
                    list_is_personal = row.get("owner_type") == "user"
                    if list_is_personal or not is_team_admin:
                        raise HTTPException(status_code=403, detail="仅清单 Owner 可操作个人清单")

            set_clause = ", ".join(f"{k} = %s" for k in updates)
            values = list(updates.values()) + [gid]
            cur.execute(
                f"UPDATE workmanship_work_lists SET {set_clause} WHERE gid = %s AND deleted_at IS NULL", values
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="清单不存在")
        conn.commit()
    return {"success": True}


@router.delete("/api/lists/{gid}")
def delete_cloud_list(gid: str, current_user: dict = Depends(get_current_user)):
    uid = current_user["gid"]
    role = current_user.get("system_role") or current_user.get("org_role", "")
    is_team_admin = role in _ADMIN_ROLES

    with get_conn() as conn:
        with conn.cursor() as cur:
            # bop_version 软删除（保留数据，仅标记 deleted_at）
            cur.execute("SELECT gid FROM workmanship_bop_bop_versions WHERE gid = %s AND deleted_at IS NULL", (gid,))
            if cur.fetchone():
                cur.execute("UPDATE workmanship_bop_bop_versions SET deleted_at = NOW() WHERE gid = %s", (gid,))
                conn.commit()
                return {"success": True}

            # 权限检查：仅 owner 或 admin（非个人清单时）可删除
            cur.execute(
                "SELECT owner_gid, owner_type FROM workmanship_work_lists WHERE gid = %s AND deleted_at IS NULL", (gid,)
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="清单不存在")
            if row["owner_gid"] != uid:
                list_is_personal = row.get("owner_type") == "user"
                if list_is_personal or not is_team_admin:
                    raise HTTPException(status_code=403, detail="仅清单 Owner 可操作个人清单")

            # 软删除：解绑条目 + 标记 deleted_at
            cur.execute("UPDATE workmanship_proj_tasks  SET list_gid = NULL WHERE list_gid = %s", (gid,))
            cur.execute("UPDATE workmanship_proj_issues SET list_gid = NULL WHERE list_gid = %s", (gid,))
            cur.execute(
                "UPDATE workmanship_work_lists SET deleted_at = NOW() WHERE gid = %s", (gid,)
            )
        conn.commit()
    return {"success": True}


class RetargetBody(BaseModel):
    new_list_gid: str
    item_type: str = ""   # task | issue | "" = 两者都改


@router.post("/api/lists/{gid}/retarget")
def retarget_cloud_list_items(gid: str, body: RetargetBody,
                              current_user: dict = Depends(get_current_user)):
    """迁移清单用：将云端条目的 list_gid 从旧清单改指向新清单（不移动条目本身）。"""
    uid = current_user["gid"]
    role = current_user.get("system_role") or current_user.get("org_role", "")
    is_team_admin = role in _ADMIN_ROLES

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT owner_gid, owner_type FROM workmanship_work_lists WHERE gid = %s", (gid,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="清单不存在")
            if row["owner_gid"] != uid:
                list_is_personal = row.get("owner_type") == "user"
                if list_is_personal or not is_team_admin:
                    raise HTTPException(status_code=403, detail="仅清单 Owner 或管理员可操作")

            if body.item_type in ("task", ""):
                cur.execute("UPDATE workmanship_proj_tasks  SET list_gid = %s WHERE list_gid = %s",
                            (body.new_list_gid, gid))
            if body.item_type in ("issue", ""):
                cur.execute("UPDATE workmanship_proj_issues SET list_gid = %s WHERE list_gid = %s",
                            (body.new_list_gid, gid))
        conn.commit()
    return {"success": True}
