-- Auditable legacy Markdown migration control plane. Source content is never deleted.
CREATE TABLE IF NOT EXISTS workmanship_know_migration_runs (
    gid VARCHAR(128) PRIMARY KEY,
    tenant_gid VARCHAR(128) NOT NULL,
    space_gid VARCHAR(128) NOT NULL,
    actor_gid VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL,
    source_count BIGINT NOT NULL DEFAULT 0,
    source_bytes BIGINT NOT NULL DEFAULT 0,
    copied_count BIGINT NOT NULL DEFAULT 0,
    skipped_count BIGINT NOT NULL DEFAULT 0,
    failed_count BIGINT NOT NULL DEFAULT 0,
    verified_count BIGINT NOT NULL DEFAULT 0,
    last_error VARCHAR(4000) NULL,
    started_at DATETIME(6) NULL,
    finished_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    INDEX idx_know_migration_runs_tenant (tenant_gid, created_at),
    INDEX idx_know_migration_runs_status (status, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS workmanship_know_migration_items (
    run_gid VARCHAR(128) NOT NULL,
    entry_gid VARCHAR(128) NOT NULL,
    document_gid VARCHAR(128) NOT NULL,
    revision_gid VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL,
    source_sha256 CHAR(64) NOT NULL,
    object_key VARCHAR(1024) NULL,
    content_sha256 CHAR(64) NULL,
    error_message VARCHAR(4000) NULL,
    started_at DATETIME(6) NULL,
    finished_at DATETIME(6) NULL,
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (run_gid, entry_gid),
    INDEX idx_know_migration_items_status (run_gid, status),
    INDEX idx_know_migration_items_entry (entry_gid, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
