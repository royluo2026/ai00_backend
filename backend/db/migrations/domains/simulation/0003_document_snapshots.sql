-- Confirmed active VisMockup document snapshots owned by Simulation.
CREATE TABLE IF NOT EXISTS `workmanship_sim_document_snapshot_requests` (
  `snapshot_request_id` VARCHAR(128) NOT NULL,
  `request_key` VARCHAR(128) NOT NULL,
  `device_id` VARCHAR(128) NOT NULL,
  `plan_id` VARCHAR(128) NOT NULL,
  `status` VARCHAR(32) NOT NULL,
  `snapshot_hash` VARCHAR(71) NULL,
  `snapshot_json` JSON NULL,
  `failure_code` VARCHAR(128) NULL,
  `owner_gid` VARCHAR(128) NOT NULL,
  `team_gid` VARCHAR(128) NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`snapshot_request_id`),
  UNIQUE KEY `uq_sim_document_snapshot_plan` (`plan_id`),
  UNIQUE KEY `uq_sim_document_snapshot_request` (`owner_gid`,`team_gid`,`request_key`),
  CHECK (`status` IN ('queued','completed','failed','outcome_unknown'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
