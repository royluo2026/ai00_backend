-- Device-local journal fencing and a v2 outbox separate from legacy plans.
ALTER TABLE `workmanship_sim_connector_runtime_devices`
  ADD COLUMN IF NOT EXISTS `last_journal_sequence` BIGINT NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS `workmanship_sim_connector_runtime_projection_outbox` (
  `plan_id` VARCHAR(256) CHARACTER SET ascii COLLATE ascii_bin PRIMARY KEY,
  `outcome_hash` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `target_capability` VARCHAR(191) NOT NULL,
  `attempt` INT NOT NULL DEFAULT 0,
  `status` VARCHAR(32) NOT NULL DEFAULT 'pending',
  `lease_owner` VARCHAR(191) NULL,
  `lease_until` DATETIME(6) NULL,
  `error_code` VARCHAR(128) NULL,
  `next_retry_at` DATETIME(6) NULL,
  `projected_at` DATETIME(6) NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  KEY `idx_sim_runtime_projection_claim` (`status`,`next_retry_at`,`lease_until`,`created_at`),
  CHECK (`status` IN ('pending','projecting','projected','retryable_failed','reconciliation_required'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
