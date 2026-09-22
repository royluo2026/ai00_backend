-- An association is issued from verified current-open evidence, never migrated
-- from saved environment identity. Grants do not authorize opening models.
CREATE TABLE IF NOT EXISTS `workmanship_sim_viewer_source_associations` (
  `source_association_id` VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin PRIMARY KEY,
  `workspace_gid` BIGINT UNSIGNED NOT NULL,
  `document_gid` BIGINT UNSIGNED NOT NULL,
  `tenant_gid` VARCHAR(256) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `actor_gid` VARCHAR(256) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `device_id` VARCHAR(256) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `runtime_instance_id` VARCHAR(256) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `runtime_generation` BIGINT NOT NULL,
  `document_session` VARCHAR(71) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `source_revision` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `active` BOOLEAN NOT NULL,
  `created_at` DATETIME(6) NOT NULL,
  KEY `idx_sim_viewer_source_workspace` (`workspace_gid`,`active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Only finalized, bounded, device-signed summaries. Admission stays local.
CREATE TABLE IF NOT EXISTS `workmanship_sim_viewer_interaction_events` (
  `device_id` VARCHAR(256) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `request_id` VARCHAR(256) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `grant_id` VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `interaction_id` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `sequence` BIGINT NOT NULL,
  `event_digest` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `event_json` JSON NOT NULL,
  `received_at` DATETIME(6) NOT NULL,
  PRIMARY KEY (`device_id`,`request_id`),
  KEY `idx_sim_viewer_event_grant` (`grant_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_sim_viewer_interaction_grants` (
  `grant_id` VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin PRIMARY KEY,
  `source_association_id` VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `session_nonce` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `grant_generation` BIGINT NOT NULL,
  `issued_at` DATETIME(6) NOT NULL,
  `expires_at` DATETIME(6) NOT NULL,
  CONSTRAINT `uq_sim_viewer_grant_generation` UNIQUE (`source_association_id`,`session_nonce`,`grant_generation`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
