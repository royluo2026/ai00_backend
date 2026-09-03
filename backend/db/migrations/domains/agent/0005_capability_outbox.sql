CREATE TABLE IF NOT EXISTS workmanship_agent_capability_outbox (
    event_id VARCHAR(64) PRIMARY KEY,
    operation_id VARCHAR(128) NOT NULL DEFAULT '',
    request_id VARCHAR(128) NOT NULL,
    capability_id VARCHAR(255) NOT NULL,
    payload_json JSON NOT NULL,
    state VARCHAR(16) NOT NULL DEFAULT 'pending',
    attempt_count INT NOT NULL DEFAULT 0,
    next_attempt_at DATETIME(6) NULL,
    delivered_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    KEY idx_agent_capability_outbox_dispatch (state, next_attempt_at, created_at),
    KEY idx_agent_capability_outbox_operation (operation_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
