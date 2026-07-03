"""
backend/routers/plugins.py
──────────────────────────
插件管理 API（网页版，提供 Electron 插件接口的对等实现）
"""
from fastapi import APIRouter, Depends

from backend.routers.deps import get_current_user

router = APIRouter(prefix="/api/plugin", tags=["plugin"])


@router.get("/list")
def list_plugins(current_user: dict = Depends(get_current_user)):
    """返回所有已安装插件列表（从 plugin_loader 读取）。"""
    from backend.main import _plugin_loader
    plugins = []
    for manifest in _plugin_loader._plugins:
        plugins.append({
            "plugin_id":   manifest.get("plugin_id", ""),
            "name":        manifest.get("name", ""),
            "version":     manifest.get("version", ""),
            "category":    manifest.get("category", "official"),
            "enabled":     True,
            "builtin":     manifest.get("category") == "official",
        })
    return {"success": True, "data": plugins}
