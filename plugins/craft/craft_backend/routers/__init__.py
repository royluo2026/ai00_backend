"""
packages/craft-plugin/craft_backend/routers/__init__.py
工艺规划插件路由入口 — 物理迁移完成，使用相对 import
"""
from .bop import router as bop_router
from .gbop import router as gbop_router
from .ebom import router as ebom_router
from .factory import router as factory_router
from .craft_library import router as craft_library_router
from .std_op import router as std_op_router
from .projects import router as projects_router
from .approval import router as approval_router
from .canvases import router as canvases_router
from .import_export import router as import_export_router
from .bitable_sync import router as bitable_sync_router
from .task_templates import router as task_templates_router
from .vpps_audit import router as vpps_audit_router
from .promotion import router as promotion_router


def get_routers():
    return [
        bop_router, gbop_router, ebom_router, factory_router,
        craft_library_router, std_op_router, projects_router,
        approval_router, canvases_router, import_export_router,
        bitable_sync_router, task_templates_router,
        vpps_audit_router, promotion_router,
    ]


# backend/main.py 自动扫描时跳过这些模块（由 PluginLoader 负责）
OWNED_MODULES = {
    "bop", "gbop", "ebom", "factory", "craft_library", "std_op",
    "projects", "approval", "canvases", "import_export",
    "bitable_sync", "task_templates", "vpps_audit", "promotion",
}
