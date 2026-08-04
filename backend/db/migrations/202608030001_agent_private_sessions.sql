-- Agent-owned private sessions. Deployment-only; never run from application startup.
CREATE TABLE IF NOT EXISTS workmanship_app_ai_sessions (
    gid CHAR(36) PRIMARY KEY,
    user_gid VARCHAR(191) NOT NULL,
    title VARCHAR(512) NOT NULL DEFAULT ('新对话'),
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    INDEX idx_ai_sessions_user_updated (user_gid, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS workmanship_app_ai_turns (
    gid CHAR(36) PRIMARY KEY,
    session_gid CHAR(36) NOT NULL,
    role VARCHAR(32) NOT NULL,
    content MEDIUMTEXT NOT NULL,
    tool_calls JSON NOT NULL DEFAULT (JSON_ARRAY()),
    sort_order DOUBLE NOT NULL DEFAULT 0,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    INDEX idx_ai_turns_session_order (session_gid, sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
