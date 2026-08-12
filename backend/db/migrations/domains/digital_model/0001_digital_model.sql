-- Independent Digital Model database; applied only with AI00_DIGITAL_MODEL_DDL_DB_URL.
CREATE TABLE IF NOT EXISTS `workmanship_model_schema_migrations` (`version` VARCHAR(128) PRIMARY KEY, `checksum` CHAR(64) NOT NULL, `applied_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS `workmanship_model_models` (
 `model_id` VARCHAR(128) PRIMARY KEY, `name` VARCHAR(255) NOT NULL, `project_ref` VARCHAR(255) NOT NULL,
 `owner_gid` VARCHAR(128) NOT NULL, `team_gid` VARCHAR(128) NULL, `latest_version_id` VARCHAR(128) NULL,
 `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 INDEX `idx_model_project` (`project_ref`,`updated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS `workmanship_model_versions` (
 `version_id` VARCHAR(128) PRIMARY KEY, `model_id` VARCHAR(128) NOT NULL, `version_label` VARCHAR(128) NOT NULL,
 `parent_version_id` VARCHAR(128) NULL, `snapshot_hash` VARCHAR(72) NOT NULL, `artifact_id` VARCHAR(256) NOT NULL,
 `artifact_media_type` VARCHAR(255) NOT NULL, `artifact_sha256` CHAR(64) NOT NULL, `artifact_byte_size` BIGINT NOT NULL,
 `artifact_version` INT NOT NULL, `snapshot_json` JSON NOT NULL, `created_by` VARCHAR(128) NOT NULL,
 `published_at` DATETIME(6) NULL, `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE KEY `uq_model_snapshot_hash` (`model_id`,`snapshot_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS `workmanship_model_components` (
 `version_id` VARCHAR(128) NOT NULL, `component_id` VARCHAR(256) NOT NULL, `parent_component_id` VARCHAR(256) NULL,
 `name` VARCHAR(512) NOT NULL, `component_type` VARCHAR(64) NOT NULL, `geometry_summary` JSON NOT NULL,
 PRIMARY KEY (`version_id`,`component_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
