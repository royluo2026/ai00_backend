-- Private simulation workspaces and versioned VisMockup document projections.
CREATE TABLE IF NOT EXISTS `workmanship_sim_workspaces` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `tenant_gid` BIGINT UNSIGNED NOT NULL,
  `owner_gid` BIGINT UNSIGNED NOT NULL,
  `name` VARCHAR(255) NOT NULL,
  `status` VARCHAR(32) NOT NULL DEFAULT 'active',
  `row_version` BIGINT UNSIGNED NOT NULL DEFAULT 1,
  `removed_at` DATETIME(6) NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  UNIQUE KEY `uq_sim_workspace_owner_name` (`tenant_gid`,`owner_gid`,`name`),
  KEY `idx_sim_workspace_owner` (`tenant_gid`,`owner_gid`,`status`,`updated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_sim_workspace_versions` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `workspace_gid` BIGINT UNSIGNED NOT NULL,
  `tenant_gid` BIGINT UNSIGNED NOT NULL,
  `owner_gid` BIGINT UNSIGNED NOT NULL,
  `sequence` BIGINT UNSIGNED NOT NULL,
  `status` VARCHAR(32) NOT NULL DEFAULT 'draft',
  `content_hash` VARCHAR(71) CHARACTER SET ascii COLLATE ascii_bin NULL,
  `manifest_artifact_gid` BIGINT UNSIGNED NULL,
  `manifest_artifact_ref_json` JSON NULL,
  `algorithm_versions_json` JSON NULL,
  `row_version` BIGINT UNSIGNED NOT NULL DEFAULT 1,
  `removed_at` DATETIME(6) NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  UNIQUE KEY `uq_sim_workspace_version_sequence` (`workspace_gid`,`sequence`),
  CONSTRAINT `fk_sim_workspace_version_workspace` FOREIGN KEY (`workspace_gid`) REFERENCES `workmanship_sim_workspaces` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_sim_workspace_heads` (
  `workspace_gid` BIGINT UNSIGNED NOT NULL,
  `version_gid` BIGINT UNSIGNED NOT NULL,
  `row_version` BIGINT UNSIGNED NOT NULL DEFAULT 1,
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`workspace_gid`),
  UNIQUE KEY `uq_sim_workspace_head_version` (`version_gid`),
  CONSTRAINT `fk_sim_workspace_head_workspace` FOREIGN KEY (`workspace_gid`) REFERENCES `workmanship_sim_workspaces` (`gid`),
  CONSTRAINT `fk_sim_workspace_head_version` FOREIGN KEY (`version_gid`) REFERENCES `workmanship_sim_workspace_versions` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_sim_workspace_nodes` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `workspace_gid` BIGINT UNSIGNED NOT NULL,
  `tenant_gid` BIGINT UNSIGNED NOT NULL,
  `owner_gid` BIGINT UNSIGNED NOT NULL,
  `parent_gid` BIGINT UNSIGNED NULL,
  `node_type` VARCHAR(32) NOT NULL,
  `name` VARCHAR(255) NOT NULL,
  `sort_order` INT UNSIGNED NOT NULL,
  `source_bop_node_gid` BIGINT UNSIGNED NULL,
  `row_version` BIGINT UNSIGNED NOT NULL DEFAULT 1,
  `removed_at` DATETIME(6) NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  UNIQUE KEY `uq_sim_workspace_node_order` (`workspace_gid`,`parent_gid`,`sort_order`),
  KEY `idx_sim_workspace_node_tree` (`workspace_gid`,`parent_gid`,`removed_at`),
  CONSTRAINT `fk_sim_workspace_node_workspace` FOREIGN KEY (`workspace_gid`) REFERENCES `workmanship_sim_workspaces` (`gid`),
  CONSTRAINT `fk_sim_workspace_node_parent` FOREIGN KEY (`parent_gid`) REFERENCES `workmanship_sim_workspace_nodes` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_sim_workspace_bindings` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `workspace_gid` BIGINT UNSIGNED NOT NULL,
  `tenant_gid` BIGINT UNSIGNED NOT NULL,
  `owner_gid` BIGINT UNSIGNED NOT NULL,
  `node_gid` BIGINT UNSIGNED NOT NULL,
  `occurrence_gid` BIGINT UNSIGNED NOT NULL,
  `binding_role` VARCHAR(32) NOT NULL,
  `row_version` BIGINT UNSIGNED NOT NULL DEFAULT 1,
  `removed_at` DATETIME(6) NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  KEY `idx_sim_workspace_binding_node` (`workspace_gid`,`node_gid`,`removed_at`),
  KEY `idx_sim_workspace_binding_occurrence` (`workspace_gid`,`occurrence_gid`,`binding_role`,`removed_at`),
  CONSTRAINT `fk_sim_workspace_binding_workspace` FOREIGN KEY (`workspace_gid`) REFERENCES `workmanship_sim_workspaces` (`gid`),
  CONSTRAINT `fk_sim_workspace_binding_node` FOREIGN KEY (`node_gid`) REFERENCES `workmanship_sim_workspace_nodes` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_sim_workspace_load_claims` (
  `workspace_gid` BIGINT UNSIGNED NOT NULL,
  `occurrence_gid` BIGINT UNSIGNED NOT NULL,
  `binding_gid` BIGINT UNSIGNED NOT NULL,
  PRIMARY KEY (`workspace_gid`,`occurrence_gid`),
  UNIQUE KEY `uq_sim_workspace_load_binding` (`binding_gid`),
  CONSTRAINT `fk_sim_workspace_load_claim_workspace` FOREIGN KEY (`workspace_gid`) REFERENCES `workmanship_sim_workspaces` (`gid`),
  CONSTRAINT `fk_sim_workspace_load_claim_binding` FOREIGN KEY (`binding_gid`) REFERENCES `workmanship_sim_workspace_bindings` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_sim_workspace_idempotency` (
  `workspace_gid` BIGINT UNSIGNED NOT NULL,
  `idempotency_key` VARCHAR(191) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `request_hash` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `response_json` JSON NOT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `expires_at` DATETIME(6) NOT NULL,
  PRIMARY KEY (`workspace_gid`,`idempotency_key`),
  CONSTRAINT `fk_sim_workspace_idempotency_workspace` FOREIGN KEY (`workspace_gid`) REFERENCES `workmanship_sim_workspaces` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_sim_vm_documents` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `workspace_gid` BIGINT UNSIGNED NOT NULL,
  `tenant_gid` BIGINT UNSIGNED NOT NULL,
  `owner_gid` BIGINT UNSIGNED NOT NULL,
  `source_kind` VARCHAR(32) NOT NULL,
  `source_identity_hash` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `status` VARCHAR(32) NOT NULL DEFAULT 'active',
  `row_version` BIGINT UNSIGNED NOT NULL DEFAULT 1,
  `removed_at` DATETIME(6) NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  UNIQUE KEY `uq_sim_vm_document_source` (`workspace_gid`,`source_identity_hash`),
  CONSTRAINT `fk_sim_vm_document_workspace` FOREIGN KEY (`workspace_gid`) REFERENCES `workmanship_sim_workspaces` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_sim_vm_sessions` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `document_gid` BIGINT UNSIGNED NOT NULL,
  `tenant_gid` BIGINT UNSIGNED NOT NULL,
  `owner_gid` BIGINT UNSIGNED NOT NULL,
  `runtime_instance_id` VARCHAR(191) NOT NULL,
  `window_identity_hash` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `opened_at` DATETIME(6) NOT NULL,
  `closed_at` DATETIME(6) NULL,
  `row_version` BIGINT UNSIGNED NOT NULL DEFAULT 1,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  KEY `idx_sim_vm_session_document` (`document_gid`,`opened_at`),
  CONSTRAINT `fk_sim_vm_session_document` FOREIGN KEY (`document_gid`) REFERENCES `workmanship_sim_vm_documents` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_sim_vm_snapshots` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `document_gid` BIGINT UNSIGNED NOT NULL,
  `session_gid` BIGINT UNSIGNED NOT NULL,
  `tenant_gid` BIGINT UNSIGNED NOT NULL,
  `owner_gid` BIGINT UNSIGNED NOT NULL,
  `sequence` BIGINT UNSIGNED NOT NULL,
  `artifact_gid` BIGINT UNSIGNED NOT NULL,
  `artifact_sha256` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `artifact_byte_size` BIGINT UNSIGNED NOT NULL,
  `snapshot_hash` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `parser_algorithm_version` VARCHAR(64) NOT NULL,
  `identity_algorithm_version` VARCHAR(64) NOT NULL,
  `status` VARCHAR(32) NOT NULL DEFAULT 'accepted',
  `row_version` BIGINT UNSIGNED NOT NULL DEFAULT 1,
  `removed_at` DATETIME(6) NULL,
  `captured_at` DATETIME(6) NOT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  UNIQUE KEY `uq_sim_vm_snapshot_sequence` (`document_gid`,`sequence`),
  UNIQUE KEY `uq_sim_vm_snapshot_hash` (`document_gid`,`snapshot_hash`),
  CONSTRAINT `fk_sim_vm_snapshot_document` FOREIGN KEY (`document_gid`) REFERENCES `workmanship_sim_vm_documents` (`gid`),
  CONSTRAINT `fk_sim_vm_snapshot_session` FOREIGN KEY (`session_gid`) REFERENCES `workmanship_sim_vm_sessions` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_sim_vm_snapshot_heads` (
  `document_gid` BIGINT UNSIGNED NOT NULL,
  `snapshot_gid` BIGINT UNSIGNED NOT NULL,
  `row_version` BIGINT UNSIGNED NOT NULL DEFAULT 1,
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`document_gid`),
  UNIQUE KEY `uq_sim_vm_snapshot_head` (`snapshot_gid`),
  CONSTRAINT `fk_sim_vm_snapshot_head_document` FOREIGN KEY (`document_gid`) REFERENCES `workmanship_sim_vm_documents` (`gid`),
  CONSTRAINT `fk_sim_vm_snapshot_head_snapshot` FOREIGN KEY (`snapshot_gid`) REFERENCES `workmanship_sim_vm_snapshots` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_sim_vm_occurrences` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `document_gid` BIGINT UNSIGNED NOT NULL,
  `tenant_gid` BIGINT UNSIGNED NOT NULL,
  `owner_gid` BIGINT UNSIGNED NOT NULL,
  `predecessor_gid` BIGINT UNSIGNED NULL,
  `kind` VARCHAR(32) NOT NULL,
  `model_number` VARCHAR(255) NOT NULL,
  `first_session_gid` BIGINT UNSIGNED NOT NULL,
  `status` VARCHAR(32) NOT NULL DEFAULT 'active',
  `row_version` BIGINT UNSIGNED NOT NULL DEFAULT 1,
  `removed_at` DATETIME(6) NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  KEY `idx_sim_vm_occurrence_document` (`document_gid`,`kind`,`model_number`,`status`),
  CONSTRAINT `fk_sim_vm_occurrence_document` FOREIGN KEY (`document_gid`) REFERENCES `workmanship_sim_vm_documents` (`gid`),
  CONSTRAINT `fk_sim_vm_occurrence_predecessor` FOREIGN KEY (`predecessor_gid`) REFERENCES `workmanship_sim_vm_occurrences` (`gid`),
  CONSTRAINT `fk_sim_vm_occurrence_session` FOREIGN KEY (`first_session_gid`) REFERENCES `workmanship_sim_vm_sessions` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_sim_vm_observations` (
  `snapshot_gid` BIGINT UNSIGNED NOT NULL,
  `occurrence_gid` BIGINT UNSIGNED NOT NULL,
  `source_instance_id` VARCHAR(191) NOT NULL,
  `bom_line` VARCHAR(512) NOT NULL,
  `revision_code` VARCHAR(128) NOT NULL,
  `catia_occurrence_name` VARCHAR(512) NOT NULL,
  `parent_path_json` JSON NOT NULL,
  `normalized_transform_json` JSON NOT NULL,
  `raw_transform_json` JSON NOT NULL,
  `representation_locations_json` JSON NOT NULL,
  `change_kind` VARCHAR(32) NOT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`snapshot_gid`,`occurrence_gid`),
  KEY `idx_sim_vm_observation_occurrence` (`occurrence_gid`,`snapshot_gid`),
  CONSTRAINT `fk_sim_vm_observation_snapshot` FOREIGN KEY (`snapshot_gid`) REFERENCES `workmanship_sim_vm_snapshots` (`gid`),
  CONSTRAINT `fk_sim_vm_observation_occurrence` FOREIGN KEY (`occurrence_gid`) REFERENCES `workmanship_sim_vm_occurrences` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_sim_vm_poses` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `snapshot_gid` BIGINT UNSIGNED NOT NULL,
  `occurrence_gid` BIGINT UNSIGNED NOT NULL,
  `normalized_transform_json` JSON NOT NULL,
  `pose_hash` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  UNIQUE KEY `uq_sim_vm_pose_snapshot_occurrence` (`snapshot_gid`,`occurrence_gid`),
  CONSTRAINT `fk_sim_vm_pose_snapshot` FOREIGN KEY (`snapshot_gid`) REFERENCES `workmanship_sim_vm_snapshots` (`gid`),
  CONSTRAINT `fk_sim_vm_pose_occurrence` FOREIGN KEY (`occurrence_gid`) REFERENCES `workmanship_sim_vm_occurrences` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_sim_workspace_freeze_outbox` (
  -- status includes completed, orphaned and unavailable for reconciliation.
  `gid` BIGINT UNSIGNED NOT NULL,
  `workspace_gid` BIGINT UNSIGNED NOT NULL,
  `version_gid` BIGINT UNSIGNED NOT NULL,
  `tenant_gid` BIGINT UNSIGNED NOT NULL,
  `owner_gid` BIGINT UNSIGNED NOT NULL,
  `idempotency_key` VARCHAR(191) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `content_hash` VARCHAR(71) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `artifact_ref_json` JSON NOT NULL,
  `status` VARCHAR(32) NOT NULL,
  `last_error` VARCHAR(1000) NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  UNIQUE KEY `uq_sim_workspace_freeze_key` (`workspace_gid`,`idempotency_key`),
  KEY `idx_sim_workspace_freeze_reconcile` (`status`,`updated_at`),
  CONSTRAINT `fk_sim_workspace_freeze_workspace` FOREIGN KEY (`workspace_gid`) REFERENCES `workmanship_sim_workspaces` (`gid`),
  CONSTRAINT `fk_sim_workspace_freeze_version` FOREIGN KEY (`version_gid`) REFERENCES `workmanship_sim_workspace_versions` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_sim_environment_publish_plans` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `workspace_gid` BIGINT UNSIGNED NOT NULL,
  `environment_version_gid` BIGINT UNSIGNED NOT NULL,
  `tenant_gid` BIGINT UNSIGNED NOT NULL,
  `owner_gid` BIGINT UNSIGNED NOT NULL,
  `base_bop_version_gid` BIGINT UNSIGNED NOT NULL,
  `base_bop_revision` BIGINT UNSIGNED NOT NULL,
  `selection_hash` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `plan_hash` VARCHAR(71) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `plan_json` JSON NOT NULL,
  `craft_action_ref_json` JSON NULL,
  `craft_bop_version_gid` BIGINT UNSIGNED NULL,
  `craft_bop_revision` BIGINT UNSIGNED NULL,
  `outcome_hash` VARCHAR(71) CHARACTER SET ascii COLLATE ascii_bin NULL,
  `idempotency_key` VARCHAR(191) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `status` VARCHAR(32) NOT NULL DEFAULT 'prepared',
  `last_error` VARCHAR(1000) NULL,
  `row_version` BIGINT UNSIGNED NOT NULL DEFAULT 1,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  UNIQUE KEY `uq_sim_environment_publish_key` (`workspace_gid`,`idempotency_key`),
  KEY `idx_sim_environment_publish_owner` (`tenant_gid`,`owner_gid`,`status`,`updated_at`),
  CONSTRAINT `fk_sim_environment_publish_workspace` FOREIGN KEY (`workspace_gid`) REFERENCES `workmanship_sim_workspaces` (`gid`),
  CONSTRAINT `fk_sim_environment_publish_version` FOREIGN KEY (`environment_version_gid`) REFERENCES `workmanship_sim_workspace_versions` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_sim_environment_publish_maps` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `publish_plan_gid` BIGINT UNSIGNED NOT NULL,
  `environment_node_gid` BIGINT UNSIGNED NOT NULL,
  `craft_node_gid` BIGINT UNSIGNED NOT NULL,
  `client_ref` VARCHAR(191) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `tenant_gid` BIGINT UNSIGNED NOT NULL,
  `owner_gid` BIGINT UNSIGNED NOT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  UNIQUE KEY `uq_sim_environment_publish_node` (`publish_plan_gid`,`environment_node_gid`),
  UNIQUE KEY `uq_sim_environment_publish_ref` (`publish_plan_gid`,`client_ref`),
  CONSTRAINT `fk_sim_environment_publish_map_plan` FOREIGN KEY (`publish_plan_gid`) REFERENCES `workmanship_sim_environment_publish_plans` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_sim_environment_publish_outbox` (
  `gid` BIGINT UNSIGNED NOT NULL,
  `publish_plan_gid` BIGINT UNSIGNED NOT NULL,
  `tenant_gid` BIGINT UNSIGNED NOT NULL,
  `owner_gid` BIGINT UNSIGNED NOT NULL,
  `effect_type` VARCHAR(64) NOT NULL,
  `payload_json` JSON NOT NULL,
  `status` VARCHAR(32) NOT NULL DEFAULT 'pending',
  `attempt` INT UNSIGNED NOT NULL DEFAULT 0,
  `lease_owner` VARCHAR(191) NULL,
  `lease_expires_at` DATETIME(6) NULL,
  `last_error` VARCHAR(1000) NULL COMMENT 'Use outcome_unknown when Craft outcome cannot be proven',
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`gid`),
  UNIQUE KEY `uq_sim_environment_publish_effect` (`publish_plan_gid`,`effect_type`),
  KEY `idx_sim_environment_publish_outbox_claim` (`status`,`lease_expires_at`,`created_at`),
  CONSTRAINT `fk_sim_environment_publish_outbox_plan` FOREIGN KEY (`publish_plan_gid`) REFERENCES `workmanship_sim_environment_publish_plans` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
