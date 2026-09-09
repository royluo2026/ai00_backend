from pathlib import Path


SQL = (
    Path(__file__).resolve().parents[1]
    / "db/migrations/domains/simulation/0011_simulation_workspaces.sql"
).read_text(encoding="utf-8")


def test_workspace_migration_has_private_scope_versioning_and_soft_deletion():
    for marker in (
        "workmanship_sim_workspaces",
        "tenant_gid",
        "owner_gid",
        "row_version",
        "removed_at",
        "workmanship_sim_workspace_heads",
        "UNIQUE KEY `uq_sim_workspace_owner_name`",
    ):
        assert marker in SQL


def test_vm_snapshot_schema_preserves_artifact_identity_and_algorithms():
    for marker in (
        "workmanship_sim_vm_documents",
        "workmanship_sim_vm_sessions",
        "workmanship_sim_vm_snapshots",
        "artifact_gid",
        "artifact_sha256",
        "parser_algorithm_version",
        "identity_algorithm_version",
        "workmanship_sim_vm_snapshot_heads",
    ):
        assert marker in SQL


def test_occurrence_observation_and_pose_schema_uses_decimal_string_safe_gids():
    for marker in (
        "workmanship_sim_vm_occurrences",
        "predecessor_gid",
        "catia_occurrence_name",
        "bom_line",
        "workmanship_sim_vm_observations",
        "normalized_transform_json",
        "workmanship_sim_vm_poses",
        "BIGINT UNSIGNED",
    ):
        assert marker in SQL


def test_workspace_atomic_edit_schema_has_nodes_bindings_and_idempotency():
    for marker in (
        "workmanship_sim_workspace_nodes",
        "parent_gid",
        "sort_order",
        "workmanship_sim_workspace_bindings",
        "binding_role",
        "workmanship_sim_workspace_idempotency",
        "request_hash",
        "response_json",
    ):
        assert marker in SQL


def test_freeze_and_publish_sagas_have_owned_reconciliation_state():
    for marker in (
        "workmanship_sim_workspace_freeze_outbox",
        "artifact_ref_json",
        "orphaned",
        "workmanship_sim_environment_publish_plans",
        "selection_hash",
        "craft_action_ref_json",
        "workmanship_sim_environment_publish_maps",
        "craft_node_gid",
        "workmanship_sim_environment_publish_outbox",
        "outcome_unknown",
    ):
        assert marker in SQL
