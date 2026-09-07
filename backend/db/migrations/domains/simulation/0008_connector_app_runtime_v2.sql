-- Additive v2 storage. Legacy connector tables remain v1 and are never copied
-- or upgraded implicitly. Binary identifiers preserve the v2 wire identity.
ALTER TABLE `workmanship_sim_connector_bindings`
  ADD COLUMN IF NOT EXISTS `protocol` VARCHAR(64) NOT NULL DEFAULT 'ai00.connector.execution-plan.v1';
ALTER TABLE `workmanship_sim_connector_plans`
  ADD COLUMN IF NOT EXISTS `protocol` VARCHAR(64) NOT NULL DEFAULT 'ai00.connector.execution-plan.v1';
ALTER TABLE `workmanship_sim_connector_pairings`
  ADD COLUMN IF NOT EXISTS `protocol` VARCHAR(64) NOT NULL DEFAULT 'ai00.connector.execution-plan.v1';
ALTER TABLE `workmanship_sim_connector_pairing_bootstraps`
  ADD COLUMN IF NOT EXISTS `protocol` VARCHAR(64) NOT NULL DEFAULT 'ai00.connector.execution-plan.v1';

CREATE TABLE IF NOT EXISTS `workmanship_sim_connector_runtime_devices` (
  `device_id` VARCHAR(256) CHARACTER SET ascii COLLATE ascii_bin PRIMARY KEY,
  `protocol` VARCHAR(64) NOT NULL,
  `owner_user_gid` VARCHAR(256) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `tenant_gid` VARCHAR(256) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `device_signing_jwk` JSON NOT NULL,
  `device_key_id` VARCHAR(256) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `credential_generation` BIGINT NOT NULL,
  `runtime_generation` BIGINT NOT NULL,
  `current_runtime_instance_id` VARCHAR(256) CHARACTER SET ascii COLLATE ascii_bin NULL,
  `session_token_hash` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
  `session_expires_at` DATETIME(6) NULL,
  `session_registered_at` DATETIME(6) NULL,
  `status` VARCHAR(32) NOT NULL,
  `activated_at` DATETIME(6) NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  UNIQUE KEY `uq_sim_runtime_session_hash` (`session_token_hash`),
  KEY `idx_sim_runtime_device_owner` (`tenant_gid`,`owner_user_gid`),
  KEY `idx_sim_runtime_session_expiry` (`status`,`session_expires_at`),
  CHECK (`protocol` = 'ai00.connector.execution-plan.v2'),
  CHECK (`credential_generation` >= 1 AND `runtime_generation` >= 1),
  CHECK (`status` IN ('pending_activation','active','revoked')),
  CHECK ((`current_runtime_instance_id` IS NULL AND `session_token_hash` IS NULL AND `session_expires_at` IS NULL)
    OR (`current_runtime_instance_id` IS NOT NULL AND `session_token_hash` IS NOT NULL AND `session_expires_at` IS NOT NULL))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_sim_connector_runtime_plans` (
  `plan_id` VARCHAR(256) CHARACTER SET ascii COLLATE ascii_bin PRIMARY KEY,
  `protocol` VARCHAR(64) NOT NULL,
  `device_id` VARCHAR(256) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `runtime_generation` BIGINT NOT NULL,
  `runtime_instance_id` VARCHAR(256) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `session_token_hash` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `tenant_gid` VARCHAR(256) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `actor_gid` VARCHAR(256) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `idempotency_key` VARCHAR(256) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `plan_hash` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `plan_json` JSON NOT NULL,
  `status` VARCHAR(32) NOT NULL,
  `lease_id` VARCHAR(256) CHARACTER SET ascii COLLATE ascii_bin NULL,
  `lease_until` DATETIME(6) NULL,
  `attempts` INT NOT NULL DEFAULT 0,
  `outcome_json` JSON NULL,
  `outcome_hash` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
  `reconciliation_state` VARCHAR(32) NOT NULL DEFAULT 'not_required',
  `reconciled_at` DATETIME(6) NULL,
  `expires_at` DATETIME(6) NOT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  UNIQUE KEY `uq_sim_runtime_plan_idempotency` (`device_id`,`idempotency_key`),
  UNIQUE KEY `uq_sim_runtime_plan_lease` (`lease_id`),
  KEY `idx_sim_runtime_plan_lease` (`device_id`,`status`,`expires_at`,`created_at`),
  CHECK (`protocol` = 'ai00.connector.execution-plan.v2'),
  CHECK (`runtime_generation` >= 1),
  CHECK (`status` IN ('queued','leased','executing','succeeded','failed_without_effect','outcome_unknown','manual_review_required','expired')),
  CHECK (`reconciliation_state` IN ('not_required','pending','succeeded','failed_without_effect','manual_review_required'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Two independent possession keys. Only public keys and nonce/challenge hashes
-- are persisted. The v1 bootstrap/status schema is deliberately not reused.
CREATE TABLE IF NOT EXISTS `workmanship_sim_connector_app_pairings` (
  `pairing_id` VARCHAR(256) CHARACTER SET ascii COLLATE ascii_bin PRIMARY KEY,
  `protocol` VARCHAR(64) NOT NULL,
  `bootstrap_encryption_jwk` JSON NOT NULL,
  `bootstrap_nonce_hash` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `device_signing_jwk` JSON NOT NULL,
  `device_key_id` VARCHAR(256) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `activation_challenge_hash` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
  `credential_envelope_json` JSON NULL,
  `credential_generation` BIGINT NULL,
  `device_id` VARCHAR(256) CHARACTER SET ascii COLLATE ascii_bin NULL,
  `owner_user_gid` VARCHAR(256) CHARACTER SET ascii COLLATE ascii_bin NULL,
  `tenant_gid` VARCHAR(256) CHARACTER SET ascii COLLATE ascii_bin NULL,
  `status` VARCHAR(32) NOT NULL,
  `resource_version` BIGINT NOT NULL DEFAULT 1,
  `expires_at` DATETIME(6) NOT NULL,
  `user_bound_at` DATETIME(6) NULL,
  `activated_at` DATETIME(6) NULL,
  `cancelled_at` DATETIME(6) NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  UNIQUE KEY `uq_sim_app_pairing_nonce` (`bootstrap_nonce_hash`),
  KEY `idx_sim_app_pairing_expiry` (`status`,`expires_at`),
  KEY `idx_sim_app_pairing_owner` (`tenant_gid`,`owner_user_gid`,`status`),
  CHECK (`protocol` = 'ai00.connector.execution-plan.v2'),
  CHECK (`status` IN ('created','user_bound','activated','expired','cancelled'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_sim_connector_runtime_recovery_sessions` (
  `device_id` VARCHAR(256) CHARACTER SET ascii COLLATE ascii_bin PRIMARY KEY,
  `protocol` VARCHAR(64) NOT NULL,
  `runtime_generation` BIGINT NOT NULL,
  `execution_instance_id` VARCHAR(256) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `execution_session_token_hash` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `recovery_instance_id` VARCHAR(256) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `plan_id` VARCHAR(256) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `token_hash` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `scope` VARCHAR(32) NOT NULL,
  `expires_at` DATETIME(6) NOT NULL,
  `consumed_at` DATETIME(6) NULL,
  `created_at` DATETIME(6) NOT NULL,
  UNIQUE KEY `uq_sim_runtime_recovery_token` (`token_hash`),
  KEY `idx_sim_runtime_recovery_plan` (`plan_id`,`expires_at`),
  CHECK (`protocol` = 'ai00.connector.execution-plan.v2'),
  CHECK (`scope` = 'plan_reconciliation')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_sim_connector_runtime_audit` (
  `audit_id` VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin PRIMARY KEY,
  `protocol` VARCHAR(64) NOT NULL,
  `device_id` VARCHAR(256) CHARACTER SET ascii COLLATE ascii_bin NULL,
  `runtime_generation` BIGINT NULL,
  `runtime_instance_id` VARCHAR(256) CHARACTER SET ascii COLLATE ascii_bin NULL,
  `recovery_instance_id` VARCHAR(256) CHARACTER SET ascii COLLATE ascii_bin NULL,
  `recovery_session_token_hash` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
  `session_token_hash` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
  `pairing_id` VARCHAR(256) CHARACTER SET ascii COLLATE ascii_bin NULL,
  `plan_id` VARCHAR(256) CHARACTER SET ascii COLLATE ascii_bin NULL,
  `event_type` VARCHAR(64) NOT NULL,
  `actor_id` VARCHAR(256) CHARACTER SET ascii COLLATE ascii_bin NULL,
  `reason` VARCHAR(1024) NULL,
  `outcome_hash` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
  `outcome_json` JSON NULL,
  `created_at` DATETIME(6) NOT NULL,
  KEY `idx_sim_runtime_audit_device` (`device_id`,`created_at`),
  KEY `idx_sim_runtime_audit_pairing` (`pairing_id`,`created_at`),
  KEY `idx_sim_runtime_audit_plan` (`plan_id`,`created_at`),
  CHECK (`protocol` = 'ai00.connector.execution-plan.v2')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
