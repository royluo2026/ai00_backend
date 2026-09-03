CREATE TABLE IF NOT EXISTS `workmanship_device_connector_projection_outbox` (
  `plan_id` VARCHAR(128) NOT NULL,
  `outcome_hash` VARCHAR(71) NOT NULL,
  `target_capability` VARCHAR(191) NOT NULL,
  `attempt` INT NOT NULL,
  `status` VARCHAR(32) NOT NULL,
  `error_code` VARCHAR(128) NULL,
  `next_retry_at` DATETIME(6) NULL,
  `projected_at` DATETIME(6) NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`plan_id`, `attempt`),
  KEY `idx_connector_projection_retry` (`status`, `next_retry_at`),
  CHECK (`status` IN ('projecting','projected','retryable_failed','reconciliation_required'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
