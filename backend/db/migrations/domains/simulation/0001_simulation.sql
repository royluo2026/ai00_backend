-- Independent Simulation database; applied only with AI00_SIMULATION_DDL_DB_URL.
CREATE TABLE IF NOT EXISTS `workmanship_sim_schema_migrations` (`version` VARCHAR(128) PRIMARY KEY, `checksum` CHAR(64) NOT NULL, `applied_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS `workmanship_sim_parameter_sets` (
 `parameter_set_id` VARCHAR(128) NOT NULL, `version` INT NOT NULL, `name` VARCHAR(255) NOT NULL,
 `content_hash` VARCHAR(71) NOT NULL, `parameters_json` JSON NOT NULL, `owner_gid` VARCHAR(128) NOT NULL,
 `team_gid` VARCHAR(128) NULL, `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY (`parameter_set_id`,`version`), UNIQUE KEY `uq_sim_parameter_hash` (`parameter_set_id`,`content_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS `workmanship_sim_profiles` (
 `profile_id` VARCHAR(128) NOT NULL, `version` INT NOT NULL, `name` VARCHAR(255) NOT NULL,
 `solver` VARCHAR(128) NOT NULL, `solver_version` VARCHAR(128) NOT NULL, `content_hash` VARCHAR(71) NOT NULL,
 `settings_json` JSON NOT NULL, `owner_gid` VARCHAR(128) NOT NULL, `team_gid` VARCHAR(128) NULL,
 `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (`profile_id`,`version`),
 UNIQUE KEY `uq_sim_profile_hash` (`profile_id`,`content_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS `workmanship_sim_environments` (
 `gid` VARCHAR(128) PRIMARY KEY, `name` VARCHAR(255) NOT NULL, `status` VARCHAR(32) NOT NULL DEFAULT 'draft',
 `owner_gid` VARCHAR(128) NOT NULL, `team_gid` VARCHAR(128) NULL, `source_bop_version_gid` VARCHAR(128) NOT NULL,
 `source_bop_revision` INT NOT NULL, `source_bop_hash` CHAR(64) NOT NULL, `execution_plan_snapshot_uri` VARCHAR(2048) NOT NULL,
 `pinned_source` JSON NOT NULL, `source_fingerprint` VARCHAR(71) NOT NULL,
 `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS `workmanship_sim_runs` (
 `run_id` VARCHAR(128) PRIMARY KEY, `environment_id` VARCHAR(128) NOT NULL, `operation_id` VARCHAR(128) NOT NULL,
 `status` VARCHAR(32) NOT NULL, `source_fingerprint` VARCHAR(71) NOT NULL, `craft_commit_ref` VARCHAR(2048) NOT NULL,
 `model_snapshot_hash` VARCHAR(71) NOT NULL, `parameter_set_id` VARCHAR(128) NOT NULL, `parameter_version` INT NOT NULL,
 `profile_id` VARCHAR(128) NOT NULL, `profile_version` INT NOT NULL, `solver` VARCHAR(128) NOT NULL,
 `solver_version` VARCHAR(128) NOT NULL, `pinned_source` JSON NOT NULL, `result_artifact_refs` JSON NOT NULL,
 `owner_gid` VARCHAR(128) NOT NULL, `team_gid` VARCHAR(128) NULL,
 `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE KEY `uq_sim_run_operation` (`operation_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
