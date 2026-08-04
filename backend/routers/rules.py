"""Compatibility import; Craft owns rule CRUD and persistence."""

from plugins.craft.craft_backend.routers.rules import router

__all__ = ["router"]
