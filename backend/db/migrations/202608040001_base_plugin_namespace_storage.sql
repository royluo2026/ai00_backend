CREATE TABLE IF NOT EXISTS workmanship_plugin_namespace_kv (
    tenant_gid VARCHAR(128) NOT NULL,
    plugin_id VARCHAR(255) NOT NULL,
    storage_key VARCHAR(512) NOT NULL,
    value_json JSON NOT NULL,
    version BIGINT NOT NULL DEFAULT 1,
    created_by VARCHAR(128) NOT NULL,
    updated_by VARCHAR(128) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (tenant_gid, plugin_id, storage_key),
    INDEX idx_plugin_namespace_updated (tenant_gid, plugin_id, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;