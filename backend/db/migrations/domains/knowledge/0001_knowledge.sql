-- Independent Knowledge database; applied only with AI00_KNOWLEDGE_DDL_DB_URL.
CREATE TABLE IF NOT EXISTS `workmanship_knowledge_schema_migrations` (`version` VARCHAR(128) PRIMARY KEY, `checksum` CHAR(64) NOT NULL, `applied_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP);

CREATE TABLE IF NOT EXISTS `workmanship_know_spaces` (
  `gid` VARCHAR(128) PRIMARY KEY, `tenant_gid` VARCHAR(128) NOT NULL, `name` VARCHAR(512) NOT NULL,
  `visibility` VARCHAR(32) NOT NULL DEFAULT 'team', `archived` BOOLEAN NOT NULL DEFAULT FALSE,
  `created_by` VARCHAR(128) NOT NULL, `created_at` DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY `uq_know_space_tenant_name` (`tenant_gid`,`name`)
);
CREATE TABLE IF NOT EXISTS `workmanship_know_documents` (
  `gid` VARCHAR(128) PRIMARY KEY, `tenant_gid` VARCHAR(128) NOT NULL, `space_gid` VARCHAR(128) NOT NULL,
  `title` VARCHAR(512) NOT NULL, `slug` VARCHAR(255) NOT NULL, `status` VARCHAR(32) NOT NULL DEFAULT 'draft',
  `current_revision_gid` VARCHAR(128) NULL, `published_revision_gid` VARCHAR(128) NULL, `source_entry_gid` VARCHAR(128) NULL,
  `created_by` VARCHAR(128) NOT NULL, `created_at` DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY `uq_know_document_space_slug` (`space_gid`,`slug`), UNIQUE KEY `uq_know_document_source` (`source_entry_gid`)
);
CREATE TABLE IF NOT EXISTS `workmanship_know_revisions` (
  `gid` VARCHAR(128) PRIMARY KEY, `tenant_gid` VARCHAR(128) NOT NULL, `space_gid` VARCHAR(128) NOT NULL,
  `document_gid` VARCHAR(128) NOT NULL, `revision_no` BIGINT NOT NULL, `base_revision_gid` VARCHAR(128) NULL,
  `restored_from_revision_gid` VARCHAR(128) NULL, `proposal_gid` VARCHAR(128) NULL, `object_key` VARCHAR(1024) NOT NULL,
  `content_sha256` CHAR(64) NOT NULL, `byte_size` BIGINT NOT NULL, `media_type` VARCHAR(128) NOT NULL,
  `state` VARCHAR(32) NOT NULL DEFAULT 'draft', `created_by` VARCHAR(128) NOT NULL, `channel` VARCHAR(32) NOT NULL DEFAULT 'web',
  `delegated_user_gid` VARCHAR(128) NULL, `agent_run_gid` VARCHAR(128) NULL, `plugin_id` VARCHAR(128) NULL,
  `plugin_version` VARCHAR(128) NULL, `request_id` VARCHAR(128) NULL, `before_sha256` CHAR(64) NULL,
  `after_sha256` CHAR(64) NULL, `change_summary` VARCHAR(2048) NULL, `created_at` DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6),
  UNIQUE KEY `uq_know_revision_number` (`document_gid`,`revision_no`), UNIQUE KEY `uq_know_revision_object` (`object_key`)
);
CREATE TABLE IF NOT EXISTS `workmanship_know_document_acl` (
  `document_gid` VARCHAR(128) NOT NULL, `subject_type` VARCHAR(32) NOT NULL, `subject_gid` VARCHAR(128) NOT NULL,
  `permission` VARCHAR(32) NOT NULL, `created_by` VARCHAR(128) NOT NULL, `created_at` DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`document_gid`,`subject_type`,`subject_gid`)
);
CREATE TABLE IF NOT EXISTS `workmanship_know_entries` (
  `gid` VARCHAR(128) PRIMARY KEY, `display_id` VARCHAR(128) NULL, `title` VARCHAR(512) NOT NULL,
  `entry_type` VARCHAR(64) NOT NULL, `status` VARCHAR(32) NOT NULL DEFAULT 'draft', `share_scope` VARCHAR(32) NOT NULL DEFAULT 'personal',
  `tags` JSON NULL, `creator_gid` VARCHAR(128) NOT NULL, `team_id` VARCHAR(128) NULL, `content_md` LONGTEXT NULL,
  `content_ref` VARCHAR(2048) NULL, `source_gid` VARCHAR(128) NULL, `created_at` DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
);
CREATE TABLE IF NOT EXISTS `workmanship_know_folders` (
  `gid` VARCHAR(128) PRIMARY KEY, `name` VARCHAR(512) NOT NULL, `parent_gid` VARCHAR(128) NULL,
  `scope_type` VARCHAR(32) NOT NULL DEFAULT 'personal', `owner_user_gid` VARCHAR(128) NULL, `team_id` VARCHAR(128) NULL,
  `created_by` VARCHAR(128) NOT NULL, `created_at` DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
);
CREATE TABLE IF NOT EXISTS `workmanship_know_items` (
  `gid` VARCHAR(128) PRIMARY KEY, `folder_gid` VARCHAR(128) NULL, `title` VARCHAR(512) NOT NULL, `item_type` VARCHAR(64) NOT NULL,
  `scope_type` VARCHAR(32) NOT NULL DEFAULT 'personal', `owner_user_gid` VARCHAR(128) NULL, `team_id` VARCHAR(128) NULL,
  `creator_gid` VARCHAR(128) NOT NULL, `content` LONGTEXT NULL, `is_system` BOOLEAN NOT NULL DEFAULT FALSE,
  `created_at` DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6), `updated_at` DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
);
CREATE TABLE IF NOT EXISTS `workmanship_know_favorites` (
  `user_gid` VARCHAR(128) NOT NULL, `item_gid` VARCHAR(128) NOT NULL, `created_at` DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`user_gid`,`item_gid`)
);
CREATE TABLE IF NOT EXISTS `workmanship_know_recent` (
  `user_gid` VARCHAR(128) NOT NULL, `item_gid` VARCHAR(128) NOT NULL, `accessed_at` DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`user_gid`,`item_gid`)
);
CREATE TABLE IF NOT EXISTS `workmanship_know_proposals` (
  `gid` VARCHAR(128) PRIMARY KEY, `base_gid` VARCHAR(128) NULL, `title` VARCHAR(255) NOT NULL, `content_md` LONGTEXT NOT NULL,
  `summary` TEXT NULL, `tags` JSON NULL, `status` VARCHAR(32) NOT NULL DEFAULT 'pending', `creator_gid` VARCHAR(128) NOT NULL,
  `team_gid` VARCHAR(128) NULL, `reviewer_gid` VARCHAR(128) NULL, `review_note` TEXT NULL, `reviewed_at` DATETIME NULL,
  `published_gid` VARCHAR(128) NULL, `ois_url` TEXT NULL, `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS `workmanship_know_publish_outbox` (
  `gid` VARCHAR(128) PRIMARY KEY, `proposal_gid` VARCHAR(128) NOT NULL, `payload` JSON NOT NULL,
  `status` VARCHAR(32) NOT NULL DEFAULT 'pending', `attempts` INT NOT NULL DEFAULT 0,
  `next_retry_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, `last_error` TEXT NULL,
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP, `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS `workmanship_know_domain_outbox` (
  `gid` VARCHAR(128) PRIMARY KEY, `event_type` VARCHAR(128) NOT NULL, `event_version` INT NOT NULL,
  `subject_ref` VARCHAR(128) NOT NULL, `payload` JSON NOT NULL, `status` VARCHAR(32) NOT NULL DEFAULT 'pending',
  `attempts` INT NOT NULL DEFAULT 0, `created_at` DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  KEY `idx_know_domain_outbox_delivery` (`status`,`created_at`)
);
CREATE TABLE IF NOT EXISTS `workmanship_know_reference_datasets` (
  `gid` VARCHAR(128) PRIMARY KEY, `tenant_gid` VARCHAR(128) NOT NULL, `name` VARCHAR(512) NOT NULL,
  `current_version` BIGINT NOT NULL DEFAULT 1, `published_version_gid` VARCHAR(128) NULL,
  `maintainer_gid` VARCHAR(128) NOT NULL, `created_at` DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY `uq_know_reference_dataset_name` (`tenant_gid`,`name`)
);
CREATE TABLE IF NOT EXISTS `workmanship_know_reference_versions` (
  `gid` VARCHAR(128) PRIMARY KEY, `dataset_gid` VARCHAR(128) NOT NULL, `version_no` BIGINT NOT NULL,
  `schema_json` JSON NOT NULL, `rows_json` JSON NOT NULL, `created_by` VARCHAR(128) NOT NULL,
  `created_at` DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6),
  UNIQUE KEY `uq_know_reference_version` (`dataset_gid`,`version_no`)
);
CREATE TABLE IF NOT EXISTS `workmanship_know_migration_runs` (
  `gid` VARCHAR(128) PRIMARY KEY, `tenant_gid` VARCHAR(128) NOT NULL, `space_gid` VARCHAR(128) NOT NULL,
  `actor_gid` VARCHAR(128) NOT NULL, `status` VARCHAR(32) NOT NULL, `source_count` BIGINT DEFAULT 0,
  `source_bytes` BIGINT DEFAULT 0, `copied_count` BIGINT DEFAULT 0, `skipped_count` BIGINT DEFAULT 0,
  `failed_count` BIGINT DEFAULT 0, `verified_count` BIGINT DEFAULT 0, `last_error` VARCHAR(4000) NULL,
  `started_at` DATETIME(6) NULL, `finished_at` DATETIME(6) NULL, `created_at` DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
);
CREATE TABLE IF NOT EXISTS `workmanship_know_migration_items` (
  `run_gid` VARCHAR(128) NOT NULL, `entry_gid` VARCHAR(128) NOT NULL, `document_gid` VARCHAR(128) NOT NULL,
  `revision_gid` VARCHAR(128) NOT NULL, `status` VARCHAR(32) NOT NULL, `source_sha256` CHAR(64) NOT NULL,
  `object_key` VARCHAR(1024) NULL, `content_sha256` CHAR(64) NULL, `error_message` VARCHAR(4000) NULL,
  `started_at` DATETIME(6) NULL, `finished_at` DATETIME(6) NULL,
  `updated_at` DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6), PRIMARY KEY (`run_gid`,`entry_gid`)
);
