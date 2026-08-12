-- Native PBOM slice in the independent Craft database.
CREATE TABLE IF NOT EXISTS `workmanship_craft_schema_migrations` (
  `version` VARCHAR(128) PRIMARY KEY, `checksum` CHAR(64) NOT NULL,
  `applied_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE `workmanship_bop_pbom_versions`
  ADD COLUMN IF NOT EXISTS `project_ref` VARCHAR(256) NULL,
  ADD COLUMN IF NOT EXISTS `knowledge_revision_ref` VARCHAR(256) NULL,
  ADD COLUMN IF NOT EXISTS `ontology_release_ref` VARCHAR(256) NULL,
  ADD COLUMN IF NOT EXISTS `revision_commit_ref` VARCHAR(256) NULL,
  ADD COLUMN IF NOT EXISTS `revision` BIGINT NOT NULL DEFAULT 1;

CREATE TABLE IF NOT EXISTS `workmanship_craft_pbom_change_previews` (
  `gid` VARCHAR(128) PRIMARY KEY,
  `version_gid` VARCHAR(128) NOT NULL,
  `base_revision` BIGINT NOT NULL,
  `content_sha256` CHAR(64) NOT NULL,
  `changes_json` JSON NOT NULL,
  `created_by` VARCHAR(128) NOT NULL,
  `applied_at` DATETIME(6) NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  INDEX `idx_craft_pbom_preview_version` (`version_gid`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
