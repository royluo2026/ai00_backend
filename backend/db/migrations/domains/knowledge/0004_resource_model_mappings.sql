CREATE TABLE IF NOT EXISTS `workmanship_knowledge_resource_model_mappings` (
  `gid` VARCHAR(64) PRIMARY KEY,
  `tenant_gid` VARCHAR(128) NOT NULL,
  `resource_type` VARCHAR(32) NOT NULL,
  `normalized_code` VARCHAR(255) NOT NULL,
  `model_ref_json` JSON NOT NULL,
  `mapping_version` BIGINT NOT NULL,
  `valid_from` DATETIME(6) NOT NULL,
  `valid_to` DATETIME(6) NULL,
  `content_hash` VARCHAR(71) NOT NULL,
  `created_by_gid` VARCHAR(64) NOT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  UNIQUE KEY `uq_know_resource_model_mapping` (
    `tenant_gid`, `resource_type`, `normalized_code`, `mapping_version`
  ),
  KEY `idx_know_resource_model_mapping_active` (
    `tenant_gid`, `resource_type`, `normalized_code`, `valid_from`, `valid_to`
  )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
