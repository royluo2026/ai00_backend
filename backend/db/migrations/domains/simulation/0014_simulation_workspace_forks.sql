-- Durable Preview/Apply plans for immutable private Simulation workspace forks.
CREATE TABLE IF NOT EXISTS `workmanship_sim_workspace_fork_plans` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `tenant_gid` BIGINT UNSIGNED NOT NULL,
  `actor_gid` BIGINT UNSIGNED NOT NULL,
  `source_workspace_gid` BIGINT UNSIGNED NOT NULL,
  `source_version_gid` BIGINT UNSIGNED NOT NULL,
  `target_name` VARCHAR(255) NOT NULL,
  `target_version_label` VARCHAR(128) NOT NULL,
  `input_hash` CHAR(71) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `plan_hash` CHAR(71) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `expires_at` DATETIME(6) NOT NULL,
  `apply_idempotency_key` VARCHAR(191) CHARACTER SET ascii COLLATE ascii_bin NULL,
  `apply_request_hash` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
  `outcome_json` JSON NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  KEY `idx_sim_workspace_fork_source` (`source_workspace_gid`,`source_version_gid`),
  KEY `idx_sim_workspace_fork_actor` (`tenant_gid`,`actor_gid`,`expires_at`),
  CONSTRAINT `fk_sim_workspace_fork_source` FOREIGN KEY (`source_workspace_gid`) REFERENCES `workmanship_sim_workspaces` (`gid`),
  CONSTRAINT `fk_sim_workspace_fork_version` FOREIGN KEY (`source_version_gid`) REFERENCES `workmanship_sim_workspace_versions` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
