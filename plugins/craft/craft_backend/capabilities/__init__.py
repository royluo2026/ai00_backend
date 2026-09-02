"""Craft-owned Capability provider entry point."""
from __future__ import annotations
from typing import Any

from .bop_compare import register_bop_compare_capability
from .bop_structure import register_bop_structure_capabilities
from .bop_navigation import register_bop_navigation_capabilities
from .bop_entry_relations import register_bop_entry_relation_capabilities
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
from .library_read import register_craft_library_read_capability
from .library_change import register_craft_library_change_capability
from .canvas import register_canvas_capabilities
from .standard_operation import register_standard_operation_capabilities
from .vpps_audit import register_vpps_audit_capabilities
from .rule_engine import register_rule_engine_capability
from .pbom_change_point import register_pbom_change_point_capability
from .rule_library import register_rule_library_capabilities
from .gbop_catalog import register_gbop_catalog_capability
from .gbop_navigation import register_gbop_navigation_capability
from .gbop_process_hierarchy import register_gbop_process_hierarchy_capability
from .gbop_navigation_change import register_gbop_navigation_change_capability
from .bop_entry_search import register_bop_entry_search_capability
from .bop_alt_hierarchy import register_bop_alt_hierarchy_capability
from .bop_line_operation_catia import register_bop_line_operation_catia_capability
from .bop_pbom_lifecycle_read import register_bop_pbom_lifecycle_read_capability
from .bop_lifecycle_read import register_bop_lifecycle_read_capability
from .bop_lifecycle_state import register_bop_lifecycle_state_capability
from .bop_version_legacy_read import register_bop_version_legacy_read_capability
from .bop_entry_legacy_read import register_bop_entry_legacy_read_capability
from .bop_gbop_legacy_read import register_bop_gbop_legacy_read_capability
from .bop_staging_read import register_bop_staging_read_capability
from .station_autolink_preview import register_station_autolink_preview_capability
from .ebom_legacy_read import register_ebom_legacy_read_capability
from .vpps_check import register_vpps_check_capability
from .bop_fork_preset_read import register_bop_fork_preset_read_capability
from .bop_fork_preset_change import register_bop_fork_preset_change_capability
from .bop_lifecycle_change import register_bop_lifecycle_change_capability
from .bop_version_lifecycle_change import register_bop_version_lifecycle_change_capability
from .bop_version_layout_change import register_bop_version_layout_change_capability
from .bop_staging_change import register_bop_staging_change_capability
from .bop_version_freeze_change import register_bop_version_freeze_change_capability
from .bop_entry_link_change import register_bop_entry_link_change_capability
from .bop_staging_lifecycle_change import register_bop_staging_lifecycle_change_capability
from .bop_entry_change import register_bop_entry_change_capability
from .bop_picture_upload import register_bop_picture_upload_capability
from .bop_lifecycle_state_change import register_bop_lifecycle_state_change_capability
from .bop_checkpoint_change import register_bop_checkpoint_change_capability
from .bop_checkpoint_rollback import register_bop_checkpoint_rollback_capability
from .bop_lifecycle_history_change import register_bop_lifecycle_history_change_capability
from .bop_lifecycle_step_rollback import register_bop_lifecycle_step_rollback_capability
from .bop_lifecycle_stats_refresh import register_bop_lifecycle_stats_refresh_capability
from .bop_template_change import register_bop_template_change_capability
from .bop_version_snapshot_change import register_bop_version_snapshot_change_capability
from .bop_fork_change import register_bop_fork_change_capability
from .bop_entry_bulk_change import register_bop_entry_bulk_change_capability
from .bop_gbop_change import register_bop_gbop_change_capability
from .gbop_version_change import register_gbop_version_change_capability
from .gbop_entity_change import register_gbop_entity_change_capability
from .gbop_import_change import register_gbop_import_change_capability
from .gbop_station_autolink_change import register_gbop_station_autolink_change_capability
from .gbop_import_tc_change import register_gbop_import_tc_change_capability
from .ebom_change import register_ebom_change_capability
from .ebom_snapshot_change import register_ebom_snapshot_change_capabilities
from .ebom_snapshot_status_change import register_ebom_snapshot_status_change_capability
from .ebom_vpps_stats_change import register_ebom_vpps_stats_change_capability
from .ebom_part_change import register_ebom_part_change_capabilities
from .data_exchange import register_data_exchange_capability
from .lark_exchange import register_lark_exchange_capabilities
from .resource_requirements import register_resource_requirement_capabilities


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
    register_bop_navigation_capabilities(native)
    register_bop_entry_relation_capabilities(native)
    register_bop_compare_capability(native)
    register_pbom_capabilities(native)
    register_gbop_capabilities(native)
    register_rule_capabilities(native)
    register_bop_write_capabilities(native)
    register_craft_library_read_capability(native)
    register_craft_library_change_capability(native)
    register_resource_requirement_capabilities(native)
    register_canvas_capabilities(native)
    register_standard_operation_capabilities(native)
    register_vpps_audit_capabilities(native)
    register_rule_engine_capability(native)
    register_pbom_change_point_capability(native)
    register_rule_library_capabilities(native)
    register_gbop_catalog_capability(native)
    register_gbop_navigation_capability(native)
    register_gbop_process_hierarchy_capability(native)
    register_gbop_navigation_change_capability(native)
    register_bop_entry_search_capability(native)
    register_bop_alt_hierarchy_capability(native)
    register_bop_line_operation_catia_capability(native)
    register_bop_pbom_lifecycle_read_capability(native)
    register_bop_lifecycle_read_capability(native)
    register_bop_lifecycle_state_capability(native)
    register_bop_version_legacy_read_capability(native)
    register_bop_entry_legacy_read_capability(native)
    register_bop_gbop_legacy_read_capability(native)
    register_bop_staging_read_capability(native)
    register_station_autolink_preview_capability(native)
    register_ebom_legacy_read_capability(native)
    register_vpps_check_capability(native)
    register_bop_fork_preset_read_capability(native)
    register_bop_fork_preset_change_capability(native)
    register_bop_lifecycle_change_capability(native)
    register_bop_version_lifecycle_change_capability(native)
    register_bop_version_layout_change_capability(native)
    register_bop_staging_change_capability(native)
    register_bop_version_freeze_change_capability(native)
    register_bop_entry_link_change_capability(native)
    register_bop_staging_lifecycle_change_capability(native)
    register_bop_entry_change_capability(native)
    register_bop_picture_upload_capability(native)
    register_bop_lifecycle_state_change_capability(native)
    register_bop_checkpoint_change_capability(native)
    register_bop_checkpoint_rollback_capability(native)
    register_bop_lifecycle_history_change_capability(native)
    register_bop_lifecycle_step_rollback_capability(native)
    register_bop_lifecycle_stats_refresh_capability(native)
    register_bop_template_change_capability(native)
    register_bop_version_snapshot_change_capability(native)
    register_bop_fork_change_capability(native)
    register_bop_entry_bulk_change_capability(native)
    register_bop_gbop_change_capability(native)
    register_gbop_version_change_capability(native)
    register_gbop_entity_change_capability(native)
    register_gbop_import_change_capability(native)
    register_gbop_station_autolink_change_capability(native)
    register_gbop_import_tc_change_capability(native)
    register_ebom_change_capability(native)
    register_ebom_snapshot_change_capabilities(native)
    register_ebom_snapshot_status_change_capability(native)
    register_ebom_vpps_stats_change_capability(native)
    register_ebom_part_change_capabilities(native)
    register_data_exchange_capability(native)
    register_lark_exchange_capabilities(native)
    register_reviewed_capabilities(registry)
    versioned_resource_resolvers.register("craft.execution_plan", resolve_execution_plan_reference)
