"""
backend/routers/org.py
──────────────────────
组织管理 API（超管专属）

端点：
  POST /api/org/sync-from-feishu   全量同步飞书成员+部门（超管触发）
  GET  /api/org/teams              列出全部团队（含飞书部门映射）
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from pydantic import BaseModel

from backend.routers.deps import get_current_user
from backend.base.structural_web import list_organization_teams

router = APIRouter(prefix="/api/org", tags=["org"])


def _require_super_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("system_role") != "super_admin":
        raise HTTPException(status_code=403, detail="仅超管可操作")
    return current_user


class SyncFromFeishuBody(BaseModel):
    dept_id: Optional[str] = None


@router.post("/sync-from-feishu")
def sync_from_feishu(
    body: SyncFromFeishuBody = None,
    current_user: dict = Depends(_require_super_admin),
):
    """
    同步飞书组织到 AI00。
    body.dept_id: 指定根部门 open_department_id，为空时全量同步。
    """
    from backend.services.org_sync_service import sync_all_from_feishu
    root_dept_id = (body.dept_id if body else None) or None
    try:
        stats = sync_all_from_feishu(root_dept_id=root_dept_id)
        return {"ok": True, **stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/teams")
def list_teams(current_user: dict = Depends(get_current_user)):
    """列出全部团队，含飞书部门映射关系。"""
    return list_organization_teams(actor=current_user)["teams"]
