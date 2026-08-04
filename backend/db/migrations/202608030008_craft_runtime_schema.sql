-- Craft-owned schema previously created or patched inside request handlers.
-- Runtime code must assume this migration has completed before startup.

ALTER TABLE workmanship_bop_pbom_versions ADD COLUMN IF NOT EXISTS name VARCHAR(512) DEFAULT '';
ALTER TABLE workmanship_bop_pbom_versions ADD COLUMN IF NOT EXISTS meta JSON NOT NULL DEFAULT (JSON_OBJECT());
ALTER TABLE workmanship_bop_pbom_versions ADD COLUMN IF NOT EXISTS project_gid CHAR(36) NULL;
ALTER TABLE workmanship_bop_pbom_versions ADD COLUMN IF NOT EXISTS visibility VARCHAR(32) DEFAULT 'project';
ALTER TABLE workmanship_bop_pbom_versions ADD COLUMN IF NOT EXISTS shared_team_gid CHAR(36) NULL;
ALTER TABLE workmanship_bop_pbom_versions ADD COLUMN IF NOT EXISTS shared_project_gid CHAR(36) NULL;

ALTER TABLE workmanship_bop_pbom ADD COLUMN IF NOT EXISTS vpps VARCHAR(255);
ALTER TABLE workmanship_bop_pbom ADD COLUMN IF NOT EXISTS vpps_desc VARCHAR(512) DEFAULT '';
ALTER TABLE workmanship_bop_pbom ADD COLUMN IF NOT EXISTS parent_vpps VARCHAR(255) DEFAULT '';
ALTER TABLE workmanship_bop_pbom ADD COLUMN IF NOT EXISTS parent_vpps_name VARCHAR(512) DEFAULT '';
ALTER TABLE workmanship_bop_pbom ADD COLUMN IF NOT EXISTS bom_row VARCHAR(255) DEFAULT '';
ALTER TABLE workmanship_bop_pbom ADD COLUMN IF NOT EXISTS bom_row_label VARCHAR(512) DEFAULT '';
ALTER TABLE workmanship_bop_pbom ADD COLUMN IF NOT EXISTS component_id VARCHAR(255) DEFAULT '';
ALTER TABLE workmanship_bop_pbom ADD COLUMN IF NOT EXISTS component_type VARCHAR(64) DEFAULT '';
ALTER TABLE workmanship_bop_pbom ADD COLUMN IF NOT EXISTS component_version_status VARCHAR(64) DEFAULT '';
ALTER TABLE workmanship_bop_pbom ADD COLUMN IF NOT EXISTS purchase_status VARCHAR(64) DEFAULT '';
ALTER TABLE workmanship_bop_pbom ADD COLUMN IF NOT EXISTS variable_formula VARCHAR(2048) DEFAULT '';
ALTER TABLE workmanship_bop_pbom ADD COLUMN IF NOT EXISTS torque VARCHAR(128) DEFAULT '';
ALTER TABLE workmanship_bop_pbom ADD COLUMN IF NOT EXISTS torque_importance VARCHAR(64) DEFAULT '';
ALTER TABLE workmanship_bop_pbom ADD COLUMN IF NOT EXISTS ownership_user VARCHAR(255) DEFAULT '';
ALTER TABLE workmanship_bop_pbom ADD COLUMN IF NOT EXISTS level INTEGER NULL;
ALTER TABLE workmanship_bop_pbom ADD COLUMN IF NOT EXISTS home VARCHAR(255) DEFAULT '';
ALTER TABLE workmanship_bop_pbom ADD COLUMN IF NOT EXISTS configuration VARCHAR(255) DEFAULT '';
ALTER TABLE workmanship_bop_pbom ADD COLUMN IF NOT EXISTS parent_bom_row VARCHAR(255) DEFAULT '';
ALTER TABLE workmanship_bop_pbom ADD COLUMN IF NOT EXISTS remark VARCHAR(2048) DEFAULT '';
ALTER TABLE workmanship_bop_pbom ADD COLUMN IF NOT EXISTS temp_vpps VARCHAR(255) DEFAULT '';
ALTER TABLE workmanship_bop_pbom ADD COLUMN IF NOT EXISTS catia_occurrence_name VARCHAR(512) DEFAULT '';
ALTER TABLE workmanship_bop_pbom ADD COLUMN IF NOT EXISTS catia_file_name VARCHAR(512) DEFAULT '';
ALTER TABLE workmanship_bop_pbom ADD COLUMN IF NOT EXISTS catia_uuid VARCHAR(255) DEFAULT '';
ALTER TABLE workmanship_bop_pbom ADD COLUMN IF NOT EXISTS default_matrix VARCHAR(2048) DEFAULT '';
ALTER TABLE workmanship_bop_pbom ADD COLUMN IF NOT EXISTS abs_matrix VARCHAR(2048) DEFAULT '';
ALTER TABLE workmanship_bop_pbom ADD COLUMN IF NOT EXISTS rel_matrix VARCHAR(2048) DEFAULT '';
ALTER TABLE workmanship_bop_pbom ADD COLUMN IF NOT EXISTS local_bbox VARCHAR(1024) DEFAULT '';
ALTER TABLE workmanship_bop_pbom ADD COLUMN IF NOT EXISTS ecn VARCHAR(255) DEFAULT '';
ALTER TABLE workmanship_bop_pbom ADD COLUMN IF NOT EXISTS fna VARCHAR(255) DEFAULT '';
ALTER TABLE workmanship_bop_pbom ADD COLUMN IF NOT EXISTS geo_main_part VARCHAR(255) DEFAULT '';
ALTER TABLE workmanship_bop_pbom ADD COLUMN IF NOT EXISTS ref_main_vpps_desc VARCHAR(512) DEFAULT '';
ALTER TABLE workmanship_bop_pbom ADD COLUMN IF NOT EXISTS ref_main_vpps VARCHAR(255) DEFAULT '';
ALTER TABLE workmanship_bop_pbom ADD COLUMN IF NOT EXISTS main_part_consistency VARCHAR(64) DEFAULT '';
ALTER TABLE workmanship_bop_pbom ADD COLUMN IF NOT EXISTS geo_evidence VARCHAR(2048) DEFAULT '';
ALTER TABLE workmanship_bop_pbom ADD COLUMN IF NOT EXISTS lr_side VARCHAR(32) DEFAULT '';
ALTER TABLE workmanship_bop_pbom ADD COLUMN IF NOT EXISTS vpps_source VARCHAR(32) NOT NULL DEFAULT ('auto');
ALTER TABLE workmanship_bop_pbom ADD COLUMN IF NOT EXISTS is_deleted TINYINT(1) NOT NULL DEFAULT 0;
ALTER TABLE workmanship_bop_pbom ADD COLUMN IF NOT EXISTS meta JSON NOT NULL DEFAULT (JSON_OBJECT());

