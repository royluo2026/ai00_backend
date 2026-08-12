-- Independent Factory database. Apply with the Factory DDL credential only.
CREATE TABLE IF NOT EXISTS `workmanship_factory_schema_migrations` (
  `version` VARCHAR(128) PRIMARY KEY,
  `checksum` CHAR(64) NOT NULL,
  `applied_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS `workmanship_factory_structures` (
  `gid` VARCHAR(64) PRIMARY KEY,
  `kind` ENUM('factory','section','line','station') NOT NULL,
  `name` VARCHAR(255) NOT NULL,
  `parent_gid` VARCHAR(64) NULL,
  `tenant_gid` VARCHAR(64) NOT NULL,
  `version` BIGINT NOT NULL DEFAULT 1,
  `archived` BOOLEAN NOT NULL DEFAULT FALSE,
  `attributes` JSON NOT NULL,
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY `uq_factory_structure_parent_name` (`tenant_gid`,`parent_gid`,`kind`,`name`),
  KEY `idx_factory_structure_parent` (`tenant_gid`,`parent_gid`,`kind`,`archived`)
);

CREATE TABLE IF NOT EXISTS `workmanship_factory_resource_catalog` (
  `gid` VARCHAR(64) PRIMARY KEY,
  `resource_type` ENUM('equipment','tool','fixture') NOT NULL,
  `name` VARCHAR(255) NOT NULL,
  `revision` BIGINT NOT NULL DEFAULT 1,
  `status` ENUM('draft','published','deprecated') NOT NULL DEFAULT 'draft',
  `specification` JSON NOT NULL,
  `tenant_gid` VARCHAR(64) NOT NULL,
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY `idx_factory_catalog_search` (`tenant_gid`,`resource_type`,`status`,`name`)
);

CREATE TABLE IF NOT EXISTS `workmanship_factory_assets` (
  `gid` VARCHAR(64) PRIMARY KEY,
  `asset_no` VARCHAR(128) NOT NULL,
  `asset_type` ENUM('equipment','tool','fixture') NOT NULL,
  `catalog_gid` VARCHAR(64) NULL,
  `status` ENUM('in_use','maintenance','scrapped') NOT NULL DEFAULT 'in_use',
  `tenant_gid` VARCHAR(64) NOT NULL,
  `version` BIGINT NOT NULL DEFAULT 1,
  `meta` JSON NOT NULL,
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY `uq_factory_asset_no` (`tenant_gid`,`asset_no`),
  KEY `idx_factory_asset_search` (`tenant_gid`,`asset_type`,`status`,`catalog_gid`)
);

-- Compatibility-owned source tables are recreated in the Factory database for
-- one-way data cutover; no cross-database views or foreign keys are used.
CREATE TABLE IF NOT EXISTS `workmanship_factory_factories` (`gid` VARCHAR(64) PRIMARY KEY, `name` VARCHAR(255) NOT NULL, `team_id` VARCHAR(64) NULL, `meta` JSON NULL, `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS `workmanship_factory_factory_sections` (`gid` VARCHAR(64) PRIMARY KEY, `name` VARCHAR(255) NOT NULL, `factory_gid` VARCHAR(64) NOT NULL, `sort_order` INT DEFAULT 0, `color` VARCHAR(32) NULL, `canvas_x` DOUBLE DEFAULT 0, `canvas_y` DOUBLE DEFAULT 0, `canvas_w` DOUBLE DEFAULT 400, `canvas_h` DOUBLE DEFAULT 300, `owner_gid` VARCHAR(64) NULL, `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS `workmanship_factory_factory_lines` (`gid` VARCHAR(64) PRIMARY KEY, `factory_gid` VARCHAR(64) NOT NULL, `name` VARCHAR(255) NOT NULL, `meta` JSON NULL, `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS `workmanship_factory_factory_stations` (`gid` VARCHAR(64) PRIMARY KEY, `code` VARCHAR(128) NOT NULL, `name` VARCHAR(255) NOT NULL, `factory_section_gid` VARCHAR(64) NOT NULL, `canvas_x` DOUBLE DEFAULT 0, `canvas_y` DOUBLE DEFAULT 0, `takt_time` DOUBLE DEFAULT 60, `height_mm` INT DEFAULT 1200, `meta` JSON NULL, `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS `workmanship_factory_factory_layout_templates` (`gid` VARCHAR(64) PRIMARY KEY, `name` VARCHAR(255) NOT NULL, `factory_gid` VARCHAR(64) NOT NULL, `team_id` VARCHAR(64) NULL, `stations` JSON NULL, `meta` JSON NULL, `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS `workmanship_factory_factory_equipments` (`gid` VARCHAR(64) PRIMARY KEY, `asset_no` VARCHAR(128) NOT NULL, `template_gid` VARCHAR(64) NULL, `status` VARCHAR(32) DEFAULT 'in_use', `meta` JSON NULL, `team_id` VARCHAR(64) NULL, `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP, `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS `workmanship_factory_factory_tools` (`gid` VARCHAR(64) PRIMARY KEY, `asset_no` VARCHAR(128) NOT NULL, `template_gid` VARCHAR(64) NULL, `status` VARCHAR(32) DEFAULT 'in_use', `meta` JSON NULL, `team_id` VARCHAR(64) NULL, `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP, `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS `workmanship_factory_factory_fixtures` (`gid` VARCHAR(64) PRIMARY KEY, `asset_no` VARCHAR(128) NOT NULL, `template_gid` VARCHAR(64) NULL, `status` VARCHAR(32) DEFAULT 'in_use', `meta` JSON NULL, `team_id` VARCHAR(64) NULL, `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP, `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP);

