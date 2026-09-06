ALTER TABLE `workmanship_sim_connector_pairings`
  ADD COLUMN `activation_challenge_hash` CHAR(64) NULL AFTER `credential_envelope_hash`,
  ADD COLUMN `activation_status` VARCHAR(32) NOT NULL DEFAULT 'not_issued' AFTER `activation_challenge_hash`,
  ADD COLUMN `activated_at` DATETIME(6) NULL AFTER `completed_at`;

ALTER TABLE `workmanship_sim_connector_bindings`
  ADD COLUMN `activated_at` DATETIME(6) NULL AFTER `last_seen_at`,
  ADD COLUMN `pending_pairing_id` VARCHAR(128) NULL AFTER `activated_at`;

CREATE TABLE IF NOT EXISTS `workmanship_sim_connector_pairing_bootstraps` (
  `bootstrap_id` VARCHAR(128) PRIMARY KEY,
  `owner_user_gid` VARCHAR(191) NOT NULL,
  `team_gid` VARCHAR(191) NOT NULL,
  `token_hash` CHAR(64) NOT NULL,
  `status` VARCHAR(32) NOT NULL,
  `pairing_id` VARCHAR(128) NULL,
  `expires_at` DATETIME(6) NOT NULL,
  `resource_version` INT NOT NULL DEFAULT 1,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY `uq_sim_connector_bootstrap_token` (`token_hash`),
  UNIQUE KEY `uq_sim_connector_bootstrap_pairing` (`pairing_id`),
  KEY `idx_sim_connector_bootstrap_owner` (`owner_user_gid`,`status`,`expires_at`),
  CHECK (`status` IN ('created','claimed','approved','credential_issued','active','cancelled','expired'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
