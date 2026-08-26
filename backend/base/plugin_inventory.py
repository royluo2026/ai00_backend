"""Base-owned installed-plugin projection shared by REST and Capability."""
from __future__ import annotations

from typing import Any


_loader: Any | None = None


def configure_plugin_inventory(loader: Any) -> None:
    global _loader
    _loader = loader


def list_installed_plugins() -> dict:
    if _loader is None:
        raise RuntimeError("plugin inventory is not configured")

    return {"success": True, "data": [
        {
            "plugin_id": str(manifest.get("plugin_id", "")),
            "name": str(manifest.get("name", "")),
            "version": str(manifest.get("version", "")),
            "category": str(manifest.get("category", "official")),
            "enabled": True,
            "builtin": manifest.get("category") == "official",
        }
        for manifest in _loader._plugins
    ]}


__all__ = ["configure_plugin_inventory", "list_installed_plugins"]
