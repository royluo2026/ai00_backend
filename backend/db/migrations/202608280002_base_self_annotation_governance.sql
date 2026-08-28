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
