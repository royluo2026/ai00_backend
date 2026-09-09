CREATE TABLE IF NOT EXISTS workmanship_base_line_responsibility_sources (
    gid CHAR(36) PRIMARY KEY,
    tenant_gid VARCHAR(255) NOT NULL,
    source_gid VARCHAR(255) NOT NULL,
    source_revision BIGINT NOT NULL,
    project_gid VARCHAR(255) NOT NULL,
    bop_line_gid VARCHAR(255) DEFAULT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_base_line_source (tenant_gid, source_gid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS workmanship_base_line_responsibility_targets (
    gid CHAR(36) PRIMARY KEY,
    tenant_gid VARCHAR(255) NOT NULL,
    project_gid VARCHAR(255) NOT NULL,
    bop_line_gid VARCHAR(255) NOT NULL,
    user_gid VARCHAR(255) NOT NULL,
    source_count INT NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_base_line_target (tenant_gid, project_gid, bop_line_gid, user_gid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS workmanship_base_line_responsibility_source_targets (
    tenant_gid VARCHAR(255) NOT NULL,
    source_gid VARCHAR(255) NOT NULL,
    target_gid CHAR(36) NOT NULL,
    PRIMARY KEY (tenant_gid, source_gid, target_gid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS workmanship_base_line_projection_operations (
    gid CHAR(36) PRIMARY KEY,
    tenant_gid VARCHAR(255) NOT NULL,
    operation_gid VARCHAR(255) NOT NULL,
    source_gid VARCHAR(255) NOT NULL,
    command_digest CHAR(64) NOT NULL,
    result_json JSON NOT NULL,
    actor_gid VARCHAR(255) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_base_line_projection_operation (tenant_gid, operation_gid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

