"""Craft-owned Capability provider entry point."""
from __future__ import annotations

from typing import Any

from .bop_structure import register_bop_structure_capabilities
from .bop_versions import register_bop_version_capabilities


def register_capabilities(registry: Any) -> None:
    """Register Craft-owned handlers; never mount routers or start workers."""
    register_bop_version_capabilities(registry)
    register_bop_structure_capabilities(registry)
