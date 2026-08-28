-- Base-owned saved-view lifecycle, replay, and audit evidence.
-- User view configuration remains in workmanship_app_view_configs.config.
CREATE TABLE IF NOT EXISTS workmanship_base_saved_view_states (
    view_gid VARCHAR(128) PRIMARY KEY,
    revision BIGINT NOT NULL DEFAULT 1,
    deleted TINYINT(1) NOT NULL DEFAULT 0,
    share_scope VARCHAR(32) NOT NULL DEFAULT 'private',
    grants_json JSON NOT NULL,
    team_gids_json JSON NOT NULL,
    restore_json JSON NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    INDEX idx_base_saved_view_state_scope (share_scope, deleted, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS workmanship_base_saved_view_idempotency (
    actor_gid VARCHAR(128) NOT NULL,
    operation VARCHAR(64) NOT NULL,
    idempotency_key VARCHAR(512) NOT NULL,
    status VARCHAR(32) NOT NULL,
    view_gid VARCHAR(128) NULL,
    result_json JSON NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    completed_at DATETIME(6) NULL,
    PRIMARY KEY (actor_gid, operation, idempotency_key),
    INDEX idx_base_saved_view_replay_view (view_gid, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS workmanship_base_saved_view_audit_events (
    gid VARCHAR(128) PRIMARY KEY,
    view_gid VARCHAR(128) NOT NULL,
    actor_gid VARCHAR(128) NOT NULL,
    operation VARCHAR(64) NOT NULL,
    idempotency_key VARCHAR(512) NULL,
    status VARCHAR(64) NOT NULL,
    details_json JSON NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    INDEX idx_base_saved_view_audit_view (view_gid, created_at),
    INDEX idx_base_saved_view_audit_actor (actor_gid, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
