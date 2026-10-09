"""
backend/routers/users.py
─────────────────────────
用户管理 API（超管/团队管专用）
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.services import user_service
from backend.routers.deps import get_current_user, require_role
from backend.base.structural_web import StructuralWebError, assign_user_role, list_admin_users
from backend.base.identity_profile import IdentityProfileError, IdentityProfileService

router = APIRouter(prefix="/api/users", tags=["users"])

_ADMIN_ROLES = ("super_admin", "team_admin")


class AssignRoleBody(BaseModel):
    new_role: str
    external_subtype: Optional[str] = None


@router.get("/")
def list_users(current_user: dict = Depends(require_role(*_ADMIN_ROLES))):
    return list_admin_users(actor=current_user)


@router.get("/me")
def get_me(current_user: dict = Depends(get_current_user)):
    try:
        return IdentityProfileService().get_current(actor=current_user)
    except IdentityProfileError as exc:
        status_code = 404 if exc.code == "identity_not_found" else 403 if exc.code == "tenant_mismatch" else 422
        raise HTTPException(status_code=status_code, detail={"code": exc.code, "message": str(exc)}) from exc


@router.get("/search")
def search_users(
    q: str = Query("", description="搜索关键词（姓名/邮箱）"),
    limit: int = Query(10, le=50),
    team_only: bool = Query(False, description="仅返回当前团队的协作者候选人"),
    current_user: dict = Depends(get_current_user),
):
    """模糊搜索用户，用于 @mention 候选人浮层。"""
    team_gid = str(current_user.get("team_id") or "") if team_only else None
    if team_only and not team_gid:
        raise HTTPException(status_code=403, detail="active team required")
    results = user_service.search_users(q, limit, team_gid=team_gid)
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
        return assign_user_role(
            actor=current_user, user_gid=user_gid,
            new_role=body.new_role, external_subtype=body.external_subtype,
        )
    except StructuralWebError as e:
        raise HTTPException(status_code=403, detail=str(e))
