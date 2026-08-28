ALTER TABLE `workmanship_int_ext_field_mappings`
 ADD COLUMN IF NOT EXISTS `revision` INT NOT NULL DEFAULT 1;

ALTER TABLE `workmanship_int_sync_runs`
 ADD COLUMN IF NOT EXISTS `target_major_version` INT NOT NULL DEFAULT 1,
 ADD COLUMN IF NOT EXISTS `idempotency_key` VARCHAR(255) NULL;

CREATE TABLE IF NOT EXISTS `workmanship_int_operations` (
 `operation_id` VARCHAR(128) PRIMARY KEY,
 `owner_gid` VARCHAR(128) NOT NULL,
 `team_gid` VARCHAR(128) NULL,
 `capability_id` VARCHAR(255) NOT NULL,
 `idempotency_key` VARCHAR(255) NOT NULL,
 `payload_hash` CHAR(64) NOT NULL,
 `status` VARCHAR(32) NOT NULL,
 `operation_version` INT NOT NULL DEFAULT 1,
 `result_json` JSON NULL,
 `error_code` VARCHAR(128) NULL,
 `created_at` DATETIME(6) NOT NULL,
 `updated_at` DATETIME(6) NOT NULL,
 UNIQUE KEY `uq_int_operation_idempotency` (`owner_gid`,`capability_id`,`idempotency_key`),
 INDEX `idx_int_operation_team_status` (`team_gid`,`status`,`updated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_int_audit_events` (
 `event_id` VARCHAR(128) PRIMARY KEY,
 `operation_id` VARCHAR(128) NOT NULL,
 `owner_gid` VARCHAR(128) NOT NULL,
 `team_gid` VARCHAR(128) NULL,
 `capability_id` VARCHAR(255) NOT NULL,
 `status` VARCHAR(32) NOT NULL,
 `operation_version` INT NOT NULL,
 `error_code` VARCHAR(128) NULL,
 `created_at` DATETIME(6) NOT NULL,
 INDEX `idx_int_audit_operation` (`operation_id`,`operation_version`),
 INDEX `idx_int_audit_owner` (`owner_gid`,`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
