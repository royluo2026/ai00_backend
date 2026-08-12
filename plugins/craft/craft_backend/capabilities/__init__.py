"""Craft-owned Capability provider entry point."""
from __future__ import annotations
from typing import Any

from .bop_compare import register_bop_compare_capability
from .bop_structure import register_bop_structure_capabilities
from .bop_versions import register_bop_version_capabilities
from .gbop_read import register_gbop_read_capabilities
from .pbom_descriptors import register_pbom_capabilities
from .bop_writes import register_bop_write_capabilities
from .provider import NativeContractRegistry
from backend.domain_ports.versioned_resources import versioned_resource_resolvers
from .bop_structure import resolve_execution_plan_reference


def register_capabilities(registry: Any) -> None:
    """Register Craft-owned handlers; never mount routers or start workers."""
    native = NativeContractRegistry(registry)
    register_bop_version_capabilities(native)
    register_bop_structure_capabilities(native)
    register_bop_compare_capability(native)
    register_pbom_capabilities(native)
    register_gbop_read_capabilities(native)
    register_bop_write_capabilities(native)
    versioned_resource_resolvers.register("craft.execution_plan", resolve_execution_plan_reference)
