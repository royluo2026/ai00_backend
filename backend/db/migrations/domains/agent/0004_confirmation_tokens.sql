CREATE TABLE IF NOT EXISTS workmanship_agent_confirmation_tokens (
 token_hash CHAR(64) PRIMARY KEY,
 tool_name VARCHAR(128) NOT NULL,
 inputs_json JSON NOT NULL,
 session_gid VARCHAR(128) NOT NULL,
 user_gid VARCHAR(191) NOT NULL,
 catalog_release VARCHAR(64) NOT NULL,
 capability_id VARCHAR(255) NOT NULL,
 major_version INT UNSIGNED NOT NULL,
 payload_hash CHAR(71) NOT NULL,
 idempotency_key VARCHAR(191) NOT NULL,
 agent_identity_json JSON NOT NULL,
 state VARCHAR(16) NOT NULL,
 expires_at DATETIME(6) NOT NULL,
 created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
 INDEX idx_agent_confirmation_expiry (expires_at),
 INDEX idx_agent_confirmation_session (session_gid, user_gid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
