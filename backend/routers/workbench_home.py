"""Compatibility route; the workbench composition belongs to Craft."""
from plugins.craft.craft_backend.routers.workbench_home import router

__all__ = ["router"]
