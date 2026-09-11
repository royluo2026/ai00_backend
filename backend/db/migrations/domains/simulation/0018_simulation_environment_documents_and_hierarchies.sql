-- Multi-document Simulation environments and editable VisMockup alternate hierarchies.
ALTER TABLE `workmanship_sim_vm_documents`
  ADD COLUMN IF NOT EXISTS `document_role` VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'inserted' AFTER `owner_gid`;
ALTER TABLE `workmanship_sim_vm_documents`
  ADD COLUMN IF NOT EXISTS `primary_slot` TINYINT UNSIGNED NULL AFTER `document_role`;
ALTER TABLE `workmanship_sim_vm_documents`
  ADD COLUMN IF NOT EXISTS `display_name` VARCHAR(255) NOT NULL DEFAULT '' AFTER `primary_slot`;
ALTER TABLE `workmanship_sim_vm_documents`
  ADD COLUMN IF NOT EXISTS `media_type` VARCHAR(96) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'application/plmxml+xml' AFTER `display_name`;
ALTER TABLE `workmanship_sim_vm_documents`
  ADD COLUMN IF NOT EXISTS `artifact_ref_json` JSON NULL AFTER `media_type`;
ALTER TABLE `workmanship_sim_vm_documents`
  ADD COLUMN IF NOT EXISTS `content_sha256` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT '' AFTER `artifact_ref_json`;
ALTER TABLE `workmanship_sim_vm_documents`
  ADD COLUMN IF NOT EXISTS `portability` VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'portable' AFTER `content_sha256`;
ALTER TABLE `workmanship_sim_vm_documents`
  ADD COLUMN IF NOT EXISTS `sort_order` INT UNSIGNED NOT NULL DEFAULT 0 AFTER `portability`;
CREATE UNIQUE INDEX IF NOT EXISTS `uq_sim_vm_document_primary`
  ON `workmanship_sim_vm_documents` (`workspace_gid`,`primary_slot`);
CREATE INDEX IF NOT EXISTS `idx_sim_vm_document_order`
  ON `workmanship_sim_vm_documents` (`tenant_gid`,`workspace_gid`,`removed_at`,`sort_order`);

CREATE TABLE IF NOT EXISTS `workmanship_sim_workspace_hierarchies` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `workspace_gid` BIGINT UNSIGNED NOT NULL,
  `tenant_gid` BIGINT UNSIGNED NOT NULL,
  `owner_gid` BIGINT UNSIGNED NOT NULL,
  `name` VARCHAR(255) NOT NULL,
  `source_bop_repository_gid` BIGINT UNSIGNED NULL,
  `source_bop_version_gid` BIGINT UNSIGNED NULL,
  `source_bop_fork_run_gid` BIGINT UNSIGNED NULL,
  `source_bop_content_hash` CHAR(71) CHARACTER SET ascii COLLATE ascii_bin NULL,
  `projection_identity` VARCHAR(191) CHARACTER SET ascii COLLATE ascii_bin NULL,
  `status` VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'active',
  `sort_order` INT UNSIGNED NOT NULL DEFAULT 0,
  `row_version` BIGINT UNSIGNED NOT NULL DEFAULT 1,
  `removed_at` DATETIME(6) NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  KEY `idx_sim_alt_hierarchy_workspace` (`tenant_gid`,`workspace_gid`,`removed_at`,`sort_order`),
  UNIQUE KEY `uq_sim_alt_hierarchy_fork` (`workspace_gid`,`source_bop_fork_run_gid`),
  CONSTRAINT `fk_sim_alt_hierarchy_workspace` FOREIGN KEY (`workspace_gid`)
    REFERENCES `workmanship_sim_workspaces` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- A workspace GID is itself a globally unique snowflake, so it is also a safe,
-- deterministic GID for the one compatibility hierarchy created for old rows.
-- AI00: RESUMABLE BACKFILL
INSERT INTO `workmanship_sim_workspace_hierarchies`
  (`gid`,`workspace_gid`,`tenant_gid`,`owner_gid`,`name`,`projection_identity`,`sort_order`,`row_version`)
SELECT `gid`,`gid`,`tenant_gid`,`owner_gid`,'Default','legacy-default',0,1
FROM `workmanship_sim_workspaces` WHERE `removed_at` IS NULL
ON DUPLICATE KEY UPDATE `gid`=VALUES(`gid`);

ALTER TABLE `workmanship_sim_workspace_nodes`
  ADD COLUMN IF NOT EXISTS `hierarchy_gid` BIGINT UNSIGNED NULL AFTER `owner_gid`;
