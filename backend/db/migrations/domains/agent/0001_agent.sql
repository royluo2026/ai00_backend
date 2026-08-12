-- Independent Agent database; apply only through AI00_AGENT_DDL_DB_URL.
CREATE TABLE IF NOT EXISTS workmanship_agent_schema_migrations (version VARCHAR(128) PRIMARY KEY, checksum CHAR(64) NOT NULL, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS workmanship_agent_capability_resources (
 resource_gid VARCHAR(128) PRIMARY KEY, resource_type VARCHAR(64) NOT NULL, tenant_gid VARCHAR(191) NOT NULL,
 owner_gid VARCHAR(191) NOT NULL, version BIGINT UNSIGNED NOT NULL DEFAULT 1, status VARCHAR(32) NOT NULL,
 content_json JSON NOT NULL, created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
 INDEX idx_agent_resource_owner (tenant_gid,owner_gid,resource_type,updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS workmanship_agent_runs (
 run_id VARCHAR(64) PRIMARY KEY, session_gid VARCHAR(64) NOT NULL, tenant_gid VARCHAR(191) NOT NULL,
 requested_by_user_gid VARCHAR(191) NOT NULL, status VARCHAR(32) NOT NULL, run_input_ciphertext MEDIUMTEXT NOT NULL,
 catalog_release VARCHAR(64) NOT NULL, delegation_id VARCHAR(191) NOT NULL, delegation_ciphertext MEDIUMTEXT NOT NULL,
 selected_tools_json JSON NOT NULL, version BIGINT UNSIGNED NOT NULL DEFAULT 1,
 created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6), updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 UNIQUE KEY uq_agent_runs_delegation (delegation_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
