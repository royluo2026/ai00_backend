CREATE TABLE IF NOT EXISTS `workmanship_craft_process_screenshots` (
  `gid` VARCHAR(64) PRIMARY KEY,
  `bop_version_gid` VARCHAR(64) NOT NULL,
  `operation_id` VARCHAR(255) NOT NULL,
  `capture_run_id` VARCHAR(64) NOT NULL,
  `artifact_ref_json` JSON NOT NULL,
  `artifact_sha256` CHAR(64) NOT NULL,
  `created_by_gid` VARCHAR(64) NOT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  UNIQUE KEY `uq_craft_process_capture` (`bop_version_gid`,`operation_id`,`capture_run_id`),
  KEY `idx_craft_process_screenshot_operation` (`bop_version_gid`,`operation_id`,`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
