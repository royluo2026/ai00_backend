"""
backend/routers/users_compat.py
───────────────────────────────
兼容旧版前端用户接口路径。

历史客户端仍会请求：
  GET /users/me
  GET /users/
当前主路径为：
  GET /auth/me
  GET /api/users/
"""
from fastapi import APIRouter, Depends

from backend.routers.deps import get_current_user, build_profile, require_role
from backend.services import user_service

router = APIRouter(prefix="/users", tags=["users_compat"])

_ADMIN_ROLES = ("super_admin", "team_admin")


@router.get("/me")
def get_me_compat(current_user: dict = Depends(get_current_user)):
    """兼容旧路径：返回当前登录用户信息。"""
    return {"success": True, "data": build_profile(current_user)}


@router.get("/")
def list_users_compat(current_user: dict = Depends(require_role(*_ADMIN_ROLES))):
    """兼容旧路径：返回用户列表（管理员权限）。"""
    users = user_service.list_users()
    return {"success": True, "data": users}
