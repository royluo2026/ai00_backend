CREATE TABLE IF NOT EXISTS workmanship_plugin_usage_events (
    dedupe_key CHAR(64) PRIMARY KEY,
    tenant_gid VARCHAR(128) NOT NULL,
    plugin_id VARCHAR(255) NOT NULL,
    plugin_version VARCHAR(64) NOT NULL,
    channel VARCHAR(16) NOT NULL,
    capability_id VARCHAR(160) NOT NULL,
    user_gid VARCHAR(128) NOT NULL,
    succeeded BOOLEAN NOT NULL DEFAULT FALSE,
    occurred_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    INDEX idx_plugin_usage_month (tenant_gid, occurred_at, plugin_id),
    INDEX idx_plugin_usage_channel (tenant_gid, channel, occurred_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS workmanship_plugin_usage_monthly (
    tenant_gid VARCHAR(128) NOT NULL,
    plugin_id VARCHAR(255) NOT NULL,
    month_start DATE NOT NULL,
    usage_count BIGINT NOT NULL DEFAULT 0,
    attempt_count BIGINT NOT NULL DEFAULT 0,
    success_rate DECIMAL(7,4) NOT NULL DEFAULT 0,
    generated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (tenant_gid, plugin_id, month_start),
    INDEX idx_plugin_month_rank (tenant_gid, month_start, usage_count)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS workmanship_plugin_usage_month_closures (
    tenant_gid VARCHAR(128) NOT NULL,
    month_start DATE NOT NULL,
    closed_by VARCHAR(128) NOT NULL,
    closed_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (tenant_gid, month_start)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;