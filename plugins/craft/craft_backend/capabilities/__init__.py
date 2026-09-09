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
from .bop_active_line import register_bop_active_line_capabilities
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
from .process_screenshot import register_process_screenshot_capability
from .bop_repositories import candidate_specs as bop_repository_candidate_specs
from .bop_repository_fork import candidate_specs as bop_repository_fork_candidate_specs
from .bop_vpps_groups import candidate_specs as bop_vpps_group_candidate_specs
from .bop_collaboration import candidate_specs as bop_collaboration_candidate_specs


def _authorize_bop_version(resource_id, identity) -> bool:
    # Craft's existing BOP list/get contract is intentionally authenticated-read;
    # capability permissions still govern every write operation.
    return bool(resource_id and identity.actor.user_id)


def _authorize_repository_resource(table, resource_id, identity, *, owner_only=False) -> bool:
    if not resource_id or not identity.actor.user_id:
        return False
    from ..data.connection import get_craft_conn
    column={"workmanship_craft_bop_repositories":"gid","workmanship_craft_bop_spaces":"gid","workmanship_craft_bop_change_proposals":"gid"}[table]
    with get_craft_conn() as conn,conn.cursor() as cur:
        if table=="workmanship_craft_bop_spaces" and owner_only:
            cur.execute(
                f"SELECT 1 FROM {table} WHERE {column}=%s "
                "AND (space_kind='team' OR owner_user_gid=%s) AND deleted_at IS NULL",
                (resource_id,identity.actor.user_id),
            )
        elif table=="workmanship_craft_bop_change_proposals":
            cur.execute("SELECT 1 FROM workmanship_craft_bop_change_proposals p JOIN workmanship_craft_bop_repositories r ON r.gid=p.repository_gid WHERE p.gid=%s AND r.tenant_gid=%s AND r.deleted_at IS NULL",(resource_id,identity.tenant.tenant_id))
        else:
            cur.execute(f"SELECT 1 FROM {table} WHERE {column}=%s AND deleted_at IS NULL",(resource_id,))
        return cur.fetchone() is not None


def _authorize_repository(resource_id,identity):return _authorize_repository_resource("workmanship_craft_bop_repositories",resource_id,identity)
def _authorize_space(resource_id,identity):return _authorize_repository_resource("workmanship_craft_bop_spaces",resource_id,identity,owner_only=True)
def _authorize_proposal(resource_id,identity):return _authorize_repository_resource("workmanship_craft_bop_change_proposals",resource_id,identity)


def register_capabilities(registry: Any) -> None:
    """Register Craft-owned handlers; never mount routers or start workers."""
    resource_authorizers.register("craft-bop-version", _authorize_bop_version)
    resource_authorizers.register("craft-bop-repository", _authorize_repository)
    resource_authorizers.register("craft-bop-space", _authorize_space)
    resource_authorizers.register("craft-bop-proposal", _authorize_proposal)
    from .desktop_vpps import register_desktop_vpps
    register_desktop_vpps(registry)
    native = NativeContractRegistry(registry)
    for spec, handler in bop_repository_candidate_specs():
        native.register(spec, handler)
    for spec, handler in bop_repository_fork_candidate_specs():
        native.register(spec, handler)
    for spec, handler in bop_vpps_group_candidate_specs():
        native.register(spec, handler)
    for spec, handler in bop_collaboration_candidate_specs():
        native.register(spec, handler)
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
    register_process_screenshot_capability(registry)
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
    register_bop_active_line_capabilities(registry)
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
    for capability_id in ("craft.library.change.apply", "craft.rule.library.change.apply"):
        original = registry.get(capability_id, 1)
        from .desktop_library_v2 import change_library_v2
        handler = change_library_v2 if capability_id == "craft.library.change.apply" else original.handler
        changes = {"version": 2}
        if capability_id == "craft.rule.library.change.apply":
            changes["permissions"] = ("rule.manage",)
        native.register(original.spec.model_copy(update=changes), handler)
    versioned_resource_resolvers.register("craft.execution_plan", resolve_execution_plan_reference)
    from .desktop_exchange import register_desktop_exchange
    register_desktop_exchange(registry)
    from .desktop_attachments import register_attachments
    register_attachments(registry)
