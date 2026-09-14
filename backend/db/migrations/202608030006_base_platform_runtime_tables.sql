CREATE TABLE IF NOT EXISTS workmanship_app_capability_audit (
    id BIGINT AUTO_INCREMENT PRIMARY KEY, event_type VARCHAR(64) NOT NULL,
    capability_id VARCHAR(160) NOT NULL, version INT NOT NULL,
    user_gid VARCHAR(128) NOT NULL, source VARCHAR(64) NOT NULL,
    request_id VARCHAR(128) NULL, payload_hash CHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL, error_message TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_cap_audit_capability (capability_id, created_at),
    INDEX idx_cap_audit_user (user_gid, created_at),
    INDEX idx_cap_audit_status (status, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS workmanship_app_worker_heartbeats (
    worker_name VARCHAR(128) PRIMARY KEY, worker_id VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL, details JSON NULL,
    heartbeat_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS workmanship_app_operational_alerts (
    gid VARCHAR(128) PRIMARY KEY, alert_type VARCHAR(64) NOT NULL,
    severity VARCHAR(16) NOT NULL, source_gid VARCHAR(128) NOT NULL,
    message TEXT NOT NULL, status VARCHAR(32) NOT NULL DEFAULT 'open',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_operational_alert_source (alert_type, source_gid),
    INDEX idx_operational_alert_status (status, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS workmanship_app_feishu_search_cache (
    user_gid CHAR(36) NOT NULL, entity_type VARCHAR(64) NOT NULL,
    entity_id VARCHAR(255) NOT NULL, name TEXT NOT NULL,
    search_ext TEXT NOT NULL, data JSON NOT NULL DEFAULT (JSON_OBJECT()),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (user_gid, entity_type, entity_id),
    INDEX idx_feishu_cache_name (user_gid, entity_type, name(191)),
    INDEX idx_feishu_cache_updated (user_gid, entity_type, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS workmanship_plugin_publishers (
    publisher_id VARCHAR(128) PRIMARY KEY, display_name VARCHAR(255) NOT NULL,
    public_key_pem TEXT NOT NULL, key_fingerprint CHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'active', created_by VARCHAR(128) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS workmanship_plugin_releases (
    plugin_id VARCHAR(255) NOT NULL, version VARCHAR(64) NOT NULL,
    publisher_id VARCHAR(128) NOT NULL, manifest JSON NOT NULL,
    artifact_object_key VARCHAR(1024) NOT NULL, artifact_sha256 CHAR(64) NOT NULL,
    publisher_signature TEXT NOT NULL, platform_signature TEXT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'submitted', review_note TEXT NULL,
    submitted_by VARCHAR(128) NOT NULL, reviewed_by VARCHAR(128) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (plugin_id, version), INDEX idx_plugin_release_catalog (status, plugin_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS workmanship_plugin_installations (
    tenant_gid VARCHAR(128) NOT NULL, plugin_id VARCHAR(255) NOT NULL,
    current_version VARCHAR(64) NOT NULL, previous_version VARCHAR(64) NULL,
    state VARCHAR(32) NOT NULL DEFAULT 'disabled', granted_capabilities JSON NOT NULL,
    previous_granted_capabilities JSON NULL, installed_by VARCHAR(128) NOT NULL,
    last_error TEXT NULL, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_gid, plugin_id), INDEX idx_plugin_install_state (tenant_gid, state)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS workmanship_plugin_lifecycle_events (
    gid VARCHAR(128) PRIMARY KEY, tenant_gid VARCHAR(128) NOT NULL,
    plugin_id VARCHAR(255) NOT NULL, from_state VARCHAR(32) NULL,
    to_state VARCHAR(32) NOT NULL, version VARCHAR(64) NOT NULL,
    actor_gid VARCHAR(128) NOT NULL, detail JSON NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_plugin_event_tenant (tenant_gid, plugin_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
