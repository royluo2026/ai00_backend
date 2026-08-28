ALTER TABLE `workmanship_int_mapping_target_bindings`
 ADD COLUMN IF NOT EXISTS `last_idempotency_key` VARCHAR(255) NULL;

ALTER TABLE `workmanship_int_sync_runs`
 ADD COLUMN IF NOT EXISTS `claim_token` VARCHAR(128) NULL,
 ADD COLUMN IF NOT EXISTS `claimed_at` DATETIME(6) NULL,
 ADD COLUMN IF NOT EXISTS `error_code` VARCHAR(128) NULL,
 ADD COLUMN IF NOT EXISTS `attempt_count` INT NOT NULL DEFAULT 0,
 ADD COLUMN IF NOT EXISTS `next_attempt_at` DATETIME(6) NULL,
 ADD COLUMN IF NOT EXISTS `target_dispatched_at` DATETIME(6) NULL,
 ADD COLUMN IF NOT EXISTS `target_idempotency_key` VARCHAR(255) NULL;
