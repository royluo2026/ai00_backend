-- Cache revision token plus immutable VM checkpoint and difference evidence.
ALTER TABLE `workmanship_sim_workspaces`
  ADD COLUMN IF NOT EXISTS `cache_revision_hash` VARCHAR(71) CHARACTER SET ascii COLLATE ascii_bin
    NOT NULL DEFAULT 'sha256:0000000000000000000000000000000000000000000000000000000000000000'
    AFTER `row_version`;

CREATE TABLE IF NOT EXISTS `workmanship_sim_vm_checkpoints` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `snapshot_gid` BIGINT UNSIGNED NOT NULL,
  `workspace_gid` BIGINT UNSIGNED NOT NULL,
  `tenant_gid` BIGINT UNSIGNED NOT NULL,
  `created_by` BIGINT UNSIGNED NOT NULL,
  `scope` VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `name` VARCHAR(255) NOT NULL,
  `note` TEXT NULL,
  `idempotency_key` VARCHAR(191) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `request_hash` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `row_version` BIGINT UNSIGNED NOT NULL DEFAULT 1,
  `archived_at` DATETIME(6) NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  UNIQUE KEY `uq_sim_vm_checkpoint_request` (`workspace_gid`,`created_by`,`idempotency_key`),
  KEY `idx_sim_vm_checkpoint_workspace` (`workspace_gid`,`scope`,`created_at`),
  CONSTRAINT `fk_sim_vm_checkpoint_snapshot`
    FOREIGN KEY (`snapshot_gid`) REFERENCES `workmanship_sim_vm_snapshots` (`gid`),
  CONSTRAINT `fk_sim_vm_checkpoint_workspace`
    FOREIGN KEY (`workspace_gid`) REFERENCES `workmanship_sim_workspaces` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_sim_vm_diff_reports` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `workspace_gid` BIGINT UNSIGNED NOT NULL,
  `tenant_gid` BIGINT UNSIGNED NOT NULL,
  `created_by` BIGINT UNSIGNED NOT NULL,
  `before_snapshot_gid` BIGINT UNSIGNED NOT NULL,
  `after_snapshot_gid` BIGINT UNSIGNED NOT NULL,
  `report_kind` VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `algorithm_version` VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `status` VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `summary_json` JSON NOT NULL,
  `compacted_at` DATETIME(6) NULL,
  `archived_at` DATETIME(6) NULL,
  `row_version` BIGINT UNSIGNED NOT NULL DEFAULT 1,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  UNIQUE KEY `uq_sim_vm_diff_pair` (`before_snapshot_gid`,`after_snapshot_gid`,`algorithm_version`),
  KEY `idx_sim_vm_diff_workspace` (`workspace_gid`,`report_kind`,`created_at`),
  CONSTRAINT `fk_sim_vm_diff_workspace`
    FOREIGN KEY (`workspace_gid`) REFERENCES `workmanship_sim_workspaces` (`gid`),
  CONSTRAINT `fk_sim_vm_diff_before`
    FOREIGN KEY (`before_snapshot_gid`) REFERENCES `workmanship_sim_vm_snapshots` (`gid`),
  CONSTRAINT `fk_sim_vm_diff_after`
    FOREIGN KEY (`after_snapshot_gid`) REFERENCES `workmanship_sim_vm_snapshots` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_sim_vm_diff_items` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `report_gid` BIGINT UNSIGNED NOT NULL,
  `sequence` INT UNSIGNED NOT NULL,
  `change_type` VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `before_occurrence_gid` BIGINT UNSIGNED NULL,
  `after_occurrence_gid` BIGINT UNSIGNED NULL,
  `severity` VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `payload_json` JSON NOT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  UNIQUE KEY `uq_sim_vm_diff_item_sequence` (`report_gid`,`sequence`),
  KEY `idx_sim_vm_diff_item_type` (`report_gid`,`change_type`,`sequence`),
  CONSTRAINT `fk_sim_vm_diff_item_report`
    FOREIGN KEY (`report_gid`) REFERENCES `workmanship_sim_vm_diff_reports` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
