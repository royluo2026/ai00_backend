-- Craft-owned BOP Repository collaboration model. Additive only: legacy BOP tables remain unchanged.
CREATE TABLE IF NOT EXISTS `workmanship_craft_bop_repositories` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `tenant_gid` BIGINT UNSIGNED NOT NULL,
  `project_gid` BIGINT UNSIGNED NOT NULL,
  `baseline_version_gid` BIGINT UNSIGNED NULL,
  `lifecycle_status` VARCHAR(32) NOT NULL DEFAULT 'active',
  `row_version` BIGINT UNSIGNED NOT NULL DEFAULT 1,
  `deleted_at` DATETIME(6) NULL,
  `deleted_by` BIGINT UNSIGNED NULL,
  `deletion_gid` BIGINT UNSIGNED NULL,
  `active_project_slot` TINYINT GENERATED ALWAYS AS (CASE WHEN `deleted_at` IS NULL THEN 1 ELSE NULL END) STORED,
  `created_by` BIGINT UNSIGNED NOT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  UNIQUE KEY `uq_craft_bop_project_slot` (`tenant_gid`,`project_gid`,`active_project_slot`),
  CHECK (`lifecycle_status` IN ('active','archived'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_craft_bop_spaces` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `repository_gid` BIGINT UNSIGNED NOT NULL,
  `tenant_gid` BIGINT UNSIGNED NOT NULL,
  `space_kind` VARCHAR(32) NOT NULL,
  `owner_user_gid` BIGINT UNSIGNED NULL,
  `fork_base_version_gid` BIGINT UNSIGNED NULL,
  `frozen_version_gid` BIGINT UNSIGNED NULL,
  `row_version` BIGINT UNSIGNED NOT NULL DEFAULT 1,
  `deleted_at` DATETIME(6) NULL,
  `deleted_by` BIGINT UNSIGNED NULL,
  `deletion_gid` BIGINT UNSIGNED NULL,
  `active_team_slot` TINYINT GENERATED ALWAYS AS (CASE WHEN `deleted_at` IS NULL AND `space_kind`='team' THEN 1 ELSE NULL END) STORED,
  `active_personal_owner_gid` BIGINT UNSIGNED GENERATED ALWAYS AS (CASE WHEN `deleted_at` IS NULL AND `space_kind`='managed_personal' THEN `owner_user_gid` ELSE NULL END) STORED,
  `created_by` BIGINT UNSIGNED NOT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  UNIQUE KEY `uq_craft_bop_team_space` (`repository_gid`,`active_team_slot`),
  UNIQUE KEY `uq_craft_bop_personal_space` (`repository_gid`,`space_kind`,`active_personal_owner_gid`),
  KEY `idx_craft_bop_space_owner` (`tenant_gid`,`owner_user_gid`,`deleted_at`),
  CONSTRAINT `fk_craft_bop_space_repository` FOREIGN KEY (`repository_gid`) REFERENCES `workmanship_craft_bop_repositories` (`gid`),
  CHECK ((`space_kind`='team' AND `owner_user_gid` IS NULL) OR (`space_kind`='managed_personal' AND `owner_user_gid` IS NOT NULL))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_craft_bop_space_heads` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `space_gid` BIGINT UNSIGNED NOT NULL,
  `tenant_gid` BIGINT UNSIGNED NOT NULL,
  `row_version` BIGINT UNSIGNED NOT NULL DEFAULT 1,
  `content_hash` CHAR(71) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `updated_by` BIGINT UNSIGNED NOT NULL,
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  UNIQUE KEY `uq_craft_bop_space_head` (`space_gid`),
  CONSTRAINT `fk_craft_bop_head_space` FOREIGN KEY (`space_gid`) REFERENCES `workmanship_craft_bop_spaces` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_craft_bop_space_versions` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `space_gid` BIGINT UNSIGNED NOT NULL,
  `tenant_gid` BIGINT UNSIGNED NOT NULL,
  `version_kind` VARCHAR(32) NOT NULL,
  `parent_version_gid` BIGINT UNSIGNED NULL,
  `source_refs_json` JSON NOT NULL,
  `algorithm_versions_json` JSON NOT NULL,
  `manifest_artifact_ref_json` JSON NULL,
  `manifest_hash` CHAR(71) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `created_by` BIGINT UNSIGNED NOT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  UNIQUE KEY `uq_craft_bop_space_manifest` (`space_gid`,`manifest_hash`),
  KEY `idx_craft_bop_space_version` (`space_gid`,`created_at`,`gid`),
  CONSTRAINT `fk_craft_bop_version_space` FOREIGN KEY (`space_gid`) REFERENCES `workmanship_craft_bop_spaces` (`gid`),
  CHECK (`version_kind` IN ('saved','frozen','fork_base','proposal_base'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_craft_bop_nodes` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `repository_gid` BIGINT UNSIGNED NOT NULL,
  `tenant_gid` BIGINT UNSIGNED NOT NULL,
  `lineage_gid` BIGINT UNSIGNED NOT NULL,
  `derived_from_node_gid` BIGINT UNSIGNED NULL,
  `source_repository_gid` BIGINT UNSIGNED NULL,
  `source_version_gid` BIGINT UNSIGNED NULL,
  `created_by` BIGINT UNSIGNED NOT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  KEY `idx_craft_bop_node_lineage` (`repository_gid`,`lineage_gid`),
  CONSTRAINT `fk_craft_bop_node_repository` FOREIGN KEY (`repository_gid`) REFERENCES `workmanship_craft_bop_repositories` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_craft_bop_node_revisions` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `node_gid` BIGINT UNSIGNED NOT NULL,
  `tenant_gid` BIGINT UNSIGNED NOT NULL,
  `parent_node_gid` BIGINT UNSIGNED NULL,
  `node_type` VARCHAR(32) NOT NULL,
  `order_key` VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `properties_json` JSON NOT NULL,
  `content_hash` CHAR(71) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `actor_gid` BIGINT UNSIGNED NOT NULL,
  `actor_type` VARCHAR(16) NOT NULL,
  `evidence_refs_json` JSON NOT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  UNIQUE KEY `uq_craft_bop_node_revision_hash` (`node_gid`,`content_hash`),
  CONSTRAINT `fk_craft_bop_node_revision_node` FOREIGN KEY (`node_gid`) REFERENCES `workmanship_craft_bop_nodes` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_craft_bop_bindings` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `repository_gid` BIGINT UNSIGNED NOT NULL,
  `tenant_gid` BIGINT UNSIGNED NOT NULL,
  `lineage_gid` BIGINT UNSIGNED NOT NULL,
  `derived_from_binding_gid` BIGINT UNSIGNED NULL,
  `created_by` BIGINT UNSIGNED NOT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  KEY `idx_craft_bop_binding_lineage` (`repository_gid`,`lineage_gid`),
  CONSTRAINT `fk_craft_bop_binding_repository` FOREIGN KEY (`repository_gid`) REFERENCES `workmanship_craft_bop_repositories` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_craft_bop_binding_revisions` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `binding_gid` BIGINT UNSIGNED NOT NULL,
  `tenant_gid` BIGINT UNSIGNED NOT NULL,
  `source_node_gid` BIGINT UNSIGNED NOT NULL,
  `target_ref_kind` VARCHAR(32) NOT NULL,
  `target_ref_gid` BIGINT UNSIGNED NOT NULL,
  `binding_role` VARCHAR(32) NOT NULL,
  `properties_json` JSON NOT NULL,
  `content_hash` CHAR(71) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `actor_gid` BIGINT UNSIGNED NOT NULL,
  `evidence_refs_json` JSON NOT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  UNIQUE KEY `uq_craft_bop_binding_revision_hash` (`binding_gid`,`content_hash`),
  CONSTRAINT `fk_craft_bop_binding_revision_binding` FOREIGN KEY (`binding_gid`) REFERENCES `workmanship_craft_bop_bindings` (`gid`),
  CONSTRAINT `fk_craft_bop_binding_revision_source` FOREIGN KEY (`source_node_gid`) REFERENCES `workmanship_craft_bop_nodes` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_craft_bop_space_head_members` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `space_head_gid` BIGINT UNSIGNED NOT NULL,
  `member_kind` VARCHAR(16) NOT NULL,
  `logical_gid` BIGINT UNSIGNED NOT NULL,
  `node_revision_gid` BIGINT UNSIGNED NULL,
  `binding_revision_gid` BIGINT UNSIGNED NULL,
  `vpps_group_version_gid` BIGINT UNSIGNED NULL,
  `is_tombstone` TINYINT(1) NOT NULL DEFAULT 0,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  UNIQUE KEY `uq_craft_bop_head_member` (`space_head_gid`,`member_kind`,`logical_gid`),
  CONSTRAINT `fk_craft_bop_head_member_head` FOREIGN KEY (`space_head_gid`) REFERENCES `workmanship_craft_bop_space_heads` (`gid`),
  CONSTRAINT `fk_craft_bop_head_member_node_revision` FOREIGN KEY (`node_revision_gid`) REFERENCES `workmanship_craft_bop_node_revisions` (`gid`),
  CONSTRAINT `fk_craft_bop_head_member_binding_revision` FOREIGN KEY (`binding_revision_gid`) REFERENCES `workmanship_craft_bop_binding_revisions` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_craft_bop_space_version_members` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `space_version_gid` BIGINT UNSIGNED NOT NULL,
  `member_kind` VARCHAR(16) NOT NULL,
  `logical_gid` BIGINT UNSIGNED NOT NULL,
  `node_revision_gid` BIGINT UNSIGNED NULL,
  `binding_revision_gid` BIGINT UNSIGNED NULL,
  `vpps_group_version_gid` BIGINT UNSIGNED NULL,
  `is_tombstone` TINYINT(1) NOT NULL DEFAULT 0,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  UNIQUE KEY `uq_craft_bop_version_member` (`space_version_gid`,`member_kind`,`logical_gid`),
  CONSTRAINT `fk_craft_bop_version_member_version` FOREIGN KEY (`space_version_gid`) REFERENCES `workmanship_craft_bop_space_versions` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_craft_bop_fork_workflows` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `tenant_gid` BIGINT UNSIGNED NOT NULL,
  `actor_gid` BIGINT UNSIGNED NOT NULL,
  `target_project_gid` BIGINT UNSIGNED NULL,
  `include_personal_migration` TINYINT(1) NOT NULL DEFAULT 0,
  `status` VARCHAR(32) NOT NULL DEFAULT 'previewing',
  `correlation_gid` BIGINT UNSIGNED NOT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  UNIQUE KEY `uq_craft_bop_fork_correlation` (`correlation_gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_craft_bop_fork_plans` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `workflow_gid` BIGINT UNSIGNED NOT NULL,
  `tenant_gid` BIGINT UNSIGNED NOT NULL,
  `source_version_gid` BIGINT UNSIGNED NOT NULL,
  `target_project_gid` BIGINT UNSIGNED NULL,
  `fork_depth` VARCHAR(32) NOT NULL,
  `input_hash` CHAR(71) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `plan_hash` CHAR(71) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `owner_verdicts_json` JSON NOT NULL,
  `allowed_decisions_json` JSON NOT NULL,
  `expires_at` DATETIME(6) NOT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  UNIQUE KEY `uq_craft_bop_fork_plan_hash` (`workflow_gid`,`plan_hash`),
  CONSTRAINT `fk_craft_bop_fork_plan_workflow` FOREIGN KEY (`workflow_gid`) REFERENCES `workmanship_craft_bop_fork_workflows` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_craft_bop_fork_runs` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `workflow_gid` BIGINT UNSIGNED NOT NULL,
  `plan_gid` BIGINT UNSIGNED NOT NULL,
  `repository_gid` BIGINT UNSIGNED NULL,
  `step_kind` VARCHAR(32) NOT NULL,
  `status` VARCHAR(32) NOT NULL,
  `idempotency_key` VARCHAR(191) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `request_hash` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `outcome_json` JSON NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  UNIQUE KEY `uq_craft_bop_fork_step_idempotency` (`workflow_gid`,`step_kind`,`idempotency_key`),
  CONSTRAINT `fk_craft_bop_fork_run_workflow` FOREIGN KEY (`workflow_gid`) REFERENCES `workmanship_craft_bop_fork_workflows` (`gid`),
  CONSTRAINT `fk_craft_bop_fork_run_plan` FOREIGN KEY (`plan_gid`) REFERENCES `workmanship_craft_bop_fork_plans` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_craft_bop_fork_blueprint_nodes` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `fork_run_gid` BIGINT UNSIGNED NOT NULL,
  `source_node_gid` BIGINT UNSIGNED NOT NULL,
  `source_node_lineage_gid` BIGINT UNSIGNED NOT NULL,
  `parent_blueprint_gid` BIGINT UNSIGNED NULL,
  `vpps_gid` BIGINT UNSIGNED NOT NULL,
  `node_level` VARCHAR(32) NOT NULL,
  `order_key` VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  KEY `idx_craft_bop_blueprint_run` (`fork_run_gid`,`parent_blueprint_gid`,`order_key`),
  CONSTRAINT `fk_craft_bop_blueprint_run` FOREIGN KEY (`fork_run_gid`) REFERENCES `workmanship_craft_bop_fork_runs` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_craft_bop_vpps_groups` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `space_gid` BIGINT UNSIGNED NOT NULL,
  `boundary_node_gid` BIGINT UNSIGNED NOT NULL,
  `group_lineage_gid` BIGINT UNSIGNED NOT NULL,
  `derived_from_group_gid` BIGINT UNSIGNED NULL,
  `reference_group_version_gid` BIGINT UNSIGNED NULL,
  `current_group_version_gid` BIGINT UNSIGNED NULL,
  `row_version` BIGINT UNSIGNED NOT NULL DEFAULT 1,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  UNIQUE KEY `uq_craft_bop_vpps_boundary` (`space_gid`,`boundary_node_gid`),
  CONSTRAINT `fk_craft_bop_vpps_group_space` FOREIGN KEY (`space_gid`) REFERENCES `workmanship_craft_bop_spaces` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_craft_bop_vpps_group_versions` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `target_group_gid` BIGINT UNSIGNED NOT NULL,
  `version_kind` VARCHAR(32) NOT NULL,
  `parent_version_gid` BIGINT UNSIGNED NULL,
  `reference_version_gid` BIGINT UNSIGNED NULL,
  `root_scope_gid` BIGINT UNSIGNED NOT NULL,
  `matcher_policy_hash` CHAR(71) CHARACTER SET ascii COLLATE ascii_bin NULL,
  `generation_status` VARCHAR(16) NOT NULL DEFAULT 'ready',
  `content_hash` CHAR(71) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `actor_gid` BIGINT UNSIGNED NOT NULL,
  `actor_type` VARCHAR(16) NOT NULL,
  `evidence_refs_json` JSON NOT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  UNIQUE KEY `uq_craft_bop_vpps_generation` (`target_group_gid`,`reference_version_gid`,`matcher_policy_hash`),
  CONSTRAINT `fk_craft_bop_vpps_version_group` FOREIGN KEY (`target_group_gid`) REFERENCES `workmanship_craft_bop_vpps_groups` (`gid`),
  CHECK (`version_kind` IN ('reference','generated_initial','adjustment'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_craft_bop_vpps_group_members` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `group_version_gid` BIGINT UNSIGNED NOT NULL,
  `vpps_gid` BIGINT UNSIGNED NOT NULL,
  `parent_scope_gid` BIGINT UNSIGNED NOT NULL,
  `node_level` VARCHAR(32) NOT NULL,
  `order_key` VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `source_bop_node_gid` BIGINT UNSIGNED NULL,
  `source_node_lineage_gid` BIGINT UNSIGNED NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  UNIQUE KEY `uq_craft_bop_vpps_sibling_order` (`group_version_gid`,`parent_scope_gid`,`order_key`),
  CONSTRAINT `fk_craft_bop_vpps_member_version` FOREIGN KEY (`group_version_gid`) REFERENCES `workmanship_craft_bop_vpps_group_versions` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_craft_bop_change_proposals` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `repository_gid` BIGINT UNSIGNED NOT NULL,
  `personal_space_gid` BIGINT UNSIGNED NOT NULL,
  `personal_version_gid` BIGINT UNSIGNED NOT NULL,
  `team_base_version_gid` BIGINT UNSIGNED NOT NULL,
  `diff_hash` CHAR(71) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `review_status` VARCHAR(32) NOT NULL DEFAULT 'draft',
  `apply_status` VARCHAR(32) NOT NULL DEFAULT 'not_started',
  `remaining_set_json` JSON NOT NULL,
  `row_version` BIGINT UNSIGNED NOT NULL DEFAULT 1,
  `created_by` BIGINT UNSIGNED NOT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  KEY `idx_craft_bop_proposal_space` (`personal_space_gid`,`review_status`,`apply_status`),
  CONSTRAINT `fk_craft_bop_proposal_repository` FOREIGN KEY (`repository_gid`) REFERENCES `workmanship_craft_bop_repositories` (`gid`),
  CHECK (`review_status` IN ('draft','submitted','reviewing','accepted','partially_accepted','rejected','withdrawn','cancelled','superseded')),
  CHECK (`apply_status` IN ('not_started','applying','partially_applied','applied','apply_failed','reconciling'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_craft_bop_change_proposal_units` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `proposal_gid` BIGINT UNSIGNED NOT NULL,
  `component_gid` BIGINT UNSIGNED NOT NULL,
  `unit_kind` VARCHAR(32) NOT NULL,
  `payload_json` JSON NOT NULL,
  `dependencies_json` JSON NOT NULL,
  `review_decision` VARCHAR(16) NULL,
  `apply_outcome_json` JSON NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  KEY `idx_craft_bop_proposal_component` (`proposal_gid`,`component_gid`),
  CONSTRAINT `fk_craft_bop_proposal_unit_proposal` FOREIGN KEY (`proposal_gid`) REFERENCES `workmanship_craft_bop_change_proposals` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_craft_bop_change_proposal_conflicts` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `proposal_gid` BIGINT UNSIGNED NOT NULL,
  `unit_gid` BIGINT UNSIGNED NULL,
  `conflict_kind` VARCHAR(32) NOT NULL,
  `details_json` JSON NOT NULL,
  `resolution_json` JSON NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  KEY `idx_craft_bop_proposal_conflict` (`proposal_gid`,`unit_gid`),
  CONSTRAINT `fk_craft_bop_proposal_conflict_proposal` FOREIGN KEY (`proposal_gid`) REFERENCES `workmanship_craft_bop_change_proposals` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_craft_bop_personal_import_operations` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `personal_space_gid` BIGINT UNSIGNED NOT NULL,
  `source_export_ref_hash` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `source_content_hash` CHAR(71) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `preview_hash` CHAR(71) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `status` VARCHAR(32) NOT NULL,
  `idempotency_key` VARCHAR(191) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `outcome_json` JSON NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  UNIQUE KEY `uq_craft_bop_personal_import_idempotency` (`personal_space_gid`,`idempotency_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_craft_bop_operation_ledger` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `tenant_gid` BIGINT UNSIGNED NOT NULL,
  `operation_kind` VARCHAR(64) NOT NULL,
  `resource_gid` BIGINT UNSIGNED NULL,
  `idempotency_key` VARCHAR(191) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `request_hash` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `status` VARCHAR(32) NOT NULL,
  `outcome_json` JSON NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  UNIQUE KEY `uq_craft_bop_operation_idempotency` (`tenant_gid`,`operation_kind`,`idempotency_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
