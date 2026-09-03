-- Simulation-owned AI00 Connector control plane and browser pairing state.
CREATE TABLE IF NOT EXISTS `workmanship_sim_connector_bindings` (
  `connector_id` VARCHAR(128) PRIMARY KEY,
  `owner_user_gid` VARCHAR(191) NOT NULL,
  `team_gid` VARCHAR(191) NULL,
  `installation_id` VARCHAR(191) NULL,
  `windows_sid_hash` CHAR(64) NULL,
  `display_name` VARCHAR(255) NOT NULL,
  `platform` VARCHAR(64) NOT NULL DEFAULT 'windows',
  `runtime_version` VARCHAR(64) NOT NULL DEFAULT '',
  `token_hash` CHAR(64) NOT NULL,
  `capabilities` JSON NULL,
  `status` VARCHAR(32) NOT NULL DEFAULT 'offline',
  `last_seen_at` DATETIME(6) NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY `uq_sim_connector_binding_owner` (`owner_user_gid`),
  UNIQUE KEY `uq_sim_connector_binding_installation` (`installation_id`),
  KEY `idx_sim_connector_binding_status` (`status`,`last_seen_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_sim_connector_enrollments` (
  `gid` VARCHAR(128) PRIMARY KEY,
  `token_hash` CHAR(64) NOT NULL UNIQUE,
  `created_by` VARCHAR(191) NOT NULL,
  `team_gid` VARCHAR(191) NULL,
  `display_name` VARCHAR(255) NOT NULL,
  `expires_at` DATETIME(6) NOT NULL,
  `used_at` DATETIME(6) NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_sim_connector_legacy_commands` (
  `gid` VARCHAR(128) PRIMARY KEY,
  `connector_id` VARCHAR(128) NOT NULL,
  `capability_id` VARCHAR(128) NOT NULL,
  `capability_version` INT NOT NULL,
  `protocol_version` VARCHAR(64) NOT NULL,
  `payload` JSON NOT NULL,
  `payload_hash` CHAR(64) NOT NULL,
  `requested_by` VARCHAR(191) NOT NULL,
  `status` VARCHAR(32) NOT NULL DEFAULT 'queued',
  `attempts` INT NOT NULL DEFAULT 0,
  `expires_at` DATETIME(6) NOT NULL,
  `lease_id` VARCHAR(128) NULL,
  `lease_until` DATETIME(6) NULL,
  `result` JSON NULL,
  `error` VARCHAR(128) NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  KEY `idx_sim_connector_legacy_lease` (`connector_id`,`status`,`expires_at`,`created_at`),
  KEY `idx_sim_connector_legacy_owner` (`requested_by`,`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_sim_connector_health` (
  `connector_id` VARCHAR(128) PRIMARY KEY,
  `bound_user_id` VARCHAR(191) NOT NULL,
  `session_id` VARCHAR(128) NOT NULL,
  `health_json` JSON NOT NULL,
  `health_hash` VARCHAR(71) NOT NULL,
  `reported_at` DATETIME(6) NOT NULL,
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  KEY `idx_sim_connector_health_user` (`bound_user_id`,`reported_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_sim_connector_heartbeat_audit` (
  `gid` VARCHAR(128) PRIMARY KEY,
  `connector_id` VARCHAR(128) NOT NULL,
  `health_hash` VARCHAR(71) NOT NULL,
  `health_json` JSON NOT NULL,
  `reported_at` DATETIME(6) NOT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  KEY `idx_sim_connector_heartbeat_audit` (`connector_id`,`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_sim_connector_plans` (
  `plan_id` VARCHAR(128) PRIMARY KEY,
  `connector_id` VARCHAR(128) NOT NULL,
  `tenant_gid` VARCHAR(191) NOT NULL,
  `user_gid` VARCHAR(191) NOT NULL,
  `plan_hash` VARCHAR(71) NOT NULL,
  `plan_json` JSON NOT NULL,
  `status` VARCHAR(32) NOT NULL DEFAULT 'queued',
  `attempts` INT NOT NULL DEFAULT 0,
  `lease_id` VARCHAR(128) NULL,
  `lease_until` DATETIME(6) NULL,
  `outcome_json` JSON NULL,
  `outcome_hash` VARCHAR(71) NULL,
  `expires_at` DATETIME(6) NOT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  KEY `idx_sim_connector_plan_lease` (`connector_id`,`status`,`expires_at`,`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_sim_connector_projection_outbox` (
  `plan_id` VARCHAR(128) NOT NULL,
  `outcome_hash` VARCHAR(71) NOT NULL,
  `target_capability` VARCHAR(191) NOT NULL,
  `attempt` INT NOT NULL DEFAULT 0,
  `status` VARCHAR(32) NOT NULL DEFAULT 'pending',
  `lease_owner` VARCHAR(191) NULL,
  `lease_until` DATETIME(6) NULL,
  `error_code` VARCHAR(128) NULL,
  `next_retry_at` DATETIME(6) NULL,
  `projected_at` DATETIME(6) NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`plan_id`,`outcome_hash`,`target_capability`),
  KEY `idx_sim_connector_projection_claim` (`status`,`next_retry_at`,`lease_until`,`created_at`),
  CHECK (`status` IN ('pending','projecting','projected','retryable_failed','reconciliation_required'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_sim_connector_pairings` (
  `pairing_id` VARCHAR(128) PRIMARY KEY,
  `installation_id` VARCHAR(191) NOT NULL,
  `nonce_hash` CHAR(64) NOT NULL,
  `verifier_hash` CHAR(64) NOT NULL,
  `user_code_hash` CHAR(64) NOT NULL,
  `user_code_display` VARCHAR(32) NOT NULL,
  `device_name` VARCHAR(255) NOT NULL,
  `runtime_version` VARCHAR(64) NOT NULL,
  `windows_sid_hash` CHAR(64) NOT NULL,
  `masked_windows_user` VARCHAR(255) NOT NULL,
  `ephemeral_public_key` TEXT NOT NULL,
  `status` VARCHAR(32) NOT NULL DEFAULT 'pending',
  `resource_version` INT NOT NULL DEFAULT 1,
  `approved_user_gid` VARCHAR(191) NULL,
  `team_gid` VARCHAR(191) NULL,
  `connector_id` VARCHAR(128) NULL,
  `credential_envelope_json` JSON NULL,
  `credential_envelope_hash` VARCHAR(71) NULL,
  `expires_at` DATETIME(6) NOT NULL,
  `approved_at` DATETIME(6) NULL,
  `completed_at` DATETIME(6) NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY `uq_sim_connector_pairing_nonce` (`installation_id`,`nonce_hash`),
  UNIQUE KEY `uq_sim_connector_pairing_code` (`user_code_hash`),
  KEY `idx_sim_connector_pairing_expiry` (`status`,`expires_at`),
  CHECK (`status` IN ('pending','approved','completing','completed','rejected','expired','reconciliation_required'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
