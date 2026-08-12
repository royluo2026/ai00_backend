-- Independent Integration database; applied only with AI00_INTEGRATION_DDL_DB_URL.
CREATE TABLE IF NOT EXISTS `workmanship_int_schema_migrations` (`version` VARCHAR(128) PRIMARY KEY, `checksum` CHAR(64) NOT NULL, `applied_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS `workmanship_int_ext_datasources` (
 `gid` VARCHAR(128) PRIMARY KEY, `revision` INT NOT NULL DEFAULT 1, `name` VARCHAR(255) NOT NULL,
 `connector_type` VARCHAR(64) NOT NULL, `host` VARCHAR(255) NOT NULL, `port` INT NOT NULL,
 `database_name` VARCHAR(255) NOT NULL, `username` VARCHAR(255) NOT NULL, `credential_ref` VARCHAR(512) NOT NULL,
 `status` VARCHAR(32) NOT NULL DEFAULT 'untested', `archived_at` DATETIME(6) NULL,
 `owner_gid` VARCHAR(128) NOT NULL, `team_gid` VARCHAR(128) NULL,
 `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6), `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 INDEX `idx_int_connector_owner` (`owner_gid`,`updated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS `workmanship_int_ext_mappings` (
 `gid` VARCHAR(128) PRIMARY KEY, `revision` INT NOT NULL DEFAULT 1, `datasource_gid` VARCHAR(128) NOT NULL,
 `name` VARCHAR(255) NOT NULL, `source_object` VARCHAR(512) NOT NULL, `target_domain` VARCHAR(64) NOT NULL,
 `target_capability_id` VARCHAR(255) NOT NULL, `target_major_version` INT NOT NULL, `minimum_catalog_release` VARCHAR(128) NOT NULL,
 `field_mappings_json` JSON NOT NULL, `status` VARCHAR(32) NOT NULL DEFAULT 'active', `archived_at` DATETIME(6) NULL,
 `owner_gid` VARCHAR(128) NOT NULL, `team_gid` VARCHAR(128) NULL,
 `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6), `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 INDEX `idx_int_mapping_connector` (`datasource_gid`,`updated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS `workmanship_int_ext_field_mappings` (
 `gid` VARCHAR(128) PRIMARY KEY, `mapping_gid` VARCHAR(128) NOT NULL, `source_field` VARCHAR(255) NOT NULL,
 `target_field` VARCHAR(255) NOT NULL, `transform_expression` VARCHAR(1000) NULL, `sort_order` INT NOT NULL DEFAULT 0,
 INDEX `idx_int_field_mapping` (`mapping_gid`,`sort_order`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS `workmanship_int_sync_runs` (
 `run_id` VARCHAR(128) PRIMARY KEY, `mapping_gid` VARCHAR(128) NOT NULL, `operation_id` VARCHAR(128) NOT NULL,
 `status` VARCHAR(32) NOT NULL, `cursor_json` JSON NULL, `target_capability_id` VARCHAR(255) NOT NULL,
 `catalog_release` VARCHAR(128) NOT NULL, `owner_gid` VARCHAR(128) NOT NULL, `team_gid` VARCHAR(128) NULL,
 `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6), `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 UNIQUE KEY `uq_int_sync_operation` (`operation_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