CREATE INDEX IF NOT EXISTS `idx_sim_workspace_node_hierarchy`
  ON `workmanship_sim_workspace_nodes` (`workspace_gid`,`hierarchy_gid`,`parent_gid`,`removed_at`);

-- AI00: RESUMABLE BACKFILL
UPDATE `workmanship_sim_workspace_nodes`
SET `hierarchy_gid`=`workspace_gid`
WHERE `hierarchy_gid` IS NULL AND `removed_at` IS NULL;

CREATE TABLE IF NOT EXISTS `workmanship_sim_workspace_placements` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `hierarchy_gid` BIGINT UNSIGNED NOT NULL,
  `workspace_gid` BIGINT UNSIGNED NOT NULL,
  `tenant_gid` BIGINT UNSIGNED NOT NULL,
  `owner_gid` BIGINT UNSIGNED NOT NULL,
  `target_node_gid` BIGINT UNSIGNED NULL,
  `parent_placement_gid` BIGINT UNSIGNED NULL,
  `source_kind` VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `source_ref_json` JSON NOT NULL,
  `transform_json` JSON NOT NULL,
  `display_name` VARCHAR(255) NOT NULL DEFAULT '',
  `sort_order` INT UNSIGNED NOT NULL DEFAULT 0,
  `row_version` BIGINT UNSIGNED NOT NULL DEFAULT 1,
  `removed_at` DATETIME(6) NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  KEY `idx_sim_placement_hierarchy` (`tenant_gid`,`hierarchy_gid`,`removed_at`,`sort_order`),
  KEY `idx_sim_placement_workspace` (`tenant_gid`,`workspace_gid`,`removed_at`),
  CONSTRAINT `fk_sim_placement_hierarchy` FOREIGN KEY (`hierarchy_gid`) REFERENCES `workmanship_sim_workspace_hierarchies` (`gid`),
  CONSTRAINT `fk_sim_placement_workspace` FOREIGN KEY (`workspace_gid`) REFERENCES `workmanship_sim_workspaces` (`gid`),
  CONSTRAINT `fk_sim_placement_target_node` FOREIGN KEY (`target_node_gid`) REFERENCES `workmanship_sim_workspace_nodes` (`gid`),
  CONSTRAINT `fk_sim_placement_parent` FOREIGN KEY (`parent_placement_gid`) REFERENCES `workmanship_sim_workspace_placements` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_sim_vm_session_documents` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `session_gid` BIGINT UNSIGNED NOT NULL,
  `document_gid` BIGINT UNSIGNED NOT NULL,
  `tenant_gid` BIGINT UNSIGNED NOT NULL,
  `owner_gid` BIGINT UNSIGNED NOT NULL,
  `document_role` VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `inserted_index` INT UNSIGNED NULL,
  `actual_identity_hash` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `actual_content_sha256` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `sync_state` VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `row_version` BIGINT UNSIGNED NOT NULL DEFAULT 1,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  UNIQUE KEY `uq_sim_session_document` (`session_gid`,`document_gid`),
  UNIQUE KEY `uq_sim_session_inserted_index` (`session_gid`,`inserted_index`),
  CONSTRAINT `fk_sim_session_document_session` FOREIGN KEY (`session_gid`) REFERENCES `workmanship_sim_vm_sessions` (`gid`),
  CONSTRAINT `fk_sim_session_document_document` FOREIGN KEY (`document_gid`) REFERENCES `workmanship_sim_vm_documents` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_sim_materialization_verifications` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `workspace_gid` BIGINT UNSIGNED NOT NULL,
  `version_gid` BIGINT UNSIGNED NOT NULL,
  `tenant_gid` BIGINT UNSIGNED NOT NULL,
  `actor_gid` BIGINT UNSIGNED NOT NULL,
  `state` VARCHAR(24) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `manifest_hash` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `runtime_package_artifact_ref_json` JSON NULL,
  `connector_device_id` VARCHAR(191) CHARACTER SET ascii COLLATE ascii_bin NULL,
  `report_json` JSON NOT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  UNIQUE KEY `uq_sim_verification_version_manifest` (`tenant_gid`,`version_gid`,`manifest_hash`),
  KEY `idx_sim_verification_workspace` (`tenant_gid`,`workspace_gid`,`state`,`updated_at`),
  CONSTRAINT `fk_sim_verification_workspace` FOREIGN KEY (`workspace_gid`) REFERENCES `workmanship_sim_workspaces` (`gid`),
  CONSTRAINT `fk_sim_verification_version` FOREIGN KEY (`version_gid`) REFERENCES `workmanship_sim_workspace_versions` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
