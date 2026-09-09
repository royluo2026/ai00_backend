from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "backend/db/migrations/domains/craft/0010_bop_repositories.sql"

REQUIRED_TABLES = (
    "workmanship_craft_bop_repositories",
    "workmanship_craft_bop_spaces",
    "workmanship_craft_bop_space_heads",
    "workmanship_craft_bop_space_versions",
    "workmanship_craft_bop_nodes",
    "workmanship_craft_bop_node_revisions",
    "workmanship_craft_bop_bindings",
    "workmanship_craft_bop_binding_revisions",
    "workmanship_craft_bop_space_head_members",
    "workmanship_craft_bop_space_version_members",
    "workmanship_craft_bop_fork_workflows",
    "workmanship_craft_bop_fork_plans",
    "workmanship_craft_bop_fork_runs",
    "workmanship_craft_bop_fork_blueprint_nodes",
    "workmanship_craft_bop_vpps_groups",
    "workmanship_craft_bop_vpps_group_versions",
    "workmanship_craft_bop_vpps_group_members",
    "workmanship_craft_bop_change_proposals",
    "workmanship_craft_bop_change_proposal_units",
    "workmanship_craft_bop_change_proposal_conflicts",
    "workmanship_craft_bop_personal_import_operations",
    "workmanship_craft_bop_operation_ledger",
)


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def test_repository_schema_declares_all_owned_additive_tables():
    sql = _sql()

    for table in REQUIRED_TABLES:
        assert f"CREATE TABLE IF NOT EXISTS `{table}`" in sql
    assert "ALTER TABLE `workmanship_bop_" not in sql
    assert "DROP TABLE" not in sql.upper()


def test_repository_and_space_uniqueness_survives_tombstones():
    sql = _sql()

    assert "`active_project_slot`" in sql
    assert "UNIQUE KEY `uq_craft_bop_project_slot` (`tenant_gid`,`project_gid`,`active_project_slot`)" in sql
    assert "`active_team_slot`" in sql
    assert "UNIQUE KEY `uq_craft_bop_team_space` (`repository_gid`,`active_team_slot`)" in sql
    assert "`active_personal_owner_gid`" in sql
    assert "UNIQUE KEY `uq_craft_bop_personal_space` (`repository_gid`,`space_kind`,`active_personal_owner_gid`)" in sql


def test_identity_revision_and_membership_are_separate_and_immutable():
    sql = _sql()

    assert "`node_gid` BIGINT UNSIGNED NOT NULL" in sql
    assert "`binding_gid` BIGINT UNSIGNED NOT NULL" in sql
    assert "`node_revision_gid` BIGINT UNSIGNED NULL" in sql
    assert "`binding_revision_gid` BIGINT UNSIGNED NULL" in sql
    assert "`is_tombstone` TINYINT(1) NOT NULL DEFAULT 0" in sql
    assert "UNIQUE KEY `uq_craft_bop_head_member` (`space_head_gid`,`member_kind`,`logical_gid`)" in sql
    assert "UNIQUE KEY `uq_craft_bop_version_member` (`space_version_gid`,`member_kind`,`logical_gid`)" in sql


def test_space_versions_own_freeze_and_repository_only_owns_validated_baseline_pointer():
    sql = _sql()

    assert "`frozen_version_gid` BIGINT UNSIGNED NULL" in sql
    assert "`baseline_version_gid` BIGINT UNSIGNED NULL" in sql
    assert "`space_gid` BIGINT UNSIGNED NOT NULL" in sql
    assert "`version_kind` VARCHAR(32) NOT NULL" in sql
    assert "`manifest_hash` CHAR(71)" in sql


def test_vpps_root_scope_and_generated_initial_identity_are_database_enforced():
    sql = _sql()

    assert "`parent_scope_gid` BIGINT UNSIGNED NOT NULL" in sql
    assert "UNIQUE KEY `uq_craft_bop_vpps_sibling_order` (`group_version_gid`,`parent_scope_gid`,`order_key`)" in sql
    assert "UNIQUE KEY `uq_craft_bop_vpps_generation` (`target_group_gid`,`reference_version_gid`,`matcher_policy_hash`)" in sql


def test_proposal_status_pairs_and_fork_preview_fields_are_persisted():
    sql = _sql()

    for token in (
        "`review_status`",
        "`apply_status`",
        "`remaining_set_json`",
        "`plan_hash`",
        "`input_hash`",
        "`owner_verdicts_json`",
        "`allowed_decisions_json`",
        "`expires_at`",
        "`workflow_gid`",
    ):
        assert token in sql
