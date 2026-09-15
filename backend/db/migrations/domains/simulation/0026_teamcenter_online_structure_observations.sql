-- Append-only observations of Teamcenter online product structures.
-- A source row represents one insertion into an AI00 simulation environment;
-- equal names and equal Teamcenter revisions are intentionally not deduplicated.
CREATE TABLE IF NOT EXISTS `workmanship_sim_online_model_sources` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `tenant_gid` BIGINT UNSIGNED NOT NULL,
  `owner_gid` BIGINT UNSIGNED NOT NULL,
  `workspace_gid` BIGINT UNSIGNED NOT NULL,
  `document_gid` BIGINT UNSIGNED NOT NULL,
  `insertion_instance_id` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `source_identity_hash` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `endpoint_id` VARCHAR(128) COLLATE utf8mb4_bin NOT NULL,
  `object_uid` VARCHAR(128) COLLATE utf8mb4_bin NOT NULL,
  `item_revision_uid` VARCHAR(128) COLLATE utf8mb4_bin NULL,
  `bom_view_uid` VARCHAR(128) COLLATE utf8mb4_bin NULL,
  `revision_rule` VARCHAR(128) COLLATE utf8mb4_bin NOT NULL,
  `configuration_date` DATETIME(6) NOT NULL,
  `display_name` VARCHAR(512) NULL,
  `source_selector_json` LONGTEXT NOT NULL,
  `inserted_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  UNIQUE KEY `uq_sim_online_source_identity`
    (`workspace_gid`,`source_identity_hash`,`insertion_instance_id`),
  KEY `ix_sim_online_source_lookup` (`tenant_gid`,`workspace_gid`,`source_identity_hash`),
  CONSTRAINT `fk_sim_online_source_workspace` FOREIGN KEY (`workspace_gid`)
    REFERENCES `workmanship_sim_workspaces` (`gid`),
  CONSTRAINT `fk_sim_online_source_document` FOREIGN KEY (`document_gid`)
    REFERENCES `workmanship_sim_vm_documents` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_sim_product_structure_observations` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `tenant_gid` BIGINT UNSIGNED NOT NULL,
  `workspace_gid` BIGINT UNSIGNED NOT NULL,
  `source_gid` BIGINT UNSIGNED NOT NULL,
  `observation_id` CHAR(70) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `captured_at` DATETIME(6) NOT NULL,
  `node_count` INT UNSIGNED NOT NULL,
  `page_count` INT UNSIGNED NOT NULL,
  `complete` TINYINT(1) NOT NULL,
  `manifest_hash` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `schema_version` SMALLINT UNSIGNED NOT NULL DEFAULT 1,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  UNIQUE KEY `uq_sim_product_structure_observation` (`tenant_gid`,`observation_id`),
  KEY `ix_sim_product_structure_source_time` (`source_gid`,`captured_at`),
  CONSTRAINT `fk_sim_product_structure_observation_workspace` FOREIGN KEY (`workspace_gid`)
    REFERENCES `workmanship_sim_workspaces` (`gid`),
  CONSTRAINT `fk_sim_product_structure_observation_source` FOREIGN KEY (`source_gid`)
    REFERENCES `workmanship_sim_online_model_sources` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_sim_product_structure_chunks` (
  `observation_gid` BIGINT UNSIGNED NOT NULL,
  `page_index` INT UNSIGNED NOT NULL,
  `cursor_value` INT UNSIGNED NOT NULL,
  `node_count` SMALLINT UNSIGNED NOT NULL,
  `payload_json` LONGTEXT NOT NULL,
  `page_hash` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`observation_gid`,`page_index`),
  CONSTRAINT `fk_sim_product_structure_chunk_observation` FOREIGN KEY (`observation_gid`)
    REFERENCES `workmanship_sim_product_structure_observations` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
