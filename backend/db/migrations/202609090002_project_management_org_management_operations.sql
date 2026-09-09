CREATE TABLE IF NOT EXISTS workmanship_proj_org_management_operations (
    gid CHAR(36) PRIMARY KEY,
    tenant_gid VARCHAR(255) NOT NULL,
    actor_gid VARCHAR(255) NOT NULL,
    project_gid VARCHAR(255) NOT NULL,
    revision BIGINT NOT NULL,
    operation VARCHAR(64) NOT NULL,
    idempotency_key VARCHAR(255) NOT NULL,
    command_digest CHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    error_code VARCHAR(128) DEFAULT NULL,
    result_json JSON NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_proj_org_operation (tenant_gid, actor_gid, idempotency_key),
    KEY idx_proj_org_project (tenant_gid, project_gid, revision)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS workmanship_proj_org_management_outbox (
    gid CHAR(36) PRIMARY KEY,
    operation_gid CHAR(36) NOT NULL,
    tenant_gid VARCHAR(255) NOT NULL,
    project_gid VARCHAR(255) NOT NULL,
    payload_json JSON NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    attempts INT NOT NULL DEFAULT 0,
    available_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    leased_until DATETIME(6) DEFAULT NULL,
    last_error VARCHAR(1024) DEFAULT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_proj_org_outbox_operation (operation_gid),
    KEY idx_proj_org_outbox_work (status, available_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
