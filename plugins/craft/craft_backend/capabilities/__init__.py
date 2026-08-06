"""Craft-owned Capability provider entry point."""
from __future__ import annotations
from typing import Any

from .bop_compare import register_bop_compare_capability
from .bop_structure import register_bop_structure_capabilities
from .bop_versions import register_bop_version_capabilities
from .gbop_read import register_gbop_read_capabilities
from .pbom_read import register_pbom_read_capabilities


def register_capabilities(registry: Any) -> None:
    """Register Craft-owned handlers; never mount routers or start workers."""
    register_bop_version_capabilities(registry)
    register_bop_structure_capabilities(registry)
    register_bop_compare_capability(registry)
    register_pbom_read_capabilities(registry)
    register_gbop_read_capabilities(registry)
