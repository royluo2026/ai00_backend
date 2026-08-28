-- Base-owned self-annotation revision, replay, and audit evidence.
CREATE TABLE IF NOT EXISTS workmanship_base_self_annotation_states (
    item_gid VARCHAR(128) NOT NULL,
    user_gid VARCHAR(128) NOT NULL,
    revision BIGINT NOT NULL DEFAULT 1,
    deleted TINYINT(1) NOT NULL DEFAULT 0,
    restore_json JSON NULL,
    PRIMARY KEY (item_gid, user_gid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS workmanship_base_self_annotation_idempotency (
    actor_gid VARCHAR(128) NOT NULL,
    operation VARCHAR(64) NOT NULL,
    idempotency_key VARCHAR(512) NOT NULL,
    status VARCHAR(32) NOT NULL,
    item_gid VARCHAR(128) NULL,
    result_json JSON NULL,
    completed_at DATETIME(6) NULL,
    PRIMARY KEY (actor_gid, operation, idempotency_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS workmanship_base_self_annotation_audit_events (
    gid VARCHAR(128) PRIMARY KEY,
    item_gid VARCHAR(128) NOT NULL,
    actor_gid VARCHAR(128) NOT NULL,
    operation VARCHAR(64) NOT NULL,
    idempotency_key VARCHAR(512) NOT NULL,
    status VARCHAR(64) NOT NULL,
    details_json JSON NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Base attachment ownership evidence. New annotation references must be
-- registered by the Base attachment owner for the authenticated actor+tenant.
-- Existing typed references on the same annotation are preserved in-place;
-- this is the bounded legacy migration path and never trusts caller visibility.
CREATE TABLE IF NOT EXISTS workmanship_base_attachment_references (
    attachment_gid VARCHAR(128) NOT NULL,
    actor_gid VARCHAR(128) NOT NULL,
    tenant_gid VARCHAR(128) NOT NULL,
    media_type VARCHAR(128) NOT NULL,
    display_name VARCHAR(512) NOT NULL,
    size BIGINT NOT NULL,
    checksum VARCHAR(80) NOT NULL,
    registered_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (attachment_gid, actor_gid, tenant_gid),
    CONSTRAINT chk_base_attachment_reference_size CHECK (size >= 0 AND size <= 52428800)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
