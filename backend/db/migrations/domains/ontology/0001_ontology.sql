-- Independent Ontology database; applied only with AI00_ONTOLOGY_DDL_DB_URL.
CREATE TABLE IF NOT EXISTS `workmanship_ontology_schema_migrations` (
  `version` VARCHAR(128) PRIMARY KEY,
  `checksum` CHAR(64) NOT NULL,
  `applied_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS `workmanship_base_ontology_releases` (
  `gid` VARCHAR(128) PRIMARY KEY,
  `parent_release_gid` VARCHAR(128) NULL,
  `source` VARCHAR(64) NOT NULL,
  `source_gid` VARCHAR(128) NULL,
  `content_sha256` CHAR(64) NOT NULL,
  `object_count` BIGINT NOT NULL,
  `ois_object_key` VARCHAR(1024) NOT NULL,
  `created_by` VARCHAR(128) NOT NULL,
  `revision_commit_id` VARCHAR(64) NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  UNIQUE KEY `uq_ontology_release_hash` (`content_sha256`),
  UNIQUE KEY `uq_ontology_release_source` (`source`, `source_gid`),
  INDEX `idx_ontology_release_parent` (`parent_release_gid`, `created_at`),
  INDEX `idx_ontology_release_revision_commit` (`revision_commit_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `workmanship_base_ontology_release_objects` (
  `release_gid` VARCHAR(128) NOT NULL,
  `object_kind` VARCHAR(32) NOT NULL,
  `stable_object_gid` VARCHAR(128) NOT NULL,
  `object_sha256` CHAR(64) NOT NULL,
  `object_json` JSON NOT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`release_gid`, `object_kind`, `stable_object_gid`),
  INDEX `idx_ontology_object_identity` (`object_kind`, `stable_object_gid`, `release_gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `workmanship_base_ontology_change_proposals` (
  `gid` VARCHAR(128) PRIMARY KEY,
  `base_release_gid` VARCHAR(128) NOT NULL,
  `status` VARCHAR(32) NOT NULL DEFAULT 'draft',
  `author_gid` VARCHAR(128) NOT NULL,
  `channel` VARCHAR(32) NOT NULL DEFAULT 'web',
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  INDEX `idx_ontology_proposal_base` (`base_release_gid`, `status`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `workmanship_base_ontology_proposal_revisions` (
  `gid` VARCHAR(128) PRIMARY KEY,
  `proposal_gid` VARCHAR(128) NOT NULL,
  `revision_no` BIGINT NOT NULL,
  `content_sha256` CHAR(64) NOT NULL,
  `changes_json` JSON NOT NULL,
  `evidence_json` JSON NULL,
  `created_by` VARCHAR(128) NOT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  UNIQUE KEY `uq_ontology_proposal_revision` (`proposal_gid`, `revision_no`),
  UNIQUE KEY `uq_ontology_proposal_revision_hash` (`proposal_gid`, `content_sha256`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `workmanship_base_ontology_proposal_reviews` (
  `gid` VARCHAR(128) PRIMARY KEY,
  `proposal_gid` VARCHAR(128) NOT NULL,
  `proposal_revision_gid` VARCHAR(128) NOT NULL,
  `content_sha256` CHAR(64) NOT NULL,
  `decision` VARCHAR(32) NOT NULL,
  `reviewer_gid` VARCHAR(128) NOT NULL,
  `comment` TEXT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  UNIQUE KEY `uq_ontology_review` (`proposal_revision_gid`, `reviewer_gid`),
  INDEX `idx_ontology_review_proposal` (`proposal_gid`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `workmanship_base_ontology_active_refs` (
  `ref_name` VARCHAR(128) PRIMARY KEY,
  `release_gid` VARCHAR(128) NOT NULL,
  `release_sha256` CHAR(64) NOT NULL,
  `updated_by` VARCHAR(128) NOT NULL,
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  INDEX `idx_ontology_active_release` (`release_gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `workmanship_onto_classes` (
  `gid` CHAR(36) PRIMARY KEY,
  `name` VARCHAR(512) NOT NULL DEFAULT '',
  `label_zh` VARCHAR(512) NOT NULL DEFAULT '',
  `label_en` VARCHAR(512) NOT NULL DEFAULT '',
  `parent_gid` CHAR(36) DEFAULT NULL,
  `node_type_binding` TEXT,
  `is_abstract` TINYINT(1) NOT NULL DEFAULT 0,
  `color` TEXT,
  `icon` TEXT,
  `description` VARCHAR(2048) NOT NULL DEFAULT '',
  `sort_order` INT NOT NULL DEFAULT 0,
  `abbr` TEXT,
  `ai00_level` INT DEFAULT NULL,
  `display_layer` TEXT,
  `stats_priority` INT DEFAULT 99,
  `is_hidden_in_layout` TINYINT(1) NOT NULL DEFAULT 0,
  `suggested_child_type` TEXT,
  `entity_table` TEXT,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  INDEX `idx_onto_classes_parent` (`parent_gid`),
  INDEX `idx_onto_classes_binding` (`node_type_binding`(64)),
  INDEX `idx_onto_classes_entity_table` (`entity_table`(128))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `workmanship_onto_properties` (
  `gid` CHAR(36) PRIMARY KEY,
  `class_gid` CHAR(36) NOT NULL,
  `name` TEXT NOT NULL,
  `label_zh` VARCHAR(512) NOT NULL DEFAULT '',
  `prop_kind` VARCHAR(255) NOT NULL DEFAULT 'data',
  `data_type` TEXT,
  `range_class_gid` CHAR(36) DEFAULT NULL,
  `enum_values` JSON NOT NULL,
  `required` TINYINT(1) NOT NULL DEFAULT 0,
  `min_val` DOUBLE DEFAULT NULL,
  `max_val` DOUBLE DEFAULT NULL,
  `description` VARCHAR(2048) NOT NULL DEFAULT '',
  `sort_order` INT NOT NULL DEFAULT 0,
  `storage_hint` VARCHAR(255) NOT NULL DEFAULT 'meta',
  `field_widget` VARCHAR(255) NOT NULL DEFAULT 'text',
  `field_config` JSON NOT NULL,
  `show_in_create_dialog` TINYINT(1) NOT NULL DEFAULT 1,
  `dialog_order` INT NOT NULL DEFAULT 99,
  `show_in_detail` TINYINT(1) NOT NULL DEFAULT 1,
  `detail_order` INT NOT NULL DEFAULT 99,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  INDEX `idx_onto_props_class` (`class_gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `workmanship_onto_relations` (
  `gid` CHAR(36) PRIMARY KEY,
  `name` TEXT NOT NULL,
  `label_zh` VARCHAR(512) NOT NULL DEFAULT '',
  `domain_class_gid` CHAR(36) DEFAULT NULL,
  `range_class_gid` CHAR(36) DEFAULT NULL,
  `is_functional` TINYINT(1) NOT NULL DEFAULT 0,
  `inverse_of_gid` CHAR(36) DEFAULT NULL,
  `description` VARCHAR(2048) NOT NULL DEFAULT '',
  `link_type_binding` TEXT,
  `deep_copy_on_fork` TINYINT(1) NOT NULL DEFAULT 0,
  `shared_on_fork` TINYINT(1) NOT NULL DEFAULT 0,
  `skip_on_fork` TINYINT(1) NOT NULL DEFAULT 0,
  `snapshot_on_freeze` TINYINT(1) NOT NULL DEFAULT 0,
  `sort_order` INT NOT NULL DEFAULT 0,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `workmanship_onto_axioms` (
  `gid` CHAR(36) PRIMARY KEY,
  `class_gid` CHAR(36) NOT NULL,
  `axiom_type` TEXT NOT NULL,
  `target_gid` CHAR(36) DEFAULT NULL,
  `expression` TEXT,
  `description` VARCHAR(2048) NOT NULL DEFAULT '',
  `property_gid` CHAR(36) DEFAULT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
