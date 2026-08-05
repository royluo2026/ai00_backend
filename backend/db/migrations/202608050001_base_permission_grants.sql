CREATE TABLE IF NOT EXISTS workmanship_auth_permission_grants (
    gid VARCHAR(128) PRIMARY KEY,
    grantee_gid VARCHAR(128) NOT NULL,
    grant_type VARCHAR(64) NOT NULL,
    scope_gid VARCHAR(128) NULL,
    granted_by VARCHAR(128) NULL,
    granted_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    expires_at DATETIME(6) NULL,
    note VARCHAR(2048) NOT NULL DEFAULT '',
    UNIQUE KEY uq_permission_grantee_scope (grantee_gid, grant_type, scope_gid),
    INDEX idx_grants_grantee (grantee_gid),
    INDEX idx_grants_type_scope (grant_type, scope_gid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