ALTER TABLE workmanship_tpl_vpps_parts ADD COLUMN IF NOT EXISTS alias JSON NOT NULL DEFAULT (JSON_ARRAY());

ALTER TABLE workmanship_bop_bop_line_operation_log ADD COLUMN IF NOT EXISTS old_state LONGTEXT NULL;
ALTER TABLE workmanship_bop_bop_line_operation_log ADD COLUMN IF NOT EXISTS new_state LONGTEXT NULL;
ALTER TABLE workmanship_bop_bop_line_operation_log ADD COLUMN IF NOT EXISTS batch_status VARCHAR(20) NOT NULL DEFAULT 'active';
ALTER TABLE workmanship_bop_bop_line_operation_log ADD COLUMN IF NOT EXISTS redo_guard_json JSON NULL;
ALTER TABLE workmanship_bop_bop_line_operation_log ADD COLUMN IF NOT EXISTS touched_refs_json JSON NULL;
ALTER TABLE workmanship_bop_bop_line_operation_log ADD COLUMN IF NOT EXISTS undone_at DATETIME(6) NULL;
ALTER TABLE workmanship_bop_bop_line_operation_log ADD COLUMN IF NOT EXISTS undone_by TEXT NULL;
ALTER TABLE workmanship_bop_bop_line_operation_log ADD COLUMN IF NOT EXISTS redone_at DATETIME(6) NULL;
ALTER TABLE workmanship_bop_bop_line_operation_log ADD COLUMN IF NOT EXISTS redone_by TEXT NULL;
ALTER TABLE workmanship_bop_bop_line_operation_log ADD COLUMN IF NOT EXISTS invalidate_reason TEXT NULL;

CREATE TABLE IF NOT EXISTS workmanship_bop_bop_line_history_state (
    version_gid CHAR(36) NOT NULL, line_gid CHAR(36) NOT NULL,
    current_batch_id TEXT NULL, current_direction VARCHAR(20) NOT NULL DEFAULT 'active',
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (version_gid, line_gid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS workmanship_bop_gbop_match_staging (
    gid CHAR(36) PRIMARY KEY, pbom_version_gid CHAR(36) NOT NULL,
    gbop_entry_gid CHAR(36) NULL, pbom_entry_gid CHAR(36) NOT NULL,
    bop_version_gid CHAR(36) NULL, match_status VARCHAR(32) NOT NULL DEFAULT 'pending',
    extra_entry_gids JSON NOT NULL DEFAULT (JSON_ARRAY()), created_entry_gid TEXT NULL,
    confirmed_by TEXT NULL, confirmed_at DATETIME(6) NULL, created_by TEXT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_gbop_staging (pbom_version_gid, pbom_entry_gid),
    INDEX idx_gbop_staging_pbom_ver (pbom_version_gid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS workmanship_bop_gbop_nav_bindings (
    gid CHAR(36) PRIMARY KEY, pbom_version_gid CHAR(36) NOT NULL,
    gbop_process_entry_gid CHAR(36) NULL, gbop_op_entry_gid CHAR(36) NOT NULL,
    pbom_entry_gid CHAR(36) NOT NULL, is_part_feed TINYINT(1) NOT NULL DEFAULT 1,
    confirmed TINYINT(1) NOT NULL DEFAULT 0,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_gbop_nav (pbom_version_gid, gbop_op_entry_gid, pbom_entry_gid),
    INDEX idx_gbop_nav_pbom_ver (pbom_version_gid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS workmanship_app_wfc_canvases (
    gid CHAR(36) PRIMARY KEY, owner_gid VARCHAR(128) NOT NULL DEFAULT '',
    title VARCHAR(512) NOT NULL DEFAULT '未命名画布', data JSON NOT NULL DEFAULT (JSON_OBJECT()),
    is_shared TINYINT(1) NOT NULL DEFAULT 0,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    INDEX idx_wfc_canvases_owner (owner_gid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
