CREATE TABLE IF NOT EXISTS workmanship_work_list_bitable_bindings (
    list_gid VARCHAR(128) PRIMARY KEY,
    app_token VARCHAR(512) NOT NULL,
    table_id VARCHAR(255) NOT NULL,
    field_mapping JSON NOT NULL,
    sync_enabled TINYINT(1) NOT NULL DEFAULT 1,
    webhook_secret VARCHAR(512) NULL,
    has_remote_updates TINYINT(1) NOT NULL DEFAULT 0,
    last_push_at DATETIME(6) NULL,
    last_pull_at DATETIME(6) NULL,
    created_by VARCHAR(128) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    is_deleted TINYINT(1) NOT NULL DEFAULT 0,
    deleted_at DATETIME(6) NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS workmanship_work_list_bitable_record_map (
    list_gid VARCHAR(128) NOT NULL,
    item_gid VARCHAR(128) NOT NULL,
    record_id VARCHAR(255) NOT NULL,
    ai00_updated_at DATETIME(6) NULL,
    feishu_updated_at DATETIME(6) NULL,
    is_deleted TINYINT(1) NOT NULL DEFAULT 0,
    deleted_at DATETIME(6) NULL,
    PRIMARY KEY (list_gid, item_gid),
    INDEX idx_bitable_record_map_record (list_gid, record_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS workmanship_work_list_shares (
    gid VARCHAR(128) PRIMARY KEY,
    list_gid VARCHAR(128) NOT NULL,
    shared_to VARCHAR(128) NOT NULL,
    permission VARCHAR(32) NOT NULL DEFAULT 'read',
    shared_by VARCHAR(128) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_list_shares_target (list_gid, shared_to),
    INDEX idx_list_shares_user (shared_to)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS workmanship_work_item_shares (
    gid VARCHAR(128) PRIMARY KEY,
    item_type VARCHAR(64) NOT NULL,
    item_gid VARCHAR(128) NOT NULL,
    shared_to VARCHAR(128) NOT NULL,
    permission VARCHAR(32) NOT NULL DEFAULT 'read',
    shared_by VARCHAR(128) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_item_shares_target (item_type, item_gid, shared_to),
    INDEX idx_item_shares_user (shared_to)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS workmanship_work_share_links (
    token VARCHAR(191) PRIMARY KEY,
    target_type VARCHAR(64) NOT NULL,
    target_gid VARCHAR(128) NOT NULL,
    item_type VARCHAR(64) NULL,
    display_name VARCHAR(512) NOT NULL DEFAULT '',
    created_by VARCHAR(128) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    expires_at DATETIME(6) NULL,
    INDEX idx_share_links_target (target_type, target_gid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS workmanship_work_permission_requests (
    gid VARCHAR(128) PRIMARY KEY,
    requester_gid VARCHAR(128) NOT NULL,
    target_type VARCHAR(64) NOT NULL,
    target_gid VARCHAR(128) NOT NULL,
    want_permission VARCHAR(32) NOT NULL DEFAULT 'read',
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    message VARCHAR(2048) NOT NULL DEFAULT '',
    responded_by VARCHAR(128) NULL,
    responded_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    INDEX idx_perm_req_target (target_type, target_gid),
    INDEX idx_perm_req_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS workmanship_work_item_change_logs (
    gid VARCHAR(128) PRIMARY KEY,
    item_type VARCHAR(64) NOT NULL,
    item_gid VARCHAR(128) NOT NULL,
    list_gid VARCHAR(128) NULL,
    changed_by VARCHAR(128) NOT NULL,
    changed_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    field_name VARCHAR(255) NOT NULL,
    old_value LONGTEXT NULL,
    new_value LONGTEXT NULL,
    INDEX idx_change_logs_item (item_type, item_gid),
    INDEX idx_change_logs_list (list_gid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
