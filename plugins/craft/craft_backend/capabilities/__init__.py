"""Craft-owned Capability provider entry point."""
from __future__ import annotations
from typing import Any

from .bop_compare import register_bop_compare_capability
from .bop_structure import register_bop_structure_capabilities
from .bop_versions import register_bop_version_capabilities
from .gbop_descriptors import register_gbop_capabilities
from .rule_descriptors import register_rule_capabilities
from .pbom_descriptors import register_pbom_capabilities
from .bop_writes import register_bop_write_capabilities
from .provider import NativeContractRegistry
from .reviewed import register_reviewed_capabilities
from backend.domain_ports.versioned_resources import versioned_resource_resolvers
from backend.domain_ports.resource_authorization import resource_authorizers
from .bop_structure import resolve_execution_plan_reference


def _authorize_bop_version(resource_id, identity) -> bool:
    # Craft's existing BOP list/get contract is intentionally authenticated-read;
    # capability permissions still govern every write operation.
    return bool(resource_id and identity.actor.user_id)


def register_capabilities(registry: Any) -> None:
    """Register Craft-owned handlers; never mount routers or start workers."""
    resource_authorizers.register("craft-bop-version", _authorize_bop_version)
    native = NativeContractRegistry(registry)
    register_bop_version_capabilities(native)
    register_bop_structure_capabilities(native)
    register_bop_compare_capability(native)
    register_pbom_capabilities(native)
    register_gbop_capabilities(native)
    register_rule_capabilities(native)
    register_bop_write_capabilities(native)
    register_reviewed_capabilities(registry)
    versioned_resource_resolvers.register("craft.execution_plan", resolve_execution_plan_reference)
