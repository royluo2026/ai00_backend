-- Craft-owned persistence for governed BOP write previews, idempotency and import previews.
CREATE TABLE IF NOT EXISTS workmanship_craft_bop_change_previews (
    gid VARCHAR(128) PRIMARY KEY,
    version_gid VARCHAR(128) NOT NULL,
    base_revision BIGINT NOT NULL,
    payload_hash CHAR(64) NOT NULL,
    before_hash CHAR(64) NOT NULL,
    after_hash CHAR(64) NOT NULL,
    commands_json JSON NOT NULL,
    idempotency_key VARCHAR(256) NULL,
    expires_at DATETIME(6) NOT NULL,
    applied_result_json JSON NULL,
    created_by VARCHAR(128) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_craft_bop_preview_idempotency (version_gid, idempotency_key),
    INDEX idx_craft_bop_preview_expiry (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS workmanship_craft_bop_write_idempotency (
    idempotency_key VARCHAR(256) PRIMARY KEY,
    capability_id VARCHAR(128) NOT NULL,
    version_gid VARCHAR(128) NULL,
    result_json JSON NOT NULL,
    created_by VARCHAR(128) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS workmanship_craft_bop_import_previews (
    gid VARCHAR(128) PRIMARY KEY,
    content_sha256 CHAR(64) NOT NULL,
    document_json JSON NOT NULL,
    entry_count BIGINT NOT NULL,
    expires_at DATETIME(6) NOT NULL,
    created_by VARCHAR(128) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    INDEX idx_craft_bop_import_expiry (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
