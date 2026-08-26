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

from backend.base import grant_service
from backend.routers.deps import get_current_user, _get_user_grants

router = APIRouter(tags=["grants"])

class GrantBody(BaseModel):
    grantee_gid: str
    grant_type: str
    scope_gid: Optional[str] = None
    expires_at: Optional[str] = None
    note: str = ""


def _can_manage_grants(user: dict, target_scope_gid: Optional[str] = None) -> bool:
    return grant_service.can_manage(user, target_scope_gid)


@router.get("/api/grants/me")
def get_my_grants(current_user: dict = Depends(get_current_user)):
    """当前用户自己的 grants。"""
    return {"grants": _get_user_grants(current_user["gid"])}


@router.get("/api/grants")
def list_grants(
    user_gid: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    try:
        return grant_service.list_grants(actor=current_user, user_gid=user_gid)
    except grant_service.GrantServiceError as exc:
        raise HTTPException(status_code=403 if exc.code == "permission_denied" else 400, detail=str(exc)) from exc


@router.post("/api/grants", status_code=status.HTTP_201_CREATED)
def create_grant(body: GrantBody, current_user: dict = Depends(get_current_user)):
    try:
        return grant_service.create_grant(actor=current_user, **body.model_dump())
    except grant_service.GrantServiceError as exc:
        code = 403 if exc.code == "permission_denied" else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.delete("/api/grants/{gid}")
def delete_grant(gid: str, current_user: dict = Depends(get_current_user)):
    try:
        return grant_service.revoke_grant(actor=current_user, gid=gid)
    except grant_service.GrantServiceError as exc:
        code = 404 if exc.code == "resource_not_found" else 403
        raise HTTPException(status_code=code, detail=str(exc)) from exc
