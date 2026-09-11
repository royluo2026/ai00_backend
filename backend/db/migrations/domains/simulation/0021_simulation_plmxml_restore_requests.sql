CREATE TABLE IF NOT EXISTS `workmanship_sim_plmxml_restore_requests` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `tenant_gid` BIGINT UNSIGNED NOT NULL,
  `actor_gid` BIGINT UNSIGNED NOT NULL,
  `idempotency_key` VARCHAR(191) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `request_hash` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `workspace_gid` BIGINT UNSIGNED NOT NULL,
  `response_json` JSON NOT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `expires_at` DATETIME(6) NOT NULL,
  PRIMARY KEY (`gid`),
  UNIQUE KEY `uq_sim_plmxml_restore_actor_key` (`tenant_gid`,`actor_gid`,`idempotency_key`),
  KEY `idx_sim_plmxml_restore_workspace` (`workspace_gid`,`created_at`),
  CONSTRAINT `fk_sim_plmxml_restore_workspace` FOREIGN KEY (`workspace_gid`) REFERENCES `workmanship_sim_workspaces` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
