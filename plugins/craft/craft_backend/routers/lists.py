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
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from backend.capability_v2.gateway import get_default_gateway
from backend.platform_sdk.access import build_access_scope
from ..data.connection import get_conn
from backend.platform_sdk.auth import get_authenticated_principal, get_current_user
from backend.platform_sdk.project_management import (
    build_web_compatibility_envelope,
    invoke_compatibility,
)

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


async def _invoke_project(request, user, principal, gateway, operation, arguments, *, write=False):
    request_id = request.headers.get("X-Request-ID") or f"project_{uuid4().hex}"
    result = await invoke_compatibility(gateway, build_web_compatibility_envelope(
        gateway, capability_id="project.list.change.apply" if write else "project.list.read",
        payload={"operation": operation, "arguments": arguments}, current_user=user,
        principal=principal, request_id=request_id,
        trace_id=request.headers.get("X-Trace-ID") or request_id,
        idempotency_key=request.headers.get("X-Idempotency-Key") if write else None,
        approval_reference=request.headers.get("X-Capability-Approval") if write else None,
    ))
    if not result.ok:
        code = result.error.code if result.error else ""
        status = {"not_found": 404, "forbidden": 403, "invalid_input": 400}.get(code, 422)
        raise HTTPException(status_code=status, detail=result.error.model_dump(mode="json") if result.error else None)
    return result.data["data"]


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
async def list_cloud_lists(
    item_type: Optional[str] = Query(default=None),
    owner_team_gid: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
    request: Request = None,
    current_user: dict = Depends(get_current_user),
    principal=Depends(get_authenticated_principal),
    gateway=Depends(get_default_gateway),
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

    scope = build_access_scope(current_user)
    return await _invoke_project(request, current_user, principal, gateway, "lists.search", {
        "item_type": item_type, "owner_team_gid": owner_team_gid, "q": q, "scope": scope,
    })


def _visibility_to_read_scope(visibility: str) -> str:
    return {"public": "global", "private": "personal", "team": "team", "project": "project"}.get(visibility, "team")


def _visibility_to_write_scope(visibility: str) -> str:
    return {"public": "team", "private": "personal", "team": "team", "project": "team"}.get(visibility, "personal")


@router.post("/api/lists", status_code=201)
async def create_cloud_list(body: ListBody, request: Request, current_user: dict = Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke_project(request, current_user, principal, gateway, "lists.create", body.model_dump(), write=True)


@router.patch("/api/lists/{gid}")
async def update_cloud_list(gid: str, body: ListPatchBody, request: Request,
                            current_user: dict = Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    if body.archive:
        return await _invoke_project(request, current_user, principal, gateway, "lists.delete", {"gid": gid}, write=True)
    updates = body.model_dump(exclude_none=True)
    updates.pop("archive", None)
    return await _invoke_project(request, current_user, principal, gateway, "lists.update", {"gid": gid, "updates": updates}, write=True)


@router.delete("/api/lists/{gid}")
async def delete_cloud_list(gid: str, request: Request, current_user: dict = Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            # bop_version 软删除（保留数据，仅标记 deleted_at）
            cur.execute("SELECT gid FROM workmanship_bop_bop_versions WHERE gid = %s AND deleted_at IS NULL", (gid,))
            if cur.fetchone():
                cur.execute("UPDATE workmanship_bop_bop_versions SET deleted_at = NOW() WHERE gid = %s", (gid,))
                conn.commit()
                return {"success": True}
    return await _invoke_project(request, current_user, principal, gateway, "lists.delete", {"gid": gid}, write=True)


class RetargetBody(BaseModel):
    new_list_gid: str
    item_type: str = ""   # task | issue | "" = 两者都改


@router.post("/api/lists/{gid}/retarget")
async def retarget_cloud_list_items(gid: str, body: RetargetBody, request: Request,
                                    current_user: dict = Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    """迁移清单用：将云端条目的 list_gid 从旧清单改指向新清单（不移动条目本身）。"""
    return await _invoke_project(request, current_user, principal, gateway, "lists.retarget", {"gid": gid, **body.model_dump()}, write=True)
