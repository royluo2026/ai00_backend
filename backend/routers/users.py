"""
backend/routers/users.py
─────────────────────────
用户管理 API（超管/团队管专用）
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.services import user_service
from backend.routers.deps import get_current_user, require_role, build_profile

router = APIRouter(prefix="/api/users", tags=["users"])

_ADMIN_ROLES = ("super_admin", "team_admin")


class AssignRoleBody(BaseModel):
    new_role: str
    external_subtype: Optional[str] = None


@router.get("/")
def list_users(current_user: dict = Depends(require_role(*_ADMIN_ROLES))):
    users = user_service.list_users()
    return {"success": True, "data": users}


@router.get("/me")
def get_me(current_user: dict = Depends(get_current_user)):
    return {"success": True, "data": build_profile(current_user)}


@router.get("/search")
def search_users(
    q: str = Query("", description="搜索关键词（姓名/邮箱）"),
    limit: int = Query(10, le=50),
    current_user: dict = Depends(get_current_user),
):
    """模糊搜索用户，用于 @mention 候选人浮层。"""
    results = user_service.search_users(q, limit)
    return {"success": True, "data": [
        {"gid": u["gid"], "name": u["name"],
         "email": u["email"], "avatar_url": u.get("avatar_url", "")}
        for u in results
    ]}


@router.patch("/{user_gid}/role")
def assign_role(
    user_gid: str,
    body: AssignRoleBody,
    current_user: dict = Depends(require_role(*_ADMIN_ROLES)),
):
    try:
        updated = user_service.assign_role(
            operator_gid=current_user["gid"],
            target_gid=user_gid,
            new_role=body.new_role,
            external_subtype=body.external_subtype,
        )
        return {"success": True, "data": updated}
    except (PermissionError, ValueError) as e:
        raise HTTPException(status_code=403, detail=str(e))
