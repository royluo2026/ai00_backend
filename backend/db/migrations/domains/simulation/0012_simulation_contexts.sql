-- Simulation references to Craft repositories and scoped immutable workspace exports.
CREATE TABLE IF NOT EXISTS `workmanship_sim_contexts` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `workspace_gid` BIGINT UNSIGNED NOT NULL,
  `tenant_gid` BIGINT UNSIGNED NOT NULL,
  `owner_gid` BIGINT UNSIGNED NOT NULL,
  `repository_gid` BIGINT UNSIGNED NULL,
  `space_gid` BIGINT UNSIGNED NULL,
  `space_version_gid` BIGINT UNSIGNED NULL,
  `row_version` BIGINT UNSIGNED NOT NULL DEFAULT 1,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  UNIQUE KEY `uq_sim_context_workspace` (`workspace_gid`),
  CONSTRAINT `fk_sim_context_workspace` FOREIGN KEY (`workspace_gid`) REFERENCES `workmanship_sim_workspaces` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_sim_workspace_export_refs` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `workspace_gid` BIGINT UNSIGNED NOT NULL,
  `workspace_version_gid` BIGINT UNSIGNED NOT NULL,
  `tenant_gid` BIGINT UNSIGNED NOT NULL,
  `owner_gid` BIGINT UNSIGNED NOT NULL,
  `target_personal_space_gid` BIGINT UNSIGNED NOT NULL,
  `target_repository_gid` BIGINT UNSIGNED NOT NULL,
  `consumer_capability_id` VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `consumer_major_version` INT UNSIGNED NOT NULL,
  `content_hash` VARCHAR(71) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `token_digest` VARCHAR(71) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `idempotency_key` VARCHAR(191) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `expires_at` DATETIME(6) NOT NULL,
  `revoked_at` DATETIME(6) NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  UNIQUE KEY `uq_sim_export_token` (`token_digest`),
  UNIQUE KEY `uq_sim_export_idempotency` (`workspace_gid`,`owner_gid`,`idempotency_key`),
  KEY `idx_sim_export_expiry` (`expires_at`,`revoked_at`),
  CONSTRAINT `fk_sim_export_workspace` FOREIGN KEY (`workspace_gid`) REFERENCES `workmanship_sim_workspaces` (`gid`),
  CONSTRAINT `fk_sim_export_version` FOREIGN KEY (`workspace_version_gid`) REFERENCES `workmanship_sim_workspace_versions` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
