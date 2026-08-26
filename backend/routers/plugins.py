"""
backend/routers/plugins.py
──────────────────────────
插件管理 API（网页版，提供 Electron 插件接口的对等实现）
"""
from fastapi import APIRouter, Depends

from backend.base.plugin_inventory import list_installed_plugins
from backend.routers.deps import get_current_user

router = APIRouter(prefix="/api/plugin", tags=["plugin"])


@router.get("/list")
def list_plugins(current_user: dict = Depends(get_current_user)):
    return list_installed_plugins()
