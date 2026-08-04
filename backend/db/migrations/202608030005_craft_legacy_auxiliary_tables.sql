CREATE TABLE IF NOT EXISTS workmanship_bop_vpps_operations (
    gid CHAR(36) PRIMARY KEY,
    pbom_version_gid CHAR(36) NOT NULL,
    pbom_row_gid CHAR(36) NOT NULL,
    operation_type TEXT NOT NULL,
    rule_no INTEGER NULL,
    field_name TEXT NULL,
    original_value TEXT NULL,
    new_value TEXT NULL,
    actor_gid CHAR(36) NOT NULL,
    actor_name TEXT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    notes TEXT NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    reverted_at DATETIME(6) NULL,
    reverted_by_gid CHAR(36) NULL,
    reverted_by_name TEXT NULL,
    INDEX idx_vpps_ops_version (pbom_version_gid),
    INDEX idx_vpps_ops_row (pbom_row_gid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS workmanship_work_task_dependencies (
    gid CHAR(36) PRIMARY KEY,
    source_gid CHAR(36) NOT NULL,
    target_gid CHAR(36) NOT NULL,
    edge_type VARCHAR(64) NOT NULL DEFAULT ('prerequisite'),
    dep_condition VARCHAR(64) NOT NULL DEFAULT ('done'),
    dep_group TEXT NULL,
    label VARCHAR(512) NOT NULL DEFAULT (''),
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    INDEX idx_work_task_deps_src (source_gid),
    INDEX idx_work_task_deps_tgt (target_gid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
