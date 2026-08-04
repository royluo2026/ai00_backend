CREATE TABLE IF NOT EXISTS workmanship_app_ai_memory (
    gid CHAR(36) PRIMARY KEY,
    user_gid VARCHAR(191) NOT NULL,
    memory_key VARCHAR(191) NOT NULL,
    content TEXT NOT NULL,
    tag VARCHAR(64) NOT NULL DEFAULT 'preference',
    scope VARCHAR(32) NOT NULL DEFAULT 'user',
    confidence DOUBLE NOT NULL DEFAULT 1.0,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_ai_memory_user_key (user_gid, memory_key),
    INDEX idx_ai_memory_user_tag (user_gid, tag)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS workmanship_app_ai_audit_logs (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    gid CHAR(36) NOT NULL,
    session_gid VARCHAR(128) NOT NULL DEFAULT '',
    user_gid VARCHAR(191) NOT NULL,
    tool_name VARCHAR(128) NOT NULL DEFAULT '',
    is_write TINYINT(1) NOT NULL DEFAULT 0,
    is_confirmed TINYINT(1) NOT NULL DEFAULT 0,
    inputs_json LONGTEXT,
    result_json LONGTEXT,
    resource_gid VARCHAR(128) NOT NULL DEFAULT '',
    resource_type VARCHAR(64) NOT NULL DEFAULT '',
    status VARCHAR(32) NOT NULL DEFAULT 'ok',
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_ai_audit_gid (gid),
    INDEX idx_ai_audit_created (created_at),
    INDEX idx_ai_audit_session (session_gid),
    INDEX idx_ai_audit_user (user_gid),
    INDEX idx_ai_audit_tool (tool_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS workmanship_app_skills (
    gid CHAR(36) PRIMARY KEY,
    name VARCHAR(191) NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    skill_type VARCHAR(32) NOT NULL,
    scope VARCHAR(32) NOT NULL DEFAULT 'private',
    status VARCHAR(32) NOT NULL DEFAULT 'draft',
    owner_gid VARCHAR(191) NOT NULL,
    is_system TINYINT(1) NOT NULL DEFAULT 0,
    content JSON NOT NULL DEFAULT (JSON_OBJECT()),
    icon TEXT NOT NULL,
    tags JSON NOT NULL DEFAULT (JSON_ARRAY()),
    sort_order INT NOT NULL DEFAULT 0,
    is_pinned TINYINT(1) NOT NULL DEFAULT 0,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    deleted_at DATETIME(6) NULL,
    UNIQUE KEY uq_agent_skill_name (name),
    INDEX idx_agent_skills_owner (owner_gid),
    INDEX idx_agent_skills_scope_status (scope, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
