-- Immutable Connector environment and capture lifecycle owned by Simulation.
CREATE TABLE IF NOT EXISTS `workmanship_sim_connector_environments` (
  `environment_id` VARCHAR(128) NOT NULL,
  `name` VARCHAR(255) NOT NULL,
  `status` VARCHAR(32) NOT NULL DEFAULT 'active',
  `owner_gid` VARCHAR(128) NOT NULL,
  `team_gid` VARCHAR(128) NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`environment_id`),
  CHECK (`status` IN ('active','archived'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_sim_environment_manifests` (
  `environment_id` VARCHAR(128) NOT NULL,
  `environment_version` BIGINT NOT NULL,
  `manifest_hash` VARCHAR(71) NOT NULL,
  `manifest_json` JSON NOT NULL,
  `owner_gid` VARCHAR(128) NOT NULL,
  `team_gid` VARCHAR(128) NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`environment_id`, `environment_version`),
  UNIQUE KEY `uq_sim_manifest_hash` (`environment_id`, `manifest_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_sim_environment_bindings` (
  `environment_id` VARCHAR(128) NOT NULL,
  `environment_version` BIGINT NOT NULL,
  `binding_kind` VARCHAR(32) NOT NULL,
  `source_type` VARCHAR(32) NOT NULL,
  `source_code` VARCHAR(255) NOT NULL,
  `node_key` VARCHAR(255) NOT NULL,
  `binding_json` JSON NOT NULL,
  `owner_gid` VARCHAR(128) NOT NULL,
  `team_gid` VARCHAR(128) NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`environment_id`, `environment_version`, `binding_kind`, `source_type`, `source_code`),
  CHECK (`binding_kind` IN ('product','resource')),
  CHECK (`source_type` IN ('product','tool','equipment','fixture'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_sim_materialization_runs` (
  `run_id` VARCHAR(128) NOT NULL,
  `environment_id` VARCHAR(128) NOT NULL,
  `environment_version` BIGINT NOT NULL,
  `manifest_hash` VARCHAR(71) NOT NULL,
  `device_id` VARCHAR(128) NOT NULL,
  `plan_id` VARCHAR(128) NULL,
  `status` VARCHAR(32) NOT NULL,
  `failure_code` VARCHAR(128) NULL,
  `owner_gid` VARCHAR(128) NOT NULL,
  `team_gid` VARCHAR(128) NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`run_id`),
  UNIQUE KEY `uq_sim_materialization_plan` (`plan_id`),
  CHECK (`status` IN ('queued','leased','running','completed','failed','cancelled','outcome_unknown'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_sim_capture_runs` (
  `capture_run_id` VARCHAR(128) NOT NULL,
  `environment_id` VARCHAR(128) NOT NULL,
  `environment_version` BIGINT NOT NULL,
  `manifest_hash` VARCHAR(71) NOT NULL,
  `device_id` VARCHAR(128) NOT NULL,
  `plan_id` VARCHAR(128) NULL,
  `status` VARCHAR(32) NOT NULL,
  `failure_code` VARCHAR(128) NULL,
  `owner_gid` VARCHAR(128) NOT NULL,
  `team_gid` VARCHAR(128) NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`capture_run_id`),
  UNIQUE KEY `uq_sim_capture_plan` (`plan_id`),
  CHECK (`status` IN ('queued','leased','running','completed','partial','failed','cancelled','outcome_unknown'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_sim_capture_steps` (
  `capture_run_id` VARCHAR(128) NOT NULL,
  `step_id` VARCHAR(128) NOT NULL,
  `operation_id` VARCHAR(128) NOT NULL,
  `sequence` BIGINT NOT NULL,
  `status` VARCHAR(32) NOT NULL,
  `expected_scene_hash` VARCHAR(71) NOT NULL,
  `actual_scene_hash` VARCHAR(71) NULL,
  `failure_code` VARCHAR(128) NULL,
  `owner_gid` VARCHAR(128) NOT NULL,
  `team_gid` VARCHAR(128) NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`capture_run_id`, `step_id`),
  UNIQUE KEY `uq_sim_capture_operation` (`capture_run_id`, `operation_id`),
  CHECK (`status` IN ('queued','running','completed','failed','skipped','outcome_unknown'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_sim_capture_artifact_refs` (
  `capture_run_id` VARCHAR(128) NOT NULL,
  `step_id` VARCHAR(128) NOT NULL,
  `operation_id` VARCHAR(128) NOT NULL,
  `artifact_id` VARCHAR(128) NOT NULL,
  `artifact_version` BIGINT NOT NULL,
  `artifact_sha256` CHAR(64) NOT NULL,
  `artifact_ref_json` JSON NOT NULL,
  `craft_attachment_status` VARCHAR(32) NOT NULL DEFAULT 'pending',
  `owner_gid` VARCHAR(128) NOT NULL,
  `team_gid` VARCHAR(128) NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`capture_run_id`, `step_id`, `artifact_id`, `artifact_version`),
  UNIQUE KEY `uq_sim_capture_artifact_hash` (`capture_run_id`, `step_id`, `artifact_sha256`),
  CHECK (`craft_attachment_status` IN ('pending','attached','failed'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
