-- Craft-owned process resource requirement standards.
CREATE TABLE IF NOT EXISTS `workmanship_craft_resource_requirements` (
  `gid` CHAR(36) PRIMARY KEY,
  `resource_type` VARCHAR(16) NOT NULL,
  `code` VARCHAR(128) NOT NULL,
  `name` VARCHAR(255) NOT NULL,
  `attributes` JSON NOT NULL,
  `source` VARCHAR(255) NOT NULL DEFAULT 'manual',
  `status` VARCHAR(16) NOT NULL DEFAULT 'active',
  `resource_version` BIGINT NOT NULL DEFAULT 1,
  `created_by` VARCHAR(255) NOT NULL DEFAULT '',
  `updated_by` VARCHAR(255) NOT NULL DEFAULT '',
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY `uq_craft_resource_type_code` (`resource_type`, `code`),
  KEY `idx_craft_resource_status_gid` (`resource_type`, `status`, `gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `workmanship_craft_resource_aliases` (
  `gid` CHAR(36) PRIMARY KEY,
  `resource_gid` CHAR(36) NOT NULL,
  `alias_value` VARCHAR(255) NOT NULL,
  `normalized_value` VARCHAR(255) NOT NULL,
  `created_by` VARCHAR(255) NOT NULL DEFAULT '',
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY `uq_craft_resource_alias` (`resource_gid`, `normalized_value`),
  KEY `idx_craft_resource_alias_normalized` (`normalized_value`),
  CONSTRAINT `fk_craft_resource_alias_resource` FOREIGN KEY (`resource_gid`)
    REFERENCES `workmanship_craft_resource_requirements` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `workmanship_craft_tc_resource_staging` (
  `gid` CHAR(36) PRIMARY KEY,
  `version_gid` CHAR(36) NOT NULL,
  `entry_gid` CHAR(36) NOT NULL,
  `resource_type` VARCHAR(16) NOT NULL,
  `raw_name` VARCHAR(255) NOT NULL,
  `raw_payload` JSON NOT NULL,
  `match_status` VARCHAR(16) NOT NULL DEFAULT 'pending',
  `matched_resource_gid` CHAR(36) NULL,
  `candidate_resource_gids` JSON NOT NULL,
  `review_note` VARCHAR(1000) NULL,
  `resource_version` BIGINT NOT NULL DEFAULT 1,
  `decided_by` VARCHAR(255) NULL,
  `decided_at` DATETIME(6) NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  KEY `idx_craft_tc_resource_staging_version_status_gid` (`version_gid`, `match_status`, `gid`),
  KEY `idx_craft_tc_resource_staging_entry` (`entry_gid`),
  KEY `idx_craft_tc_resource_staging_matched_resource` (`matched_resource_gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Preserve existing VPPS standards while all consumers move to the governed model.
/* AI00: RESUMABLE BACKFILL */
INSERT INTO `workmanship_craft_resource_requirements`
  (`gid`,`resource_type`,`code`,`name`,`attributes`,`source`,`status`,`created_at`,`updated_at`)
SELECT
  `gid`, 'tool', COALESCE(NULLIF(`vpps`, ''), `gid`), LEFT(COALESCE(NULLIF(`name`, ''), `gid`), 255),
  JSON_OBJECT(
    'gun_model', `gun_model`, 'matou_part_no', `matou_part_no`, 'importance', `importance`,
    'gun_type', `gun_type`, 'wireless', `wireless`, 'output_square', `output_square`,
    'torque_min', `torque_min`, 'torque_recommended', `torque_recommended`,
    'cad_model_no', `cad_model_no`, 'socket_model', `socket_model`,
    'fastener_type', `fastener_type`, 'fastener_params', `fastener_params`,
    'extension_model', `extension_model`, 'socket_cad_no', `socket_cad_no`,
    'extension_cad_no', `extension_cad_no`, 'category', `category`, 'legacy_spec', `spec`
  ),
  'legacy:vpps_tools', IF(`status`='active', 'active', 'retired'), `created_at`, `created_at`
FROM `workmanship_tpl_vpps_tools`
ON DUPLICATE KEY UPDATE `resource_version`=`resource_version`;

/* AI00: RESUMABLE BACKFILL */
INSERT INTO `workmanship_craft_resource_requirements`
  (`gid`,`resource_type`,`code`,`name`,`attributes`,`source`,`status`,`created_at`,`updated_at`)
SELECT
  `gid`, 'fixture', `gid`, LEFT(COALESCE(NULLIF(`name`, ''), `gid`), 255),
  JSON_OBJECT('category', `category`, 'legacy_spec', `spec`),
  'legacy:vpps_fixtures', IF(`status`='active', 'active', 'retired'), `created_at`, `created_at`
FROM `workmanship_tpl_vpps_fixtures`
ON DUPLICATE KEY UPDATE `resource_version`=`resource_version`;

/* AI00: RESUMABLE BACKFILL */
INSERT INTO `workmanship_craft_resource_requirements`
  (`gid`,`resource_type`,`code`,`name`,`attributes`,`source`,`status`,`created_at`,`updated_at`)
SELECT
  `gid`, 'equipment', `gid`, LEFT(COALESCE(NULLIF(`name`, ''), `gid`), 255),
  JSON_OBJECT('category', `category`, 'legacy_spec', `spec`),
  'legacy:vpps_equipments', IF(`status`='active', 'active', 'retired'), `created_at`, `created_at`
FROM `workmanship_tpl_vpps_equipments`
ON DUPLICATE KEY UPDATE `resource_version`=`resource_version`;
