"""Transitional official Provider entry point for the Base domain."""
from __future__ import annotations

from typing import Any

from backend.base.operations import register_worker_capability
from backend.capabilities.plugin_marketplace_next import register_plugin_marketplace_capabilities
from backend.capabilities.system_shared_next import register_system_shared_capabilities
from backend.plugin_platform.storage import register_plugin_storage_capabilities

def register_capabilities(registry: Any) -> None:
    register_system_shared_capabilities(registry)
    register_worker_capability(registry)
    register_plugin_marketplace_capabilities(registry)
    register_plugin_storage_capabilities(registry)


__all__ = ["register_capabilities"]
