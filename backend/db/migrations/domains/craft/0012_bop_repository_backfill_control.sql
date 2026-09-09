CREATE TABLE IF NOT EXISTS `workmanship_craft_bop_repository_migration_control` (
  `migration_key` VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `status` VARCHAR(32) NOT NULL DEFAULT 'report_only',
  `preliminary_high_water_gid` BIGINT UNSIGNED NULL,
  `preliminary_at` DATETIME(6) NULL,
  `fence_activation_gid` BIGINT UNSIGNED NULL,
  `final_high_water_gid` BIGINT UNSIGNED NULL,
  `fenced_at` DATETIME(6) NULL,
  `active_lease_count` INT UNSIGNED NOT NULL DEFAULT 0,
  `row_version` BIGINT UNSIGNED NOT NULL DEFAULT 1,
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`migration_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_craft_bop_repository_id_map` (
  `legacy_kind` VARCHAR(32) NOT NULL,
  `legacy_gid` BIGINT UNSIGNED NOT NULL,
  `repository_gid` BIGINT UNSIGNED NOT NULL,
  `logical_gid` BIGINT UNSIGNED NULL,
  `revision_gid` BIGINT UNSIGNED NULL,
  `source_operation_gid` BIGINT UNSIGNED NULL,
  `mapping_hash` CHAR(71) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`legacy_kind`,`legacy_gid`),
  KEY `idx_craft_bop_map_repository` (`repository_gid`,`logical_gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_craft_bop_repository_migration_leases` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `capability_id` VARCHAR(128) NOT NULL,
  `actor_gid` BIGINT UNSIGNED NOT NULL,
  `expires_at` DATETIME(6) NOT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  KEY `idx_craft_bop_migration_lease_expiry` (`expires_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_craft_bop_repository_write_journal` (
  `journal_seq` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `lease_gid` BIGINT UNSIGNED NOT NULL,
  `capability_id` VARCHAR(128) NOT NULL,
  `actor_gid` BIGINT UNSIGNED NOT NULL,
  `result_hash` CHAR(71) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `result_json` JSON NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`journal_seq`),
  UNIQUE KEY `uq_craft_bop_journal_lease` (`lease_gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_craft_bop_repository_quarantine` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `legacy_kind` VARCHAR(32) NOT NULL,
  `legacy_gid` BIGINT UNSIGNED NOT NULL,
  `reason_code` VARCHAR(64) NOT NULL,
  `details_json` JSON NOT NULL,
  `resolved_at` DATETIME(6) NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  UNIQUE KEY `uq_craft_bop_quarantine_legacy` (`legacy_kind`,`legacy_gid`,`reason_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
