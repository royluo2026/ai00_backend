CREATE TABLE IF NOT EXISTS workmanship_base_project_manager_heads (
    tenant_gid VARCHAR(255) NOT NULL,
    project_gid VARCHAR(255) NOT NULL,
    revision BIGINT NOT NULL DEFAULT 0,
    managed TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (tenant_gid, project_gid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS workmanship_base_project_manager_assignments (
    gid CHAR(36) PRIMARY KEY,
    tenant_gid VARCHAR(255) NOT NULL,
    project_gid VARCHAR(255) NOT NULL,
    user_gid VARCHAR(255) NOT NULL,
    created_by VARCHAR(255) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_base_project_manager (tenant_gid, project_gid, user_gid),
    KEY idx_base_project_manager_user (tenant_gid, user_gid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS workmanship_base_project_manager_operations (
    gid CHAR(36) PRIMARY KEY,
    tenant_gid VARCHAR(255) NOT NULL,
    actor_gid VARCHAR(255) NOT NULL,
    project_gid VARCHAR(255) NOT NULL,
    idempotency_key VARCHAR(255) NOT NULL,
    command_digest CHAR(64) NOT NULL,
    result_json JSON NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_base_project_manager_operation (tenant_gid, actor_gid, idempotency_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
