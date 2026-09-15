-- Durable adoption only. A governed caller must verify native session authenticity.
-- Reservations and workspace/version/head creation commit together. Retain stale
-- bindings and request results; deleting them would permit accidental recreation.
CREATE TABLE IF NOT EXISTS `workmanship_sim_live_document_bindings` (
  `tenant_gid` BIGINT UNSIGNED NOT NULL,
  `actor_gid` BIGINT UNSIGNED NOT NULL,
  `session_identity_hash` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `connector_device_id` VARCHAR(191) COLLATE utf8mb4_bin NOT NULL,
  `document_session` TEXT COLLATE utf8mb4_bin NOT NULL,
  `workspace_gid` BIGINT UNSIGNED NULL,
  `state` VARCHAR(32) NOT NULL DEFAULT 'importing',
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`tenant_gid`,`actor_gid`,`session_identity_hash`),
  CONSTRAINT `fk_sim_live_document_workspace` FOREIGN KEY (`workspace_gid`)
    REFERENCES `workmanship_sim_workspaces` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_sim_live_document_adoptions` (
  `tenant_gid` BIGINT UNSIGNED NOT NULL,
  `actor_gid` BIGINT UNSIGNED NOT NULL,
  `idempotency_key` VARCHAR(191) COLLATE utf8mb4_bin NOT NULL,
  `request_hash` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `response_json` LONGTEXT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`tenant_gid`,`actor_gid`,`idempotency_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
