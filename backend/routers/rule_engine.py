"""Compatibility import; the rule-engine HTTP adapter is Craft-owned."""

from plugins.craft.craft_backend.routers.rule_engine import router

__all__ = ["router"]
