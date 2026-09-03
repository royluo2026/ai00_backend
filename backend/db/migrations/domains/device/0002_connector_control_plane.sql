CREATE TABLE IF NOT EXISTS `workmanship_device_connector_health` (
  `device_gid` VARCHAR(128) PRIMARY KEY,
  `bound_user_id` VARCHAR(191) NOT NULL,
  `session_id` VARCHAR(128) NOT NULL,
  `health_json` JSON NOT NULL,
  `health_hash` VARCHAR(71) NOT NULL,
  `reported_at` DATETIME(6) NOT NULL,
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  KEY `idx_device_connector_health_user` (`bound_user_id`,`reported_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_device_connector_heartbeat_audit` (
  `gid` VARCHAR(128) PRIMARY KEY,
  `device_gid` VARCHAR(128) NOT NULL,
  `health_hash` VARCHAR(71) NOT NULL,
  `health_json` JSON NOT NULL,
  `reported_at` DATETIME(6) NOT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  KEY `idx_device_connector_heartbeat_audit` (`device_gid`,`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_device_connector_plans` (
  `plan_id` VARCHAR(128) PRIMARY KEY,
  `device_gid` VARCHAR(128) NOT NULL,
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
  KEY `idx_device_connector_plan_lease` (`device_gid`,`status`,`expires_at`,`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
